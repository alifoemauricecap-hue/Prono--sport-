"""Regroupement des matchs JUMEAUX pour l'AFFICHAGE (API) — ne fusionne JAMAIS les entités
en base (§5 : la résolution d'entités reste stricte). Un même match physique rapporté par
ESPN (« Stade de Reims ») et fduk (« Reims ») doit apparaître UNE seule fois.

Règle : mêmes compétition + même jour + similarité des DEUX côtés (domicile ET extérieur)
avec Jaccard(tokens significatifs) ≥ 0.5 ou contenu strict — sinon deux matchs distincts.
"""
from __future__ import annotations

from ..ingest.resolution import normalize_name

STOP_TOKENS = {
    "fc", "cf", "afc", "sc", "as", "ac", "sv", "sk", "fk", "bk", "rc", "ud", "cd", "ca",
    "de", "del", "la", "le", "les", "the", "club", "sporting", "real", "1", "1846",
    "sd", "se", "ec", "us", "ogc", "ssc", "uc", "stade",
}
SIMILARITY_MIN = 0.5


# Tokens qui ne prouvent PAS l'identité à eux seuls (noms de ville ou suffixes communs) :
# « paris » est partagé par Paris FC et PSG, « united » par une dizaine de clubs…
WEAK_PROOF_TOKENS = {
    "paris", "real", "united", "city", "town", "county", "athletic", "rovers",
    "dynamo", "dinamo", "lokomotiv", "spartak", "cska", "olympique", "sport",
    "borussia", "wanderers", "wanderer",
}


def strong_tokens(name: str) -> set[str]:
    toks = set(normalize_name(name or "").split())
    return {t for t in toks if t not in STOP_TOKENS}


def _alias_link(a: str, b: str) -> bool:
    """Lien prouvé via les alias administrés §5 (ex. wolves ↔ wolverhampton wanderers)."""
    from ..ingest.resolution import ALIAS_SEEDS
    na, nb = normalize_name(a), normalize_name(b)
    return ALIAS_SEEDS.get(na) == nb or ALIAS_SEEDS.get(nb) == na


def _similar(a: str, b: str) -> bool:
    na, nb = normalize_name(a), normalize_name(b)
    if not na or not nb:
        return False
    if na == nb or _alias_link(a, b):
        return True
    ta, tb = strong_tokens(a), strong_tokens(b)
    if not ta or not tb:
        return False
    inter = len(ta & tb)
    if inter / len(ta | tb) >= SIMILARITY_MIN:
        return True
    # inclusion d'un petit ensemble : acceptée SEULEMENT si elle contient un token probant
    # (≥5 lettres, hors tokens faibles) — « reims » ✓ · « paris »/« united » ✗ (PSG ≠ Paris FC)
    small = ta if len(ta) <= len(tb) else tb
    if small <= (tb if small is ta else ta):
        return any(len(t) >= 5 and t not in WEAK_PROOF_TOKENS for t in small)
    return False


def match_same_side(home_a: str, away_a: str, home_b: str, away_b: str) -> bool:
    """Deux descriptions désignent-elles le même match ? (les deux côtés doivent concorder)"""
    return _similar(home_a, home_b) and _similar(away_a, away_b)


def twin_clusters(items: list[dict], same_day_comp: bool = True) -> list[list[int]]:
    """items : [{'i': idx, 'home': str, 'away': str, 'date': str, 'comp': any}]
    → clusters d'indices jumeaux. Complexité O(n²) acceptable (≤ ~600 matchs/jour)."""
    n = len(items)
    parent = list(range(n))

    def find(x):
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    def union(a, b):
        ra, rb = find(a), find(b)
        if ra != rb:
            parent[ra] = rb

    for i in range(n):
        for j in range(i + 1, n):
            a, b = items[i], items[j]
            if same_day_comp and (a["date"] != b["date"] or a["comp"] != b["comp"]):
                continue
            if match_same_side(a["home"], a["away"], b["home"], b["away"]):
                union(i, j)
    clusters: dict[int, list[int]] = {}
    for i in range(n):
        clusters.setdefault(find(i), []).append(i)
    return list(clusters.values())
