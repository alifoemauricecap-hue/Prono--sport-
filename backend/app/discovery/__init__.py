"""Moteur de découverte des sources — PRONO SPORT 3.0.

Cycle de vie d'une source :
    DISCOVERED → TESTING → VALIDATED → APPROVED
                        ↘ REJECTED / NOT_ALLOWED
    (observé en continu) → DOWN → ré-essai → APPROVED

Règles absolues :
- La fiabilité est TOUJOURS calculée sur l'observé (sync_jobs / provider_health) ;
  une source nouvelle a reliability_score = NULL.
- Aucune source n'est automatiquement fiable à l'arrivée.
- terms_status = TO_VERIFY / FORBIDDEN → jamais utilisée (pas de contournement).
- Tout est 0 € : les sources nécessitant une clé (gratuite) sont optionnelles.
"""
from .catalog import CANDIDATES, CATEGORIES_FR
from .checker import check_source, compute_reliability
from .engine import ensure_sources, run_discovery

__all__ = [
    "CANDIDATES", "CATEGORIES_FR",
    "check_source", "compute_reliability",
    "ensure_sources", "run_discovery",
]
