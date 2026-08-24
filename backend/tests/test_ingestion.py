"""Tests du pipeline : idempotence, résolution d'entités, traçabilité."""
from datetime import datetime, timezone

from app.db.models import EntityMapping, Fixture, OddsSnapshot, Team
from app.ingest.service import IngestReport, ingest_one
from app.providers.base import OddsRef, RawFixture, TeamRef
from app.providers.espn import EspnProvider
from app.providers.football_data_uk import FootballDataUKProvider

KO = datetime(2026, 8, 20, 19, 0, tzinfo=timezone.utc)


def _raw(score_h=2, score_a=1, status="FINISHED", pid="match-1"):
    return RawFixture(
        provider="fduk", provider_id=pid, provider_competition="E0",
        competition_name="Premier League", competition_area="Angleterre",
        season_label="2026-2027", kickoff_utc=KO, kickoff_time_known=True,
        status=status,
        home=TeamRef(name="Alpha FC", provider_id="alpha"),
        away=TeamRef(name="Beta United", provider_id="beta"),
        home_score=score_h if status == "FINISHED" else None,
        away_score=score_a if status == "FINISHED" else None,
        home_xg=1.8, away_xg=0.9, referee="M. Test",
        odds=[
            OddsRef(bookmaker="PINN", market="1X2", selection="H", odds=1.95),
            OddsRef(bookmaker="PINN", market="1X2", selection="D", odds=3.6),
            OddsRef(bookmaker="PINN", market="1X2", selection="A", odds=4.2),
        ],
        raw={"fictif": True},
    )


def test_ingestion_cree_un_match(session):
    report = IngestReport(provider="fduk")
    ingest_one(session, _raw(), report)
    session.commit()
    assert report.created == 1 and report.rejected == 0
    fx = session.query(Fixture).one()
    assert fx.status == "FINISHED" and fx.home_score == 2
    assert fx.data_status == "VERIFIED"
    assert fx.raw_payload is not None          # §47 traçabilité
    assert fx.source_provider == "fduk"


def test_idempotence_aucune_doublon(session):
    rep1, rep2 = IngestReport(provider="fduk"), IngestReport(provider="fduk")
    ingest_one(session, _raw(), rep1)
    ingest_one(session, _raw(), rep2)   # même payload → rien ne bouge
    session.commit()
    assert rep1.created == 1
    assert rep2.created == 0 and rep2.updated == 0 and rep2.skipped_unchanged == 1
    assert session.query(Fixture).count() == 1
    assert session.query(Team).count() == 2
    assert session.query(OddsSnapshot).count() == 3   # pas de doublon de cotes


def test_mise_a_jour_score(session):
    rep1, rep2 = IngestReport(provider="fduk"), IngestReport(provider="fduk")
    ingest_one(session, _raw(1, 0), rep1)
    ingest_one(session, _raw(3, 2), rep2)
    session.commit()
    assert rep2.updated == 1
    fx = session.query(Fixture).one()
    assert (fx.home_score, fx.away_score) == (3, 2)
    assert fx.last_updated_at >= fx.created_at


def test_mapping_entities(session):
    report = IngestReport(provider="fduk")
    ingest_one(session, _raw(), report)
    session.commit()
    mappings = session.query(EntityMapping).filter_by(entity_type="team").all()
    assert len(mappings) == 2
    assert all(m.provider == "fduk" for m in mappings)


def test_rejet_stocke_pour_audit(session):
    bad = _raw()
    bad.away = TeamRef(name="Alpha FC", provider_id="alpha-bis")  # même nom des 2 côtés
    report = IngestReport(provider="fduk")
    ingest_one(session, bad, report)
    session.commit()
    assert report.rejected == 1
    assert session.query(Fixture).count() == 0


ESPN_SAMPLE = {
    "leagues": [{"name": "English Premier League"}],
    "events": [{
        "id": "999001",
        "name": "Gamma FC at Delta Town",
        "date": "2026-08-30T16:00Z",
        "status": {"type": {"name": "STATUS_SCHEDULED"}},
        "competitions": [{
            "venue": {"fullName": "Delta Stadium"},
            "competitors": [
                {"homeAway": "home", "score": "", "team": {"id": "71", "displayName": "Delta Town",
                                                           "logos": [{"href": "https://img.es/delta.png"}]}},
                {"homeAway": "away", "score": "", "team": {"id": "72", "displayName": "Gamma FC"}},
            ],
        }],
    }],
}


def test_espn_parse_et_ingere(session):
    provider = EspnProvider()
    raws = list(provider.parse(ESPN_SAMPLE, league="eng.1"))
    assert len(raws) == 1
    assert raws[0].status == "SCHEDULED"
    assert raws[0].kickoff_utc.year == 2026
    assert raws[0].season_label == "2026-2027"
    report = IngestReport(provider="espn")
    for r in raws:
        ingest_one(session, r, report)
    session.commit()
    assert report.created == 1
    fx = session.query(Fixture).one()
    assert fx.data_status == "UNVERIFIED"       # ESPN non confirmé par 2ᵉ source (§1)
    assert fx.venue == "Delta Stadium"


def test_fduk_parse_csv_minimal():
    csv_txt = (
        "Div,Date,Time,HomeTeam,AwayTeam,FTHG,FTAG,FTR,HxG,AxG,Referee,"
        "B365H,B365D,B365A,PSH,PSD,PSA,MaxH,MaxD,MaxA,AvgH,AvgD,AvgA,B365>2.5,B365<2.5\n"
        "E0,20/08/2026,19:00,Alpha FC,Beta United,2,1,H,1.8,0.9,M. Test,"
        "1.9,3.6,4.2,1.95,3.7,4.4,1.96,3.75,4.5,1.92,3.68,4.35,1.85,2.0\n"
    )
    provider = FootballDataUKProvider()
    rows = list(provider.parse(csv_txt, div="E0", season="2627"))
    assert len(rows) == 1
    r = rows[0]
    assert r.status == "FINISHED"
    assert r.home_xg == 1.8 and r.referee == "M. Test"
    books = {o.bookmaker for o in r.odds}
    assert {"B365", "PINN", "MAX", "AVG"} <= books        # 1X2 complet
    assert any(o.market == "OU_2.5" and o.selection == "Over" for o in r.odds)
    assert r.kickoff_utc == datetime(2026, 8, 20, 19, 0, tzinfo=timezone.utc)
