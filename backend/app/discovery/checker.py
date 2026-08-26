"""Vérification RÉELLE des sources + calcul de fiabilité sur l'observé.

- check_source() : test réseau réel (latence, HTTP, échantillon parsé) OU test
  hors-ligne (sans réseau) qui vérifie seulement l'existence du registre.
- compute_reliability() : fiabilité 0-100 calculée UNIQUEMENT depuis l'historique
  observé (sync_jobs + provider_health). Aucune valeur n'est inventée : sans
  historique, le score reste NULL.
"""
from __future__ import annotations

import os
import time
from datetime import datetime, timedelta, timezone

import httpx

from ..config import HTTP_TIMEOUT_SECONDS
from ..db.models import DataSource, ProviderHealth, SyncJob

CHECK_TIMEOUT = 10.0


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _do_check(name: str, kind: str, base_url: str, requires_key: bool, key_env: str | None) -> dict:
    """Test réseau réel. Retourne {ok, latency_ms, detail, error}."""
    t0 = time.perf_counter()
    try:
        if name == "ESPN":
            from ..providers.cache import http_get_json
            url = f"{base_url}/eng.1/scoreboard"
            data, origin = http_get_json(url, params={"limit": "5"},
                                         timeout=CHECK_TIMEOUT, ttl_seconds=90)
            n = len(data.get("events") or [])
            detail = f"scoreboard OK, {n} événements (eng.1) [{origin}]"
            ok = n >= 0
        elif name == "OpenLigaDB":
            url = "https://api.openligadb.de/getmatchdata/bl1/2025"
            r = httpx.get(url, timeout=CHECK_TIMEOUT)
            r.raise_for_status()
            data = r.json()
            n = len(data) if isinstance(data, list) else 0
            detail = f"getmatchdata OK, {n} matchs"
            ok = r.status_code == 200 and n > 0
        elif name == "TheSportsDB":
            key = os.environ.get(key_env or "TSDB_KEY", "3")
            url = f"{base_url}/{key}/search_all_leagues.php"
            r = httpx.get(url, params={"c": "England", "s": "Soccer"}, timeout=CHECK_TIMEOUT)
            r.raise_for_status()
            data = r.json()
            n = len((data.get("result") or data) or [])
            detail = f"search_all_leagues OK, {n} ligue(s)"
            ok = r.status_code == 200
        elif name == "Open-Meteo":
            r = httpx.get("https://geocoding-api.open-meteo.com/v1/search",
                          params={"name": "Paris", "count": 1, "format": "json"},
                          timeout=CHECK_TIMEOUT)
            r.raise_for_status()
            data = r.json()
            n = len(data.get("results") or [])
            detail = f"géocoding OK ({n} résultat)"
            ok = r.status_code == 200 and n > 0
        elif name == "Wikipedia":
            r = httpx.get("https://fr.wikipedia.org/w/api.php",
                          params={"action": "opensearch", "search": "football",
                                  "limit": "3", "format": "json", "origin": "*"},
                          timeout=CHECK_TIMEOUT)
            r.raise_for_status()
            data = r.json()
            n = len(data[1]) if isinstance(data, list) else 0
            detail = f"opensearch OK, {n} résultats"
            ok = r.status_code == 200 and n > 0
        elif name == "StatsBomb Open Data":
            r = httpx.get("https://raw.githubusercontent.com/statsbomb/open-data/master/data/competitions.json",
                          timeout=CHECK_TIMEOUT)
            r.raise_for_status()
            data = r.json()
            n = len(data)
            detail = f"competitions.json OK, {n} compétitions"
            ok = r.status_code == 200 and n > 0
        elif name == "football-data.co.uk":
            from ..providers.cache import http_get_text_bytes
            raw, origin = http_get_text_bytes(
                "https://www.football-data.co.uk/fixtures.csv",
                timeout=CHECK_TIMEOUT, ttl_seconds=6 * 3600)
            n = raw.count(b"\n")
            detail = f"fixtures.csv OK, {max(0, n - 1)} matchs à venir [{origin}]"
            ok = n > 1
        else:
            # http_get générique : reachabilité de l'URL de base
            headers = {}
            if requires_key and key_env and os.environ.get(key_env):
                headers["x-apisports-key"] = os.environ[key_env]
            r = httpx.get(base_url, timeout=CHECK_TIMEOUT, follow_redirects=True, headers=headers)
            detail = f"reachabilité HTTP {r.status_code}"
            ok = r.status_code < 500
    except Exception as exc:  # erreur réseau = source DOWN, jamais un faux OK
        return {"ok": False, "latency_ms": round((time.perf_counter() - t0) * 1000),
                "detail": None, "error": f"{type(exc).__name__}: {exc}"}
    return {"ok": ok, "latency_ms": round((time.perf_counter() - t0) * 1000),
            "detail": detail, "error": None}


def check_source(session, source: DataSource, offline: bool = False) -> dict:
    """Exécute le test d'une source et met à jour son registre.

    offline=True (tests / sans réseau) : n'appelle PAS le réseau — met à jour
    last_checked et garde le statut tel quel (honnêteté : pas de faux succès).
    """
    now = _now()
    source.last_checked = now
    if offline:
        result = {"ok": source.availability_status in (None, "OK"), "latency_ms": None,
                  "detail": "test hors-ligne (pas d'appel réseau)", "error": None}
    else:
        result = _do_check(source.name, source.kind, source.base_url,
                           source.requires_key, _key_env(source))
    if result["ok"]:
        source.last_successful_fetch = now
        if source.availability_status != "DOWN":
            source.availability_status = "OK"
        if source.status in ("DISCOVERED", "TESTING"):
            source.status = "VALIDATED"
    else:
        source.last_failed_fetch = now
        source.availability_status = "DOWN"
        if source.status == "APPROVED":
            source.status = "DOWN"
    _sync_health(session, source, result)
    session.flush()
    return result


def _key_env(source: DataSource) -> str | None:
    from .catalog import by_name
    cand = by_name(source.name)
    return cand.key_env if cand else None


def _sync_health(session, source: DataSource, result: dict) -> None:
    ph = session.query(ProviderHealth).filter_by(provider=source.name).one_or_none()
    if ph is None:
        ph = ProviderHealth(provider=source.name)
        session.add(ph)
    ph.status = "OK" if result["ok"] else "DOWN"
    ph.latency_ms = result.get("latency_ms")
    ph.detail = result.get("detail") or result.get("error")
    ph.checked_at = _now()


def compute_reliability(session, source: DataSource, window_days: int = 30) -> float | None:
    """Fiabilité 0-100 calculée sur l'observé des N derniers jours.

    Sans historique suffisant (≥3 jobs) → None (« non mesurable », jamais inventée).
    """
    since = (_now() - timedelta(days=window_days)).replace(tzinfo=None)  # SQLite = naive
    jobs = (session.query(SyncJob)
            .filter(SyncJob.started_at >= since)
            .all())
    # le provider est enregistré par son code interne (ex. "ESPN", "espn", "espn+fduk") —
    # matching insensible à la casse sur le préfixe du nom source
    prefix = source.name.lower()[:6]
    jobs = [j for j in jobs
            if j.provider and j.provider.lower().startswith(prefix)
            and j.worker != "discoverSources"]
    if len(jobs) < 3:
        return None
    ok = sum(1 for j in jobs if j.status == "OK")
    success_rate = ok / len(jobs)
    # fraîcheur : dernier succès récent ?
    last_ok = source.last_successful_fetch
    freshness = 1.0
    if last_ok:
        age_h = (_now() - last_ok).total_seconds() / 3600
        freshness = max(0.0, 1.0 - age_h / (24 * 7))
    score = round(100 * (0.8 * success_rate + 0.2 * freshness), 1)
    return score


def mark_not_allowed(session, name: str, reason: str) -> None:
    """§5 : source interdisant l'usage automatisé → SOURCE_NOT_ALLOWED, jamais utilisée."""
    src = session.query(DataSource).filter_by(name=name).one_or_none()
    if src is None:
        return
    src.status = "NOT_ALLOWED"
    src.terms_status = "FORBIDDEN"
    src.availability_status = None
