"""Régistre de sources + worker `discoverSources`.

- ensure_sources() : inscrit les candidats du catalogue (idempotent).
- run_discovery()  : passe le registre au pipeline TEST → VALIDATE → QUALITY
  et recalcule la fiabilité sur l'observé. Worker journalisé (SyncJob).
"""
from __future__ import annotations

import time
from datetime import datetime, timezone

from sqlalchemy.orm import Session

from ..db.models import DataSource, SyncJob
from .catalog import CANDIDATES
from .checker import check_source, compute_reliability


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


# Correspondance avec les noms legacy (seed 2.0) pour éviter les doublons au registre
LEGACY_ALIASES = {
    "ESPN": "espn",
    "football-data.co.uk": "fduk",
    "football-data.org": "fdorg",
    "OpenLigaDB": "openligadb",
    "TheSportsDB": "tsdb",
}


def legacy_name(name: str) -> str | None:
    return LEGACY_ALIASES.get(name)


def ensure_sources(session: Session) -> int:
    """Inscrit (sans écraser l'état observé) toutes les sources du catalogue.

    Fusionne les lignes legacy (noms courts 2.0) avec leurs entrées catalogue :
    une seule ligne par source réelle, l'historique observé est conservé.
    """
    created = 0
    for cand in CANDIDATES:
        row = session.query(DataSource).filter_by(name=cand.name).one_or_none()
        legacy_n = legacy_name(cand.name)
        legacy = (session.query(DataSource).filter_by(name=legacy_n).one_or_none()
                  if legacy_n else None)
        if row is None and legacy is not None:
            legacy.name = cand.name  # adopte la ligne legacy (historique observé conservé)
            row = legacy
        elif row is not None and legacy is not None and legacy.id != row.id:
            session.delete(legacy)  # les deux existaient : on garde la ligne catalogue
            session.flush()
        if row is None:
            row = DataSource(name=cand.name, kind=cand.kind, base_url=cand.base_url)
            session.add(row)
            created += 1
        # champs descriptifs : toujours alignés sur le catalogue (documentés)
        row.kind = cand.kind
        row.base_url = cand.base_url
        row.data_categories = cand.data_categories
        row.coverage = cand.coverage
        row.update_frequency = cand.update_frequency
        row.requires_key = cand.requires_key
        row.attribution_required = cand.attribution_required
        if row.terms_status is None:
            row.terms_status = cand.terms_status
        if row.status is None:
            row.status = "APPROVED" if cand.verified else "DISCOVERED"
        # fiabilité initiale : uniquement si le candidat a réellement été vérifié,
        # sinon NULL (jamais inventée). L'observé prendra le relais.
        if row.reliability_score is None:
            row.reliability_score = cand.reliability_hints.get("initial")
    session.commit()
    return created


def run_discovery(session: Session, offline: bool = False, only: str | None = None) -> dict:
    """Worker discoverSources : teste chaque source active, met à jour le registry.

    - sources requiring une clé absente → skip (absence de dépendance, §95)
    - termes TO_VERIFY/FORBIDDEN → pas de test d'utilisation (seule la reachabilité
      est mesurée pour les sources OK ; les autres restent non actives)
    """
    t0 = time.perf_counter()
    results: dict[str, dict] = {}
    sources = session.query(DataSource).order_by(DataSource.name).all()
    n_ok = 0
    for src in sources:
        if only and src.name != only:
            continue
        if src.requires_key:
            from .catalog import by_name
            cand = by_name(src.name)
            key_env = cand.key_env if cand else None
            import os
            if key_env and not os.environ.get(key_env):
                results[src.name] = {"skipped": True,
                                     "reason": "MISSING DEPENDENCY — clé gratuite absente "
                                               f"({key_env}) ; source optionnelle désactivée"}
                continue
        res = check_source(session, src, offline=offline)
        results[src.name] = res
        if res.get("ok"):
            n_ok += 1
    # fiabilité sur l'observé (remplace les valeurs initiales une fois mesurable)
    for src in sources:
        observed = compute_reliability(session, src)
        if observed is not None:
            src.reliability_score = observed
    session.commit()
    return {
        "worker": "discoverSources",
        "offline": offline,
        "checked": len(results),
        "ok": n_ok,
        "down": len(sources) - n_ok - sum(1 for r in results.values() if r.get("skipped")),
        "skipped": sum(1 for r in results.values() if r.get("skipped")),
        "results": results,
        "latency_ms": round((time.perf_counter() - t0) * 1000),
    }


def log_job(session: Session, worker: str, provider: str | None, status: str,
            records: int | None = None, created: int | None = None,
            updated: int | None = None, rejected: int | None = None,
            latency_ms: float | None = None, errors: list | None = None,
            started_at: datetime | None = None) -> SyncJob:
    """Journalise une exécution de worker (§14 : tout worker est journalisé)."""
    job = SyncJob(
        worker=worker, provider=provider, status=status, records=records,
        created=created, updated=updated, rejected=rejected,
        latency_ms=latency_ms, errors=errors,
        started_at=started_at or utcnow(), finished_at=utcnow(),
    )
    session.add(job)
    session.commit()
    return job
