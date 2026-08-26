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
import json
import os
import time
from datetime import datetime, timezone
from pathlib import Path

from fastapi import FastAPI, Header, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from sqlalchemy.orm import Session, joinedload

from .config import DATABASE_URL
from .db.base import make_engine, make_session_factory, ensure_schema
from .db.models import (
    Bookmaker,
    Competition,
    Fixture,
    Market,
    Notification,
    OddsSnapshot,
    Prediction,
    PredictionResult,
    ProviderHealth,
    Team,
    TeamAnalytics,
    ValueBet,
)

from .realtime import BUS, emit

STATIC_DIR = Path(__file__).parent / "static"

LIVE_STATUSES = {"LIVE", "HALFTIME", "EXTRA_TIME", "PENALTIES"}
UPCOMING_STATUSES = {"SCHEDULED", "UPCOMING", "LINEUPS_PENDING", "LINEUPS_CONFIRMED"}
FINISHED_STATUSES = {"FINISHED"}

ENGINE = make_engine(DATABASE_URL)
ensure_schema(ENGINE)  # crée les tables 3.0 + migre les bases 2.0 (colonnes manquantes)
SF = make_session_factory(ENGINE)

app = FastAPI(title="PRONO SPORT API", version="3.0.0-alpha", docs_url="/v1/docs")
app.add_middleware(CORSMiddleware, allow_origins=["*"],
                   allow_methods=["GET", "POST", "OPTIONS"], allow_headers=["*"])

# =============================================================================
# PHASE 19 — SÉCURITÉ : rate limiting (0 €, mémoire, par IP)
# Le flux SSE /v1/events est exempté (connexion longue par nature).
# =============================================================================
from collections import deque

from starlette.responses import PlainTextResponse

RATE_LIMIT_PER_MIN = 300
RATE_WINDOW_S = 60
_RATE_BUCKETS: dict[str, deque] = {}


def _rate_limit_check(path: str, ip: str) -> bool:
    """Fenêtre glissante par IP — True = autorisé. /v1/events est exempté (SSE)."""
    if not path.startswith("/v1") or path == "/v1/events":
        return True
    now = time.monotonic()
    dq = _RATE_BUCKETS.setdefault(ip, deque())
    while dq and now - dq[0] > RATE_WINDOW_S:
        dq.popleft()
    if len(dq) >= RATE_LIMIT_PER_MIN:
        return False
    dq.append(now)
    return True


@app.middleware("http")
async def _rate_limit(request, call_next):
    ip = request.client.host if request.client else "inconnu"
    if not _rate_limit_check(request.url.path, ip):
        return PlainTextResponse(
            f"429 — TROP DE REQUÊTES (limite : {RATE_LIMIT_PER_MIN}/min par IP). Ralentissez.",
            status_code=429)
    return await call_next(request)

# Frontend statique (style.css, app.js, images) — servi par l'API (1 seul déploiement, 0 €)
from fastapi.staticfiles import StaticFiles
app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")

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


# =============================================================================
# PRONO SPORT 3.0 — NOUVEAUX ENDPOINTS
# =============================================================================

@app.get("/v1/health")
def health() -> JSONResponse:
    """Santé globale de la plateforme (API + base + sources)."""
    from .db.models import DataSource
    with SF() as s:
        sources = s.query(DataSource).count()
        try:
            n_fixtures = s.query(Fixture).count()
        except Exception:
            n_fixtures = -1
    return JSONResponse({
        "status": "OK",
        "api": "prono-sport:3.0-alpha",
        "db": "OK" if n_fixtures >= 0 else "ERREUR",
        "sources_registered": sources,
        "sse_clients": BUS.n_subscribers,
        "generated_at": datetime.now(timezone.utc).isoformat(),
    })


@app.get("/v1/sources")
def sources() -> JSONResponse:
    """§62 SOURCE MONITOR — registre des sources : statut, fiabilité, dernière sync,
    erreurs, latence, catégories, conditions d'utilisation."""
    from .db.models import DataSource, SyncJob
    from .discovery.catalog import CATEGORIES_FR
    from .discovery.engine import legacy_name
    with SF() as s:
        ph = {h.provider: h for h in s.query(ProviderHealth).all()}
        last_jobs = {}
        for j in s.query(SyncJob).order_by(SyncJob.started_at.desc()).limit(200).all():
            last_jobs.setdefault(j.provider or j.worker, j)
        out = []
        for src in s.query(DataSource).order_by(DataSource.name).all():
            health_row = ph.get(src.name) or ph.get(legacy_name(src.name) or "")
            out.append({
                "name": src.name,
                "kind": src.kind,
                "status": src.status,
                "availability": src.availability_status or (health_row.status if health_row else "UNKNOWN"),
                "reliability": src.reliability_score,
                "reliability_note": None if src.reliability_score is not None
                                     else "non mesurée — historique insuffisant (jamais inventée)",
                "categories": [CATEGORIES_FR.get(c, c) for c in (src.data_categories or [])],
                "coverage": src.coverage,
                "update_frequency": src.update_frequency,
                "terms_status": src.terms_status,
                "attribution_required": src.attribution_required,
                "requires_key": src.requires_key,
                "latency_ms": health_row.latency_ms if health_row else None,
                "detail": health_row.detail if health_row else None,
                "checked_at": _iso(health_row.checked_at) if health_row else None,
                "last_successful": _iso(src.last_successful_fetch),
                "last_failed": _iso(src.last_failed_fetch),
                "last_job": _iso(last_jobs[src.name].started_at) if src.name in last_jobs else None,
            })
        return JSONResponse({"sources": out,
                             "note": "Fiabilité calculée sur l'observé (sync_jobs) — jamais inventée."})


@app.get("/v1/sync-jobs")
def sync_jobs(limit: int = Query(50, le=500)) -> JSONResponse:
    """§63 Admin — journal des workers (idempotence, erreurs, latence)."""
    from .db.models import SyncJob
    with SF() as s:
        rows = s.query(SyncJob).order_by(SyncJob.started_at.desc()).limit(limit).all()
        return JSONResponse({"jobs": [{
            "id": j.id, "worker": j.worker, "provider": j.provider, "status": j.status,
            "records": j.records, "created": j.created, "updated": j.updated,
            "rejected": j.rejected, "latency_ms": j.latency_ms, "errors": j.errors,
            "started_at": _iso(j.started_at), "finished_at": _iso(j.finished_at),
        } for j in rows]})


@app.get("/v1/quality")
def quality(refresh: bool = False) -> JSONResponse:
    """§47/§61 COVERAGE CENTER — qualité de données par compétition (calculée)."""
    from .analytics.quality import compute_quality
    with SF() as s:
        data = compute_quality(s) if refresh else _quality_cache(s)
    return JSONResponse({"quality": list(data.values()),
                         "note": "Score calculé sur l'état réel de la base (couverture, "
                                 "vérification croisée, sources, historique, fraîcheur)."})


def _quality_cache(s) -> dict:
    """Qualité en cache si computed_at < 30 min, sinon recalcul (pas de surcharge)."""
    from datetime import timedelta
    from .db.models import DataQuality
    rows = s.query(DataQuality).all()
    fresh = [r for r in rows
             if r.computed_at and (datetime.now(timezone.utc)
                                   - _as_utc(r.computed_at)) < timedelta(minutes=30)]
    if fresh:
        out = {}
        for r in fresh:
            c = s.get(Competition, r.competition_id)
            out[c.code] = {"code": c.code, "name": c.name, "score": r.score,
                           "fixtures": r.fixtures, "verified_pct": r.verified_pct,
                           "n_sources": r.n_sources, "history_from": r.history_from,
                           "history_to": r.history_to, "freshness_min": r.freshness_min,
                           "missing": r.missing}
        return out
    from .analytics.quality import compute_quality
    return compute_quality(s)


def _as_utc(dt: datetime) -> datetime:
    return dt.replace(tzinfo=timezone.utc) if dt.tzinfo is None else dt


@app.get("/v1/fixtures/{fixture_id}/events")
def fixture_events(fixture_id: int) -> JSONResponse:
    """§16/§52 — événements du match (buts dérivés de deltas de score réels, statuts)."""
    from .db.models import FixtureEvent, Team
    with SF() as s:
        if s.get(Fixture, fixture_id) is None:
            return JSONResponse({"error": "match inconnu"}, status_code=404)
        teams = {t.id: t for t in s.query(Team).all()}
        rows = (s.query(FixtureEvent)
                .filter(FixtureEvent.fixture_id == fixture_id)
                .order_by(FixtureEvent.created_at.asc()).all())
        return JSONResponse({"events": [{
            "minute": e.minute, "type": e.type,
            "team": teams.get(e.team_id).name if e.team_id else None,
            "detail": e.detail, "origin": e.origin,
            "created_at": _iso(e.created_at),
        } for e in rows],
        "note": "Buts : DERIVED = déduits d'un changement de score réel observé (jamais inventés)."})


@app.get("/v1/fixtures/{fixture_id}/stats")
def fixture_stats(fixture_id: int) -> JSONResponse:
    """§52 — statistiques d'équipe du match (source réelle si disponible)."""
    from .db.models import Team, TeamStat
    with SF() as s:
        if s.get(Fixture, fixture_id) is None:
            return JSONResponse({"error": "match inconnu"}, status_code=404)
        teams = {t.id: t for t in s.query(Team).all()}
        rows = s.query(TeamStat).filter(TeamStat.fixture_id == fixture_id).all()
        out = []
        for st in rows:
            t = teams.get(st.team_id)
            out.append({
                "team": t.name if t else "?",
                "possession": st.possession, "tirs": st.shots,
                "tirs_cadres": st.shots_on_target, "corners": st.corners,
                "fautes": st.fouls, "cartons": st.yellow_cards,
                "source": st.source, "as_of": _iso(st.as_of),
            })
        if not out:
            return JSONResponse({"stats": [], "status": "DONNÉE INDISPONIBLE",
                                 "note": "Aucune statistique de match fournie par une source active."})
        return JSONResponse({"stats": out, "status": "AVAILABLE"})


@app.get("/v1/reports/{fixture_id}")
def fixture_report(fixture_id: int, refresh: bool = False) -> JSONResponse:
    """§46 EXPERT MATCH REPORT — recherche approfondie multi-sources (0 €)."""
    from .research.engine import build_expert_report, report_freshness
    with SF() as s:
        try:
            rep = build_expert_report(s, fixture_id, refresh=refresh)
        except ValueError:
            return JSONResponse({"error": "match inconnu"}, status_code=404)
        rep["freshness"] = report_freshness(rep.get("generated_at"))
        return JSONResponse(rep)


@app.get("/v1/search")
def search(q: str = Query(..., min_length=2, description="recherche globale (fr)")) -> JSONResponse:
    """§81 — recherche globale : équipes, compétitions, matchs (base) + web (Wikipedia, 0 €)."""
    from .research.search import search_global
    with SF() as s:
        return JSONResponse(search_global(s, q))


@app.get("/v1/fixtures/{fixture_id}/report")
def fixture_report_alt(fixture_id: int, refresh: bool = False) -> JSONResponse:
    """Alias de /v1/reports/{id} (convenance frontend)."""
    return fixture_report(fixture_id, refresh=refresh)


@app.get("/v1/backtest")
def backtest(refresh: bool = False) -> JSONResponse:
    """§35/§36 BACKTEST LAB — walk-forward sur données réelles : Brier/LogLoss,
    top-1 accuracy, et comparaison modèle vs MARCHÉ (cotes réelles, marge retirée).
    Séparation BACKTEST / PAPER TRACKING / LIVE (§55) : ici, uniquement le backtest."""
    from datetime import timedelta
    from .ml.backtest import load_last_backtest, run_backtest
    with SF() as s:
        rep = None if refresh else load_last_backtest(s)
        if rep is None or _stale_backtest(rep):
            rep = run_backtest(s)
        return JSONResponse({
            **rep,
            "note_global": ("Interprétation honnête : sur cet échantillon, le marché "
                            "réel est souvent plus calibré que le modèle — celui-ci "
                            "s'améliore avec plus d'historique (saisons complètes). "
                            "C'est exactement pourquoi les value bets restent prudemment "
                            "limitées (NO QUALIFIED PICK fréquent, jamais de pick forcé)."),
        })


def _stale_backtest(rep: dict) -> bool:
    from datetime import timedelta
    try:
        dt = datetime.fromisoformat(rep.get("generated_at", ""))
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return (datetime.now(timezone.utc) - dt) > timedelta(hours=6)
    except ValueError:
        return True


@app.get("/v1/predictions/results")
def prediction_results(limit: int = Query(50, le=500)) -> JSONResponse:
    """§54 — résultats des pronostics APRÈS les matchs (WIN/LOSS/VOID/PENDING).
    La prédiction originale est conservée telle quelle (résolution non-destructive)."""
    from .db.models import PredictionResult, Team
    with SF() as s:
        rows = (s.query(PredictionResult)
                .order_by(PredictionResult.resolved_at.desc()).limit(limit).all())
        out = []
        for r in rows:
            fx = s.get(Fixture, r.fixture_id)
            if fx is None:
                continue
            h = s.get(Team, fx.home_team_id)
            a = s.get(Team, fx.away_team_id)
            out.append({
                "fixture_id": r.fixture_id,
                "home": h.name if h else "?", "away": a.name if a else "?",
                "market": r.market, "selection": r.selection,
                "actual": r.actual, "result": r.result,
                "final_score": r.final_score,
                "resolved_at": _iso(r.resolved_at),
            })
        return JSONResponse({"count": len(out), "results": out})


@app.get("/v1/events")
async def sse_events() -> "StreamingResponse":
    """Temps réel : pousse buts, statuts, value bets, sources, jobs (SSE)."""
    from fastapi.responses import StreamingResponse
    q = BUS.subscribe()

    async def gen():
        try:
            yield f"event: hello\ndata: {json.dumps({'type': 'CONNECTED', 'ts': time.time()})}\n\n"
            while True:
                try:
                    ev = await asyncio.wait_for(q.get(), timeout=25)
                    yield f"event: {ev.get('type', 'msg')}\ndata: {json.dumps(ev, ensure_ascii=False)}\n\n"
                except asyncio.TimeoutError:
                    yield f"event: ping\ndata: {json.dumps({'type': 'HEARTBEAT'})}\n\n"
        finally:
            BUS.unsubscribe(q)

    return StreamingResponse(gen(), media_type="text/event-stream",
                             headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})


@app.get("/v1/notifications")
def notifications(limit: int = Query(30, le=200)) -> JSONResponse:
    """§83 — notifications réelles (événements observés en base)."""
    with SF() as s:
        rows = (s.query(Notification)
                .filter(Notification.user == "local")
                .order_by(Notification.created_at.desc()).limit(limit).all())
        return JSONResponse({"notifications": [{
            "id": n.id, "type": n.type, "fixture_id": n.fixture_id,
            "message": n.message, "read": n.read, "created_at": _iso(n.created_at),
        } for n in rows]})


@app.post("/v1/notifications/read")
def mark_notifications_read() -> JSONResponse:
    with SF() as s:
        rows = s.query(Notification).filter(Notification.user == "local",
                                            Notification.read == False).all()  # noqa: E712
        for n in rows:
            n.read = True
        s.commit()
        return JSONResponse({"marked": len(rows)})


@app.post("/v1/admin/sync/{worker}")
def admin_sync(worker: str, x_admin_token: str | None = Header(default=None, alias="x-admin-token")) -> JSONResponse:
    """§63 Admin — déclenche un worker à la demande (optionnel : ADMIN_TOKEN, en-tête x-admin-token)."""
    import os
    expected = os.environ.get("ADMIN_TOKEN")
    if expected and x_admin_token != expected:
        return JSONResponse({"error": "token admin invalide"}, status_code=403)
    from .workers import definitions as W
    handlers = {
        "syncFixtures": lambda s: W.run_fixtures(s),
        "syncLiveMatches": lambda s: W.run_live(s),
        "syncResults": lambda s: W.run_results(s),
        "syncLineups": lambda s: W.run_lineups(s),
        "syncOddsLive": lambda s: W.run_odds_live(s),
        "syncWeather": lambda s: W.run_weather(s),
        "syncHistorical": lambda s: W.run_historical(s),
        "discoverSources": lambda s: W.run_discover(s, offline=False),
    }
    if worker not in handlers:
        return JSONResponse({"error": f"worker inconnu: {worker}",
                             "workers": list(handlers)}, status_code=404)
    try:
        with SF() as s:
            result = handlers[worker](s)
        emit("SYNC_DONE", worker=worker, result=result)
        return JSONResponse(result)
    except Exception as exc:
        return JSONResponse({"error": f"{type(exc).__name__}: {exc}"}, status_code=500)


@app.get("/v1/admin/overview")
def admin_overview() -> JSONResponse:
    """§63 ADMIN — vue d'ensemble de la plateforme (état RÉEL de la base)."""
    from sqlalchemy import func
    from .db.models import AnalysisReport, SyncJob
    with SF() as s:
        # select() + group_by explicite : le Query legacy (colonne + agrégat) n'émet
        # PAS de GROUP BY → SQLite retournerait le statut d'une ligne arbitraire.
        from sqlalchemy import select
        by_status = {st: n for st, n in
                     s.execute(select(Fixture.status, func.count(Fixture.id))
                               .group_by(Fixture.status)).all()}
        last_sync: dict[str, dict] = {}
        for r in s.query(SyncJob).order_by(SyncJob.id.desc()).all():
            if r.worker not in last_sync:
                last_sync[r.worker] = {"status": r.status, "records": r.records,
                                       "at": r.finished_at.isoformat() if r.finished_at else None}
        return JSONResponse({
            "api": "prono-sport:3.0-alpha",
            "fixtures": {"total": s.query(Fixture).count(), "by_status": by_status},
            "competitions": s.query(Competition).count(),
            "predictions": s.query(Prediction).count(),
            "value_bets": s.query(ValueBet).count(),
            "reports": s.query(AnalysisReport).count(),
            "sse_clients": BUS.n_subscribers,
            "last_sync": last_sync,
            "generated_at": datetime.now(timezone.utc).isoformat(),
        })


@app.get("/v1/admin/errors")
def admin_errors() -> JSONResponse:
    """§63 ADMIN — jobs de sync en erreur ou avec rejets (réels, table sync_jobs)."""
    from .db.models import SyncJob
    with SF() as s:
        rows = (s.query(SyncJob)
                .filter((SyncJob.status == "FAILED") | (SyncJob.rejected > 0)
                        | SyncJob.errors.isnot(None))
                .order_by(SyncJob.id.desc()).limit(30).all())
        return JSONResponse({
            "errors": [{"worker": r.worker, "provider": r.provider, "status": r.status,
                        "records": r.records, "rejected": r.rejected, "errors": r.errors,
                        "latency_ms": r.latency_ms,
                        "finished_at": r.finished_at.isoformat() if r.finished_at else None}
                       for r in rows],
            "note": "Enregistrements réels de sync_jobs — liste vide = aucune erreur, rien n'est masqué."})


@app.get("/v1/admin/backup")
def admin_backup(x_admin_token: str | None = Header(default=None, alias="x-admin-token")):
    """§63/§78 ADMIN — téléchargement d'une sauvegarde SQLite COHÉRENTE (sqlite3.backup)."""
    import sqlite3
    import tempfile
    from fastapi.responses import Response
    expected = os.environ.get("ADMIN_TOKEN")
    if expected and x_admin_token != expected:
        return Response("403 — token admin invalide (en-tête x-admin-token)", status_code=403)
    if not DATABASE_URL.startswith("sqlite:///"):
        return Response("400 — backup via cet endpoint réservé à SQLite (Postgres : pg_dump)",
                        status_code=400)
    src_path = DATABASE_URL.replace("sqlite:///", "", 1)
    tmp = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
    tmp.close()
    try:
        src = sqlite3.connect(src_path)
        dst = sqlite3.connect(tmp.name)
        with dst:
            src.backup(dst)
        src.close()
        dst.close()
        with open(tmp.name, "rb") as f:
            data = f.read()
    finally:
        os.unlink(tmp.name)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
    return Response(content=data, media_type="application/x-sqlite3",
                    headers={"Content-Disposition": f'attachment; filename="prono-sport-{stamp}.db"'})


# --- Scheduler live 3.0 (§43 : workers nommés, journalisés, événements SSE) ---

def _live_cycle() -> dict:
    """Cycle live SYNCHRONE (exécuté en thread) :
    1. état avant (scores + statuts des matchs concernés)
    2. ingestion ESPN ciblée (ligues live + départs imminents)
    3. détection d'événements (buts dérivés, transitions) → FixtureEvent + Notification
    4. résolution des pronostics des matchs terminés (WIN/LOSS/VOID, non-destructif)
    5. push SSE à tous les clients
    """
    from datetime import timedelta
    from .db.models import EntityMapping
    from .ingest.consistency import run_consistency
    from .ingest.service import run_ingestion
    from .providers.registry import get_provider
    from .live.events import detect_events, resolve_predictions

    with SF() as s:
        now = datetime.now(timezone.utc)
        # (a) ligues avec match en cours ; (b) départs imminents (−60 min → +30 min)
        live_comps = {fx.competition_id for fx in s.query(Fixture).filter(
            Fixture.status.in_(list(LIVE_STATUSES))).all()}
        soon = (s.query(Fixture)
                .filter(Fixture.kickoff_utc >= now - timedelta(hours=1),
                        Fixture.kickoff_utc <= now + timedelta(minutes=30))
                .all())
        soon_comps = {f.competition_id for f in soon}
        comps = live_comps | soon_comps
        if not comps:
            return {"slugs": 0, "events": []}
        slug_map = {m.entity_id: m.provider_id for m in s.query(EntityMapping).filter(
            EntityMapping.entity_type == "competition",
            EntityMapping.provider == "espn").all()}
        slugs = {slug_map[c] for c in comps if c in slug_map}

        # état AVANT (tous les matchs de ces compétitions, joués ou à venir proche)
        before: dict[int, tuple] = {}
        for fx in s.query(Fixture).filter(Fixture.competition_id.in_(list(comps))).all():
            before[fx.id] = ((fx.home_score, fx.away_score), fx.status)

        provider = get_provider("espn")
        day = now.strftime("%Y%m%d")
        for slug in slugs:
            try:
                payload = provider.fetch(league=slug, date=day)
                raws = list(provider.parse(payload, league=slug,
                                           source_url=provider.scoreboard_url(slug)))
                run_ingestion(s, provider, raws)
            except Exception:
                continue  # §64 : une ligue en échec ne bloque pas les autres
        run_consistency(s)

        # détection + résolution
        events_all: list[dict] = []
        for fx in s.query(Fixture).filter(Fixture.id.in_(list(before.keys()) or [0])).all():
            prev_score, prev_status = before[fx.id]
            evs = detect_events(s, fx, prev_score, prev_status)
            for ev in evs:
                events_all.append(ev)
                emit("LIVE", **ev)
            if fx.status == "FINISHED" and prev_status != "FINISHED":
                r = resolve_predictions(s, fx)
                if r.get("resolved"):
                    emit("PREDICTION_RESOLVED", **r)
        return {"slugs": len(slugs), "events": events_all}


def _fixtures_cycle() -> dict:
    """Cycle fixtures/résultats (5 min) : worker syncFixtures (ESPN + fduk cotes)."""
    from .workers.definitions import run_fixtures
    with SF() as s:
        return run_fixtures(s)


def _compute_cycle() -> dict:
    """Recalcule analytics + prédictions + value bets + qualité (1 h par défaut)."""
    from .analytics.engine import compute_all
    from .analytics.quality import compute_quality
    from .ml.engine import predict_upcoming
    from .db.models import ValueBet, Fixture
    with SF() as s:
        before_ids = {v.id for v in s.query(ValueBet).filter(
            ValueBet.level.in_(["QUALIFIED", "STRONG"])).all()}
        compute_all(s)
        reports = predict_upcoming(s)
        compute_quality(s)
        new = (s.query(ValueBet).filter(
            ValueBet.level.in_(["QUALIFIED", "STRONG"])).all())
        for v in new:
            if v.id not in before_ids:
                fx = s.get(Fixture, v.fixture_id)
                if fx:
                    from .db.models import Team
                    h, a = s.get(Team, fx.home_team_id), s.get(Team, fx.away_team_id)
                    emit("VALUE_BET", fixture_id=fx.id,
                         home=h.name if h else "?", away=a.name if a else "?",
                         market=v.market, selection=v.selection, level=v.level,
                         ev_pct=round(v.ev * 100, 1))
        return {"predictions": sum(r.predictions for r in reports),
                "value_bets_new": len([v for v in new if v.id not in before_ids])}


async def _auto_ingest_loop() -> None:  # pragma: no cover - boucle de fond
    interval = int(os.environ.get("AUTO_INGEST_SECONDS", "300"))
    while True:
        await asyncio.sleep(interval)
        try:
            res = await asyncio.to_thread(_fixtures_cycle)
            emit("SYNC_DONE", worker="syncFixtures", result=res)
        except Exception:
            pass  # §64 : un échec de cycle ne doit jamais tuer le serveur


async def _live_fast_loop() -> None:  # pragma: no cover - M6 : rafraîchissement LIVE rapide
    interval = int(os.environ.get("AUTO_LIVE_SECONDS", "75"))
    while True:
        await asyncio.sleep(interval)
        try:
            res = await asyncio.to_thread(_live_cycle)
            if res.get("events"):
                emit("LIVE_BURST", events=res["events"])
        except Exception:
            pass


async def _auto_compute_loop() -> None:  # pragma: no cover - boucle de fond
    interval = int(os.environ.get("AUTO_COMPUTE_SECONDS", "3600"))
    await asyncio.sleep(60)  # laisse le démarrage/bootstrap respirer
    while True:
        try:
            res = await asyncio.to_thread(_compute_cycle)
            emit("SYNC_DONE", worker="compute", result=res)
        except Exception:
            pass
        await asyncio.sleep(interval)


async def _discover_loop() -> None:  # pragma: no cover - P8 : découverte hebdo
    interval = int(os.environ.get("DISCOVER_SECONDS", 7 * 86400))
    await asyncio.sleep(120)
    while True:
        try:
            def _d() -> dict:
                from .workers.definitions import run_discover
                with SF() as s:
                    return run_discover(s, offline=False)
            res = await asyncio.to_thread(_d)
            emit("SYNC_DONE", worker="discoverSources", result=res)
        except Exception:
            pass
        await asyncio.sleep(interval)


async def _lineups_loop() -> None:  # pragma: no cover - P4 : compositions (clé free)
    from .providers import api_football as af
    if not af.available():
        return  # sans clé gratuite → pas de boucle (MISSING DEPENDENCY, jamais de fake)
    interval = int(os.environ.get("LINEUPS_SECONDS", 45 * 60))
    await asyncio.sleep(90)
    while True:
        try:
            def _l() -> dict:
                from .workers.definitions import run_lineups
                with SF() as s:
                    return run_lineups(s)
            res = await asyncio.to_thread(_l)
            emit("SYNC_DONE", worker="syncLineups", result=res)
        except Exception:
            pass
        await asyncio.sleep(interval)


async def _odds_live_loop() -> None:  # pragma: no cover - P5 : cotes live (clé free)
    from .providers import odds_api as oapi
    if not oapi.available():
        return  # sans clé gratuite → pas de boucle (MISSING DEPENDENCY, jamais de fake)
    interval = int(os.environ.get("ODDS_LIVE_SECONDS", 3 * 3600))
    await asyncio.sleep(60)
    while True:
        try:
            def _o() -> dict:
                from .workers.definitions import run_odds_live
                with SF() as s:
                    return run_odds_live(s)
            res = await asyncio.to_thread(_o)
            emit("SYNC_DONE", worker="syncOddsLive", result=res)
        except Exception:
            pass
        await asyncio.sleep(interval)


@app.on_event("startup")
async def startup() -> None:  # pragma: no cover
    # registre des sources : toujours initialisé (idempotent)
    def _ensure() -> None:
        from .discovery.engine import ensure_sources
        with SF() as s:
            ensure_sources(s)
    await asyncio.to_thread(_ensure)
    if os.environ.get("AUTO_INGEST") == "1":
        asyncio.create_task(_auto_ingest_loop())
        if os.environ.get("AUTO_LIVE", "1") == "1":
            asyncio.create_task(_live_fast_loop())
        if os.environ.get("AUTO_COMPUTE", "1") == "1":
            asyncio.create_task(_auto_compute_loop())
        if os.environ.get("AUTO_DISCOVER", "1") == "1":
            asyncio.create_task(_discover_loop())
        # sources à clé GRATUITE : boucles lancées seulement si la clé est fournie
        asyncio.create_task(_lineups_loop())
        asyncio.create_task(_odds_live_loop())
