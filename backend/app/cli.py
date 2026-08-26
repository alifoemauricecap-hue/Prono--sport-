"""CLI PRONO SPORT — ingestion et diagnostic.

Exemples :
  python -m app.cli init-db
  python -m app.cli ingest-fduk --divs E0 E1 --seasons 2526 2627
  python -m app.cli ingest-espn --leagues eng.1
  python -m app.cli status
"""
from __future__ import annotations

import argparse
import json
import sys

from .config import DATABASE_URL
from .db.base import Base, make_engine, make_session_factory
from .db.models import Competition, Fixture, ProviderHealth, Team
from .ingest.service import run_ingestion
from .providers.registry import get_provider, seed_data_sources


def _session():
    engine = make_engine(DATABASE_URL)
    Base.metadata.create_all(engine)
    return make_session_factory(engine)()


def cmd_init_db(_args) -> int:
    s = _session()
    created = seed_data_sources(s)
    s.commit()
    print(json.dumps({"database": DATABASE_URL, "data_sources_seedés": created}, ensure_ascii=False))
    return 0


def cmd_ingest_fduk(args) -> int:
    from .providers import football_data_uk as fduk
    provider = get_provider("fduk")
    reports = []
    for div in args.divs:
        if div not in fduk.DIVISIONS:
            print(f"⚠️  division inconnue ignorée : {div} (connues : {sorted(fduk.DIVISIONS)})", file=sys.stderr)
            continue
        for season in args.seasons:
            s = _session()
            try:
                payload = provider.fetch(div=div, season=season)
                source_url = provider.url_for(div, season)
                raws = list(provider.parse(payload, div=div, season=season, source_url=source_url))
                rep = run_ingestion(s, provider, raws)
                reports.append({"div": div, "season": season, **rep.as_dict()})
            except Exception as exc:
                reports.append({"div": div, "season": season, "error": f"{type(exc).__name__}: {exc}"})
            finally:
                s.close()
    print(json.dumps(reports, ensure_ascii=False, indent=2))
    return 0


def _dates_range(back: int, ahead: int) -> list[str]:
    from datetime import date, timedelta
    today = date.today()
    return [(today + timedelta(days=d)).strftime("%Y%m%d") for d in range(-back, ahead + 1)]


def cmd_ingest_espn(args) -> int:
    provider = get_provider("espn")
    dates = _dates_range(args.days_back, args.days_ahead)
    reports = []
    for league in args.leagues:
        league_rep = {"league": league, "jours": len(dates), "created": 0, "updated": 0,
                      "skipped": 0, "rejected": 0, "errors": []}
        for d in dates:
            s = _session()
            try:
                payload = provider.fetch(league=league, date=d)
                raws = list(provider.parse(payload, league=league,
                                           source_url=provider.scoreboard_url(league)))
                rep = run_ingestion(s, provider, raws)
                league_rep["created"] += rep.created
                league_rep["updated"] += rep.updated
                league_rep["skipped"] += rep.skipped_unchanged
                league_rep["rejected"] += rep.rejected
                league_rep["errors"] += rep.errors
            except Exception as exc:
                league_rep["errors"].append(f"{d}: {type(exc).__name__}: {exc}")
            finally:
                s.close()
        s = _session(); seed_data_sources(s); s.commit(); s.close()
        reports.append(league_rep)
    print(json.dumps(reports, ensure_ascii=False, indent=2))
    return 0


def cmd_ingest_openligadb(args) -> int:
    provider = get_provider("openligadb")
    reports = []
    for league in args.leagues:
        for year in args.years:
            s = _session()
            try:
                payload = provider.fetch(league=league, year=year)
                raws = list(provider.parse(payload, league=league))
                rep = run_ingestion(s, provider, raws)
                reports.append({"league": league, "year": year, **rep.as_dict()})
            except Exception as exc:
                reports.append({"league": league, "year": year, "error": f"{type(exc).__name__}: {exc}"})
            finally:
                s.close()
    print(json.dumps(reports, ensure_ascii=False, indent=2))
    return 0


def cmd_ingest_tsdb(args) -> int:
    from .providers import thesportsdb as tsdb_mod
    provider = get_provider("tsdb")
    reports = []
    for lid in args.league_ids:
        s = _session()
        try:
            key = tsdb_mod._key()
            url = f"{tsdb_mod.BASE}/{key}/eventsseason.php?id={lid}&s={args.season}" if args.season \
                else f"{tsdb_mod.BASE}/{key}/eventsnextleague.php?id={lid}"
            payload = provider.fetch(league_id=lid, season=args.season)
            raws = list(provider.parse(payload, league_id=lid, source_url=url))
            rep = run_ingestion(s, provider, raws)
            reports.append({"league_id": lid, "season": args.season, **rep.as_dict()})
        except Exception as exc:
            reports.append({"league_id": lid, "error": f"{type(exc).__name__}: {exc}"})
        finally:
            s.close()
    print(json.dumps(reports, ensure_ascii=False, indent=2))
    return 0


def cmd_ingest_tsdb_day(args) -> int:
    """TSDB eventsday : TOUS les matchs mondiaux d'un jour en 1 seule requête (worldwide)."""
    from datetime import date
    from .providers import thesportsdb as tsdb_mod
    provider = get_provider("tsdb")
    day = args.date or date.today().isoformat()
    r = None
    s = _session()
    try:
        payload = provider._get("eventsday.php", {"d": day, "s": "Soccer"})
        events = payload.get("events") or []
        rep = run_ingestion(s, provider, [])  # no-op health init
        created = 0
        from .ingest.service import IngestReport, ingest_one
        from .providers.base import RawFixture, TeamRef
        from datetime import datetime, timezone
        report = IngestReport(provider="tsdb")
        for e in events:
            # Réutilise le parseur d'événements TSDB générique (mêmes champs str*)
            raws = list(provider.parse({"events": [e]}, league_id=str(e.get("idLeague") or "eventsday"),
                                        source_url=f"eventsday {day}"))
            for raw in raws:
                ingest_one(s, raw, report)
        s.commit()
        r = {"day": day, "received": report.received, "created": report.created,
             "rejected": report.rejected, "odds_rows": report.odds_rows, "errors": report.errors}
    except Exception as exc:
        r = {"day": day, "error": f"{type(exc).__name__}: {exc}"}
    finally:
        s.close()
    print(json.dumps(r, ensure_ascii=False, indent=2))
    return 0


def cmd_ingest_fdorg(args) -> int:
    provider = get_provider("fdorg")
    reports = []
    for comp in args.competitions:
        s = _session()
        try:
            payload = provider.fetch(competition=comp, season_year=args.season)
            url = f"https://api.football-data.org/v4/competitions/{comp}/matches"
            raws = list(provider.parse(payload, competition=comp, source_url=url))
            rep = run_ingestion(s, provider, raws)
            reports.append({"competition": comp, **rep.as_dict()})
        except Exception as exc:
            reports.append({"competition": comp, "error": f"{type(exc).__name__}: {exc}"})
        finally:
            s.close()
    print(json.dumps(reports, ensure_ascii=False, indent=2))
    return 0


def cmd_tsdb_logos(args) -> int:
    """Enrichit les logos/stades via TSDB (§57 : logos de sources autorisées uniquement)."""
    from .ingest.resolution import resolve_team
    provider = get_provider("tsdb")
    s = _session()
    updated = 0
    for pair in args.leagues:
        if ":" not in pair:
            print(f"⚠️ format attendu 'Nom de ligue:Pays' — ignoré : {pair}", file=sys.stderr)
            continue
        league_name, area = pair.rsplit(":", 1)
        try:
            payload = provider.fetch_teams(league_name)
            for tref in provider.parse_teams(payload, area=area):
                team, created = resolve_team(s, tref, provider="tsdb")
                updated += 1
            s.commit()
        except Exception as exc:
            print(f"⚠️ {league_name}: {type(exc).__name__}: {exc}", file=sys.stderr)
    print(json.dumps({"logos_teams_traités": updated}, ensure_ascii=False))
    return 0


def cmd_verify(_args) -> int:
    from .ingest.consistency import run_consistency, sweep_stale
    s = _session()
    swept = sweep_stale(s)
    rep = run_consistency(s)
    print(json.dumps({"stale_swept_to_unknown": swept, **rep.as_dict()},
                     ensure_ascii=False, indent=2))
    return 0


def cmd_sweep_stale(_args) -> int:
    """Fixtures restées SCHEDULED après leur kickoff → UNKNOWN (DONNÉE NON VÉRIFIÉE, §1)."""
    from .ingest.consistency import sweep_stale
    s = _session()
    print(json.dumps({"stale_swept_to_unknown": sweep_stale(s)}, ensure_ascii=False))
    return 0


def cmd_espn_media(_args) -> int:
    """§57 : logos RÉELS depuis ESPN (1 appel/ligue) — équipes + ligues, jamais de faux logo."""
    from .ingest.resolution import resolve_team
    from .db.models import Competition
    from .providers.base import TeamRef
    from .providers import espn as espn_mod
    provider = get_provider("espn")
    import httpx
    stats = {"leagues": 0, "teams": 0, "league_logos": 0}
    s = _session()
    for slug, (code, _name, area) in espn_mod.LEAGUES.items():
        try:
            r = httpx.get(f"https://site.api.espn.com/apis/site/v2/sports/soccer/{slug}/teams",
                          params={"limit": "100"}, timeout=25)
            r.raise_for_status()
            payload = r.json()
            lg = (((payload.get("sports") or [{}])[0].get("leagues") or [{}])[0])
            for entry in lg.get("teams") or []:
                t = entry.get("team") or {}
                tlogos = t.get("logos") or []
                ref = TeamRef(name=t.get("displayName") or "?",
                              provider_id=str(t.get("id")) if t.get("id") is not None else None,
                              logo_url=(tlogos[0].get("href") if tlogos else None),
                              country=area)
                resolve_team(s, ref, provider="espn")
                stats["teams"] += 1
            stats["leagues"] += 1
            # logo de la ligue : présent dans le SCOREBOARD (vérifié en direct), pas dans teams
            comp = s.query(Competition).filter_by(code=code).one_or_none()
            if comp is not None and not comp.logo_url:
                sb = provider.fetch(league=slug, limit=1)
                lgl = ((sb.get("leagues") or [{}])[0].get("logos") or [])
                if lgl:
                    comp.logo_url = lgl[0].get("href")
                    stats["league_logos"] += 1
        except Exception as exc:
            print(f"⚠️ {slug}: {type(exc).__name__}", file=sys.stderr)
    s.commit()
    print(json.dumps(stats, ensure_ascii=False, indent=2))
    return 0


def cmd_ingest_fduk_fixtures(_args) -> int:
    """fixtures.csv fduk : prochains matchs toutes divisions + cotes actuelles réelles (M4)."""
    provider = get_provider("fduk")
    s = _session()
    payload = provider.fetch_fixtures_all()
    raws = list(provider.parse_fixtures_csv(payload))
    rep = run_ingestion(s, provider, raws)
    print(json.dumps(rep.as_dict(), ensure_ascii=False, indent=2))
    return 0


def cmd_analytics(_args) -> int:
    """M3 : recalcule Elo + features depuis les fixtures FINISHED réelles (§16, §21)."""
    from .analytics.engine import compute_all
    s = _session()
    rep = compute_all(s)
    print(json.dumps(rep.as_dict(), ensure_ascii=False, indent=2))
    return 0


def cmd_predictions(args) -> int:
    """M4 : entraîne les modèles sur l'historique réel, prédit les prochains matchs,
    qualifie les Value Bets sur cotes réelles (§33-39)."""
    from .ml.engine import predict_upcoming
    s = _session()
    reports = predict_upcoming(s, competition_code=args.competition)
    print(json.dumps([r.as_dict() for r in reports], ensure_ascii=False, indent=2))
    return 0


def cmd_ingest_apifootball(args) -> int:
    """P4 : compositions + blessures via API-Football (clé GRATUITE, ~100 req/jour)."""
    from datetime import date
    from .providers import api_football as af
    if not af.available():
        print(json.dumps({"error": "MISSING DEPENDENCY : API_FOOTBALL_KEY absente "
                                   "(clé gratuite à créer sur api-sports.io)"},
                         ensure_ascii=False, indent=2))
        return 1
    day = args.date or date.today().isoformat()
    p = af.ApiFootballProvider()
    s = _session()
    try:
        payload = p.fetch(day)
        raws = list(p.parse(payload, day, source_url=p.fixtures_url(day)))
        rep = run_ingestion(s, p, raws)
        from .ingest.enrichment import ingest_injuries, ingest_lineups
        lineups = p.fetch_lineups(day)
        players = ingest_lineups(s, "apifootball", lineups)
        injuries = p.fetch_injuries(day)
        n_inj = ingest_injuries(s, "apifootball", injuries)
        from .ingest.consistency import run_consistency
        run_consistency(s)
        print(json.dumps({"day": day, **rep.as_dict(),
                          "lineup_players": players, "injuries": n_inj},
                         ensure_ascii=False, indent=2))
    except Exception as exc:
        print(json.dumps({"day": day, "error": f"{type(exc).__name__}: {exc}"},
                         ensure_ascii=False, indent=2))
    finally:
        s.close()
    return 0


def cmd_ingest_oddsapi(_args) -> int:
    """P5 : cotes live multi-bookmakers via The Odds API (clé GRATUITE)."""
    from .providers import odds_api as oapi
    if not oapi.available():
        print(json.dumps({"error": "MISSING DEPENDENCY : ODDS_API_KEY absente "
                                   "(clé gratuite à créer sur the-odds-api.com)"},
                         ensure_ascii=False, indent=2))
        return 1
    p = oapi.OddsApiProvider()
    s = _session()
    try:
        events = p.fetch()
        from .ingest.service import attach_odds_to_fixture
        matched = unmatched = new_snaps = 0
        for ev in events:
            home, away, kickoff, odds = p.parse_odds(ev)
            if not odds:
                continue
            fx = p.match_fixture(s, home, away, kickoff)
            if fx is None:
                unmatched += 1
                continue
            matched += 1
            new_snaps += attach_odds_to_fixture(s, fx, odds, "oddsapi")
        s.commit()
        print(json.dumps({"events": len(events), "matched": matched,
                          "unmatched": unmatched, "new_snapshots": new_snaps},
                         ensure_ascii=False, indent=2))
    except Exception as exc:
        print(json.dumps({"error": f"{type(exc).__name__}: {exc}"}, ensure_ascii=False, indent=2))
    finally:
        s.close()
    return 0


def cmd_backtest(args) -> int:
    """§35/§36 : backtest walk-forward (Brier/LogLoss, modèle vs marché)."""
    from .ml.backtest import run_backtest
    s = _session()
    rep = run_backtest(s, min_history=args.min_history)
    print(json.dumps(rep, ensure_ascii=False, indent=2))
    return 0


def cmd_status(_args) -> int:
    s = _session()
    n_fixtures = s.query(Fixture).count()
    n_teams = s.query(Team).count()
    n_comps = s.query(Competition).count()
    health = [
        {"provider": h.provider, "status": h.status, "latency_ms": h.latency_ms,
         "detail": h.detail, "checked_at": str(h.checked_at)}
        for h in s.query(ProviderHealth).all()
    ]
    rows = s.query(Fixture).order_by(Fixture.kickoff_utc.desc()).limit(5).all()
    out = {
        "database": DATABASE_URL,
        "fixtures": n_fixtures,
        "teams": n_teams,
        "competitions": n_comps,
        "provider_health": health,
        "derniers_matchs": [
            {"id": f.id, "kickoff": str(f.kickoff_utc), "status": f.status,
             "home_id": f.home_team_id, "away_id": f.away_team_id,
             "score": f"{f.home_score}-{f.away_score}" if f.status == "FINISHED" else None,
             "provider": f.source_provider, "data_status": f.data_status}
            for f in rows
        ],
    }
    print(json.dumps(out, ensure_ascii=False, indent=2))
    return 0


def main() -> int:
    p = argparse.ArgumentParser(prog="prono-sport")
    sub = p.add_subparsers(required=True)

    sp = sub.add_parser("init-db"); sp.set_defaults(fn=cmd_init_db)

    sp = sub.add_parser("ingest-fduk")
    sp.add_argument("--divs", nargs="+", required=True, help="ex. E0 E1 D1 SP1")
    sp.add_argument("--seasons", nargs="+", required=True, help="ex. 2526 2627")
    sp.set_defaults(fn=cmd_ingest_fduk)

    sp = sub.add_parser("ingest-espn")
    sp.add_argument("--leagues", nargs="+", required=True, help="ex. eng.1 esp.1 uefa.champions")
    sp.add_argument("--days-back", type=int, default=0)
    sp.add_argument("--days-ahead", type=int, default=0)
    sp.set_defaults(fn=cmd_ingest_espn)

    sp = sub.add_parser("ingest-openligadb")
    sp.add_argument("--leagues", nargs="+", required=True, help="ex. bl1 bl2 bl3")
    sp.add_argument("--years", nargs="+", type=int, required=True, help="année de début, ex. 2026")
    sp.set_defaults(fn=cmd_ingest_openligadb)

    sp = sub.add_parser("ingest-tsdb")
    sp.add_argument("--league-ids", nargs="+", required=True, help="ex. 4328 (EPL)")
    sp.add_argument("--season", default=None, help="ex. 2025-2026 ; vide = prochains matchs")
    sp.set_defaults(fn=cmd_ingest_tsdb)

    sp = sub.add_parser("ingest-tsdb-day", help="tous les matchs mondiaux d'un jour (eventsday)")
    sp.add_argument("--date", default=None, help="YYYY-MM-DD, défaut : aujourd'hui")
    sp.set_defaults(fn=cmd_ingest_tsdb_day)

    sp = sub.add_parser("ingest-fdorg")
    sp.add_argument("--competitions", nargs="+", required=True, help="ex. PL ELC PD BL1 SA FL1 CL")
    sp.add_argument("--season", type=int, default=None, help="année de début ex. 2026")
    sp.set_defaults(fn=cmd_ingest_fdorg)

    sp = sub.add_parser("tsdb-logos")
    sp.add_argument("--leagues", nargs="+", required=True,
                    help="paires 'Nom de ligue:Pays', ex. 'English Premier League:Angleterre'")
    sp.set_defaults(fn=cmd_tsdb_logos)

    sp = sub.add_parser("sweep-stale", help="fixtures SCHEDULED périmées → UNKNOWN (§1 fraîcheur)")
    sp.set_defaults(fn=cmd_sweep_stale)

    sp = sub.add_parser("verify", help="vérification croisée inter-sources (§4)")
    sp.set_defaults(fn=cmd_verify)

    sp = sub.add_parser("espn-media", help="logos réels équipes + ligues (ESPN, 1 appel/ligue)")
    sp.set_defaults(fn=cmd_espn_media)

    sp = sub.add_parser("ingest-fduk-fixtures", help="prochains matchs + cotes actuelles (fduk fixtures.csv)")
    sp.set_defaults(fn=cmd_ingest_fduk_fixtures)

    sp = sub.add_parser("compute-analytics", help="M3 : Elo + features depuis l'historique réel")
    sp.set_defaults(fn=cmd_analytics)

    sp = sub.add_parser("compute-predictions", help="M4 : Poisson/Dixon-Coles/Elo + Value Bets")
    sp.add_argument("--competition", default=None)
    sp.set_defaults(fn=cmd_predictions)

    sp = sub.add_parser("ingest-apifootball",
                        help="P4 : compositions + blessures (API-Football, clé gratuite)")
    sp.add_argument("--date", default=None, help="YYYY-MM-DD, défaut : aujourd'hui")
    sp.set_defaults(fn=cmd_ingest_apifootball)

    sp = sub.add_parser("ingest-oddsapi",
                        help="P5 : cotes live multi-bookmakers (The Odds API, clé gratuite)")
    sp.set_defaults(fn=cmd_ingest_oddsapi)

    sp = sub.add_parser("backtest", help="§35/§36 : backtest walk-forward + calibration")
    sp.add_argument("--min-history", type=int, default=30)
    sp.set_defaults(fn=cmd_backtest)

    sp = sub.add_parser("status"); sp.set_defaults(fn=cmd_status)

    args = p.parse_args()
    return args.fn(args)


if __name__ == "__main__":
    raise SystemExit(main())
