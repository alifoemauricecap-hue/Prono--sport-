"""PRONO SPORT API v1 (§90-92) — FastAPI.

Endpoints :
  GET /v1/fixtures?tab=live|upcoming|finished&competition=ENG-E0&limit=
    → matchs groupés par rencontre réelle (jumeaux inter-sources fusionnés EN CARD_UNIQUE,
      chaque source reste visible dans sources[] : transparence §4/§47)
  GET /v1/competitions
  GET /v1/health/providers    → DATA HEALTH (§75)
  GET /v1/stats
  GET /                        → interface web (static/index.html)

Scheduler optionnel : AUTO_INGEST=1 → ré-ingestion ESPN périodique + vérification croisée.
"""
from __future__ import annotations

import asyncio
import os
from datetime import datetime, timezone
from pathlib import Path

from fastapi import FastAPI, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from sqlalchemy.orm import Session, joinedload

from .config import DATABASE_URL
from .db.base import Base, make_engine, make_session_factory
from .db.models import (
    Bookmaker,
    Competition,
    Fixture,
    Market,
    OddsSnapshot,
    Prediction,
    ProviderHealth,
    Team,
    TeamAnalytics,
    ValueBet,
)

STATIC_DIR = Path(__file__).parent / "static"

LIVE_STATUSES = {"LIVE", "HALFTIME", "EXTRA_TIME", "PENALTIES"}
UPCOMING_STATUSES = {"SCHEDULED", "UPCOMING", "LINEUPS_PENDING", "LINEUPS_CONFIRMED"}
FINISHED_STATUSES = {"FINISHED"}

ENGINE = make_engine(DATABASE_URL)
Base.metadata.create_all(ENGINE)
SF = make_session_factory(ENGINE)

app = FastAPI(title="PRONO SPORT API", version="0.2.0", docs_url="/v1/docs")
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["GET"], allow_headers=["*"])

STATUS_RANK = {"VERIFIED": 2, "UNVERIFIED": 1, "CONTRADICTORY": 0, "INSUFFICIENT_SAMPLE": 1}


def _iso(dt: datetime | None) -> str | None:
    return dt.isoformat() if dt else None


def _card_data_status(statuses: list[str]) -> str:
    """Une contradiction quelque part pollue tout (§1) ; sinon le meilleur niveau gagne."""
    if "CONTRADICTORY" in statuses:
        return "CONTRADICTORY"
    if "VERIFIED" in statuses:
        return "VERIFIED"
    return "UNVERIFIED"


def main_score_known(card: dict) -> bool:
    return card["score"]["ft_home"] is not None and card["score"]["ft_away"] is not None


def _minute_from_kickoff(kickoff_iso: str | None) -> int | None:
    """Secours si le provider ne donne pas la minute : temps écoulé depuis kickoff (§1 : tracé)."""
    if not kickoff_iso:
        return None
    try:
        ko = datetime.fromisoformat(kickoff_iso)
        if ko.tzinfo is None:
            ko = ko.replace(tzinfo=timezone.utc)
        elapsed = (datetime.now(timezone.utc) - ko).total_seconds() / 60
        return max(0, min(90, int(elapsed)))
    except ValueError:
        return None


def _fixture_dict(group: list[Fixture], teams: dict[int, Team], comps: dict[int, Competition],
                  analytics: dict[int, TeamAnalytics] | None = None,
                  trends: dict[int, dict] | None = None) -> dict:
    # Carte principale : la ligne la plus fiable (VERIFIED d'abord, puis la plus fraîche).
    def rank(fx: Fixture):
        return (STATUS_RANK.get(fx.data_status, 1),
                fx.home_score is not None,
                fx.last_updated_at or datetime.min)

    main = sorted(group, key=rank, reverse=True)[0]
    home, away = teams.get(main.home_team_id), teams.get(main.away_team_id)
    comp = comps.get(main.competition_id)
    analytics = analytics or {}

    def team_payload(team_id: int, team: Team | None) -> dict:
        a = analytics.get(team_id)
        return {
            "id": team_id,
            "name": team.name if team else "?",
            "logo_url": team.logo_url if team else None,
            "elo": round(a.elo, 1) if a and a.elo is not None else None,  # §16, NULL=non calculable
            "form5": a.form5 if a else None,
            "elo_matches": a.matches_rated if a else 0,                   # profondeur échantillon (§13)
        }

    sources = sorted(
        ({"provider": g.source_provider,
          "status": g.status,
          "score_home": g.home_score,
          "score_away": g.away_score,
          "data_status": g.data_status,
          "last_updated_at": _iso(g.last_updated_at)} for g in group),
        key=lambda s: s["provider"],
    )
    return {
        "id": main.id,
        "kickoff_utc": _iso(main.kickoff_utc),
        "kickoff_time_known": main.kickoff_time_known,
        "status": main.status,
        "home": team_payload(main.home_team_id, home),
        "away": team_payload(main.away_team_id, away),
        "score": {"ft_home": main.home_score, "ft_away": main.away_score,
                  "ht_home": main.home_score_ht, "ht_away": main.away_score_ht},
        "xg": {"home": main.home_xg, "away": main.away_xg},
        "competition": {"code": comp.code if comp else "?", "name": comp.name if comp else "?",
                        "area": comp.area if comp else None,
                        "logo_url": comp.logo_url if comp else None},
        "venue": main.venue,
        "venue_city": main.venue_city,
        "clock": main.clock,                       # minute LIVE réelle (source), NULL sinon
        "referee": main.referee,
        # M5 : mouvement du marché depuis la 1re observation — points de %, signés
        "odds_trend": next((trends[g.id] for g in group if trends and g.id in trends), None),
        "data_status": _card_data_status([g.data_status for g in group]),
        "sources": sources,
        "n_sources": len({g.source_provider for g in group}),
    }


@app.get("/v1/fixtures")
def list_fixtures(
    tab: str = Query("upcoming", pattern="^(live|upcoming|finished|all)$"),
    competition: str | None = None,
    date: str | None = Query(None, description="jour optionnel YYYY-MM-DD (ex. 2026-08-24)"),
    limit: int = Query(200, le=1000),
    offset: int = 0,
) -> JSONResponse:
    with SF() as s:
        q = s.query(Fixture)
        if competition:
            comp = s.query(Competition).filter_by(code=competition).one_or_none()
            if comp is None:
                return JSONResponse({"error": f"competition inconnue: {competition}"}, status_code=404)
            q = q.filter(Fixture.competition_id == comp.id)
        if date:
            try:
                d0 = datetime.strptime(date, "%Y-%m-%d").date()
            except ValueError:
                return JSONResponse({"error": "format date attendu : YYYY-MM-DD"}, status_code=400)
            rows_all = q.all()
            rows = [r for r in rows_all
                    if r.kickoff_utc and r.kickoff_utc.date().isoformat() == d0.isoformat()]
        else:
            rows = q.all()
        if tab == "live":
            rows = [r for r in rows if r.status in LIVE_STATUSES]
        elif tab == "upcoming":
            rows = [r for r in rows if r.status in UPCOMING_STATUSES]
        elif tab == "finished":
            rows = [r for r in rows if r.status in FINISHED_STATUSES]

        team_ids = {r.home_team_id for r in rows} | {r.away_team_id for r in rows}
        teams = {t.id: t for t in s.query(Team).filter(Team.id.in_(team_ids or {0}))}
        comps = {c.id: c for c in s.query(Competition).all()}
        analytics = {a.team_id: a for a in s.query(TeamAnalytics).filter(
            TeamAnalytics.team_id.in_(team_ids or {0}))}

        # prédictions + value bets (une info par groupe de jumeaux)
        fx_ids = [r.id for r in rows]
        from .analytics.odds_trend import odds_trends
        trends = odds_trends(s, fx_ids)
        preds_by_fx: dict[int, Prediction] = {}
        for p in s.query(Prediction).filter(Prediction.fixture_id.in_(fx_ids or {0})).order_by(
                Prediction.created_at.desc()).all():
            preds_by_fx.setdefault(p.fixture_id, p)
        vbs_by_fx: dict[int, list[ValueBet]] = {}
        for vb in s.query(ValueBet).filter(ValueBet.fixture_id.in_(fx_ids or {0})).all():
            vbs_by_fx.setdefault(vb.fixture_id, []).append(vb)

        # Jumeaux cross-provider (§41) : même match, noms parfois différents
        # (« Stade de Reims » ESPN ↔ « Reims » fduk) → 1 seule carte.
        from .analytics.twins import twin_clusters
        items = [{"i": i, "home": (teams.get(r.home_team_id).name if teams.get(r.home_team_id) else ""),
                  "away": (teams.get(r.away_team_id).name if teams.get(r.away_team_id) else ""),
                  "date": r.kickoff_utc.date().isoformat() if r.kickoff_utc else "?",
                  "comp": r.competition_id} for i, r in enumerate(rows)]
        groups = [[rows[k] for k in cluster] for cluster in twin_clusters(items)]

        cards = []
        for g in groups:
            card = _fixture_dict(g, teams, comps, analytics, trends)
            pred = next((preds_by_fx[x.id] for x in g if x.id in preds_by_fx), None)
            if pred is not None:
                # M6 : en direct → probabilités IN-PLAY recalculées (score + minute réels)
                if card["status"] in LIVE_STATUSES and main_score_known(card):
                    from .ml.inplay import inplay_probabilities, parse_clock_minute
                    minute = parse_clock_minute(card.get("clock")) or _minute_from_kickoff(card["kickoff_utc"])
                    if minute is not None:
                        eg = pred.expected_goals or {}
                        card["inplay"] = inplay_probabilities(
                            float(eg.get("home") or 1.2), float(eg.get("away") or 1.0),
                            minute, card["score"]["ft_home"], card["score"]["ft_away"])
                card["prediction"] = {
                    "model_version": pred.feature_version,
                    "expected_goals": pred.expected_goals,
                    "ensemble": pred.probabilities.get("1X2_ensemble"),
                    "dc_1x2": {k: round(v, 4) for k, v in pred.probabilities["1X2"].items()},
                    "OU_2.5": pred.probabilities.get("OU_2.5"),
                    "BTTS": pred.probabilities.get("BTTS"),
                    "top_scores": pred.probabilities.get("top_scores", [])[:3],
                    "model_disagreement": pred.input_snapshot.get("model_disagreement_1x2H"),
                    "history_matches": pred.input_snapshot.get("history_matches"),
                    "created_at": _iso(pred.created_at),
                }
            vbs = sorted((vb for x in g for vb in vbs_by_fx.get(x.id, [])),
                         key=lambda v: v.ev, reverse=True)
            if vbs:
                card["value_bets"] = [{
                    "market": vb.market, "selection": vb.selection,
                    "odds": vb.odds_reference, "bookmaker": vb.bookmaker_ref,
                    "p_model": round(vb.p_model, 4), "p_fair": round(vb.p_market_fair, 4),
                    "edge_pts": round(vb.edge * 100, 1), "ev_pct": round(vb.ev * 100, 1),
                    "level": vb.level, "confidence": vb.confidence,
                } for vb in vbs[:4]]
                card["best_pick"] = card["value_bets"][0]
            else:
                card["best_pick"] = None   # NO QUALIFIED PICK si rien (§37/§85) — affiché comme tel
            cards.append(card)
        # upcoming/live : plus proche d'abord ; finished : plus récent d'abord
        cards.sort(key=lambda c: c["kickoff_utc"] or "", reverse=(tab == "finished"))
        total = len(cards)
        cards = cards[offset:offset + limit]
        return JSONResponse({
            "count": total, "returned": len(cards),
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "fixtures": cards,
        })


@app.get("/v1/value-bets")
def value_bets(min_level: str = Query("POTENTIAL", pattern="^(POTENTIAL|QUALIFIED|STRONG)$"),
               limit: int = Query(100, le=500)) -> JSONResponse:
    """Page VALUE BETS (§83-85) : UNIQUEMENT des sélections sur cotes réelles calculées
    par le moteur. NO VALUE / NO QUALIFIED PICK ne sont pas listés (§37)."""
    order = {"POTENTIAL": 0, "QUALIFIED": 1, "STRONG": 2}
    from datetime import timedelta
    cutoff = datetime.now(timezone.utc) - timedelta(hours=2, minutes=30)
    future_status = {"SCHEDULED", "UPCOMING", "LINEUPS_PENDING", "LINEUPS_CONFIRMED"}
    with SF() as s:
        rows = []
        teams = {t.id: t for t in s.query(Team).all()}
        comps = {c.id: c for c in s.query(Competition).all()}
        q = (s.query(ValueBet).join(Fixture, ValueBet.fixture_id == Fixture.id)
             .filter(Fixture.status.in_(future_status))  # jamais de VB sur match passé (§1/§38)
             .order_by(ValueBet.ev.desc()).limit(limit * 8))
        for vb in q.all():
            if order.get(vb.level, 0) < order[min_level]:
                continue
            fx = s.get(Fixture, vb.fixture_id)
            if fx is None or (fx.kickoff_utc and
                              fx.kickoff_utc.replace(tzinfo=timezone.utc if fx.kickoff_utc.tzinfo is None else fx.kickoff_utc.tzinfo) < cutoff):
                continue  # kickoff dépassé → plus de marché réel disponible
            h, a = teams.get(fx.home_team_id), teams.get(fx.away_team_id)
            comp = comps.get(fx.competition_id)
            rows.append({
                "fixture_id": fx.id, "kickoff_utc": _iso(fx.kickoff_utc),
                "home": h.name if h else "?", "away": a.name if a else "?",
                "competition": comp.name if comp else "?",
                "market": vb.market, "selection": vb.selection,
                "odds_reference": vb.odds_reference, "bookmaker": vb.bookmaker_ref,
                "p_model": round(vb.p_model, 4), "p_market_fair": round(vb.p_market_fair, 4),
                "edge_pts": round(vb.edge * 100, 1), "ev_pct": round(vb.ev * 100, 1),
                "level": vb.level, "confidence": vb.confidence,
                "probability_is_not_certainty": True,   # §38 : jamais de promesse
            })
            if len(rows) >= limit:
                break
        return JSONResponse({"count": len(rows),
                             "disclaimer": "Moteur d'analyse probabiliste — une Value Bet n'est jamais une garantie (§38/§86).",
                             "value_bets": rows})


@app.get("/v1/fixtures/{fixture_id}/analysis")
def fixture_analysis(fixture_id: int) -> JSONResponse:
    """§91 : analyse complète d'un match — données + modèle + marché + audit."""
    with SF() as s:
        fx = s.get(Fixture, fixture_id)
        if fx is None:
            return JSONResponse({"error": "match inconnu"}, status_code=404)
        home, away = s.get(Team, fx.home_team_id), s.get(Team, fx.away_team_id)
        comp = s.get(Competition, fx.competition_id)

        # Jumeaux (même match rapporté par plusieurs providers, noms proches) :
        # la fiche agrège prédiction + cotes de TOUTES les lignes du match (§41).
        from .analytics.twins import match_same_side
        twins = [fx]
        if fx.kickoff_utc:
            day_rows = s.query(Fixture).filter(
                Fixture.competition_id == fx.competition_id,
                Fixture.id != fx.id).all()
            hname = home.name if home else ""
            aname = away.name if away else ""
            for r in day_rows:
                if not r.kickoff_utc or r.kickoff_utc.date() != fx.kickoff_utc.date():
                    continue
                rh, ra = s.get(Team, r.home_team_id), s.get(Team, r.away_team_id)
                if rh and ra and match_same_side(hname, aname, rh.name, ra.name):
                    twins.append(r)
        twin_ids = [t.id for t in twins]
        home_ids = {t.home_team_id for t in twins}
        away_ids = {t.away_team_id for t in twins}

        preds = s.query(Prediction).filter(Prediction.fixture_id.in_(twin_ids)) \
            .order_by(Prediction.created_at.desc()).all()
        all_side_ids = list(home_ids | away_ids)
        analytics = {a.team_id: a for a in s.query(TeamAnalytics).filter(
            TeamAnalytics.team_id.in_(all_side_ids))}

        def team_an(tids):
            """Meilleur échantillon disponible parmi les IDs jumeaux du même côté (§13)."""
            ids = tids if isinstance(tids, (set, list)) else {tids}
            best = max((analytics.get(i) for i in ids if analytics.get(i)),
                       key=lambda a: a.matches_rated or 0, default=None)
            return None if best is None else {"elo": round(best.elo, 1) if best.elo else None,
                                              "matches_rated": best.matches_rated, "form5": best.form5,
                                              "gf5": best.gf5, "ga5": best.ga5}
        pred_payload = None
        if preds:
            p = preds[0]
            pred_payload = {
                "model_version": f"ensemble-dc-poisson-elo:{p.feature_version}",
                "created_at": _iso(p.created_at),
                "probabilities": p.probabilities,
                "expected_goals": p.expected_goals,
                "input_snapshot": p.input_snapshot,     # §104 AUDIT : pourquoi cette prédiction
                "models_count": len(preds),
            }
        vbs = s.query(ValueBet).filter(ValueBet.fixture_id.in_(twin_ids)).all()

        # ---------- M7 : météo réelle si ville connue (Open-Meteo gratuit) ----------
        weather = None
        if fx.venue_city and fx.kickoff_utc:
            from .analytics.weather import forecast_at
            weather = forecast_at(fx.venue_city, fx.kickoff_utc)

        # ---------- M7 : H2H réel entre les deux équipes (tous IDs jumeaux) ----------
        from .analytics.h2h import head_to_head
        seen_h2h, h2h = set(), None
        for hid in home_ids:
            for aid in away_ids:
                key = (min(hid, aid), max(hid, aid))
                if key in seen_h2h:
                    continue
                seen_h2h.add(key)
                r = head_to_head(s, hid, aid)
                if r["count"] and (h2h is None or r["count"] > h2h["count"]):
                    h2h = r
        if h2h is None:
            h2h = {"count": 0, "meetings": [], "tally": {"home_wins": 0, "draws": 0, "away_wins": 0},
                   "note": "Aucune confrontation passée en base — DONNÉE NON DISPONIBLE"}

        # ---------- M5 : marché actuel (meilleures cotes + consensus fair) + tendance ----------
        from .analytics.odds_trend import odds_trends
        from .ml.odds_math import best_odds_per_selection, fair_probabilities
        snap_q = (s.query(OddsSnapshot, Bookmaker, Market)
                  .join(Bookmaker, OddsSnapshot.bookmaker_id == Bookmaker.id)
                  .join(Market, OddsSnapshot.market_id == Market.id)
                  .filter(OddsSnapshot.fixture_id.in_(twin_ids), OddsSnapshot.status == "ACTIVE")
                  .order_by(OddsSnapshot.captured_at.desc()))
        mkt_book: dict[str, dict[str, dict[str, float]]] = {}
        mkt_avg: dict[str, dict[str, list[float]]] = {}
        captured_max = None
        for snap, bm, mk in snap_q.all():
            captured_max = captured_max or snap.captured_at
            mkt_book.setdefault(mk.code, {}).setdefault(bm.code, {})[snap.selection] = snap.odds
            mkt_avg.setdefault(mk.code, {}).setdefault(snap.selection, []).append(snap.odds)
        market_now = {}
        for mk_code, books in mkt_book.items():
            best = best_odds_per_selection(books)
            fair = fair_probabilities({sel: sum(v) / len(v) for sel, v in mkt_avg[mk_code].items()})
            market_now[mk_code] = {
                "best": {sel: {"bookmaker": bm_, "odds": od} for sel, (bm_, od) in best.items()},
                "fair_consensus": {sel: round(p, 4) for sel, p in fair.items()},
                "n_bookmakers": len(books),
            }
        trend_all = odds_trends(s, twin_ids)
        trend = next((trend_all[t] for t in twin_ids if t in trend_all), None)

        # matrice de disponibilité §98 — honnête sur ce qui manque
        availability = {
            "fixture": True, "result": fx.status == "FINISHED",
            "xg": fx.home_xg is not None,
            "odds_1x2": bool(market_now.get("1X2")),
            "lineups": False,            # aucune source gratuite fiable → DONNÉE NON DISPONIBLE
            "weather": weather is not None,
            "referee": fx.referee is not None,
            "h2h": h2h["count"] > 0,
        }
        n_avail = sum(1 for v in availability.values() if v)
        data_quality = round(100 * n_avail / len(availability))   # §48 score simple documenté
        return JSONResponse({
            "fixture": {
                "id": fx.id, "status": fx.status, "kickoff_utc": _iso(fx.kickoff_utc),
                "home": home.name if home else "?", "away": away.name if away else "?",
                "competition": comp.name if comp else "?",
                "score": [fx.home_score, fx.away_score] if fx.status == "FINISHED" else None,
                "venue": fx.venue, "venue_city": fx.venue_city, "clock": fx.clock,
                "referee": fx.referee,
                "data_status": fx.data_status, "source_provider": fx.source_provider,
                "last_updated_at": _iso(fx.last_updated_at),
            },
            "data_availability": availability,
            "data_quality_score": data_quality,
            "team_analytics": {"home": team_an(home_ids), "away": team_an(away_ids)},
            "h2h": h2h,
            "weather": weather,
            "market_now": market_now,
            "market_captured_at": _iso(captured_max) if captured_max else None,
            "odds_trend": trend,
            "prediction": pred_payload,
            "value_bets": [{
                "market": vb.market, "selection": vb.selection,
                "odds": vb.odds_reference, "edge_pts": round(vb.edge * 100, 1),
                "ev_pct": round(vb.ev * 100, 1), "level": vb.level,
                "confidence": vb.confidence} for vb in vbs],
            "no_pick_note": None if vbs else "NO QUALIFIED PICK si aucune value robuste (§37/§85)",
            "model_uncertainty": "Probabilité ≠ certitude (§38)" if preds else None,
        })


@app.get("/v1/competitions")
def list_competitions() -> JSONResponse:
    with SF() as s:
        out = []
        for c in s.query(Competition).order_by(Competition.code).all():
            n = s.query(Fixture).filter(Fixture.competition_id == c.id).count()
            out.append({"id": c.id, "code": c.code, "name": c.name, "area": c.area, "fixtures": n})
        return JSONResponse({"competitions": out})


@app.get("/v1/teams/{team_id}")
def get_team(team_id: int) -> JSONResponse:
    with SF() as s:
        t = s.get(Team, team_id)
        if t is None:
            return JSONResponse({"error": "équipe inconnue"}, status_code=404)
        a = s.query(TeamAnalytics).filter_by(team_id=team_id).one_or_none()
        return JSONResponse({
            "id": t.id, "name": t.name, "country": t.country,
            "logo_url": t.logo_url,
            "aliases": [al.alias for al in t.aliases],
            "analytics": None if a is None else {   # §16 : NULL si pas calculable, jamais inventé
                "elo": round(a.elo, 1) if a.elo is not None else None,
                "matches_rated": a.matches_rated,
                "form5": a.form5, "points5": a.points5,
                "gf5": a.gf5, "ga5": a.ga5,
                "model_version": a.model_version,
                "features_version": a.features_version,
                "computed_at": _iso(a.computed_at),
            },
        })


@app.get("/v1/ratings")
def ratings(limit: int = Query(50, le=500)) -> JSONResponse:
    """Classement Elo global (§16) — calculé sur l'historique réel uniquement."""
    with SF() as s:
        rows = (
            s.query(TeamAnalytics, Team)
            .join(Team, TeamAnalytics.team_id == Team.id)
            .filter(TeamAnalytics.elo.isnot(None))
            .order_by(TeamAnalytics.elo.desc())
            .limit(limit)
            .all()
        )
        return JSONResponse({"model_version": "elo-v1",
                             "ratings": [{"team_id": t.id, "name": t.name,
                                          "elo": round(a.elo, 1), "matches": a.matches_rated,
                                          "form5": a.form5} for a, t in rows]})


@app.get("/v1/health/providers")
def provider_health() -> JSONResponse:
    with SF() as s:
        rows = s.query(ProviderHealth).order_by(ProviderHealth.provider).all()
        return JSONResponse({"providers": [
            {"provider": h.provider, "status": h.status, "latency_ms": h.latency_ms,
             "detail": h.detail, "checked_at": _iso(h.checked_at)} for h in rows]})  # §75


@app.get("/v1/chat")
def chat(q: str = Query(..., min_length=2, description="question en langage naturel (fr)")) -> JSONResponse:
    """M8 : assistant PRONO SPORT — réponses UNIQUEMENT depuis les données réelles (§1)."""
    from .chat.engine import answer
    with SF() as s:
        out = answer(s, q)
    out["engine"] = "prono-chat:v1 (règles déterministes, aucun service externe)"
    return JSONResponse(out)


@app.get("/v1/stats")
def stats() -> JSONResponse:
    with SF() as s:
        from .db.models import EntityMapping, IngestionReject, OddsSnapshot
        return JSONResponse({
            "fixtures": s.query(Fixture).count(),
            "teams": s.query(Team).count(),
            "competitions": s.query(Competition).count(),
            "odds_snapshots": s.query(OddsSnapshot).count(),
            "entity_mappings": s.query(EntityMapping).count(),
            "ingestion_rejects": s.query(IngestionReject).count(),
            "data_status": {  # §1 transparence : combien de matchs par niveau de confiance
                k: s.query(Fixture).filter(Fixture.data_status == k).count()
                for k in ("VERIFIED", "UNVERIFIED", "CONTRADICTORY")
            },
            "generated_at": datetime.now(timezone.utc).isoformat(),
        })


@app.get("/", include_in_schema=False)
def index() -> FileResponse:
    return FileResponse(STATIC_DIR / "index.html")


@app.get("/prono-sport-code.zip", include_in_schema=False)
def pack_zip() -> FileResponse:
    """Lien direct du pack projet (pour le guide Termux : 1 seule commande à coller).
    Présent seulement sur le serveur atelier où le pack a été déposé (§1 : 404 ailleurs)."""
    from fastapi import HTTPException
    p = STATIC_DIR / "prono-sport-code.zip"
    if not p.exists():
        raise HTTPException(404, "pack non présent sur ce serveur")
    return FileResponse(p, media_type="application/zip", filename="prono-sport-code.zip")


# --- Scheduler live (§43 : fréquence réelle, latence affichée) ---
async def _auto_ingest_loop() -> None:  # pragma: no cover - boucle de fond
    from .ingest.consistency import run_consistency, sweep_stale
    from .ingest.service import run_ingestion
    from .providers.registry import get_provider
    interval = int(os.environ.get("AUTO_INGEST_SECONDS", "120"))
    # monde entier par défaut (55 ligues validées) — surchargé via env si on veut cibler
    from .providers import espn as espn_mod
    leagues = os.environ.get("AUTO_INGEST_LEAGUES", " ".join(espn_mod.AUTO_WATCH_LEAGUES)).split()
    from datetime import timedelta as _td
    while True:
        await asyncio.sleep(interval)
        try:
            provider = get_provider("espn")
            # hier/aujourd'hui/demain → les statuts des matchs joués sont rafraîchis (§ fraîcheur)
            days = [(datetime.now(timezone.utc) + _td(days=d)).strftime("%Y%m%d") for d in (-1, 0, 1)]
            with SF() as s:
                for league in leagues:
                    for day in days:
                        payload = provider.fetch(league=league, date=day)
                        raws = list(provider.parse(payload, league=league,
                                                   source_url=provider.scoreboard_url(league)))
                        run_ingestion(s, provider, raws)
                sweep_stale(s)   # statuts périmés → UNKNOWN jusqu'à re-vérification (§1)
                run_consistency(s)
        except Exception:
            pass  # un échec de cycle ne doit jamais tuer le serveur (§64) ; provider_health garde la trace


async def _live_fast_loop() -> None:  # pragma: no cover - M6 : rafraîchissement LIVE rapide
    """Tant qu'un match est EN COURS en base : refresh ESPN de SES ligues seulement,
    toutes les AUTO_LIVE_SECONDS (défaut 75 s). Sans match live → la boucle dort (0 requête)."""
    from .db.models import EntityMapping
    from .ingest.consistency import run_consistency
    from .ingest.service import run_ingestion
    from .providers.registry import get_provider
    interval = int(os.environ.get("AUTO_LIVE_SECONDS", "75"))
    while True:
        await asyncio.sleep(interval)
        try:
            provider = get_provider("espn")
            with SF() as s:
                live_comps = {fx.competition_id for fx in s.query(Fixture).filter(
                    Fixture.status.in_(list(LIVE_STATUSES))).all()}
                if not live_comps:
                    continue
                slugs = [m.provider_id for m in s.query(EntityMapping).filter(
                    EntityMapping.entity_type == "competition",
                    EntityMapping.provider == "espn").all()
                    if m.entity_id in live_comps]
                day = datetime.now(timezone.utc).strftime("%Y%m%d")
                for slug in slugs:
                    payload = provider.fetch(league=slug, date=day)
                    raws = list(provider.parse(payload, league=slug,
                                               source_url=provider.scoreboard_url(slug)))
                    run_ingestion(s, provider, raws)
                run_consistency(s)
        except Exception:
            pass  # §64 : la boucle live ne doit jamais tuer l'API


async def _auto_compute_loop() -> None:  # pragma: no cover - boucle de fond
    """Recalcule analytics + prédictions/value bets toutes les AUTO_COMPUTE_SECONDS (défaut 3600 s).
    Indispensable sur un serveur 24/7 : sans ça, les pronos restent figés alors que les cotes
    réelles bougent (§35 : la value doit être recalculée sur les dernières cotes)."""
    interval = int(os.environ.get("AUTO_COMPUTE_SECONDS", "3600"))
    await asyncio.sleep(90)  # laisse le démarrage/bootstrap respirer
    while True:
        try:
            def _compute() -> None:
                from .analytics.engine import compute_all
                from .ml.engine import predict_upcoming
                with SF() as s:
                    compute_all(s)
                    predict_upcoming(s)
            await asyncio.to_thread(_compute)
        except Exception:
            pass  # §64 : un échec de recalcul ne doit jamais tuer l'API
        await asyncio.sleep(interval)


@app.on_event("startup")
async def startup() -> None:  # pragma: no cover
    if os.environ.get("AUTO_INGEST") == "1":
        asyncio.create_task(_auto_ingest_loop())
        if os.environ.get("AUTO_LIVE", "1") == "1":
            asyncio.create_task(_live_fast_loop())
        if os.environ.get("AUTO_COMPUTE", "1") == "1":
            asyncio.create_task(_auto_compute_loop())
