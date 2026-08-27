"""§35/§36 — Backtest Lab : walk-forward anti-leakage, Brier/LogLoss,
modèle vs marché, historique insuffisant → jamais de fiction."""
from datetime import datetime, timedelta, timezone

import pytest

from app.db.models import Competition, Fixture, Team
from app.ml.backtest import run_backtest


def _team(session, name):
    t = Team(name=name)
    session.add(t)
    session.flush()
    return t


def _match(session, comp, home, away, hs, as_, dt):
    fx = Fixture(
        competition_id=comp.id, home_team_id=home.id, away_team_id=away.id,
        kickoff_utc=dt, status="FINISHED", home_score=hs, away_score=as_,
        source_provider="test", source_event_id=f"bt-{dt:%Y%m%d}-{home.id}-{away.id}",
    )
    session.add(fx)
    return fx


def test_backtest_walkforward_synthetique(session):
    """6 équipes, 36 matchs chronologiques : les 10 premiers servent d'historique
    minimum ; les 26 suivants sont prédits UN PAR UN sur le passé uniquement."""
    comp = Competition(code="TEST-BT", name="Backtest League", area="Testland")
    session.add(comp)
    session.flush()
    teams = [_team(session, f"Team {i}") for i in range(6)]
    base = datetime(2025, 8, 1, 18, 0, tzinfo=timezone.utc)
    scores = [(1, 0), (0, 1), (2, 1), (0, 0), (1, 1), (3, 0),
              (2, 2), (1, 2), (0, 3), (1, 0), (2, 0), (0, 2),
              (1, 0), (0, 1), (1, 1), (2, 1), (1, 3), (0, 0),
              (2, 1), (1, 0), (0, 1), (1, 2), (2, 2), (1, 0),
              (0, 2), (1, 1), (2, 0), (1, 1), (0, 1), (1, 0),
              (2, 1), (0, 0), (1, 2), (2, 0), (1, 0), (0, 1)]
    for i, (hs, as_) in enumerate(scores):
        h, a = teams[i % 6], teams[(i + 2) % 6]
        _match(session, comp, h, a, hs, as_, base + timedelta(days=i))
    session.commit()

    rep = run_backtest(session, min_history=10)
    comp_out = next(c for c in rep["competitions"] if c["code"] == "TEST-BT")
    assert comp_out["matches_total"] == 36
    assert comp_out["matches_backtested"] == 26  # 36 - 10 (historique minimum)
    # Brier d'une distribution valide ∈ [0, 2]
    assert 0.0 <= comp_out["brier_model"] <= 2.0
    assert comp_out["logloss_model"] > 0
    assert 0.0 <= comp_out["accuracy_top1_model"] <= 1.0
    # marché : aucune cote en base sur ce match → comparé à 0 match
    assert comp_out["market"] is None or comp_out["market"]["matches_with_odds"] == 0
    assert rep["overall"]["matches_backtested"] == 26


def test_backtest_historique_insuffisant(session):
    """Moins de min_history matchs → AUCUN backtest, jamais de fiction."""
    comp = Competition(code="TEST-PETIT", name="Petite Ligue", area="Testland")
    session.add(comp)
    session.flush()
    teams = [_team(session, f"P {i}") for i in range(4)]
    base = datetime(2025, 8, 1, 18, 0, tzinfo=timezone.utc)
    for i in range(5):
        _match(session, comp, teams[i % 4], teams[(i + 1) % 4], 1, 0,
               base + timedelta(days=i))
    session.commit()
    rep = run_backtest(session, min_history=30)
    comp_out = next(c for c in rep["competitions"] if c["code"] == "TEST-PETIT")
    assert comp_out["matches_backtested"] == 0
    assert "insuffisant" in (comp_out.get("note") or "").lower()
    assert rep["overall"]["matches_backtested"] == 0


def test_backtest_persiste_model_version(session):
    from app.db.models import ModelVersion
    comp = Competition(code="TEST-PV", name="PV Ligue", area="Testland")
    session.add(comp)
    session.flush()
    teams = [_team(session, f"PV {i}") for i in range(6)]
    base = datetime(2025, 8, 1, 18, 0, tzinfo=timezone.utc)
    for i in range(12):
        _match(session, comp, teams[i % 6], teams[(i + 3) % 6], i % 2, (i + 1) % 2,
               base + timedelta(days=i))
    session.commit()
    rep = run_backtest(session, min_history=10)
    mv = session.query(ModelVersion).filter_by(model_id="backtest-walkforward-v1").one()
    assert mv.metrics is not None
    assert mv.metrics["model_id"] == rep["model_id"]
