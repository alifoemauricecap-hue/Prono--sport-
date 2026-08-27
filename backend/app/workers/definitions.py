"""Définitions des workers — synchronisation continue (§9, §14, §15).

Chaque worker est une fonction `(session) -> dict` :
- idempotente (ré-exécuter = même état)
- journalisée dans sync_jobs (via log_job)
- tolérante aux erreurs (retourne un rapport, ne lève pas)

Priorité de collecte (§10) :
  P1 live → P2 fixtures proches → P3 résultats → P4 compositions → P5 cotes →
  P6 météo/contexte → P7 historique → P8 découverte de sources.
"""
from __future__ import annotations

import time
from datetime import datetime, timedelta, timezone

from sqlalchemy.orm import Session

from ..db.models import Fixture, WeatherSnapshot
from ..ingest.consistency import run_consistency, sweep_stale
from ..ingest.service import run_ingestion
from ..providers.registry import get_provider
from ..discovery.engine import log_job, run_discovery as _disc

WORKERS: dict[str, str] = {
    "syncLiveMatches": "P1 — matchs en direct (75 s)",
    "syncFixtures": "P2 — nouveaux/changements de matchs (5 min)",
    "syncResults": "P3 — résultats + cotes closing (5 min)",
    "syncWorldDaily": "P2b — backbone MONDIAL : tous les matchs du jour (TSDB eventsday, 1 h)",
    "syncLineups": "P4 — compositions + blessures (API-Football free, 45 min)",
    "syncOdds": "P5 — cotes actuelles fduk fixtures.csv (15 min)",
    "syncOddsLive": "P5 — cotes live multi-books (The Odds API free, 3 h)",
    "syncWeather": "P6 — météo stades (1 h)",
    "syncHistorical": "P7 — historiques fduk (quotidien)",
    "discoverSources": "P8 — découverte/contrôle des sources (hebdo)",
}


def _leagues(session: Session | None = None):
    from ..providers import espn as espn_mod
    import os
    return os.environ.get("AUTO_INGEST_LEAGUES", " ".join(espn_mod.AUTO_WATCH_LEAGUES)).split()


def _espn_payloads(session: Session, days: list[int]):
    """Yield (raws, provider, url) pour les ligues surveillées, par jour."""
    provider = get_provider("espn")
    for league in _leagues(session):
        for d in days:
            day = (datetime.now(timezone.utc) + timedelta(days=d)).strftime("%Y%m%d")
            try:
                payload = provider.fetch(league=league, date=day)
            except Exception:
                continue
            raws = list(provider.parse(payload, league=league,
                                       source_url=provider.scoreboard_url(league)))
            yield league, raws


def run_live(session: Session) -> dict:
    """P1 — syncLiveMatches : rafraîchit SEULEMENT les ligues avec match en cours.
    Sans match live → 0 requête (économie, 0 €)."""
    t0 = time.perf_counter()
    live_comps = {fx.competition_id for fx in session.query(Fixture).filter(
        Fixture.status.in_(["LIVE", "HALFTIME", "EXTRA_TIME", "PENALTIES"])).all()}
    if not live_comps:
        log_job(session, "syncLiveMatches", "espn", "OK",
                records=0, latency_ms=0, started_at=datetime.now(timezone.utc))
        return {"worker": "syncLiveMatches", "live_comps": 0, "created": 0, "updated": 0}
    from ..db.models import EntityMapping
    slugs = [m.provider_id for m in session.query(EntityMapping).filter(
        EntityMapping.entity_type == "competition",
        EntityMapping.provider == "espn").all() if m.entity_id in live_comps]
    provider = get_provider("espn")
    day = datetime.now(timezone.utc).strftime("%Y%m%d")
    created = updated = 0
    for slug in slugs:
        try:
            payload = provider.fetch(league=slug, date=day)
            raws = list(provider.parse(payload, league=slug,
                                       source_url=provider.scoreboard_url(slug)))
        except Exception:
            continue
        rep = run_ingestion(session, provider, raws)
        created += rep.created
        updated += rep.updated
    run_consistency(session)
    latency = round((time.perf_counter() - t0) * 1000)
    log_job(session, "syncLiveMatches", "espn", "OK",
            records=created + updated, created=created, updated=updated,
            latency_ms=latency)
    return {"worker": "syncLiveMatches", "live_comps": len(live_comps),
            "created": created, "updated": updated}


def run_fixtures(session: Session) -> dict:
    """P2 — syncFixtures : ESPN hier/aujourd'hui/demain + fduk fixtures.csv (cotes).
    Idempotent : upsert par (provider, event_id)."""
    t0 = time.perf_counter()
    created = updated = rejected = 0
    for _league, raws in _espn_payloads(session, days=[-1, 0, 1]):
        rep = run_ingestion(session, get_provider("espn"), raws)
        created += rep.created
        updated += rep.updated
        rejected += rep.rejected
    # cotes réelles + prochains matchs (fduk) — ajoute les marchés 1X2/OU
    try:
        p = get_provider("fduk")
        payload = p.fetch_fixtures_all()
        fraws = list(p.parse_fixtures_csv(payload))
        frep = run_ingestion(session, p, fraws)
        created += frep.created
        updated += frep.updated
        rejected += frep.rejected
    except Exception:
        pass
    sweep_stale(session)
    run_consistency(session)
    latency = round((time.perf_counter() - t0) * 1000)
    log_job(session, "syncFixtures", "espn+fduk", "OK",
            records=created + updated, created=created, updated=updated,
            rejected=rejected, latency_ms=latency)
    return {"worker": "syncFixtures", "created": created, "updated": updated,
            "rejected": rejected}


def run_world_daily(session: Session) -> dict:
    """P2b — syncWorldDaily : backbone MONDIAL (TheSportsDB eventsday).

    2 requêtes (aujourd'hui + hier) = TOUS les matchs du monde de ces jours,
    toutes ligues confondues — y compris celles hors catalogue ESPN (Afrique,
    Moyen-Orient, divisions lointaines). Idempotent, journalisé, tolérant aux
    erreurs (§64). C'est lui qui garantit « toutes les ligues du monde » à 0 €.
    """
    from datetime import date, timedelta
    from ..ingest.service import IngestReport, ingest_one
    t0 = time.perf_counter()
    provider = get_provider("tsdb")
    created = updated = rejected = 0
    days_hit: list[str] = []
    for i in (0, 1):  # aujourd'hui + hier
        day = (date.today() - timedelta(days=i)).isoformat()
        try:
            payload = provider._get("eventsday.php", {"d": day, "s": "Soccer"})
            events = payload.get("events") or []
            report = IngestReport(provider="tsdb")
            for e in events:
                raws = list(provider.parse(
                    {"events": [e]},
                    league_id=str(e.get("idLeague") or "eventsday"),
                    source_url=f"eventsday {day}"))
                for raw in raws:
                    ingest_one(session, raw, report)
            created += report.created
            updated += report.updated
            rejected += report.rejected
            days_hit.append(f"{day}:{report.received}")
        except Exception:
            continue  # un jour en échec ne bloque pas l'autre (§64)
    run_consistency(session)
    latency = round((time.perf_counter() - t0) * 1000)
    status = "OK" if days_hit else "DEGRADED"
    log_job(session, "syncWorldDaily", "tsdb", status,
            records=created + updated, created=created, updated=updated,
            rejected=rejected, latency_ms=latency,
            errors=None if days_hit else ["aucun jour récupéré (réseau ou source)"])
    return {"worker": "syncWorldDaily", "created": created, "updated": updated,
            "rejected": rejected, "days": days_hit}


def run_results(session: Session) -> dict:
    """P3 — syncResults : rafraîchit les statuts des matchs joués (ESPN) +
    cotes closing (fduk). Déclenche le passage FINISHED + résolution des pronos."""
    t0 = time.perf_counter()
    created = updated = 0
    for _league, raws in _espn_payloads(session, days=[-1, 0]):
        rep = run_ingestion(session, get_provider("espn"), raws)
        created += rep.created
        updated += rep.updated
    try:
        p = get_provider("fduk")
        payload = p.fetch_fixtures_all()
        fraws = list(p.parse_fixtures_csv(payload))
        frep = run_ingestion(session, p, fraws)
        created += frep.created
        updated += frep.updated
    except Exception:
        pass
    run_consistency(session)
    latency = round((time.perf_counter() - t0) * 1000)
    log_job(session, "syncResults", "espn+fduk", "OK",
            records=created + updated, created=created, updated=updated,
            latency_ms=latency)
    return {"worker": "syncResults", "created": created, "updated": updated}


def run_lineups(session: Session) -> dict:
    """P4 — syncLineups : compositions officielles + blessures via API-Football
    (clé GRATUITE). Sans clé → MISSING DEPENDENCY, jamais de simulation (§95)."""
    t0 = time.perf_counter()
    from ..providers import api_football as af
    if not af.available():
        log_job(session, "syncLineups", "apifootball", "SKIPPED",
                errors=["MISSING DEPENDENCY : API_FOOTBALL_KEY absente (clé gratuite)"])
        return {"worker": "syncLineups", "skipped": True,
                "reason": "MISSING DEPENDENCY — clé API_FOOTBALL_KEY absente (gratuite)"}
    p = af.ApiFootballProvider()
    day = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    try:
        payload = p.fetch(day)
        raws = list(p.parse(payload, day, source_url=p.fixtures_url(day)))
        rep = run_ingestion(session, p, raws)
        from ..ingest.enrichment import ingest_injuries, ingest_lineups
        lineups = p.fetch_lineups(day)
        players_written = ingest_lineups(session, "apifootball", lineups)
        injuries = p.fetch_injuries(day)
        injuries_written = ingest_injuries(session, "apifootball", injuries)
        run_consistency(session)
        latency = round((time.perf_counter() - t0) * 1000)
        log_job(session, "syncLineups", "apifootball", "OK",
                records=players_written, created=rep.created, updated=rep.updated,
                rejected=rep.rejected, latency_ms=latency)
        return {"worker": "syncLineups", "lineup_players": players_written,
                "injuries": injuries_written, "created": rep.created,
                "updated": rep.updated}
    except Exception as exc:  # tolérance (§66) : rapport, pas de crash
        log_job(session, "syncLineups", "apifootball", "FAILED",
                errors=[f"{type(exc).__name__}: {exc}"])
        return {"worker": "syncLineups", "error": f"{type(exc).__name__}: {exc}"}


def run_odds_live(session: Session) -> dict:
    """P5 — syncOddsLive : cotes réelles multi-bookmakers via The Odds API
    (clé GRATUITE). Associe les cotes aux fixtures DÉJÀ en base (noms + kickoff
    ±90 min) — jamais de match inventé. Sans clé → MISSING DEPENDENCY."""
    t0 = time.perf_counter()
    from ..providers import odds_api as oapi
    if not oapi.available():
        log_job(session, "syncOddsLive", "oddsapi", "SKIPPED",
                errors=["MISSING DEPENDENCY : ODDS_API_KEY absente (clé gratuite)"])
        return {"worker": "syncOddsLive", "skipped": True,
                "reason": "MISSING DEPENDENCY — clé ODDS_API_KEY absente (gratuite)"}
    p = oapi.OddsApiProvider()
    try:
        events = p.fetch()
        from ..ingest.service import attach_odds_to_fixture
        matched = unmatched = new_snaps = 0
        for ev in events:
            home, away, kickoff, odds = p.parse_odds(ev)
            if not odds:
                continue
            fx = p.match_fixture(session, home, away, kickoff)
            if fx is None:
                unmatched += 1
                continue
            matched += 1
            new_snaps += attach_odds_to_fixture(session, fx, odds, "oddsapi")
        session.commit()
        latency = round((time.perf_counter() - t0) * 1000)
        log_job(session, "syncOddsLive", "oddsapi", "OK",
                records=new_snaps, latency_ms=latency)
        return {"worker": "syncOddsLive", "events": len(events),
                "matched": matched, "unmatched": unmatched,
                "new_snapshots": new_snaps}
    except Exception as exc:
        log_job(session, "syncOddsLive", "oddsapi", "FAILED",
                errors=[f"{type(exc).__name__}: {exc}"])
        return {"worker": "syncOddsLive", "error": f"{type(exc).__name__}: {exc}"}


def run_weather(session: Session) -> dict:
    """P6 — syncWeather : météo réelle (Open-Meteo) des stades des matchs du jour,
    horodatée + sourcée. Ville inconnue → pas de ligne (jamais de météo inventée)."""
    t0 = time.perf_counter()
    from ..analytics.weather import forecast_at
    today = datetime.now(timezone.utc).date()
    fx = (session.query(Fixture)
          .filter(Fixture.kickoff_utc != None)  # noqa: E711
          .all())
    done = 0
    seen: set[tuple[str, str]] = set()
    for f in fx:
        if not f.venue_city or not f.kickoff_utc:
            continue
        if f.kickoff_utc.date() != today:
            continue
        key = (f.venue_city, f.kickoff_utc.strftime("%Y-%m-%dT%H"))
        if key in seen:
            continue
        # déjà une ligne météo pour cette ville+heure ? (idempotence)
        exists = (session.query(WeatherSnapshot)
                  .filter(WeatherSnapshot.city == f.venue_city)
                  .filter(WeatherSnapshot.at >= f.kickoff_utc)
                  .first())
        if exists:
            seen.add(key)
            continue
        data = forecast_at(f.venue_city, f.kickoff_utc)
        if not data:
            continue
        seen.add(key)
        session.add(WeatherSnapshot(
            city=f.venue_city, at=f.kickoff_utc,
            temperature=data.get("temperature"),
            precipitation=data.get("precipitation"),
            wind_speed=data.get("wind_speed"),
            humidity=data.get("humidity"),
            condition=data.get("condition"),
            source="open-meteo", fetched_at=datetime.now(timezone.utc),
        ))
        done += 1
    session.commit()
    latency = round((time.perf_counter() - t0) * 1000)
    log_job(session, "syncWeather", "open-meteo", "OK",
            records=done, created=done, latency_ms=latency)
    return {"worker": "syncWeather", "snapshots": done}


def run_historical(session: Session, divs: list[str] | None = None,
                   seasons: list[str] | None = None) -> dict:
    """P7 — syncHistorical : import des historiques fduk (CSV). Lourd : quotidien.
    divs/seasons optionnels ; par défaut la saison en cours, top 5."""
    from ..providers import football_data_uk as fduk
    provider = get_provider("fduk")
    divs = divs or list(fduk.DIVISIONS.keys())[:5]
    if not seasons:
        now = datetime.now(timezone.utc)
        start = now.year if now.month >= 8 else now.year - 1  # saison août→mai
        seasons = [f"{(start % 100):02d}{((start + 1) % 100):02d}"]
    t0 = time.perf_counter()
    created = updated = rejected = 0
    for div in divs:
        for season in seasons:
            try:
                payload = provider.fetch(div=div, season=season)
                raws = list(provider.parse(payload, div=div, season=season,
                                           source_url=provider.url_for(div, season)))
                rep = run_ingestion(session, provider, raws)
                created += rep.created
                updated += rep.updated
                rejected += rep.rejected
            except Exception:
                continue
    run_consistency(session)
    latency = round((time.perf_counter() - t0) * 1000)
    log_job(session, "syncHistorical", "fduk", "OK",
            records=created + updated, created=created, updated=updated,
            rejected=rejected, latency_ms=latency)
    return {"worker": "syncHistorical", "created": created, "updated": updated,
            "rejected": rejected}


def run_discover(session: Session, offline: bool = False) -> dict:
    """P8 — discoverSources : test réel du registre + fiabilité sur l'observé."""
    res = _disc(session, offline=offline)
    log_job(session, "discoverSources", None,
            "OK" if res.get("ok", 0) > 0 else "DEGRADED",
            records=res.get("checked"), latency_ms=res.get("latency_ms"))
    return res
