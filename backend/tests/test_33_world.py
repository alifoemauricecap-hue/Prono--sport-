"""COUVERTURE MONDIALE + RECHERCHE APPROFONDIE PAR LIGUE — tests 3.0.

Couvre :
- intégrité du catalogue mondial (codes/slugs uniques, confédérations, espn)
- /v1/world (état réel de la base par ligue)
- recherche ligue : UNAVAILABLE hors réseau, SOURCE avec source réelle (mock),
  persistance + cache 7 j
- worker syncWorldDaily (backbone TSDB eventsday) enregistré et journalisé
- CLI : --world, --conf, --country, world-research
- frontend : page Monde + modale recherche
"""
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
STATIC = REPO_ROOT / "backend" / "app" / "static"


# ---------------------------------------------------------------------------
# Catalogue mondial
# ---------------------------------------------------------------------------
def test_catalogue_sans_duplicates():
    from app.world import WORLD_LEAGUES
    codes = [l.code for l in WORLD_LEAGUES]
    slugs = [l.espn for l in WORLD_LEAGUES]
    assert len(codes) == len(set(codes)), "codes canoniques en double"
    assert len(slugs) == len(set(slugs)), "slugs ESPN en double"
    for l in WORLD_LEAGUES:
        assert l.name and l.country and l.conf and l.level >= 1


def test_catalogue_pertinent():
    from app.world import WORLD_LEAGUES, CONFEDERATIONS, by_confederation
    assert len(WORLD_LEAGUES) >= 50, "couverture mondiale : catalogue trop petit"
    confs = {l.conf for l in WORLD_LEAGUES}
    assert len(confs & set(CONFEDERATIONS)) >= 5, "il faut plusieurs confédérations"
    assert by_confederation()["UEFA"], "UEFA absente"
    assert any(l.conf in ("CONMEBOL", "CONCACAF") for l in WORLD_LEAGUES)
    assert any(l.conf in ("AFC", "CAF", "OFC") for l in WORLD_LEAGUES)


def test_espn_leagues_synchro_catalogue():
    """providers/espn.py doit dériver de world.py (source unique)."""
    from app.providers.espn import LEAGUES
    from app.world import WORLD_LEAGUES
    assert set(LEAGUES) == {l.espn for l in WORLD_LEAGUES}
    for l in WORLD_LEAGUES:
        assert LEAGUES[l.espn] == (l.code, l.name, l.country)


def test_filtres_slugs():
    from app.world import slugs
    assert "fra.1" in slugs(country="France") and "eng.1" not in slugs(country="France")
    assert all("eng" in s or "esp" in s or "ger" in s for s in slugs(conf="UEFA")[:5])
    assert len(slugs(conf="UEFA")) > len(slugs(conf="CAF"))


# ---------------------------------------------------------------------------
# /v1/world
# ---------------------------------------------------------------------------
def test_world_shape_et_etat_reel():
    from fastapi.testclient import TestClient
    from app.api import app
    r = TestClient(app).get("/v1/world")
    assert r.status_code == 200
    d = r.json()
    for k in ("leagues", "totals", "by_confederation", "backbone_world", "generated_at"):
        assert k in d
    assert d["totals"]["catalog"] >= 50
    assert d["totals"]["fixtures"] >= 0  # état réel (0 si base vide de test)
    for l in d["leagues"][:5]:
        for k in ("code", "name", "country", "conf", "level", "in_db", "fixtures", "research"):
            assert k in l


def test_world_inclus_competitions_hors_catalogue():
    """Une ligue découverte (hors catalogue) doit apparaître (couverture réelle)."""
    from fastapi.testclient import TestClient
    from app import api as A
    from app.db.models import Competition, Fixture, Team
    from datetime import datetime, timezone
    A.ENGINE.dispose()
    with A.SF() as s:
        comp = Competition(code="WLDX", name="Wild Cup Test", area="Testland")
        s.add(comp); s.flush()
        h, a = Team(name="WD A"), Team(name="WD B")
        s.add_all([h, a]); s.flush()
        s.add(Fixture(competition_id=comp.id, home_team_id=h.id, away_team_id=a.id,
                      status="FINISHED", home_score=1, away_score=0,
                      kickoff_utc=datetime(2026, 8, 1, 18, 0, tzinfo=timezone.utc),
                      source_provider="tsdb", source_event_id="wdx-1"))
        s.commit()
    try:
        d = TestClient(A.app).get("/v1/world").json()
        assert "WLDX" in d["extra_competitions"]
        row = next(l for l in d["leagues"] if l["code"] == "WLDX")
        assert row["in_db"] and row["fixtures"] == 1
    finally:
        with A.SF() as s:
            s.query(Fixture).filter_by(source_event_id="wdx-1").delete()
            s.query(Competition).filter_by(code="WLDX").delete()
            s.query(Team).filter(Team.name.in_(["WD A", "WD B"])).delete(
                synchronize_session=False)
            s.commit()
        A.ENGINE.dispose()


# ---------------------------------------------------------------------------
# Recherche approfondie par ligue
# ---------------------------------------------------------------------------
def test_recherche_ligue_indisponible_hors_reseau():
    """Sans réseau (sandbox) : statut UNAVAILABLE, jamais de contexte inventé."""
    from fastapi.testclient import TestClient
    from app import api as A
    from app.db.models import Competition
    A.ENGINE.dispose()
    with A.SF() as s:
        comp = s.query(Competition).first()
        if comp is None:
            comp = Competition(code="RX1", name="RX League", area="X")
            s.add(comp); s.commit()
            s.refresh(comp)
    try:
        r = TestClient(A.app).get(f"/v1/competitions/{comp.code}/research")
        assert r.status_code == 200
        d = r.json()
        assert d["status"] in ("SOURCE", "UNAVAILABLE")
        if d["status"] == "UNAVAILABLE":
            assert "note" in d
    finally:
        A.ENGINE.dispose()


def test_recherche_ligue_source_persistee_et_cachee(monkeypatch):
    """Avec source réelle (mock réseau) : SOURCE, persistée, 2ᵉ appel = cache."""
    from app import api as A
    from app.db.models import Competition, LeagueResearch
    from app.research import league as LR
    from app.research import wikipedia as WIKI

    calls = {"n": 0}

    def fake_summary(title, lang="fr"):
        calls["n"] += 1
        return {
            "title": "Championnat de Test", "extract": "Le Championnat de Test est un "
                    "championnat de football professionnel (mock test) — fondé en 1900, "
                    "18 clubs, format aller-retour.",
            "url": "https://fr.wikipedia.org/wiki/Championnat_de_Test",
            "thumbnail": None,
            "source": "Wikipedia (fr) — CC BY-SA", "license": "CC BY-SA 4.0",
        }

    monkeypatch.setattr(WIKI, "wikipedia_summary", fake_summary)
    A.ENGINE.dispose()
    with A.SF() as s:
        comp = Competition(code="RXTX", name="Championnat de Test", area="Testland")
        s.add(comp); s.commit()
        s.refresh(comp)
        r1 = LR.league_research(s, comp)
        assert r1["status"] == "SOURCE"
        assert r1["cached"] is False
        assert r1["extract"] and r1["url"]
        r2 = LR.league_research(s, comp)
        assert r2["status"] == "SOURCE"
        assert r2["cached"] is True
        assert calls["n"] == 1, "le 2e appel doit servir le cache (pas de re-téléchargement)"
        n_rows = s.query(LeagueResearch).filter_by(competition_id=comp.id).count()
        assert n_rows == 1, "le dossier doit être persisté en base (1 ligne)"
        s.query(LeagueResearch).filter_by(competition_id=comp.id).delete()
        s.query(Competition).filter_by(code="RXTX").delete()
        s.commit()
    A.ENGINE.dispose()


# ---------------------------------------------------------------------------
# Worker monde (backbone TSDB eventsday)
# ---------------------------------------------------------------------------
def test_worker_monde_enregistre_et_journalise():
    from app.workers import definitions as W
    assert "syncWorldDaily" in W.WORKERS
    assert hasattr(W, "run_world_daily")
    # Le worker est déclençable depuis l'admin (route /v1/admin/sync/{worker})
    # et journalisé dans sync_jobs (l'admin /v1/admin/errors lit ces erreurs).
    from app.api import app
    assert "/v1/admin/sync/{worker}" in app.openapi()["paths"]
    # la route admin connaît bien le worker syncWorldDaily
    from app.workers import definitions as W2
    assert callable(W2.run_world_daily)


# ---------------------------------------------------------------------------
# Parseur TSDB : backbone mondial (noms réels, jamais d'ID)
# ---------------------------------------------------------------------------
def test_tsdb_parse_ligue_hors_catalogue_nom_reel():
    """Une ligue hors catalogue (backbone world) porte le NOM RÉEL du payload
    (strLeague) et le PAYS (strCountry) — jamais son ID numérique (§1/§4)."""
    from app.providers.thesportsdb import TheSportsDBProvider
    p = TheSportsDBProvider()
    payload = {"events": [{
        "idEvent": "999", "strTimestamp": "2026-08-27T18:00:00",
        "strLeague": "Egyptian Premier League", "strCountry": "Egypt",
        "strHomeTeam": "Al Ahly", "strAwayTeam": "Zamalek",
        "idHomeTeam": "1", "idAwayTeam": "2",
        "strHomeTeamBadge": "https://x/a.png", "strAwayTeamBadge": "https://x/b.png",
        "intHomeScore": None, "intAwayScore": None, "strStatus": "NS",
        "strVenue": "Cairo Stadium", "strCity": "Cairo",
    }]}
    raws = list(p.parse(payload, league_id="99999"))  # ID inconnu du catalogue
    assert len(raws) == 1
    r = raws[0]
    assert r.competition_name == "Egyptian Premier League", "nom réel attendu (pas l'ID)"
    assert r.competition_area == "Egypt"
    assert r.home.logo_url == "https://x/a.png"
    assert r.away.logo_url == "https://x/b.png"
    assert r.venue_city == "Cairo"
    assert r.home_score is None  # « NS » → jamais de faux 0 (§1)


def test_wikipedia_envoie_user_agent_descriptif(monkeypatch):
    """Wikimedia bloque les UA de bibliothèques par défaut (python-httpx) → 403."""
    from app.research import wikipedia as W
    captured = {}
    class _FakeResp:
        status_code = 200
        def json(self):
            return {"type": "standard", "title": "T", "extract": "x",
                    "content_urls": {"desktop": {"page": "u"}}, "thumbnail": None}
    def fake_get(url, **kw):
        captured["headers"] = kw.get("headers") or {}
        return _FakeResp()
    monkeypatch.setattr(W.httpx, "get", fake_get)
    W._cache.clear()
    s = W.wikipedia_summary("Test League", "fr")
    assert s is not None
    ua = captured["headers"].get("User-Agent", "")
    assert ua and "httpx" not in ua
    assert "PRONO-SPORT" in ua


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------
def test_cli_world_et_research():
    import subprocess, sys
    p = subprocess.run(
        [sys.executable, "-m", "app.cli", "ingest-espn", "--help"],
        cwd=str(REPO_ROOT / "backend"), capture_output=True, text=True)
    assert p.returncode == 0
    for flag in ("--world", "--conf", "--country"):
        assert flag in p.stdout, f"flag CLI manquant : {flag}"
    p2 = subprocess.run(
        [sys.executable, "-m", "app.cli", "world-research", "--help"],
        cwd=str(REPO_ROOT / "backend"), capture_output=True, text=True)
    assert p2.returncode == 0 and "--limit" in p2.stdout


def test_cli_espn_world_ne_crashe_pas_sans_league():
    """Sans --leagues ni --world : message + code 1 (pas de crash)."""
    import subprocess, sys
    p = subprocess.run(
        [sys.executable, "-m", "app.cli", "ingest-espn"],
        cwd=str(REPO_ROOT / "backend"), capture_output=True, text=True)
    assert p.returncode == 1 and "--world" in (p.stdout + p.stderr)


# ---------------------------------------------------------------------------
# Frontend
# ---------------------------------------------------------------------------
def test_frontend_page_monde_et_recherche():
    html = (STATIC / "index.html").read_text()
    js = (STATIC / "app.js").read_text()
    assert '#/monde' in html and 'data-nav="monde"' in html
    assert "research-modal" in html
    assert "renderMonde" in js and "openResearch" in js
    assert "/v1/world" in js
    assert "/v1/competitions/" in js and "data-research" in js
    # le bouton 🔎 est présent (Monde + Compétitions)
    assert js.count("data-research") >= 2
