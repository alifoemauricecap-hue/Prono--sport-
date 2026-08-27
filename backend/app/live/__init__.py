"""MOTEUR LIVE PRONO SPORT 3.0 (§15-§17).

- Détection des événements : un BUT est DÉRIVÉ d'un changement de score observé
  entre deux lectures d'une source réelle (origine DERIVED) — jamais inventé.
- Les transitions de statut (SCHEDULED→LIVE→HALFTIME→FINISHED) sont journalisées.
- À la fin : notification MATCH_END + résolution des pronostics (WIN/LOSS/VOID/PENDING).
"""
from .events import detect_events, resolve_predictions

__all__ = ["detect_events", "resolve_predictions"]
