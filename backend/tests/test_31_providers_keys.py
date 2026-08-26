"""Providers à clé GRATUITE (API-Football, The Odds API) — §21/§22/§23/§37.

- gating : sans clé → MISSING DEPENDENCY, jamais de simulation
- parsing : compositions (lineups) + cotes 1X2/O/U 2.5 (mock réseau)
- association : cotes rattachées au fixture DÉJÀ en base (jamais de match inventé)
"""
from datetime import datetime, timedelta, timezone

import httpx
import pytest

from app.db.models import Bookmaker, Competition, Fixture, Lineup, Market, OddsSnapshot, Team
from app.ingest.resolution import normalize_name
from app.providers import api_football as af
from app.providers import odds_api as oapi


class _FakeResp:
    def __init__(self, payload, status=200):
        self._payload = payload
        self.status_code = status

    def raise_for_status(self):
        if self.status_code >= 400:
            raise httpx.HTTPStatusError("err", request=None, response=None)

    def json(self):
        return self._payload

    @property
    def text(self):
        import json
        return json.dumps(self._payload)

    @property
    def content(self):
        import json
        return json.dumps(self._payload).encode()


FIXTURES_PAYLOAD = {
    "results": 1,
    "response": [{
        "id": 111,
        "date": "2026-08-26T20:00:00Z",
        "status": {"short": "NS"},
        "league": {"name": "La Liga"},
        "home": {"team": {"id": 100, "name": "Real Madrid"}, "goals": None},
        "away": {"team": {"id": 101, "name": "Sociedad"}, "goals": None},
        "lineups": [
            {"team": {"id": 100, "name": "Real Madrid"},
             "players": [
                 {"id": 900, "name": "Karim Benzema", "number": 9,
                  "position": "Forward", "starting": True},
                 {"id": 901, "name": "Luka Modric", "number": 10,
                  "position": "Midfielder", "starting": True},
             ]},
            {"team": {"id": 101, "name": "Sociedad"},
             "players": [
                 {"id": 902, "name": "Alexander Isak", "number": 14,
                  "position": "Forward", "starting": True},
             ]},
        ],
    }],
}

INJURIES_PAYLOAD = {
    "results": 1,
    "response": [{
        "player": {"id": 900, "name": "Karim Benzema"},
        "team": {"id": 100, "name": "Real Madrid"},
        "status": "injured",
        "injury": "Cuisse",
        "description": "Blessure à la cuisse",
        "return_time": "2026-09-01T00:00:00Z",
    }],
}

ODDS_PAYLOAD = [{
    "id": "550",
    "sport_key": "soccer",
    "home_team": "Real Madrid",
    "away_team": "Sociedad",
    "commence_time": "2026-08-26T20:00:00Z",
    "bookmakers": [{
        "key": "bet365",
        "title": "Bet365",
        "markets": [
            {"key": "h2h", "outcomes": [
                {"name": "Real Madrid", "price": 1.30},
                {"name": "Draw", "price": 6.5},
                {"name": "Sociedad", "price": 10.0},
            ]},
            {"key": "totals", "point": 2.5, "outcomes": [
                {"name": "Over", "price": 1.9},
                {"name": "Under", "price": 1.95},
            ]},
        ],
    }],
}]


def test_apifootball_sans_cle_missing_dependency(monkeypatch):
    monkeypatch.delenv("API_FOOTBALL_KEY", raising=False)
    assert af.available() is False
    p = af.ApiFootballProvider()
    with pytest.raises(RuntimeError, match="MISSING DEPENDENCY"):
        p.fetch("2026-08-26")


def test_apifootball_parsing(monkeypatch):
    monkeypatch.setenv("API_FOOTBALL_KEY", "test-key")
    monkeypatch.setattr(af.httpx, "get", lambda *a, **k: _FakeResp(FIXTURES_PAYLOAD))
    p = af.ApiFootballProvider()
    assert p.available()
    payload = p.fetch("2026-08-26")
    raws = list(p.parse(payload, "2026-08-26"))
    assert len(raws) == 1
    r = raws[0]
    assert r.provider == "apifootball" and r.provider_id == "111"
    assert r.home.name == "Real Madrid" and r.away.name == "Sociedad"
    assert r.status == "SCHEDULED"
    assert r.kickoff_utc is not None

    lineups = p.fetch_lineups("2026-08-26")  # servi par le cache (0 req réseau)
    assert len(lineups) == 2
    home_lu = next(l for l in lineups if l.side == "home")
    assert home_lu.team_name == "Real Madrid" and len(home_lu.players) == 2
    assert home_lu.players[0].number == 9


def test_apifootball_blessures(monkeypatch):
    monkeypatch.setenv("API_FOOTBALL_KEY", "test-key")

    def fake_get(url, **kw):
        if "injuries" in str(url):
            return _FakeResp(INJURIES_PAYLOAD)
        return _FakeResp(FIXTURES_PAYLOAD)
    monkeypatch.setattr(af.httpx, "get", fake_get)
    p = af.ApiFootballProvider()
    injuries = p.fetch_injuries("2026-08-26")
    assert len(injuries) == 1
    assert injuries[0].status == "INJURED"
    assert injuries[0].expected_return is not None


def test_lineups_ingest_idempotent(session, monkeypatch):
    """Les compositions officielles créent des lignes Lineup (jamais inventées)
    et relancer = idempotent (pas de doublon)."""
    from app.ingest.enrichment import ingest_lineups
    comp = Competition(code="TEST-LN", name="Ligue Test", area="Testland")
    session.add(comp)
    session.flush()
    home = Team(name="Real Madrid"); away = Team(name="Sociedad")
    session.add_all([home, away])
    session.flush()
    fx = Fixture(competition_id=comp.id, home_team_id=home.id, away_team_id=away.id,
                 kickoff_utc=datetime(2026, 8, 26, 20, 0, tzinfo=timezone.utc),
                 status="SCHEDULED", source_provider="apifootball",
                 source_event_id="111")
    session.add(fx)
    session.flush()
    from app.db.models import EntityMapping
    session.add(EntityMapping(entity_type="fixture", entity_id=fx.id,
                              provider="apifootball", provider_id="111"))
    session.commit()

    lineups = [
        af.FixtureLineup(fixture_provider_id=111, team_name="Real Madrid",
                         team_provider_id=100, side="home",
                         players=[af.LineupPlayer(900, "Karim Benzema", 9, "Forward", True),
                                  af.LineupPlayer(901, "Luka Modric", 10, "Midfielder", True)]),
    ]
    assert ingest_lineups(session, "apifootball", lineups) == 2
    assert session.query(Lineup).count() == 2
    assert ingest_lineups(session, "apifootball", lineups) == 2  # idempotent
    assert session.query(Lineup).count() == 2
    # fixture inconnu → ignoré (jamais de fixture inventé)
    orphan = [af.FixtureLineup(fixture_provider_id=999, team_name="X",
                               team_provider_id=1, side="home",
                               players=[af.LineupPlayer(1, "Y", 1, None, True)])]
    assert ingest_lineups(session, "apifootball", orphan) == 0


def test_oddsapi_sans_cle_missing_dependency(monkeypatch):
    monkeypatch.delenv("ODDS_API_KEY", raising=False)
    assert oapi.available() is False
    p = oapi.OddsApiProvider()
    with pytest.raises(RuntimeError, match="MISSING DEPENDENCY"):
        p.fetch()


def test_oddsapi_parsing_et_association(session, monkeypatch):
    """Les cotes réelles sont rattachées au fixture DÉJÀ en base (noms + kickoff)
    et snapshotées ; un événement sans correspondance est ignoré (jamais inventé)."""
    from app.ingest.service import attach_odds_to_fixture
    from app.providers import cache as cache_mod
    monkeypatch.setenv("ODDS_API_KEY", "test-key")
    monkeypatch.setattr(cache_mod.httpx, "get", lambda *a, **k: _FakeResp(ODDS_PAYLOAD))
    p = oapi.OddsApiProvider()

    events = p.fetch()
    assert len(events) == 1
    home, away, kickoff, odds = p.parse_odds(events[0])
    assert home == "Real Madrid" and away == "Sociedad" and kickoff is not None
    sels_1x2 = {o.selection for o in odds if o.market == "1X2"}
    assert sels_1x2 == {"H", "D", "A"}
    assert any(o.market == "OU_2.5" and o.selection == "Over" for o in odds)
    assert any(o.market == "OU_2.5" and o.selection == "Under" for o in odds)

    # fixture correspondant en base
    comp = Competition(code="TEST-OD", name="Ligue Test", area="Testland")
    session.add(comp)
    session.flush()
    home_t = Team(name="Real Madrid"); away_t = Team(name="Sociedad")
    session.add_all([home_t, away_t])
    session.flush()
    fx = Fixture(competition_id=comp.id, home_team_id=home_t.id, away_team_id=away_t.id,
                 kickoff_utc=datetime(2026, 8, 26, 20, 0, tzinfo=timezone.utc),
                 status="SCHEDULED", source_provider="fduk", source_event_id="x")
    session.add(fx)
    session.commit()

    assert p.match_fixture(session, home, away, kickoff) is fx
    n = attach_odds_to_fixture(session, fx, odds, "oddsapi")
    session.commit()
    assert n == 5  # 3 (1X2) + 2 (O/U)
    assert session.query(OddsSnapshot).count() == 5
    # idempotence : mêmes cotes → 0 nouveau snapshot
    assert attach_odds_to_fixture(session, fx, odds, "oddsapi") == 0
    # équipe inconnue en base → None (jamais de fixture inventé)
    assert p.match_fixture(session, "Inconnu FC", "Sociedad", kickoff) is None


def test_oddsapi_variante_cree_snapshot(session, monkeypatch):
    """Une cote qui change crée un NOUVEAU snapshot (historique du mouvement, §38)."""
    from app.ingest.service import attach_odds_to_fixture
    from app.providers.base import OddsRef
    comp = Competition(code="TEST-OD2", name="L2", area="Testland")
    session.add(comp); session.flush()
    h = Team(name="A FC"); a = Team(name="B FC")
    session.add_all([h, a]); session.flush()
    fx = Fixture(competition_id=comp.id, home_team_id=h.id, away_team_id=a.id,
                 kickoff_utc=datetime(2026, 8, 28, 20, 0, tzinfo=timezone.utc),
                 status="SCHEDULED", source_provider="fduk", source_event_id="y")
    session.add(fx); session.commit()
    assert attach_odds_to_fixture(session, fx,
                                  [OddsRef("bet365", "1X2", "H", 2.10)], "oddsapi") == 1
    assert attach_odds_to_fixture(session, fx,
                                  [OddsRef("bet365", "1X2", "H", 2.00)], "oddsapi") == 1
    assert session.query(OddsSnapshot).count() == 2
