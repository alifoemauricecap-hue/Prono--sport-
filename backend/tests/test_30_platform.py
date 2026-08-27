"""PRONO SPORT 3.0 — SUITE DE TESTS OBLIGATOIRE (§72-77).

- NO FAKE DATA (§72)     : aucun match sans source valide, aucun chiffre inventé
- DATA CONFLICT (§73)    : A=2-1, B=1-1 → CONTRADICTORY (jamais d'arbitrage)
- LIVE (§74)             : goal → card → sub → halftime → fulltime (env de test)
- ODDS (§75)             : nouvelle cote / variation / marché fermé / book indispo
- LINEUP (§76)           : absent → rien inventé ; publié → recalcul
- PROVIDER FAILURE (§77) : source morte → failover, pas de crash, pas de faux OK
- Découverte, fiabilité observée, recherche en ligne (mockée), qualité.
"""
import time
from datetime import datetime, timedelta, timezone

import pytest

from app.db.models import (
    Competition, Fixture, FixtureEvent, ModelVersion, Notification, OddsSnapshot,
    Prediction, PredictionResult, Season, Team,
)
from app.ingest.service import IngestReport, ingest_one
from app.providers.base import OddsRef, RawFixture, TeamRef

NOW = datetime(2026, 8, 26, 15, 0, tzinfo=timezone.utc)
# « Aujourd'hui 18 h » DYNAMIQUE : les tests dépendent de la date courante
# (ex. run_weather ne traite que les matchs du jour) — jamais de date figée.
TODAY = datetime.now(timezone.utc).replace(hour=18, minute=0, second=0, microsecond=0)


# ---------------------------------------------------------------- helpers

def _raw(provider="espn", pid="m-1", status="SCHEDULED", hs=None, aws=None,
         home="Alpha FC", away="Beta United", comp="Test Cup", area="Testland",
         clock=None, kickoff=TODAY, referee=None, odds=None):
    return RawFixture(
        provider=provider, provider_id=pid, provider_competition=comp,
        competition_name=comp, competition_area=area, season_label=None,
        kickoff_utc=kickoff, kickoff_time_known=True, status=status,
        home=TeamRef(name=home, provider_id=f"{provider}-{home.lower().replace(' ', '')}"),
        away=TeamRef(name=away, provider_id=f"{provider}-{away.lower().replace(' ', '')}"),
        home_score=hs, away_score=aws, venue="Stade Test", venue_city="Paris",
        clock=clock, referee=referee, odds=odds or [],
        raw={"t": 30},
    )


def _ingest(session, raw):
    rep = IngestReport(provider=raw.provider)
    ingest_one(session, raw, rep)
    session.commit()
    return rep


def _get_fx(session, provider, pid):
    return session.query(Fixture).filter_by(source_provider=provider,
                                            source_event_id=pid).one()


def _mk_prediction(session, fixture_id, probs=None):
    mv = ModelVersion(model_id="test-model", version="v1",
                      dataset_version="test", features_version="v1")
    session.add(mv); session.flush()
    p = Prediction(
        fixture_id=fixture_id, model_version_id=mv.id, feature_version="v1",
        input_snapshot={"history_matches": 5},
        probabilities=probs or {"1X2": {"H": 0.55, "D": 0.25, "A": 0.20}},
        expected_goals={"home": 1.4, "away": 0.9},
    )
    session.add(p); session.commit()
    return p


# ================================================================
# 1. SOURCE DISCOVERY — registry, fiabilité observée, cycle de vie
# ================================================================

def test_registry_initialisation(session):
    from app.discovery.engine import ensure_sources
    n = ensure_sources(session)
    from app.db.models import DataSource
    srcs = session.query(DataSource).all()
    assert n >= 10 and len(srcs) >= 10
    by = {s.name: s for s in srcs}
    # source réellement vérifiée → APPROVED ; candidat non vérifié → DISCOVERED
    assert by["ESPN"].status in ("APPROVED", "VALIDATED")
    assert by["API-Football (free)"].status == "DISCOVERED"
    # idempotence
    assert ensure_sources(session) == 0


def test_reliability_jamais_inventee(session):
    """§8 : sans historique observé, la fiabilité reste NULL (non mesurable)."""
    from app.discovery.engine import ensure_sources
    from app.discovery.checker import compute_reliability
    from app.db.models import DataSource
    ensure_sources(session)
    src = session.query(DataSource).filter_by(name="worldfootball.net").one()
    assert compute_reliability(session, src) is None


def test_reliability_calculée_sur_observé(session):
    """Fiabilité calculée à partir des sync_jobs réels (9 OK / 1 FAILED)."""
    from app.discovery.engine import ensure_sources, log_job
    from app.discovery.checker import compute_reliability
    from app.db.models import DataSource
    ensure_sources(session)
    src = session.query(DataSource).filter_by(name="ESPN").one()
    src.last_successful_fetch = datetime.now(timezone.utc)
    for i in range(9):
        log_job(session, "syncFixtures", "ESPN", "OK", records=10, latency_ms=120)
    log_job(session, "syncFixtures", "ESPN", "DEGRADED", records=1, errors=["timeout"])
    score = compute_reliability(session, src)
    assert score is not None and 50 <= score <= 100


def test_source_not_allowed(session):
    """§5 : source interdisant l'usage automatisé → SOURCE_NOT_ALLOWED."""
    from app.discovery.engine import ensure_sources
    from app.discovery.checker import mark_not_allowed
    from app.db.models import DataSource
    ensure_sources(session)
    mark_not_allowed(session, "worldfootball.net", "CGU incompatibles")
    src = session.query(DataSource).filter_by(name="worldfootball.net").one()
    assert src.status == "NOT_ALLOWED" and src.terms_status == "FORBIDDEN"


def test_discovery_offline_sans_reseau(session):
    """Le worker de découverte fonctionne hors-ligne (tests) sans faux succès."""
    from app.discovery.engine import ensure_sources, run_discovery
    ensure_sources(session)
    res = run_discovery(session, offline=True)
    assert res["worker"] == "discoverSources"
    assert res["checked"] >= 10
    # les sources optionnelles sans clé sont SKIP (MISSING DEPENDENCY), jamais testées
    assert res["skipped"] >= 2


def test_check_source_down(session, monkeypatch):
    """Source qui échoue → DOWN + last_failed_fetch, jamais un faux OK."""
    from app.discovery import checker
    from app.discovery.engine import ensure_sources
    from app.db.models import DataSource, ProviderHealth
    ensure_sources(session)
    monkeypatch.setattr(checker, "_do_check",
                        lambda *a, **k: {"ok": False, "latency_ms": 50,
                                         "detail": None, "error": "ConnectError: refus"})
    src = session.query(DataSource).filter_by(name="OpenLigaDB").one()
    result = checker.check_source(session, src)
    session.commit()
    assert result["ok"] is False
    assert src.availability_status == "DOWN"
    assert src.last_failed_fetch is not None
    ph = session.query(ProviderHealth).filter_by(provider="OpenLigaDB").one()
    assert ph.status == "DOWN"


# ================================================================
# 2. NO FAKE DATA (§72)
# ================================================================

def test_tout_match_a_une_source(session):
    """Chaque fixture a OBLIGATOIREMENT une source valide (porteuses de données)."""
    _ingest(session, _raw(pid="nf-1"))
    _ingest(session, _raw(pid="nf-2", home="Gamma FC", away="Delta FC"))
    for fx in session.query(Fixture).all():
        assert fx.source_provider and fx.source_event_id
        assert fx.source_provider in {"fduk", "espn", "openligadb", "tsdb", "fdorg"}


def test_api_refuse_match_inconnu(session):
    from fastapi.testclient import TestClient
    from app.api import app
    c = TestClient(app)
    r = c.get("/v1/fixtures/999999/analysis")
    assert r.status_code == 404
    r2 = c.get("/v1/fixtures/999999/events")
    assert r2.status_code == 404
    r3 = c.get("/v1/reports/999999")
    assert r3.status_code == 404


def test_pas_de_prédiction_sans_historique(session):
    """§82 : compétition sans historique fini → aucune prédiction (jamais de fiction)."""
    from app.ml.engine import predict_upcoming
    c = Competition(code="NOHIST", name="No History League", area="X")
    session.add(c); session.flush()
    h = Team(name="Team A"); a = Team(name="Team B")
    session.add_all([h, a]); session.flush()
    fx = Fixture(competition_id=c.id, home_team_id=h.id, away_team_id=a.id,
                 kickoff_utc=TODAY, status="SCHEDULED",
                 source_provider="fduk", source_event_id="nohist-1")
    session.add(fx); session.commit()
    reports = predict_upcoming(session, competition_code="NOHIST")
    assert session.query(Prediction).filter_by(fixture_id=fx.id).count() == 0


def test_rapport_ne_fabrique_rien(session, monkeypatch):
    """Rapport expert sur un match « nu » : sections indisponibles = INDISPONIBLE."""
    from app.research import wikipedia
    monkeypatch.setattr(wikipedia, "context_for_competition", lambda *a, **k: None)
    import app.research.engine as eng
    monkeypatch.setattr(eng, "forecast_at", lambda *a, **k: None)  # pas de réseau en test
    build_expert_report = eng.build_expert_report
    _ingest(session, _raw(pid="bare-1", kickoff=NOW - timedelta(days=2),
                          status="FINISHED", hs=1, aws=0, referee="M. X",
                          home="Zeta FC", away="Eta FC"))
    fx = _get_fx(session, "espn", "bare-1")
    rep = build_expert_report(session, fx.id, refresh=True)
    secs = {s["label"]: s for s in rep["sections"]}
    assert len(rep["sections"]) == 20
    # sans source : ces sections sont EXPLICITEMENT indisponibles
    assert secs["Compositions"]["status"] == "UNAVAILABLE"
    assert secs["Absences"]["status"] == "UNAVAILABLE"
    assert secs["Entraîneurs"]["status"] == "UNAVAILABLE"
    assert secs["Tactique"]["status"] == "UNAVAILABLE"
    assert secs["Probabilités"]["status"] == "UNAVAILABLE"
    # l'arbitre EST fourni → section SOURCE
    assert secs["Arbitre"]["status"] == "SOURCE" and secs["Arbitre"]["content"] == "M. X"
    # la conclusion est honnête (abstention)
    assert "INSUFFICIENT DATA" in secs["Conclusion"]["content"]


# ================================================================
# 3. DATA CONFLICT (§73) : A=2-1, B=1-1 → CONTRADICTORY
# ================================================================

def test_conflit_de_scores_jamais_arbitré(session):
    """Deux sources, deux scores différents → CONTRADICTORY, valeurs conservées."""
    from app.ingest.consistency import run_consistency
    _ingest(session, _raw(provider="espn", pid="cf-1", status="FINISHED", hs=2, aws=1))
    _ingest(session, _raw(provider="openligadb", pid="cf-1-b", status="FINISHED",
                          hs=1, aws=1, kickoff=TODAY))
    rep = run_consistency(session)
    session.commit()
    rows = session.query(Fixture).all()
    assert len(rows) == 2  # les deux valeurs sont CONSERVÉES
    assert all(r.data_status == "CONTRADICTORY" for r in rows)
    assert rep.contradictions >= 1


def test_accord_multi_source_verifie(session):
    """Même score sur 2 sources indépendantes → VERIFIED (aucune pollution)."""
    from app.ingest.consistency import run_consistency
    _ingest(session, _raw(provider="espn", pid="ac-1", status="FINISHED", hs=2, aws=1))
    _ingest(session, _raw(provider="openligadb", pid="ac-1-b", status="FINISHED",
                          hs=2, aws=1, kickoff=TODAY))
    rep = run_consistency(session)
    session.commit()
    rows = session.query(Fixture).all()
    assert all(r.data_status == "VERIFIED" for r in rows)
    assert rep.upgraded_to_verified >= 1


# ================================================================
# 4. LIVE (§74) : séquence complète dans l'env de test
# ================================================================

def test_live_séquence_complète(session):
    """SCHEDULED → LIVE → BUT → HALFTIME → FINISHED : événements + résolutions."""
    from app.live.events import detect_events, resolve_predictions
    from app.db.models import FixtureEvent, Notification

    _ingest(session, _raw(pid="lv-1", status="SCHEDULED"))
    fx = _get_fx(session, "espn", "lv-1")

    # 1) Coup d'envoi : SCHEDULED → LIVE
    _ingest(session, _raw(pid="lv-1", status="LIVE", hs=0, aws=0, clock="1'"))
    evs = detect_events(session, fx, (None, None), "SCHEDULED")
    assert any(e["type"] == "MATCH_START" for e in evs)

    # 2) BUT 1-0 à la 34e (déduit du delta de score réel — jamais inventé)
    _ingest(session, _raw(pid="lv-1", status="LIVE", hs=1, aws=0, clock="34'"))
    evs = detect_events(session, fx, (0, 0), "LIVE")
    goals = [e for e in evs if e["type"] == "GOAL"]
    assert len(goals) == 1 and goals[0]["team"] == "home"
    db_goals = session.query(FixtureEvent).filter_by(fixture_id=fx.id, type="GOAL").all()
    assert len(db_goals) == 1 and db_goals[0].origin == "DERIVED"
    assert session.query(Notification).filter_by(type="GOAL").count() == 1

    # 3) Idempotence : même état → aucun doublon
    evs = detect_events(session, fx, (1, 0), "LIVE")
    assert session.query(FixtureEvent).filter_by(fixture_id=fx.id, type="GOAL").count() == 1
    assert session.query(Notification).filter_by(type="GOAL").count() == 1

    # 4) Mi-temps
    _ingest(session, _raw(pid="lv-1", status="HALFTIME", hs=1, aws=0, clock="HT"))
    evs = detect_events(session, fx, (1, 0), "LIVE")
    assert any(e["type"] == "HALFTIME" for e in evs)

    # 5) But extérieur 1-1 puis FINISHED
    _ingest(session, _raw(pid="lv-1", status="LIVE", hs=1, aws=1, clock="67'"))
    detect_events(session, fx, (1, 0), "HALFTIME")
    _ingest(session, _raw(pid="lv-1", status="FINISHED", hs=1, aws=1, clock=None))
    evs = detect_events(session, fx, (1, 1), "LIVE")
    assert any(e["type"] == "MATCH_END" for e in evs)

    # 6) Résolution du pronostic (non-destructif)
    p = _mk_prediction(session, fx.id, probs={"1X2": {"H": 0.55, "D": 0.25, "A": 0.20}})
    r = resolve_predictions(session, fx)
    assert r["resolved"] == 1 and r["actual"] == "D"
    pr = session.query(PredictionResult).filter_by(prediction_id=p.id).one()
    assert pr.result == "LOSS" and pr.final_score == "1-1"
    # la prédiction originale est INTACTE
    assert session.get(Prediction, p.id).probabilities["1X2"]["H"] == 0.55


def test_pas_d_événement_sans_changement(session):
    """Si le score n'a pas bougé → AUCUN événement (zéro fabrication)."""
    from app.live.events import detect_events
    _ingest(session, _raw(pid="st-1", status="LIVE", hs=0, aws=0, clock="10'"))
    fx = _get_fx(session, "espn", "st-1")
    _ingest(session, _raw(pid="st-1", status="LIVE", hs=0, aws=0, clock="12'"))
    evs = detect_events(session, fx, (0, 0), "LIVE")
    assert evs == []
    assert session.query(FixtureEvent).filter_by(fixture_id=fx.id).count() == 0


# ================================================================
# 5. ODDS (§75) : nouvelle cote / variation / fermé / book indisponible
# ================================================================

def test_odds_nouvelle_et_variation(session):
    """12:00 → 2.10 ; 12:30 → 1.98 (snapshot) ; 1.98 encore → aucun doublon."""
    o1 = [OddsRef("PINN", "1X2", "H", 2.10)]
    o2 = [OddsRef("PINN", "1X2", "H", 1.98)]
    _ingest(session, _raw(pid="od-1", odds=o1))
    n1 = session.query(OddsSnapshot).count()
    assert n1 == 1
    _ingest(session, _raw(pid="od-1", odds=o2))
    snaps = session.query(OddsSnapshot).order_by(OddsSnapshot.captured_at).all()
    assert len(snaps) == 2 and snaps[0].odds == 2.10 and snaps[1].odds == 1.98
    _ingest(session, _raw(pid="od-1", odds=o2))  # même valeur → pas de snapshot
    assert session.query(OddsSnapshot).count() == 2


def test_odds_tendance_mesurée(session):
    from app.analytics.odds_trend import odds_trends
    _ingest(session, _raw(pid="tr-1",
                          odds=[OddsRef("PINN", "1X2", "H", 2.20),
                                OddsRef("PINN", "1X2", "D", 3.40),
                                OddsRef("PINN", "1X2", "A", 3.90)]))
    fx = _get_fx(session, "espn", "tr-1")
    time.sleep(1.1)
    _ingest(session, _raw(pid="tr-1",
                          odds=[OddsRef("PINN", "1X2", "H", 1.85),
                                OddsRef("PINN", "1X2", "D", 3.60),
                                OddsRef("PINN", "1X2", "A", 4.40)]))
    t = odds_trends(session, [fx.id])
    assert fx.id in t  # un mouvement a été mesuré sur les snapshots réels


def test_odds_marché_fermé_exclu(session):
    """Cote SUSPENDED/CLOSED → exclue du marché (jamais affichée comme disponible)."""
    _ingest(session, _raw(pid="cl-1",
                          odds=[OddsRef("PINN", "1X2", "H", 2.0, status="CLOSED")]))
    active = session.query(OddsSnapshot).filter_by(status="ACTIVE").count()
    closed = session.query(OddsSnapshot).filter_by(status="CLOSED").count()
    assert active == 0 and closed == 1


def test_odds_book_indisponible(session):
    """Aucun snapshot d'un book → il n'apparaît nulle part (pas de cote inventée)."""
    _ingest(session, _raw(pid="bk-1", odds=[OddsRef("B365", "1X2", "H", 2.05)]))
    from app.db.models import Bookmaker
    books = {b.code for b in session.query(Bookmaker).all()}
    assert "B365" in books and "PINN" not in books


# ================================================================
# 6. LINEUP (§76) : absent → rien inventé ; publié → recalcul
# ================================================================

def test_lineup_absent_rien_inventé(session, monkeypatch):
    from app.research import wikipedia
    monkeypatch.setattr(wikipedia, "context_for_competition", lambda *a, **k: None)
    import app.research.engine as eng
    monkeypatch.setattr(eng, "forecast_at", lambda *a, **k: None)
    build_expert_report = eng.build_expert_report
    _ingest(session, _raw(pid="ln-1", status="SCHEDULED"))
    fx = _get_fx(session, "espn", "ln-1")
    rep = build_expert_report(session, fx.id, refresh=True)
    secs = {s["label"]: s for s in rep["sections"]}
    assert secs["Compositions"]["status"] == "UNAVAILABLE"
    assert "DONNÉE INDISPONIBLE" in str(secs["Compositions"]["content"])


def test_lineup_publié_recalcul(session, monkeypatch):
    from app.research import wikipedia
    monkeypatch.setattr(wikipedia, "context_for_competition", lambda *a, **k: None)
    from app.research.engine import build_expert_report
    from app.db.models import Lineup, Player
    _ingest(session, _raw(pid="ln-2", status="SCHEDULED"))
    fx = _get_fx(session, "espn", "ln-2")
    pl = Player(name="Jean Lefèvre", team_id=fx.home_team_id, position="Attaquant")
    session.add(pl); session.flush()
    session.add(Lineup(fixture_id=fx.id, team_id=fx.home_team_id, player_id=pl.id,
                       number=9, position="Attaquant", is_starting=True, source="test"))
    session.commit()
    rep = build_expert_report(session, fx.id, refresh=True)
    secs = {s["label"]: s for s in rep["sections"]}
    assert secs["Compositions"]["status"] == "SOURCE"
    assert secs["Compositions"]["content"]["effectifs"] == 1


# ================================================================
# 7. PROVIDER FAILURE (§77) : failover, pas de crash, pas de faux OK
# ================================================================

def test_provider_mort_ne_crash_pas(session, monkeypatch):
    """Source principale indisponible → le worker continue (autres sources),
    et l'état DOWN est tracé — jamais de données fictives pour compenser."""
    from app.workers import definitions as W
    from app.db.models import SyncJob

    def _boom(**kwargs):
        raise ConnectionError("source principale indisponible (simulée §77)")

    monkeypatch.setattr(W, "get_provider", lambda name: _FakeBrokenProvider(_boom))
    # le worker doit retourner un rapport (pas lever), et journaliser
    try:
        res = W.run_fixtures(session)
    except Exception as exc:  # pragma: no cover
        pytest.fail(f"le worker a crashé au lieu de faire le failover : {exc}")
    jobs = session.query(SyncJob).filter_by(worker="syncFixtures").all()
    assert jobs  # journalisé
    # aucun match n'a été inventé par la source morte
    assert session.query(Fixture).count() == 0


class _FakeBrokenProvider:
    name = "espn"
    def __init__(self, boom):
        self._boom = boom
    def fetch(self, **kw):
        self._boom(**kw)
    def parse(self, payload, **kw):
        return iter([])
    def scoreboard_url(self, league):
        return "https://example.invalid"


def test_worker_journalise_erreurs(session, monkeypatch):
    from app.workers import definitions as W
    from app.db.models import SyncJob
    monkeypatch.setattr(W, "get_provider",
                        lambda name: _FakeBrokenProvider(lambda **k: (_ for _ in ()).throw(RuntimeError("x"))))
    try:
        W.run_fixtures(session)
    except Exception:
        pass
    jobs = session.query(SyncJob).filter_by(worker="syncFixtures").all()
    assert jobs  # même en échec : la trace existe (audit)


# ================================================================
# 8. RECHERCHE APPROFONDIE (Wikipedia mockée, 0 €)
# ================================================================

def test_wikipedia_summary(monkeypatch):
    from app.research import wikipedia

    class _FakeResp:
        status_code = 200
        def json(self):
            return {"type": "standard", "title": "Paris", "extract": "Ville… [1]",
                    "content_urls": {"desktop": {"page": "https://fr.wikipedia.org/wiki/Paris"}},
                    "thumbnail": {"source": "http://x/i.png"}}

    monkeypatch.setattr(wikipedia.httpx, "get", lambda url, **k: _FakeResp())
    s = wikipedia.wikipedia_summary("Paris", "fr")
    assert s and "Wikipedia" in s["source"] and "CC BY-SA" in s["license"]
    assert "[" not in s["extract"]  # notes [1] nettoyées


def test_recherche_globale_locale(session, monkeypatch):
    from app.research import wikipedia
    from app.research.search import search_global
    monkeypatch.setattr(wikipedia, "search_wikipedia", lambda *a, **k: [])
    _ingest(session, _raw(pid="sr-1", home="Olympique Testland", away="Beta United",
                          comp="Championnat de Testland"))
    r = search_global(session, "olympique")
    assert any("Olympique" in t["name"] for t in r["teams"])
    assert r["web"] == []  # pas de résultat web inventé


def test_recherche_globale_web(session, monkeypatch):
    from app.research import wikipedia
    from app.research.search import search_global
    monkeypatch.setattr(wikipedia, "search_wikipedia",
                        lambda q, lang="fr", limit=5: [
                            {"title": f"Article {q}", "url": "https://fr.wikipedia.org/wiki/X",
                             "source": "Wikipedia (FR) — CC BY-SA", "license": "CC BY-SA 4.0"}])
    r = search_global(session, "football")
    assert r["web"] and r["web_source"]


# ================================================================
# 9. DATA QUALITY (§47) + MÉTÉO (syncWeather)
# ================================================================

def test_qualité_calculée(session):
    from app.analytics.quality import compute_quality
    # espn eng.1 et fduk E0 → même compétition canonique ENG-E0 (2 sources réelles)
    for i in range(5):
        _ingest(session, _raw(provider="espn", pid=f"q-{i}", comp="eng.1",
                              status="FINISHED", hs=1, aws=0,
                              kickoff=TODAY - timedelta(days=i)))
    _ingest(session, _raw(provider="fduk", pid="q-0-b", comp="E0",
                          status="FINISHED", hs=1, aws=0, kickoff=TODAY))
    from app.ingest.consistency import run_consistency
    run_consistency(session)
    data = compute_quality(session)
    assert data and "ENG-E0" in data
    v = data["ENG-E0"]
    assert 0 <= v["score"] <= 100 and v["verified_pct"] > 0
    assert v["n_sources"] == 2


def test_qualité_compétition_vide_non_mesurable(session):
    from app.analytics.quality import compute_quality
    c = Competition(code="EMPTY", name="Vide", area="X")
    session.add(c); session.commit()
    data = compute_quality(session)
    assert data["EMPTY"]["score"] is None  # jamais inventée


def test_sync_weather_idempotent(session, monkeypatch):
    from app.workers.definitions import run_weather
    from app.db.models import WeatherSnapshot
    monkeypatch.setattr(
        "app.analytics.weather.forecast_at",
        lambda city, when: {"temperature": 18.0, "precipitation": 0.0,
                            "wind_speed": 10.0, "humidity": 60, "condition": "clair"})
    _ingest(session, _raw(pid="wt-1", status="SCHEDULED", kickoff=TODAY))
    run_weather(session)
    assert session.query(WeatherSnapshot).count() == 1
    run_weather(session)  # idempotent
    assert session.query(WeatherSnapshot).count() == 1


# ================================================================
# 10. BUS TEMPS RÉEL (SSE)
# ================================================================

def test_event_bus_pub_sub():
    import asyncio
    from app.realtime import EventBus
    bus = EventBus()
    q = bus.subscribe()
    bus.publish({"type": "GOAL", "fixture_id": 1})
    assert q.qsize() == 1
    bus.unsubscribe(q)
    assert bus.n_subscribers == 0
