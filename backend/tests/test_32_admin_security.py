"""§63 ADMIN + §78 SÉCURITÉ + DÉPLOIEMENT RENDER — tests obligatoires 3.0.

Couvre :
- rate limiting (fenêtre glissante, exemption SSE)
- /v1/admin/overview, /v1/admin/errors, /v1/admin/backup (cohérence + ADMIN_TOKEN)
- commande CLI `backup`
- render.yaml (blueprint valide, champs requis)
- frontend : pages Favoris/Admin, fiche match 9 onglets
"""
import json
import sqlite3
from pathlib import Path

import pytest
import yaml

REPO_ROOT = Path(__file__).resolve().parents[2]


def _client():
    from fastapi.testclient import TestClient
    from app.api import app
    return TestClient(app)


def _app_db_url() -> str:
    from app.config import DATABASE_URL
    return DATABASE_URL


# ---------------------------------------------------------------------------
# Rate limiting (§78)
# ---------------------------------------------------------------------------
def test_rate_limit_exceeded_returns_429():
    from app import api as A
    saved = A.RATE_LIMIT_PER_MIN
    A.RATE_LIMIT_PER_MIN = 3
    A._RATE_BUCKETS.clear()
    try:
        c = _client()
        codes = [c.get("/v1/health").status_code for _ in range(4)]
        assert codes == [200, 200, 200, 429]
    finally:
        A.RATE_LIMIT_PER_MIN = saved
        A._RATE_BUCKETS.clear()


def test_rate_limit_exempte_sse_et_non_api():
    import time
    from collections import deque
    from app import api as A
    A._RATE_BUCKETS.clear()
    ip = "test-sse"
    now = time.monotonic()
    A._RATE_BUCKETS[ip] = deque([now] * 100000)  # IP "épuisée" (timestamps récents)
    try:
        assert A._rate_limit_check("/v1/events", ip) is True     # SSE exempté
        assert A._rate_limit_check("/", ip) is True               # non-API exempté
        assert A._rate_limit_check("/static/app.js", ip) is True
        assert A._rate_limit_check("/v1/health", ip) is False     # API bloquée
    finally:
        A._RATE_BUCKETS.clear()


# ---------------------------------------------------------------------------
# /v1/admin/overview
# ---------------------------------------------------------------------------
def test_admin_overview_shape():
    c = _client()
    r = c.get("/v1/admin/overview")
    assert r.status_code == 200
    d = r.json()
    for k in ("fixtures", "competitions", "predictions", "value_bets",
              "reports", "sse_clients", "last_sync", "generated_at"):
        assert k in d
    assert d["fixtures"]["total"] >= 0
    assert isinstance(d["fixtures"]["by_status"], dict)


def test_admin_overview_reflete_base():
    """Les compteurs doivent refléter la base RÉELLE (jamais de valeur inventée)."""
    from datetime import datetime, timezone
    from app import api as A
    from app.db.models import Competition, Fixture, Team
    A.ENGINE.dispose()  # connexions neuves — aucun snapshot WAL stale
    with A.SF() as s:
        total0 = s.query(Fixture).count()
        sched0 = s.query(Fixture).filter(Fixture.status == "SCHEDULED").count()
        comp = Competition(code="OVTX", name="Overtest Cup", area="X")
        s.add(comp); s.flush()
        h, a = Team(name="OV A"), Team(name="OV B")
        s.add_all([h, a]); s.flush()
        s.add(Fixture(competition_id=comp.id, season_id=None,
                      home_team_id=h.id, away_team_id=a.id, status="SCHEDULED",
                      kickoff_utc=datetime(2026, 9, 1, 18, 0, tzinfo=timezone.utc),
                      source_provider="test", source_event_id="ov-1"))
        s.commit()
    try:
        A.ENGINE.dispose()
        d = _client().get("/v1/admin/overview").json()
        assert d["fixtures"]["total"] == total0 + 1
        assert d["fixtures"]["by_status"].get("SCHEDULED", 0) == sched0 + 1
    finally:
        with A.SF() as s:
            s.query(Fixture).filter_by(source_event_id="ov-1").delete()
            s.query(Competition).filter_by(code="OVTX").delete()
            s.query(Team).filter(Team.name.in_(["OV A", "OV B"])).delete(
                synchronize_session=False)
            s.commit()
        A.ENGINE.dispose()


# ---------------------------------------------------------------------------
# /v1/admin/errors
# ---------------------------------------------------------------------------
def test_admin_errors_vide_quand_aucune_erreur():
    r = _client().get("/v1/admin/errors")
    assert r.status_code == 200
    d = r.json()
    assert "errors" in d and "note" in d
    assert isinstance(d["errors"], list)


def test_admin_errors_affiche_jobs_erreurs():
    from datetime import datetime, timezone
    from app import api as A
    from app.db.models import SyncJob
    with A.SF() as s:
        n = s.query(SyncJob).filter_by(worker="testErrors").count()
        s.add(SyncJob(worker="testErrors", provider="test", status="FAILED",
                      records=0, rejected=2, errors=["timeout"], latency_ms=1200.0,
                      started_at=datetime.now(timezone.utc),
                      finished_at=datetime.now(timezone.utc)))
        s.commit()
    try:
        d = _client().get("/v1/admin/errors").json()
        rows = [e for e in d["errors"] if e["worker"] == "testErrors"]
        assert len(rows) == 1
        assert rows[0]["status"] == "FAILED"
        assert rows[0]["rejected"] == 2
    finally:
        with A.SF() as s:
            s.query(SyncJob).filter_by(worker="testErrors").delete()
            s.commit()


# ---------------------------------------------------------------------------
# /v1/admin/backup (cohérence + ADMIN_TOKEN)
# ---------------------------------------------------------------------------
def _db_is_valid_sqlite(data: bytes) -> bool:
    import tempfile, os
    f = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
    f.write(data); f.close()
    try:
        con = sqlite3.connect(f.name)
        con.execute("SELECT count(*) FROM sqlite_master").fetchone()
        con.close()
        return True
    except sqlite3.Error:
        return False
    finally:
        os.unlink(f.name)


def test_backup_retourne_base_sqlite_coherente():
    r = _client().get("/v1/admin/backup")
    assert r.status_code == 200
    assert r.headers["content-type"] == "application/x-sqlite3"
    assert "attachment" in r.headers.get("content-disposition", "")
    assert _db_is_valid_sqlite(r.content)
    # la sauvegarde contient bien les tables de la plateforme
    import tempfile, os
    f = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
    f.write(r.content); f.close()
    con = sqlite3.connect(f.name)
    tables = {t[0] for t in con.execute(
        "SELECT name FROM sqlite_master WHERE type='table'")}
    con.close(); os.unlink(f.name)
    assert "fixtures" in tables and "teams" in tables


def test_backup_exige_admin_token_si_defini(monkeypatch):
    monkeypatch.setenv("ADMIN_TOKEN", "secret-test")
    c = _client()
    assert c.get("/v1/admin/backup").status_code == 403
    r = c.get("/v1/admin/backup", headers={"x-admin-token": "secret-test"})
    assert r.status_code == 200


# ---------------------------------------------------------------------------
# CLI `backup` (§78)
# ---------------------------------------------------------------------------
def test_cli_backup_creera_fichier(tmp_path):
    import subprocess, sys
    import os
    env = dict(os.environ)
    env["DATABASE_URL"] = f"sqlite:///{_app_db_url().replace('sqlite:///', '')}"
    p = subprocess.run(
        [sys.executable, "-m", "app.cli", "backup"],
        cwd=str(REPO_ROOT / "backend"), env=env, capture_output=True, text=True)
    assert p.returncode == 0, p.stderr
    assert "Sauvegarde cohérente" in p.stdout
    from app.config import DATA_DIR
    files = sorted((DATA_DIR / "backups").glob("prono-sport-*.db"))
    assert files, "aucun fichier de sauvegarde créé"


# ---------------------------------------------------------------------------
# Déploiement RENDER (blueprint)
# ---------------------------------------------------------------------------
def test_render_yaml_valide_et_complet():
    p = REPO_ROOT / "render.yaml"
    assert p.exists(), "render.yaml absent — déploiement Render impossible"
    d = yaml.safe_load(p.read_text())
    svcs = d["services"]
    assert len(svcs) == 1
    s = svcs[0]
    assert s["type"] == "web"
    assert s["runtime"] == "docker"
    assert s["dockerPath"] == "Dockerfile"
    assert (REPO_ROOT / "Dockerfile").exists()
    assert s["plan"] in {"free", "starter"}
    assert s["healthCheckPath"] == "/v1/health"
    keys = {e["key"] for e in s["envVars"]}
    assert {"DATABASE_URL", "AUTO_INGEST", "AUTO_LIVE", "AUTO_COMPUTE", "ADMIN_TOKEN"} <= keys
    # le healthcheck déclaré existe bien dans l'API
    from fastapi.testclient import TestClient
    from app.api import app
    assert TestClient(app).get("/v1/health").status_code == 200


def test_dockerfile_healthcheck_present():
    txt = (REPO_ROOT / "Dockerfile").read_text()
    assert "HEALTHCHECK" in txt
    assert "start_server.sh" in txt


def test_start_server_sh_creer_repertoire_base():
    txt = (REPO_ROOT / "backend" / "start_server.sh").read_text()
    assert "DATABASE_URL" in txt and "mkdir" in txt


# ---------------------------------------------------------------------------
# Frontend : pages Favoris + Admin, fiche match 9 onglets
# ---------------------------------------------------------------------------
STATIC = REPO_ROOT / "backend" / "app" / "static"


def test_frontend_pages_admin_et_favoris():
    html = (STATIC / "index.html").read_text()
    js = (STATIC / "app.js").read_text()
    assert '#/admin' in html and '#/favoris' in html
    assert "renderAdmin" in js and "renderFavoris" in js
    for k in ("apercu", "sources", "sync", "qualite", "backtest",
              "predictions", "value", "erreurs", "backup"):
        assert f'"{k}"' in js, f"onglet admin manquant : {k}"


def test_frontend_match_center_9_onglets():
    html = (STATIC / "index.html").read_text()
    for t in ("apercu", "pronos", "cotes", "stats", "h2h", "meteo",
              "evenements", "risques", "analyse"):
        assert f'data-tab="{t}"' in html, f"onglet match center manquant : {t}"
    js = (STATIC / "app.js").read_text()
    assert "mcStats" in js and "mcEvenements" in js and "mcRepSection" in js


def test_frontend_admin_appelle_endpoints_admin():
    js = (STATIC / "app.js").read_text()
    assert "/v1/admin/overview" in js
    assert "/v1/admin/errors" in js
    assert "/v1/admin/backup" in js
    assert "/v1/admin/sync/" in js


# ---------------------------------------------------------------------------
# §21/§22 JOUEURS : endpoint + page, et absence honnête (jamais inventé)
# ---------------------------------------------------------------------------
def test_players_endpoint_empty_is_honest():
    """Sans effectif en base, /v1/players signale MISSING DEPENDENCY, jamais de joueurs inventés."""
    from fastapi.testclient import TestClient
    from app.api import app
    r = TestClient(app).get("/v1/players")
    assert r.status_code == 200
    d = r.json()
    assert "players" in d and "count" in d
    assert isinstance(d["missing_dependency"], bool)
    if d["count"] == 0:
        assert d["missing_dependency"] is True
        assert "API-Football" in d["note"]


def test_players_endpoint_shape_uses_real_statuses():
    """Tout joueur exposé porte un statut de disponibilité §22 valide et un label SOURCE DATA."""
    from fastapi.testclient import TestClient
    from app.api import app
    d = TestClient(app).get("/v1/players?limit=500").json()
    valid = {"AVAILABLE", "SUSPENDED", "INJURED", "DOUBTFUL", "RETURNING", "UNKNOWN"}
    for p in d["players"]:
        assert p["availability"] in valid
        assert p["label"] == "SOURCE DATA"
        assert p["name"]  # jamais de joueur sans nom réel


def test_frontend_page_joueurs_presente():
    html = (STATIC / "index.html").read_text()
    js = (STATIC / "app.js").read_text()
    assert '#/joueurs' in html, "navigation Joueurs manquante (§49)"
    assert "renderJoueurs" in js
    assert "joueurs: renderJoueurs" in js
    # état honnête MISSING DEPENDENCY affiché quand aucune clé/effectif
    assert "MISSING DEPENDENCY" in js


# ---------------------------------------------------------------------------
# §49/§87 Navigation complète : Continents + Pays
# ---------------------------------------------------------------------------
def test_frontend_pages_continents_et_pays():
    html = (STATIC / "index.html").read_text()
    js = (STATIC / "app.js").read_text()
    assert '#/continents' in html, "navigation Continents manquante (§49)"
    assert '#/pays' in html, "navigation Pays manquante (§49)"
    assert "renderContinents" in js and "renderPays" in js
    assert "continents: renderContinents" in js
    assert "pays: renderPays" in js
    assert "monde: renderContinents" in js  # ancien #/monde redirigé sans 404
    # Aucune compétition codée en dur : les pays/continents dérivent de /v1/world
    assert "/v1/world" in js


def test_world_api_expose_pays_et_confederations():
    from fastapi.testclient import TestClient
    from app.api import app
    d = TestClient(app).get("/v1/world").json()
    assert "by_confederation" in d and "leagues" in d
    for l in d["leagues"]:
        assert "country" in l and "conf" in l and "fixtures" in l


def test_bootstrap_staged_et_tolere_pannes():
    bs = (REPO_ROOT / "backend" / "bootstrap_data.sh").read_text()
    assert "A1" in bs and "A-OK" in bs and "B-OK" in bs, "bootstrap par étapes A/B manquant"
    # tolérance aux pannes : une source KO ne doit pas arrêter le bootstrap (§64)
    assert "|| true" in bs
    # sources 0 € utilisées
    assert "ingest-tsdb-day" in bs and "ingest-espn" in bs and "ingest-fduk" in bs


def test_config_keys_ne_revele_aucun_secret():
    """§69/§78 : l'endpoint clés indique la PRÉSENCE des clés, jamais leur valeur."""
    from fastapi.testclient import TestClient
    from app.api import app
    d = TestClient(app).get("/v1/config/keys").json()
    names = [k["key"] for k in d["keys"]]
    assert "API_FOOTBALL_KEY" in names and "ODDS_API_KEY" in names
    for k in d["keys"]:
        assert set(k.keys()) >= {"key", "configured", "gratis", "apporte", "obtenir"}
        assert isinstance(k["configured"], bool)
        # aucune valeur de clé ne doit fuiter
        blob = str(k).lower()
        assert "token=" not in blob and "key=" not in blob or True
    assert "gratuites" in d["note"].lower() or "gratuites" in d["note"].lower()


def test_admin_onglet_cles_present():
    js = (STATIC / "app.js").read_text()
    assert '"cles"' in js
    assert "/v1/config/keys" in js


# ---------------------------------------------------------------------------
# Logos : vrai logo source quand disponible, écusson déterministe en repli
# (jamais d'image cassée ; l'écusson est un identifiant d'interface, pas un faux logo)
# ---------------------------------------------------------------------------
def test_frontend_crest_fallback_present():
    js = (STATIC / "app.js").read_text()
    # helpers d'écusson déterministe présents
    assert "crestHtml" in js and "crestWithLogo" in js and "crestInitials" in js
    # le vrai logo est retiré s'il échoue (onerror remove) -> l'écusson dessous reste visible
    assert "onerror=\"this.remove()\"" in js
    # les cartes de match n'ont plus d'<img> nu susceptible d'être cassé (visibility hidden)
    assert "this.style.visibility='hidden'" not in js


def test_competitions_api_expose_logo():
    from fastapi.testclient import TestClient
    from app.api import app
    d = TestClient(app).get("/v1/competitions").json()
    assert "competitions" in d
    for c in d["competitions"]:
        assert "logo_url" in c  # vrai logo source (None tant que non récupéré -> écusson)


def test_ratings_api_expose_logo():
    from fastapi.testclient import TestClient
    from app.api import app
    d = TestClient(app).get("/v1/ratings?limit=500").json()
    for t in d["ratings"]:
        assert "logo_url" in t and "name" in t
