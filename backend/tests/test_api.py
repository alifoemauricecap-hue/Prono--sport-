"""Tests de l'API v1 (M2) — grouping inter-sources et codes de santé."""
from datetime import datetime, timezone

from fastapi.testclient import TestClient

from app.api import app, SF
from app.db.models import Fixture
from app.ingest.service import IngestReport, ingest_one
from app.providers.base import RawFixture, TeamRef

KO = datetime(2025, 9, 5, 19, 0, tzinfo=timezone.utc)
client = TestClient(app)


def _seed():
    with SF() as s:
        rep = IngestReport(provider="x")
        ingest_one(s, RawFixture(
            provider="espn", provider_id="a1", provider_competition="eng.1",
            competition_name="Premier League", competition_area="Angleterre",
            season_label="2025-2026", kickoff_utc=KO, kickoff_time_known=True,
            status="FINISHED",
            home=TeamRef(name="Arsenal", provider_id="359", country="Angleterre"),
            away=TeamRef(name="Everton", provider_id="368", country="Angleterre"),
            home_score=2, away_score=0), rep)
        ingest_one(s, RawFixture(
            provider="tsdb", provider_id="a2", provider_competition="4328",
            competition_name="Premier League", competition_area="Angleterre",
            season_label="2025-2026", kickoff_utc=KO, kickoff_time_known=True,
            status="FINISHED",
            home=TeamRef(name="Arsenal", provider_id="133604", country="Angleterre"),
            away=TeamRef(name="Everton", provider_id="133615", country="Angleterre"),
            home_score=2, away_score=0), rep)
        ingest_one(s, RawFixture(
            provider="espn", provider_id="b1", provider_competition="eng.1",
            competition_name="Premier League", competition_area="Angleterre",
            season_label="2025-2026", kickoff_utc=KO, kickoff_time_known=True,
            status="SCHEDULED",
            home=TeamRef(name="Chelsea", provider_id="363", country="Angleterre"),
            away=TeamRef(name="Fulham", provider_id="370", country="Angleterre")), rep)
        s.commit()


_seed()


def test_fixtures_finished_groupe_les_jumeaux():
    d = client.get("/v1/fixtures?tab=finished").json()
    assert d["count"] == 1                       # 2 lignes DB → 1 carte regroupée
    card = d["fixtures"][0]
    assert card["n_sources"] == 2
    assert {s["provider"] for s in card["sources"]} == {"espn", "tsdb"}
    assert card["score"]["ft_home"] == 2 and card["score"]["ft_away"] == 0
    assert card["data_status"] == "UNVERIFIED"   # pas encore de vérification croisée lancée


def test_fixtures_upcoming():
    d = client.get("/v1/fixtures?tab=upcoming").json()
    assert d["count"] == 1
    assert d["fixtures"][0]["status"] == "SCHEDULED"
    assert d["fixtures"][0]["home"]["name"] == "Chelsea"


def test_fixtures_filtre_competition():
    d = client.get("/v1/fixtures?tab=all&competition=ENG-E0").json()
    assert d["count"] == 2
    r = client.get("/v1/fixtures?tab=all&competition=INCONNUE")
    assert r.status_code == 404


def test_competitions_et_sante():
    c = client.get("/v1/competitions").json()
    assert any(x["code"] == "ENG-E0" for x in c["competitions"])
    h = client.get("/v1/health/providers").json()
    assert "providers" in h
    st = client.get("/v1/stats").json()
    assert st["fixtures"] == 3 and st["teams"] == 4


def test_index_page():
    r = client.get("/")
    assert r.status_code == 200 and "PRONO" in r.text
