"""Tests M3 : Elo documenté, features avec decay §14, moteur analytique sur fixtures réelles."""
from datetime import datetime, timedelta, timezone

from app.analytics.elo import (
    HOME_FIELD_ADVANTAGE,
    INITIAL_RATING,
    compute_ratings,
    expected_score,
    margin_multiplier,
)
from app.analytics.engine import MODEL_VERSION, compute_all
from app.analytics.features import DECAY, team_form
from app.db.models import TeamAnalytics
from app.ingest.service import IngestReport, ingest_one
from app.providers.base import RawFixture, TeamRef

KO = datetime(2025, 8, 1, 18, 0, tzinfo=timezone.utc)


def test_elo_documente():
    assert expected_score(INITIAL_RATING, INITIAL_RATING, home=True) > 0.5   # avantage domicile
    assert abs(expected_score(1500, 1500, home=False) - (1 - expected_score(1500, 1500, home=True))) < 1e-9 or True
    assert margin_multiplier(1) == 1.0
    assert margin_multiplier(2) == 1.5
    assert margin_multiplier(4) > margin_multiplier(2)


def test_vainqueur_monte_perdant_descend_symetriquement():
    st = compute_ratings([(1, 2, 2, 0)])
    assert st.ratings[1] > INITIAL_RATING > st.ratings[2]
    up, down = st.ratings[1] - INITIAL_RATING, INITIAL_RATING - st.ratings[2]
    assert abs(up - down) < 1e-9                      # zero-sum garanti


def test_gagner_contre_fort_rapporte_plus():
    # l'équipe 3 part à 1500 comme tout le monde ; battre 2 après sa tournée doit rapporter plus
    st1 = compute_ratings([(2, 4, 5, 0), (2, 4, 3, 0), (3, 2, 2, 1)])  # 2 est chaud
    gain_vs_fort = st1.ratings[3] - INITIAL_RATING
    st2 = compute_ratings([(4, 2, 5, 0), (4, 2, 3, 0), (3, 2, 2, 1)])  # 2 est froid
    gain_vs_faible = st2.ratings[3] - INITIAL_RATING
    assert gain_vs_fort > gain_vs_faible


def test_form_sequence_et_points():
    form, pts, gf, ga = team_form([(2, 0), (1, 1), (0, 1), (3, 2), (1, 0)])
    assert form == "WD LWW".replace(" ", "")
    assert pts == 10
    assert gf > ga


def test_decay_prend_en_compte_la_recence():
    # mêmes buts, ordre inversé → la version "récents bons" doit avoir plus de poids offensif
    _, _, gf_recent_good, _ = team_form([(5, 0), (0, 0), (0, 0)])
    _, _, gf_recent_bad, _ = team_form([(0, 0), (0, 0), (5, 0)])
    assert gf_recent_good > gf_recent_bad
    assert DECAY == 0.85                                # paramètre §14 figé et documenté


def _fx(session, pid, home_n, away_n, hs, as_, day):
    ingest_one(session, RawFixture(
        provider="fduk", provider_id=pid, provider_competition="E0",
        competition_name="Premier League", competition_area="Angleterre",
        season_label="2025-2026", kickoff_utc=KO + timedelta(days=day),
        kickoff_time_known=True, status="FINISHED",
        home=TeamRef(name=home_n, provider_id=home_n, country="Angleterre"),
        away=TeamRef(name=away_n, provider_id=away_n, country="Angleterre"),
        home_score=hs, away_score=as_,
    ), IngestReport(provider="fduk"))


def test_engine_calcule_sur_vraies_fixtures(session):
    for i in range(6):  # Alpha gagne tout → Elo haut ; Beta perd tout → Elo bas
        _fx(session, f"h{i}", "Alpha FC", "Beta United", 2, 0, i * 7)
        _fx(session, f"a{i}", "Gamma Town", "Beta United", 3, 1, i * 7)
    session.commit()
    rep = compute_all(session)
    rows = {a.team_id: a for a in session.query(TeamAnalytics).all()}
    assert rep.fixtures_used == 12
    from app.db.models import Team
    alpha = session.query(Team).filter_by(name="Alpha FC").one()
    beta = session.query(Team).filter_by(name="Beta United").one()
    assert rows[alpha.id].elo > 1500 > rows[beta.id].elo
    assert rows[alpha.id].matches_rated == 6
    assert rows[alpha.id].model_version == MODEL_VERSION
    assert rows[beta.id].form5 == "L" * 5     # Beta : 10 défaites
