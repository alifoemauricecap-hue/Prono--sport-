"""Tests M4 : mathématiques des modèles + odds math + anti-leakage §22."""
from datetime import datetime, timedelta, timezone

import numpy as np

from app.ml.dc_models import (
    fit_dixon_coles,
    fit_poisson,
    probabilities,
    score_matrix,
    tau_dc,
)
from app.ml.odds_math import LEVELS, evaluate_selection, fair_probabilities

NOW = datetime(2026, 8, 24, tzinfo=timezone.utc)


def _synth_matches(n=220, rng_seed=7):
    """Ligue synthétique à 6 équipes aux forces connues, générée via Poisson
    (données de TEST internes au moteur, jamais affichées comme réelles)."""
    rng = np.random.default_rng(rng_seed)
    teams = ["alpha", "bravo", "charlie", "delta", "echo", "foxtrot"]
    att = {"alpha": 1.25, "bravo": 1.1, "charlie": 1.0, "delta": 0.9, "echo": 0.8, "foxtrot": 0.6}
    out = []
    for i in range(n):
        h, a = rng.choice(teams, size=2, replace=False)
        lam = att[h] / att[a] * 1.35 * 1.15     # domicile avantagé
        mu = att[a] / att[h] * 1.35 * 0.9
        hs, as_ = int(rng.poisson(lam)), int(rng.poisson(mu))
        out.append((h, a, hs, as_, NOW - timedelta(days=int(rng.integers(1, 300)))))
    return out


def test_poisson_converge_force_connue():
    matches = _synth_matches()
    st = fit_poisson(matches, NOW, NOW)
    assert st is not None
    # alpha est programmée plus forte que foxtrot → l'estimation doit le retrouver
    assert st.attack["alpha"] > st.attack["foxtrot"]
    assert st.home_advantage > 0
    lam, mu = st.lambdas("alpha", "foxtrot")
    assert lam > mu
    assert st.n_matches == len(matches)


def test_anti_leakage_cutoff_22():
    """§22 : entraîner avec cutoff=T exclut tout match postérieur à T."""
    matches = _synth_matches()
    t_future = NOW + timedelta(days=1)
    st = fit_poisson([(h, a, hs, as_, t_future) for (h, a, hs, as_, _) in matches], NOW, NOW)
    assert st is None                        # tout l'historique est "futur" → refusé
    half = NOW - timedelta(days=150)
    st2 = fit_poisson(matches, half, NOW)
    assert st2.n_matches < len(matches)


def test_matrice_probabilites_coherente():
    matches = _synth_matches()
    st = fit_poisson(matches, NOW, NOW)
    dc = fit_dixon_coles(st, matches, NOW, NOW)
    M, lam, mu = score_matrix(dc, "alpha", "foxtrot")
    assert abs(M.sum() - 1.0) < 1e-6                       # distribution normalisée
    p = probabilities(M)
    tot = sum(p["1X2"][k] for k in ("H", "D", "A"))
    assert abs(tot - 1.0) < 1e-6
    assert p["1X2"]["H"] > p["1X2"]["A"]                   # alpha favori à domicile
    assert 0 < p["OU_2.5"]["Over"] < 1
    assert abs(p["BTTS"]["Yes"] + p["BTTS"]["No"] - 1.0) < 1e-6
    assert -0.15 <= dc.rho <= 0.15                          # bornes documentées


def test_tau_dc_formule():
    assert tau_dc(0, 0, 1.5, 1.0, 0.05) == 1 - 1.5 * 0.05
    assert tau_dc(1, 1, 1.5, 1.0, 0.05) == 1 - 0.05
    assert tau_dc(2, 2, 1.5, 1.0, 0.05) == 1.0


def test_marge_retiree_equitablement():
    fair = fair_probabilities({"H": 1.9, "D": 3.6, "A": 4.4})
    assert abs(sum(fair.values()) - 1.0) < 1e-9
    assert fair["H"] > 0.5                                  # favori reste favori
    assert fair_probabilities({"H": 0.9, "A": 2.0}) == {}   # cote invalide rejetée


def test_niveaux_value_documentes():
    r = evaluate_selection(0.60, 2.0, 0.52, sample_ok=True, models_agree=True)
    assert r["ev"] > LEVELS["MIN_EV_STRONG"] * 2 and r["level"] in ("STRONG", "QUALIFIED")
    r2 = evaluate_selection(0.505, 1.9, 0.50, sample_ok=True, models_agree=True)
    assert r2["level"] == "NO_VALUE"                        # EV négatif → rien
    r3 = evaluate_selection(0.60, 2.0, 0.52, sample_ok=False, models_agree=True)
    assert r3["level"] in ("QUALIFIED", "POTENTIAL") or r3["level"] != "STRONG"  # filtre robustesse §34


# ---------- M4.1 : garde-fous honnêteté (VB jamais sur match passé, anti-désaccord) ----------

def test_extreme_disagreement_is_no_pick():
    """§34 : modèle 63 % vs marché 19 % → écart 44 pts = données douteuses → NO_PICK,
    jamais une STRONG_VALUE (régression du cas réel Pisa-Padova cote périmée)."""
    res = evaluate_selection(0.63, 5.25, 0.186, sample_ok=True, models_agree=True)
    assert res["level"] == "NO_PICK"
    res2 = evaluate_selection(0.45, 3.40, 0.30, sample_ok=True, models_agree=True)
    assert res2["level"] in ("POTENTIAL", "QUALIFIED", "STRONG")   # 15 pts : reste analysable


def test_sweep_stale_marks_unknown(session):
    """SCHEDULED dont le kickoff est dépassé → UNKNOWN (DONNÉE NON VÉRIFIÉE), sans score inventé."""
    from app.db.models import Competition, Fixture, Season, Team
    from app.ingest.consistency import sweep_stale

    comp = Competition(code="TST-X1", name="Test", area="Testland")
    h = Team(name="Stale Home FC", country="Testland")
    a = Team(name="Stale Away FC", country="Testland")
    session.add_all([comp, h, a]); session.flush()
    season = Season(competition_id=comp.id, label="2026-2027", start_year=2026, end_year=2027)
    session.add(season); session.flush()
    old = Fixture(competition_id=comp.id, season_id=season.id, home_team_id=h.id,
                  away_team_id=a.id, kickoff_utc=NOW - timedelta(hours=6),
                  status="SCHEDULED", source_provider="test", source_event_id="t-old",
                  source_url="t")
    future = Fixture(competition_id=comp.id, season_id=season.id, home_team_id=a.id,
                     away_team_id=h.id, kickoff_utc=NOW + timedelta(hours=30),
                     status="SCHEDULED", source_provider="test", source_event_id="t-fut",
                     source_url="t")
    session.add_all([old, future]); session.commit()

    n = sweep_stale(session, now=NOW)
    assert n == 1
    session.refresh(old); session.refresh(future)
    assert old.status == "UNKNOWN" and old.home_score is None
    assert future.status == "SCHEDULED"


def test_past_fixtures_purged_from_value_bets(session):
    """§1/§38 : predict_upcoming purge les VB des matchs passés et n'en recrée pas."""
    from app.db.models import (
        Competition, Fixture, ModelVersion, Prediction, Season, Team, ValueBet,
    )
    from app.ml.engine import predict_upcoming

    comp = Competition(code="TST-X2", name="Test2", area="Testland")
    h = Team(name="Gone Home FC", country="Testland")
    a = Team(name="Gone Away FC", country="Testland")
    session.add_all([comp, h, a]); session.flush()
    season = Season(competition_id=comp.id, label="2026-2027", start_year=2026, end_year=2027)
    session.add(season); session.flush()
    past = Fixture(competition_id=comp.id, season_id=season.id, home_team_id=h.id,
                   away_team_id=a.id, kickoff_utc=NOW - timedelta(hours=8),
                   status="SCHEDULED", source_provider="test", source_event_id="t-past",
                   source_url="t")
    session.add(past); session.flush()
    mv = ModelVersion(model_id="ensemble-dc-poisson-elo", version="v1", dataset_version="t")
    session.add(mv); session.flush()
    pred = Prediction(fixture_id=past.id, model_version_id=mv.id, feature_version="v1",
                      input_snapshot={}, probabilities={}, expected_goals={})
    session.add(pred); session.flush()
    session.add(ValueBet(fixture_id=past.id, prediction_id=pred.id, market="1X2",
                         selection="A", odds_reference=5.25, bookmaker_ref="B365",
                         p_model=0.63, p_market_fair=0.19, edge=0.44, ev=2.31,
                         level="STRONG", confidence="ÉLEVÉE"))
    session.commit()

    predict_upcoming(session, now=NOW)
    assert session.query(ValueBet).filter_by(fixture_id=past.id).count() == 0
    assert session.query(Prediction).filter_by(fixture_id=past.id).count() == 0
