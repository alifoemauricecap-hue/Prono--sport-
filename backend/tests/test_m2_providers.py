"""Tests M2 : nouveaux providers (openligadb, tsdb, fdorg) + consistency engine."""
from datetime import datetime, timezone

from app.db.models import Fixture
from app.ingest.consistency import run_consistency
from app.ingest.service import IngestReport, ingest_one
from app.providers.base import RawFixture, TeamRef
from app.providers.football_data_org import FootballDataOrgProvider
from app.providers.openligadb import OpenLigaDBProvider
from app.providers.thesportsdb import TheSportsDBProvider

KO = datetime(2025, 8, 15, 19, 0, tzinfo=timezone.utc)


def _draw(provider, pid, comp, comp_name, area, h, a, hs, as_, status="FINISHED"):
    return RawFixture(
        provider=provider, provider_id=pid, provider_competition=comp,
        competition_name=comp_name, competition_area=area,
        season_label="2025-2026", kickoff_utc=KO, kickoff_time_known=True,
        status=status,
        home=TeamRef(name=h[0], provider_id=h[1], country=area),
        away=TeamRef(name=a[0], provider_id=a[1], country=area),
        home_score=hs if status == "FINISHED" else None,
        away_score=as_ if status == "FINISHED" else None,
    )


OLDB_SAMPLE = [{
    "matchID": 77256,
    "matchDateTimeUTC": "2025-08-22T18:30:00Z",
    "matchIsFinished": True,
    "leagueName": "1. Fußball-Bundesliga 2025/2026",
    "team1": {"teamId": 40, "teamName": "FC Bayern München", "teamIconUrl": "https://x/bayern.png"},
    "team2": {"teamId": 7, "teamName": "RB Leipzig", "teamIconUrl": "https://x/rbl.png"},
    "matchResults": [
        {"resultTypeID": 1, "pointsTeam1": 3, "pointsTeam2": 0, "resultName": "Halbzeit"},
        {"resultTypeID": 2, "pointsTeam1": 6, "pointsTeam2": 0, "resultName": "Endergebnis"},
    ],
    "group": {"groupName": "1. Spieltag"},
    "location": {"locationStadium": "Allianz Arena"},
}]


def test_openligadb_parse(session):
    provider = OpenLigaDBProvider()
    raws = list(provider.parse(OLDB_SAMPLE, league="bl1"))
    assert len(raws) == 1
    r = raws[0]
    assert r.status == "FINISHED"
    assert (r.home_score, r.away_score) == (6, 0)
    assert (r.home_score_ht, r.away_score_ht) == (3, 0)     # mi-temps extraite
    assert r.season_label == "2025-2026"
    assert r.venue == "Allianz Arena"
    assert r.home.logo_url == "https://x/bayern.png"
    rep = IngestReport(provider="openligadb")
    ingest_one(session, r, rep)
    session.commit()
    assert rep.created == 1
    fx = session.query(Fixture).one()
    assert fx.data_status == "UNVERIFIED"


TSDB_SAMPLE = {
    "events": [{
        "idEvent": "2267073", "strEvent": "Liverpool vs Bournemouth",
        "strLeague": "English Premier League", "strSeason": "2025-2026",
        "strHomeTeam": "Liverpool", "strAwayTeam": "Bournemouth",
        "intHomeScore": "4", "intAwayScore": "2", "strStatus": "FT",
        "strTimestamp": "2025-08-15T19:00:00", "strVenue": "Anfield",
        "idHomeTeam": "133602", "idAwayTeam": "133738",
    }],
}


def test_tsdb_parse(session):
    provider = TheSportsDBProvider()
    raws = list(provider.parse(TSDB_SAMPLE, league_id="4328"))
    assert len(raws) == 1
    r = raws[0]
    assert r.status == "FINISHED" and (r.home_score, r.away_score) == (4, 2)
    assert r.venue == "Anfield" and r.season_label == "2025-2026"
    rep = IngestReport(provider="tsdb")
    ingest_one(session, r, rep)
    session.commit()
    assert rep.created == 1


TSDB_SCHEDULED = {
    "events": [{
        "idEvent": "2290001", "strEvent": "A vs B", "strSeason": "2026-2027",
        "strHomeTeam": "Team A", "strAwayTeam": "Team B",
        "intHomeScore": "0", "intAwayScore": "0", "strStatus": "Not Started",
        "strTimestamp": "2026-09-05T15:00:00",
        "idHomeTeam": "1", "idAwayTeam": "2",
    }],
}


def test_tsdb_jamais_de_faux_zero(session):
    provider = TheSportsDBProvider()
    r = list(provider.parse(TSDB_SCHEDULED, league_id="4328"))[0]
    assert r.status == "SCHEDULED"
    assert r.home_score is None and r.away_score is None   # §1


FDORG_SAMPLE = {
    "matches": [{
        "id": 523451, "utcDate": "2025-08-15T19:00:00Z", "status": "FINISHED",
        "homeTeam": {"id": 57, "name": "Arsenal FC", "crest": "https://x/ars.png"},
        "awayTeam": {"id": 58, "name": "Aston Villa FC", "crest": "https://x/av.png"},
        "score": {"fullTime": {"home": 2, "away": 0}, "halfTime": {"home": 1, "away": 0}},
        "season": {"startDate": "2025-08-01", "endDate": "2026-06-30"},
        "matchday": 1, "stage": "REGULAR_SEASON",
    }],
}


def test_fdorg_parse(session):
    provider = FootballDataOrgProvider()
    raws = list(provider.parse(FDORG_SAMPLE, competition="PL"))
    assert len(raws) == 1
    r = raws[0]
    assert r.status == "FINISHED" and (r.home_score, r.away_score) == (2, 0)
    assert r.season_label == "2025-2026"
    assert r.home.logo_url == "https://x/ars.png"
    rep = IngestReport(provider="fdorg")
    ingest_one(session, r, rep)
    session.commit()
    assert rep.created == 1


def test_consistency_deux_sources_meme_score_verified(session):
    """Même match, 2 providers, score identique → UNVERIFIED monte en VERIFIED (§4)."""
    area = "Angleterre"
    rep = IngestReport(provider="x")
    ingest_one(session, _draw("espn", "E1", "eng.1", "PL", area,
                              ("Arsenal", "359"), ("Everton", "368"), 2, 1), rep)
    ingest_one(session, _draw("tsdb", "T1", "4328", "PL", area,
                              ("Arsenal", "133604"), ("Everton", "133615"), 2, 1), rep)
    session.commit()
    report = run_consistency(session)
    assert report.twins_checked == 1
    assert report.upgraded_to_verified == 2
    assert run_consistency(session).contradictions == 0
    assert all(f.data_status == "VERIFIED" for f in session.query(Fixture).all())


def test_consistency_scores_differents_contradiction(session):
    """Même match, 2 providers, scores différents → CONTRADICTORY + trace (§1)."""
    area = "Angleterre"
    rep = IngestReport(provider="x")
    ingest_one(session, _draw("espn", "E9", "eng.1", "PL", area,
                              ("Arsenal", "359"), ("Everton", "368"), 2, 1), rep)
    ingest_one(session, _draw("tsdb", "T9", "4328", "PL", area,
                              ("Arsenal", "133604"), ("Everton", "133615"), 2, 2), rep)
    session.commit()
    report = run_consistency(session)
    assert report.contradictions == 1
    assert all(f.data_status == "CONTRADICTORY" for f in session.query(Fixture).all())


def test_consistency_source_unique_inchangee(session):
    """Une seule source → statut inchangé (jamais d'auto-certification)."""
    rep = IngestReport(provider="x")
    ingest_one(session, _draw("espn", "E5", "eng.1", "PL", "Angleterre",
                              ("Arsenal", "359"), ("Everton", "368"), 2, 1), rep)
    session.commit()
    run_consistency(session)
    assert session.query(Fixture).one().data_status == "UNVERIFIED"


def test_alias_seed_fduk_vers_nom_complet(session):
    """'Wolves' (fduk) et 'Wolverhampton Wanderers' (ESPN) = UNE équipe (seed admin audité)."""
    rep = IngestReport(provider="x")
    ingest_one(session, _draw("fduk", "F1", "E0", "PL", "Angleterre",
                              ("Wolves", "wolves"), ("Everton", "everton"), 1, 0), rep)
    ingest_one(session, _draw("espn", "E2", "eng.1", "PL", "Angleterre",
                              ("Wolverhampton Wanderers", "380"), ("Everton", "368"), 1, 0), rep)
    session.commit()
    from app.db.models import Team
    assert session.query(Team).count() == 2   # fusion via seed, sinon 4
