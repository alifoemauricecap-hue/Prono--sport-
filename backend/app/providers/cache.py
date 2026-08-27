"""CACHE INTELLIGENT DES SOURCES (§65).

Actif uniquement si la variable d'environnement PS_CACHE_DIR est définie
(répertoire local). Sur une machine normale (PS_CACHE_DIR absente), les
providers appellent le réseau directement — aucun changement de comportement.

Comportement (jamais de donnée inventée, §1) :
1. Cache frais (< ttl)  → servi SANS appel réseau.
2. Réseau OK            → réponse réseau, cache mis à jour.
3. Réseau KO + cache    → le dernier contenu RÉEL est servi (stagé, auditable
                           via l'origine renvoyée) — c'est toujours de la
                           donnée réelle, simplement plus ancienne.
4. Réseau KO + rien     → l'erreur est propagée (source DOWN, failover §64).

La clé de cache est le SHA-1 de (url + paramètres triés) : équivalent d'un
content-hash par requête.
"""
from __future__ import annotations

import hashlib
import json
import os
import time

import httpx

from ..config import HTTP_TIMEOUT_SECONDS


def cache_dir() -> str | None:
    d = os.environ.get("PS_CACHE_DIR")
    return d or None


def cache_path_for(url: str, params: dict | None = None) -> str | None:
    d = cache_dir()
    if not d:
        return None
    key = hashlib.sha1(
        (url + json.dumps(params or {}, sort_keys=True, ensure_ascii=False)).encode("utf-8")
    ).hexdigest()
    return os.path.join(d, key + ".bin")


def _read(path: str):
    try:
        with open(path, "rb") as f:
            raw = f.read()
    except OSError:
        return None
    return raw


def _write(path: str, raw: bytes) -> None:
    try:
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "wb") as f:
            f.write(raw)
    except OSError:
        pass  # cache non critique


def http_get_json(url: str, params: dict | None = None,
                  timeout: float | None = None, ttl_seconds: int = 300,
                  allow_stale: bool = True,
                  headers: dict | None = None) -> tuple[dict, str]:
    """GET JSON avec cache. Retourne (payload, origine) — origine ∈
    CACHE | NETWORK | CACHE_STALE.

    `headers` n'est utilisé QUE sur l'appel réseau (les clés API ne sont jamais
    écrites dans le cache) et n'entre pas dans la clé de cache.
    """
    timeout = timeout or HTTP_TIMEOUT_SECONDS
    path = cache_path_for(url, params)
    stale = None
    if path:
        raw = _read(path)
        if raw is not None:
            age = time.time() - os.path.getmtime(path)
            try:
                data = json.loads(raw)
            except (ValueError, UnicodeDecodeError):
                data = None  # cache corrompu → on le reconstruit
            if data is not None:
                if age < ttl_seconds:
                    return data, "CACHE"
                if allow_stale:
                    stale = data
    try:
        r = httpx.get(url, params=params, timeout=timeout, headers=headers)
        r.raise_for_status()
        data = r.json()
        if path:
            _write(path, json.dumps(data, ensure_ascii=False).encode("utf-8"))
        return data, "NETWORK"
    except Exception:
        if stale is not None:
            return stale, "CACHE_STALE"
        raise


def http_get_text(url: str, params: dict | None = None,
                  timeout: float | None = None, ttl_seconds: int = 3600,
                  allow_stale: bool = True,
                  headers: dict | None = None) -> tuple[str, str]:
    """GET texte (CSV) avec cache — même sémantique que http_get_json."""
    raw, _origin = http_get_text_bytes(url, params=params, timeout=timeout,
                                       ttl_seconds=ttl_seconds, allow_stale=allow_stale,
                                       headers=headers)
    return raw.decode("utf-8-sig"), _origin


def http_get_text_bytes(url: str, params: dict | None = None,
                        timeout: float | None = None, ttl_seconds: int = 3600,
                        allow_stale: bool = True,
                        headers: dict | None = None) -> tuple[bytes, str]:
    """Variante binaire (pour le discovery checker) — même sémantique que http_get_text."""
    timeout = timeout or HTTP_TIMEOUT_SECONDS
    path = cache_path_for(url, params)
    stale = None
    if path:
        raw = _read(path)
        if raw is not None:
            age = time.time() - os.path.getmtime(path)
            if age < ttl_seconds:
                return raw, "CACHE"
            if allow_stale:
                stale = raw
    try:
        r = httpx.get(url, params=params, timeout=timeout, follow_redirects=True,
                      headers=headers)
        r.raise_for_status()
        if path:
            _write(path, r.content)
        return r.content, "NETWORK"
    except Exception:
        if stale is not None:
            return stale, "CACHE_STALE"
        raise
