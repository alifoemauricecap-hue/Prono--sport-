"""Comportements mesurés sur données réelles (ESPN/fduk) — verrouillés par tests."""
from datetime import datetime, timezone

from app.db.models import EntityMapping, Fixture, Team
from app.ingest.service import IngestReport, ingest_one
from app.providers.base import RawFixture, TeamRef
from app.providers.espn import EspnProvider

KO = datetime(2026, 8, 24, 19, 0, tzinfo=timezone.utc)


def test_espn_score_0_sur_match_programme_normalise_null(session):
    """ESPN renvoie score='0' sur SCHEDULED → NULL en base, statut conservé."""
    sample = {
        "events": [{
            "id": "7001", "name": "Chelsea at Fulham", "date": "2026-08-24T19:00Z",
            "status": {"type": {"name": "STATUS_SCHEDULED"}},
            "competitions": [{
                "venue": {"fullName": "Craven Cottage"},
                "competitors": [
                    {"homeAway": "home", "score": "0", "team": {"id": "370", "displayName": "Fulham"}},
                    {"homeAway": "away", "score": "0", "team": {"id": "363", "displayName": "Chelsea"}},
                ],
            }],
        }],
    }
    provider = EspnProvider()
    raws = list(provider.parse(sample, league="eng.1"))
    report = IngestReport(provider="espn")
    for r in raws:
        ingest_one(session, r, report)
    session.commit()
    assert report.rejected == 0 and report.created == 1
    fx = session.query(Fixture).one()
    assert fx.status == "SCHEDULED"
    assert fx.home_score is None and fx.away_score is None  # jamais de faux 0-0 (§1)


def _ref(name, pid, country):
    return TeamRef(name=name, provider_id=pid, country=country)


def test_lien_inter_providers_alias_identique_et_meme_pays(session):
    """ESPN 'Arsenal' (id 359) puis fduk 'Arsenal' (id=nom) → UNE équipe, 2 mappings."""
    rep = IngestReport(provider="test")
    ingest_one(session, RawFixture(
        provider="espn", provider_id="e1", provider_competition="eng.1",
        competition_name="Premier League", competition_area="Angleterre",
        season_label="2026-2027", kickoff_utc=KO, kickoff_time_known=True,
        status="SCHEDULED",
        home=_ref("Arsenal", "359", "Angleterre"), away=_ref("Everton", "368", "Angleterre"),
    ), rep)
    ingest_one(session, RawFixture(
        provider="fduk", provider_id="m1", provider_competition="E0",
        competition_name="Premier League", competition_area="Angleterre",
        season_label="2026-2027", kickoff_utc=KO, kickoff_time_known=True,
        status="FINISHED", home_score=1, away_score=0,
        home=_ref("Arsenal", "Arsenal", "Angleterre"), away=_ref("Everton", "Everton", "Angleterre"),
    ), rep)
    session.commit()
    assert session.query(Team).count() == 2          # pas de doublon créé
    mappings = session.query(EntityMapping).filter_by(entity_type="team").all()
    assert len(mappings) == 4                          # 2 fournisseurs × 2 équipes


def test_alias_identique_pays_differents_aucune_fusion(session):
    """Même nom, pays différents → équipes DISTINCTES (§5), jamais de crash d'unicité."""
    rep = IngestReport(provider="test")
    for prov, pid, country, ev in (("espn", "900", "Angleterre", "e2"),
                                   ("espn", "901", "France", "e3")):
        ingest_one(session, RawFixture(
            provider=prov, provider_id=ev, provider_competition="eng.1",
            competition_name="X", competition_area=country,
            season_label="2026-2027", kickoff_utc=KO, kickoff_time_known=True,
            status="SCHEDULED",
            home=_ref("United FC", pid, country), away=_ref("Rovers", pid + "r", country),
        ), rep)
    session.commit()
    united = session.query(Team).filter(Team.name == "United FC").all()
    assert len(united) == 2
    assert rep.errors == []
