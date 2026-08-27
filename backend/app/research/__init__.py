"""MOTEUR DE RECHERCHE APPROFONDIE — PRONO SPORT 3.0.

Recherche en ligne 100 % gratuite (0 €, sans clé payante) sur des sources
publiques fiables :
- Wikipedia (API REST publique, contenu libre CC BY-SA) → contexte, historique ;
- les sources football déjà agrégées (ESPN, fduk, OpenLigaDB…) → données réelles.

Règle §45 : la recherche alimente l'analyse ; elle ne fabrique JAMAIS de
statistique, score ou probabilité. Chaque résultat porte sa provenance.
"""
from .engine import build_expert_report, report_freshness
from .search import search_global
from .wikipedia import search_wikipedia, wikipedia_summary

__all__ = [
    "build_expert_report", "report_freshness",
    "search_global",
    "search_wikipedia", "wikipedia_summary",
]
