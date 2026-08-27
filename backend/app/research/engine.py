"""EXPERT MATCH REPORT (§46) — recherche approfondie multi-sources, 100 % gratuit.

Chaque section porte un statut explicite :
    SOURCE    → donnée réelle d'une source (provenance citée)
    CALCULE   → calcul de PRONO SPORT sur données réelles
    MODELE    → estimation du modèle (probabilités, jamais une certitude)
    UNAVAILABLE → « DONNÉE INDISPONIBLE » — jamais de valeur inventée (§1/§96)

Le rapport est horodaté, sourcé, persisté (analysis_reports) et régénéré si périmé.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

from sqlalchemy.orm import Session

from ..db.models import (
    AnalysisReport, Bookmaker, Competition, Fixture, Injury, Lineup, Market,
    OddsSnapshot, Prediction, Season, Suspension, Team, TeamAnalytics, TeamStat,
    ValueBet, WeatherSnapshot,
)
from ..analytics.h2h import head_to_head
from ..analytics.odds_trend import odds_trends
from ..analytics.weather import forecast_at
from ..ml.odds_math import best_odds_per_selection
from . import wikipedia

REPORT_TTL_HOURS = 6
UNAV = "DONNÉE INDISPONIBLE"


def _iso(dt: datetime | None) -> str | None:
    return dt.isoformat() if dt else None


def _as_utc(dt: datetime | None) -> datetime | None:
    """Normalise en UTC aware (SQLite rend des datetimes naive)."""
    if dt is None:
        return None
    return dt.replace(tzinfo=timezone.utc) if dt.tzinfo is None else dt


def _sec(label: str, status: str, content, source: str | None = None,
         note: str | None = None) -> dict:
    return {"label": label, "status": status, "content": content,
            "source": source, "note": note}


def _unavailable(label: str, note: str | None = None) -> dict:
    return _sec(label, "UNAVAILABLE", UNAV, source=None, note=note)


def _fatigue(session: Session, team_id: int, before: datetime) -> dict | None:
    """Fatigue CALCULÉE sur l'historique réel en base (jours de repos, matchs récents)."""
    past = (session.query(Fixture)
            .filter(Fixture.status == "FINISHED",
                    (Fixture.home_team_id == team_id) | (Fixture.away_team_id == team_id),
                    Fixture.kickoff_utc < before)
            .order_by(Fixture.kickoff_utc.desc()).all())
    if not past:
        return None
    last = past[0]
    days_rest = (before - last.kickoff_utc).total_seconds() / 86400
    matches_7d = sum(1 for f in past[:15]
                     if (before - f.kickoff_utc).total_seconds() <= 7 * 86400)
    return {"days_rest": round(days_rest, 1), "matches_last_7d": matches_7d,
            "last_match": _iso(last.kickoff_utc)}


def _history_depth(session: Session, competition_id: int) -> dict | None:
    """Profondeur d'historique RÉELLEMENT stockée en base (jamais supposée)."""
    seasons = (session.query(Season)
               .filter(Season.competition_id == competition_id).all())
    if not seasons:
        return None
    ys = [min(x.start_year, x.end_year) for x in seasons]
    ye = [max(x.start_year, x.end_year) for x in seasons]
    return {"from": min(ys), "to": max(ye), "seasons": len(seasons)}


def build_expert_report(session: Session, fixture_id: int, refresh: bool = False) -> dict:
    fx = session.get(Fixture, fixture_id)
    if fx is None:
        raise ValueError(f"match inconnu: {fixture_id}")
    home, away = session.get(Team, fx.home_team_id), session.get(Team, fx.away_team_id)
    comp = session.get(Competition, fx.competition_id)
    now = datetime.now(timezone.utc)
    season = session.get(Season, fx.season_id) if fx.season_id else None

    if not refresh:
        cached = (session.query(AnalysisReport)
                  .filter_by(fixture_id=fixture_id).one_or_none())
        if cached and _as_utc(cached.generated_at) is not None and \
                (now - _as_utc(cached.generated_at)) < timedelta(hours=REPORT_TTL_HOURS):
            return {"fixture_id": fixture_id, "sections": cached.sections,
                    "sources_used": cached.sources_used,
                    "data_quality_score": cached.data_quality_score,
                    "model_version": cached.model_version,
                    "cached": True, "generated_at": _iso(cached.generated_at)}

    h_name, a_name = home.name if home else "?", away.name if away else "?"
    comp_name = comp.name if comp else "?"
    season_label = season.label if season else None

    sources_used: set[str] = set()
    sections: list[dict] = []

    # 1. CONTEXTE — recherche en ligne réelle (Wikipedia) + données du match
    ctx = wikipedia.context_for_competition(comp_name, season_label)
    context_ok = bool(ctx)
    if ctx:
        sources_used.add(ctx["source"])
        sections.append(_sec("Contexte", "SOURCE",
                             {"competition": comp_name, "season": season_label,
                              "zone": comp.area if comp else None,
                              "contexte_recherche": ctx["extract"],
                              "article": ctx["url"], "license": ctx["license"]},
                             source=ctx["source"]))
    else:
        sections.append(_sec("Contexte", "SOURCE",
                             {"competition": comp_name, "season": season_label,
                              "zone": comp.area if comp else None,
                              "contexte_recherche": UNAV},
                             note="Aucun article trouvé — pas de contexte inventé."))

    # 2. FORME — CALCULÉ sur historique réel
    def form_of(tid: int):
        a = session.query(TeamAnalytics).filter_by(team_id=tid).one_or_none()
        if not a or not a.matches_rated:
            return None
        return {"elo": round(a.elo, 1) if a.elo else None,
                "matches": a.matches_rated, "form5": a.form5, "points5": a.points5}
    fh, fa = form_of(fx.home_team_id), form_of(fx.away_team_id)
    sections.append(_sec("Forme", "CALCULE",
                         {"home": fh or UNAV, "away": fa or UNAV,
                          "methode": "Elo interne + forme 5 derniers matchs (historique réel en base)"},
                         source="PRONO SPORT (calcul)"))

    # 3. HISTORIQUE — profondeur réelle + H2H réel
    depth = _history_depth(session, fx.competition_id)
    h2h = head_to_head(session, fx.home_team_id, fx.away_team_id)
    sources_used.add("Base PRONO SPORT (historique réel agrégé)")
    sections.append(_sec("Historique", "SOURCE",
                         {"profondeur": depth or UNAV,
                          "h2h": ({"count": h2h["count"], "tally": h2h["tally"],
                                   "meetings": h2h["meetings"][:5]}
                                  if h2h["count"] else UNAV)},
                         source="Base PRONO SPORT (matchs réels)"))

    # 4. STATISTIQUES DU MATCH — SOURCE si TeamStat en base
    stats = session.query(TeamStat).filter(TeamStat.fixture_id == fixture_id).all()
    if stats:
        by_team: dict[int, dict] = {}
        for st in stats:
            by_team[st.team_id] = {"possession": st.possession, "tirs": st.shots,
                                   "tirs_cadres": st.shots_on_target, "corners": st.corners,
                                   "fautes": st.fouls, "cartons": st.yellow_cards}
        sections.append(_sec("Statistiques", "SOURCE",
                             {"home": by_team.get(fx.home_team_id, UNAV),
                              "away": by_team.get(fx.away_team_id, UNAV)},
                             source="; ".join({st.source for st in stats if st.source}) or None))
    else:
        sections.append(_unavailable("Statistiques",
                                     "Aucune statistique de match fournie par une source active."))

    # 5-6. ATTAQUE / DÉFENSE — CALCULÉ
    def att_def(tid: int):
        a = session.query(TeamAnalytics).filter_by(team_id=tid).one_or_none()
        if not a or a.gf5 is None:
            return None
        return {"buts_marques": a.gf5, "buts_encaisses": a.ga5}
    ah, aa = att_def(fx.home_team_id), att_def(fx.away_team_id)
    sections.append(_sec("Attaque", "CALCULE",
                         {"home": ah or UNAV, "away": aa or UNAV},
                         source="PRONO SPORT (calcul sur historique réel)"))
    sections.append(_sec("Défense", "CALCULE",
                         {"home": (ah or {}).get("buts_encaisses", UNAV),
                          "away": (aa or {}).get("buts_encaisses", UNAV),
                          "note": "Buts encaissés / match sur les 5 derniers matchs réels."},
                         source="PRONO SPORT (calcul sur historique réel)"))

    # 7. xG — SOURCE (fduk) seulement
    if fx.home_xg is not None and fx.away_xg is not None:
        sources_used.add("football-data.co.uk (xG)")
        sections.append(_sec("xG", "SOURCE", {"home": fx.home_xg, "away": fx.away_xg},
                             source="football-data.co.uk",
                             note="xG réel fourni par la source (post-match)."))
    else:
        sections.append(_unavailable("xG", "xG non disponible pour ce match/cette compétition."))

    # 8. ABSENCES — jamais inventées
    n_inj, n_sus = session.query(Injury).count(), session.query(Suspension).count()
    if n_inj or n_sus:
        sections.append(_sec("Absences", "SOURCE",
                             {"blessures": n_inj, "suspensions": n_sus},
                             source="Base PRONO SPORT"))
    else:
        sections.append(_unavailable("Absences",
                                     "Aucune source gratuite fiable d'absences active — rien n'est inventé."))

    # 9. COMPOSITIONS — jamais inventées
    n_lines = session.query(Lineup).filter(Lineup.fixture_id == fixture_id).count()
    if n_lines:
        sections.append(_sec("Compositions", "SOURCE", {"effectifs": n_lines},
                             source="Base PRONO SPORT"))
    else:
        sections.append(_unavailable("Compositions",
                                     "Compositions officielles non fournies par les sources actives."))

    # 10. TACTIQUE — seulement si les données d'événements existent
    sections.append(_unavailable("Tactique",
                                 "Nécessite des données d'événements non disponibles pour ce match — pas de spéculation."))

    # 11. ENTRAÎNEURS
    sections.append(_unavailable("Entraîneurs", "Aucune source d'entraîneurs active."))

    # 12. FATIGUE — CALCULÉ
    fh_f, fa_f = _fatigue(session, fx.home_team_id, fx.kickoff_utc), \
        _fatigue(session, fx.away_team_id, fx.kickoff_utc)
    sections.append(_sec("Fatigue", "CALCULE",
                         {"home": fh_f or UNAV, "away": fa_f or UNAV,
                          "methode": "Jours de repos + matchs des 7 derniers jours (réel)"},
                         source="PRONO SPORT (calcul)"))

    # 13. ARBITRE — SOURCE
    if fx.referee:
        sources_used.add("football-data.co.uk (arbitre)")
        sections.append(_sec("Arbitre", "SOURCE", fx.referee, source="football-data.co.uk"))
    else:
        sections.append(_unavailable("Arbitre"))

    # 14. MÉTÉO — SOURCE (Open-Meteo)
    weather = None
    if fx.venue_city:
        ws = (session.query(WeatherSnapshot)
              .filter(WeatherSnapshot.city == fx.venue_city)
              .order_by(WeatherSnapshot.at.desc()).first())
        if ws:
            weather = {"ville": ws.city, "at": _iso(ws.at), "temperature": ws.temperature,
                       "precipitation": ws.precipitation, "vent": ws.wind_speed,
                       "humidite": ws.humidity, "condition": ws.condition, "source": ws.source}
        else:
            weather = forecast_at(fx.venue_city, fx.kickoff_utc)
        if weather:
            sources_used.add("Open-Meteo")
    sections.append(_sec("Météo", "SOURCE", weather or UNAV,
                         source="Open-Meteo" if weather else None))

    # 15. MARCHÉ — cotes réelles multi-bookmakers
    sn = (session.query(OddsSnapshot, Bookmaker, Market)
          .join(Bookmaker, OddsSnapshot.bookmaker_id == Bookmaker.id)
          .join(Market, OddsSnapshot.market_id == Market.id)
          .filter(OddsSnapshot.fixture_id == fixture_id,
                  OddsSnapshot.status == "ACTIVE").all())
    if sn:
        by_mkt: dict[str, dict[str, dict[str, float]]] = {}
        for snap, bm, mk in sn:
            by_mkt.setdefault(mk.code, {}).setdefault(bm.code, {})[snap.selection] = snap.odds
        market_now = {}
        for mk_code, bks in by_mkt.items():
            best = best_odds_per_selection(bks)
            market_now[mk_code] = {
                "best": {sel: {"bookmaker": b, "odds": o} for sel, (b, o) in best.items()},
                "n_bookmakers": len(bks),
            }
        sources_used.add("Cotes réelles agrégées (football-data.co.uk)")
        sections.append(_sec("Marché", "SOURCE", market_now,
                             source="football-data.co.uk (cotes réelles multi-bookmakers)"))
    else:
        sections.append(_unavailable("Marché", "Aucune cote réelle collectée pour ce match."))

    # 16. ÉVOLUTION DES COTES — SOURCE
    trend = odds_trends(session, [fixture_id]).get(fixture_id)
    sections.append(_sec("Évolution des cotes", "SOURCE",
                         trend if trend else UNAV,
                         source="Snapshots de cotes réelles (base PRONO SPORT)",
                         note=None if trend else "Trop peu de snapshots pour mesurer un mouvement."))

    # 17. PROBABILITÉS — MODÈLE
    pred = (session.query(Prediction)
            .filter(Prediction.fixture_id == fixture_id)
            .order_by(Prediction.created_at.desc()).first())
    if pred:
        sections.append(_sec("Probabilités", "MODELE",
                             {"probabilities": pred.probabilities,
                              "expected_goals": pred.expected_goals,
                              "model_version": f"ensemble-dc-poisson-elo:{pred.feature_version}"},
                             source="Modèle PRONO SPORT (Poisson + Dixon-Coles + Elo)",
                             note="Estimation du modèle — probabilité ≠ certitude."))
    else:
        sections.append(_unavailable("Probabilités",
                                     "Historique insuffisant — aucune prédiction, jamais de fiction."))

    # 18. VALUE BETS — MODÈLE
    vbs = session.query(ValueBet).filter_by(fixture_id=fixture_id).all()
    sections.append(_sec("Value Bets", "MODELE",
                         ([{"market": v.market, "selection": v.selection,
                            "odds": v.odds_reference, "edge_pts": round(v.edge * 100, 1),
                            "ev_pct": round(v.ev * 100, 1), "level": v.level,
                            "bookmaker": v.bookmaker_ref} for v in vbs]
                          or "NO QUALIFIED PICK — aucune opportunité ne respecte les critères "
                             "(pas de pick forcé, §41)"),
                         source="Moteur Value Bet PRONO SPORT"))

    # 19. RISQUES — CALCULÉ
    risks: list[str] = []
    if pred and pred.input_snapshot.get("model_disagreement_1x2H"):
        risks.append(f"Désaccord des modèles sur la victoire domicile : "
                     f"{round(pred.input_snapshot['model_disagreement_1x2H'] * 100)} pts")
    if weather and isinstance(weather.get("precipitation"), (int, float)) and weather["precipitation"] > 2:
        risks.append(f"Précipitation prévue : {weather['precipitation']} mm")
    if fx.data_status == "CONTRADICTORY":
        risks.append("DONNÉES CONTRADICTOIRES entre sources — fiabilité du score réduite")
    for f_f, nm in ((fh_f, h_name), (fa_f, a_name)):
        if f_f and f_f["days_rest"] < 3:
            risks.append(f"{nm} : repos court ({f_f['days_rest']} j)")
    if not pred:
        risks.append("Aucun modèle entraîné sur ce périmètre — incertitude élevée")
    sections.append(_sec("Risques", "CALCULE",
                         risks or ["Aucun risque majeur identifié sur les données disponibles."],
                         source="PRONO SPORT (analyse des données disponibles)"))

    # 20. CONCLUSION — MODÈLE (synthèse honnête, jamais une promesse)
    if pred:
        p1x2 = pred.probabilities.get("1X2", {})
        best_sel = max(p1x2, key=p1x2.get) if p1x2 else None
        names = {"H": h_name, "D": "Nul", "A": a_name}
        concl = (f"Le modèle privilégie : {names.get(best_sel, best_sel)} "
                 f"({round(p1x2.get(best_sel, 0) * 100)} %). "
                 "C'est une estimation probabiliste, jamais une certitude. "
                 "Le pick final (s'il existe) est issu du moteur Value Bet sur cotes réelles.")
    else:
        concl = ("INSUFFICIENT DATA — historique insuffisant pour une prédiction fiable. "
                 "PRONO SPORT préfère l'abstention à la fiction.")
    sections.append(_sec("Conclusion", "MODELE", concl,
                         source="Synthèse PRONO SPORT (modèle + marché)"))

    n_filled = sum(1 for x in sections if x["status"] != "UNAVAILABLE")
    quality = round(100 * n_filled / len(sections))

    # On ne persiste pas un rapport dont le contexte web est indisponible (réseau coupé) :
    # il sera régénéré à la requête suivante (quand le réseau est de retour).
    cacheable = context_ok
    existing = session.query(AnalysisReport).filter_by(fixture_id=fixture_id).one_or_none()
    if not cacheable:
        if existing is not None:
            session.delete(existing)
        session.commit()
    else:
        if existing:
            existing.sections = sections
            existing.sources_used = sorted(sources_used)
            existing.data_quality_score = quality
            existing.model_version = "ensemble-dc-poisson-elo:v1" if pred else None
            existing.generated_at = now
        else:
            session.add(AnalysisReport(
                fixture_id=fixture_id, sections=sections, sources_used=sorted(sources_used),
                data_quality_score=quality,
                model_version="ensemble-dc-poisson-elo:v1" if pred else None,
                generated_at=now))
        session.commit()

    return {"fixture_id": fixture_id, "sections": sections,
            "sources_used": sorted(sources_used),
            "data_quality_score": quality,
            "model_version": "ensemble-dc-poisson-elo:v1" if pred else None,
            "cached": False, "generated_at": _iso(now)}


def report_freshness(generated_at_iso: str | None) -> str:
    if not generated_at_iso:
        return "UNKNOWN"
    try:
        dt = datetime.fromisoformat(generated_at_iso)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        age_h = (datetime.now(timezone.utc) - dt).total_seconds() / 3600
        return "FRESH" if age_h < REPORT_TTL_HOURS else "STALE"
    except ValueError:
        return "UNKNOWN"
