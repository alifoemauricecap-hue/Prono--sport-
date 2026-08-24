"""§7 : un match invalide ne doit JAMAIS entrer en base."""
from datetime import datetime, timezone

from app.ingest.validation import validate_fixture
from app.providers.base import OddsRef, RawFixture, TeamRef


def good() -> RawFixture:
    return RawFixture(
        provider="fduk", provider_id="x1", provider_competition="E0",
        competition_name="Premier League", competition_area="Angleterre",
        season_label="2026-2027",
        kickoff_utc=datetime(2026, 8, 20, 19, 0, tzinfo=timezone.utc),
        kickoff_time_known=True, status="FINISHED",
        home=TeamRef(name="Alpha FC", provider_id="alpha"),
        away=TeamRef(name="Beta United", provider_id="beta"),
        home_score=2, away_score=1,
    )


def test_fixture_valide():
    assert validate_fixture(good()) == []


def test_rejet_meme_equipe():
    r = good()
    r.away = TeamRef(name="Alpha FC", provider_id="alpha2")
    assert any("meme_equipe" in e for e in validate_fixture(r))


def test_rejet_date_absente():
    r = good()
    r.kickoff_utc = None
    assert any("date_match" in e for e in validate_fixture(r))


def test_rejet_termine_sans_score():
    r = good()
    r.home_score = None
    assert any("termine_sans_score" in e for e in validate_fixture(r))


def test_rejet_statut_inconnu():
    r = good()
    r.status = "PLAYED"
    assert any("statut_inconnu" in e for e in validate_fixture(r))


def test_rejet_cote_aberrante():
    r = good()
    r.odds = [OddsRef(bookmaker="B365", market="1X2", selection="H", odds=0.5)]
    assert any("cote_aberrante" in e for e in validate_fixture(r))


def test_schedulé_avec_score_rejeté():
    r = good()
    r.status = "SCHEDULED"
    assert any("score_present_sur_match_non_joue" in e for e in validate_fixture(r))
