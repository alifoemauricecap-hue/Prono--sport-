"""Tests M5 (value O/U + tendance), M6 (in-play), M7 (H2H/météo), M8 (chat)."""
from datetime import datetime, timedelta, timezone

import numpy as np

from app.ml.inplay import inplay_probabilities, parse_clock_minute, remaining_matrix

NOW = datetime(2026, 8, 24, 12, 0, tzinfo=timezone.utc)


# ---------------- M6 : in-play ----------------

def test_clock_parser():
    assert parse_clock_minute("67'") == 67
    assert parse_clock_minute("45+2'") == 47
    assert parse_clock_minute("HT") == 45
    assert parse_clock_minute("12:30") == 12
    assert parse_clock_minute(None) is None
    assert parse_clock_minute("??") is None
    assert parse_clock_minute("120'") == 90   # plafond temps réglementaire


def test_inplay_late_match_draw_becomes_favorite():
    """0-0 à la 89e → le nul doit dominer (il ne reste ~1 minute de buts attendus)."""
    r = inplay_probabilities(1.5, 1.2, 89, 0, 0)
    p = r["1X2"]
    assert p["D"] > p["H"] and p["D"] > p["A"] and p["D"] > 0.6
    assert r["most_likely_final"] == "0-0"


def test_inplay_leader_keeps_advantage():
    """2-0 à la 80e → l'équipe qui mène gagne presque sûrement."""
    r = inplay_probabilities(1.4, 1.1, 80, 2, 0)
    assert r["1X2"]["H"] > 0.90


def test_inplay_kickoff_equals_remaining_full_expectation():
    """Minute 0 : buts restants = buts attendus pré-match ; distribution normalisée."""
    r = inplay_probabilities(1.6, 1.0, 0, 0, 0)
    assert abs(r["goals_remaining_expected"]["home"] - 1.6) < 1e-6
    M = remaining_matrix(1.6, 1.0)
    assert abs(M.sum() - 1.0) < 1e-9


# ---------------- M5 : tendance des cotes ----------------

def _mk_team(session, name):
    from app.db.models import Team
    t = Team(name=name, country="Testland")
    session.add(t); session.flush()
    return t


def _mk_fixture(session, kickoff, status="SCHEDULED"):
    from app.db.models import Competition, Fixture, Season
    c = Competition(code="TST-T1", name="TrendLeague", area="Testland")
    session.add(c); session.flush()
    h = _mk_team(session, "Trend Home FC"); a = _mk_team(session, "Trend Away FC")
    season = Season(competition_id=c.id, label="2026-2027", start_year=2026, end_year=2027)
    session.add(season); session.flush()
    fx = Fixture(competition_id=c.id, season_id=season.id, home_team_id=h.id, away_team_id=a.id,
                 kickoff_utc=kickoff, status=status, source_provider="test",
                 source_event_id=f"t{kickoff.timestamp()}", source_url="t")
    session.add(fx); session.flush()
    return fx


def test_odds_trend_detects_movement(session):
    """Deux relevés réels → delta de probabilité fair mesuré, signe correct."""
    from app.analytics.odds_trend import odds_trends
    from app.db.models import Bookmaker, Market, OddsSnapshot

    fx = _mk_fixture(session, NOW + timedelta(hours=30))
    bm = Bookmaker(code="AVG", name="Consensus"); mk = Market(code="1X2", name="1X2")
    session.add_all([bm, mk]); session.flush()
    t0 = NOW - timedelta(hours=20)
    # 1re observation : H 2.00 / D 3.50 / A 3.80 ; dernière : H 1.70 / D 3.70 / A 5.00
    for when, odds in [(t0, {"H": 2.00, "D": 3.50, "A": 3.80}),
                       (NOW - timedelta(hours=2), {"H": 1.70, "D": 3.70, "A": 5.00})]:
        for sel, od in odds.items():
            session.add(OddsSnapshot(fixture_id=fx.id, bookmaker_id=bm.id, market_id=mk.id,
                                     selection=sel, odds=od, captured_at=when, origin="PROVIDER"))
    session.commit()
    tr = odds_trends(session, [fx.id])[fx.id]
    assert tr["H"] > 3.0       # favori renforcé : probabilité fair H en hausse
    assert tr["A"] < -2.0      # outsider délaissé
    assert tr["snapshots"] == 2


def test_odds_trend_ignores_single_observation(session):
    from app.analytics.odds_trend import odds_trends
    from app.db.models import Bookmaker, Market, OddsSnapshot
    fx = _mk_fixture(session, NOW + timedelta(hours=50))
    bm = Bookmaker(code="AVG", name="Consensus"); mk = Market(code="1X2", name="1X2")
    session.add_all([bm, mk]); session.flush()
    session.add(OddsSnapshot(fixture_id=fx.id, bookmaker_id=bm.id, market_id=mk.id,
                             selection="H", odds=2.0, captured_at=NOW, origin="PROVIDER"))
    session.commit()
    assert odds_trends(session, [fx.id]) == {}   # 1 seul relevé → pas de tendance (§1)


# ---------------- M7 : H2H ----------------

def test_h2h_counts_and_dedups_by_date(session):
    from app.analytics.h2h import head_to_head
    from app.db.models import Competition, Fixture, Season

    c = Competition(code="TST-H2H", name="H2HLeague", area="Testland")
    session.add(c); session.flush()
    h = _mk_team(session, "H2H Alpha"); a = _mk_team(session, "H2H Beta")
    season = Season(competition_id=c.id, label="2025-2026", start_year=2025, end_year=2026)
    session.add(season); session.flush()
    # 2 sources rapportent le MÊME match (Alpha 2-1 Beta, jumeaux)
    # + match retour distinct : Alpha gagne aussi, 1-2 à l'extérieur
    for prov, day, hs, as_ in [("espn", 40, 2, 1), ("fduk", 40, 2, 1), ("espn", 10, 1, 2)]:
        swap = (day == 10)
        fx = Fixture(competition_id=c.id, season_id=season.id,
                     home_team_id=a.id if swap else h.id, away_team_id=h.id if swap else a.id,
                     kickoff_utc=NOW - timedelta(days=day), status="FINISHED",
                     home_score=hs, away_score=as_, source_provider=prov,
                     source_event_id=f"{prov}{day}", source_url="t")
        session.add(fx)
    session.commit()
    r = head_to_head(session, h.id, a.id)
    assert r["count"] == 2                      # jumeaux dédupliqués
    assert r["tally"]["home_wins"] == 2         # Alpha gagne domicile ET extérieur (2-1)
    assert r["tally"]["draws"] == 0


# ---------------- M7 : météo (réseau MOCKÉ — tests reproductibles hors-ligne) ----------------

def test_weather_none_for_far_future(monkeypatch):
    from app.analytics import weather
    far = NOW + timedelta(days=60)
    called = {"n": 0}
    monkeypatch.setattr(weather, "geocode_city", lambda c: called.__setitem__("n", 1) or (0.0, 0.0))
    assert weather.forecast_at("Lomé", far) is None
    assert called["n"] == 0   # hors horizon → même pas d'appel réseau (économie + §1)


def test_weather_real_payload_mapping(monkeypatch):
    from app.analytics import weather
    weather._fcst_cache.clear(); weather._geo_cache.clear()
    monkeypatch.setattr(weather, "geocode_city", lambda c: (6.13, 1.22))
    payload = {"hourly": {"time": ["2026-08-24T19:00"],
                          "temperature_2m": [27.4], "precipitation": [0.2],
                          "precipitation_probability": [40], "wind_speed_10m": [11.0]}}
    class R:
        def json(self): return payload
    monkeypatch.setattr(weather.httpx, "get", lambda *a, **k: R())
    out = weather.forecast_at("Lomé", NOW.replace(hour=19))
    assert out and out["temperature_c"] == 27.4 and out["precipitation_prob_pct"] == 40


# ---------------- M8 : chat ----------------

def _seed_chat(session):
    from app.db.models import Competition, Fixture, Season, TeamAnalytics
    c = Competition(code="TST-CHAT", name="ChatLeague", area="Testland")
    session.add(c); session.flush()
    h = _mk_team(session, "Chat Alpha FC"); a = _mk_team(session, "Chat Beta FC")
    season = Season(competition_id=c.id, label="2026-2027", start_year=2026, end_year=2027)
    session.add(season); session.flush()
    fx = Fixture(competition_id=c.id, season_id=season.id, home_team_id=h.id, away_team_id=a.id,
                 kickoff_utc=NOW + timedelta(hours=20), status="SCHEDULED",
                 source_provider="test", source_event_id="chat1", source_url="t")
    session.add(fx)
    session.add(TeamAnalytics(team_id=h.id, elo=1720.4, matches_rated=50, form5="WWDLW",
                              gf5=9, ga5=4, computed_at=NOW))
    session.commit()
    return h, a, fx


def test_chat_forme_team(session):
    from app.chat.engine import answer
    h, _a, _fx = _seed_chat(session)
    r = answer(session, "forme de Chat Alpha FC")
    assert "1720" in r["answer"] and "WWDLW" in r["answer"]


def test_chat_value_empty_is_honest(session):
    from app.chat.engine import answer
    _seed_chat(session)
    r = answer(session, "donne-moi les value bets du jour")
    assert "NO QUALIFIED PICK" in r["answer"]


def test_chat_unknown_team_does_not_invent(session):
    from app.chat.engine import answer
    r = answer(session, "forme de Zzz Inexistant United")
    assert "introuvable" in r["answer"].lower()


def test_chat_match_prediction_uses_real_probabilities(session):
    from app.chat.engine import answer
    from app.db.models import ModelVersion, Prediction
    h, a, fx = _seed_chat(session)
    mv = ModelVersion(model_id="ensemble-dc-poisson-elo", version="v1", dataset_version="t")
    session.add(mv); session.flush()
    session.add(Prediction(
        fixture_id=fx.id, model_version_id=mv.id, feature_version="v1",
        input_snapshot={"history_matches": 300},
        probabilities={"1X2": {"H": .55, "D": .25, "A": .20},
                       "1X2_ensemble": {"H": .55, "D": .25, "A": .20},
                       "OU_2.5": {"Over": .48, "Under": .52},
                       "top_scores": [{"score": "1-0", "p": .12}]},
        expected_goals={"home": 1.6, "away": 1.0}))
    session.commit()
    r = answer(session, "prono Chat Alpha FC vs Chat Beta FC")
    assert "55 %" in r["answer"] and "300 matchs" in r["answer"] and "§38" in r["answer"]


# ---------------- Regroupement jumeaux cross-provider (affichage, §41) ----------------

def test_twins_names_variants_same_match():
    from app.analytics.twins import match_same_side
    # variantes typiques provider — MÊME match
    assert match_same_side("Stade de Reims", "Annecy FC", "Reims", "Annecy")
    assert match_same_side("Wolves", "Man United", "Wolverhampton Wanderers", "Manchester United")
    assert match_same_side("Paris FC", "Le Havre AC", "Paris FC", "Le Havre")
    # matchs DIFFÉRENTS — jamais fusionnés
    assert not match_same_side("Paris FC", "Le Havre", "Paris Saint Germain", "Le Havre")
    assert not match_same_side("Leeds United", "Hull City", "Manchester United", "Hull City")
    assert not match_same_side("Real Madrid", "Valencia", "Real Sociedad", "Valencia")
