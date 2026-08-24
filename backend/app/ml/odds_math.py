"""ODDS MATH (§31-33) : probabilités implicites, retrait de marge, EV — formules documentées.

- Probabilité implicite brute : 1/cote (jamais utilisée "réelle", §32).
- Marge (overround) retirée par normalisation proportionnelle : p_fair_i = (1/O_i) / Σ(1/O_j).
- EV = p_model × O − 1 (§33). Edge = p_model − p_fair.
- Niveaux §35 (définitions quantitatives figées ici, auditables) :
    EV < +1 %           → NO_VALUE
    +1 % ≤ EV < +3 %    → POTENTIAL_VALUE
    EV ≥ +3 % (+filtres robustesse §34) → QUALIFIED_VALUE
    EV ≥ +8 % + confiance ÉLEVÉE        → STRONG_VALUE
"""
from __future__ import annotations

LEVELS = {
    "MIN_EV_POTENTIAL": 0.01,
    "MIN_EV_QUALIFIED": 0.03,
    "MIN_EV_STRONG": 0.08,
    "MIN_EDGE_QUALIFIED": 0.02,     # edge ≥ +2 pts pour QUALIFIED (filtre robustesse §34)
    "MIN_SAMPLE_PER_TEAM": 8,       # profondeur d'historique minimale par équipe
    "MAX_MODEL_DISAGREEMENT": 0.20, # accord inter-modèles requis (écart 1X2-H max)
    "MAX_CREDIBLE_EDGE": 0.25,      # au-delà, modèle≠marché = données douteuses, pas de la value (§34)
}


def fair_probabilities(odds_by_selection: dict[str, float]) -> dict[str, float]:
    """Normalise 1/cote en retirant l'overround (méthode proportionnelle, documentée §32)."""
    if not odds_by_selection or any(o <= 1.0 for o in odds_by_selection.values()):
        return {}
    inv = {s: 1.0 / o for s, o in odds_by_selection.items()}
    overround = sum(inv.values())
    return {s: v / overround for s, v in inv.items()}


def best_odds_per_selection(book_odds: dict[str, dict[str, float]]) -> dict[str, tuple[str, float]]:
    """Pour chaque sélection : (bookmaker, meilleure cote) — MARKET CONSENSUS §31."""
    best: dict[str, tuple[str, float]] = {}
    for book, sels in (book_odds or {}).items():
        for sel, odd in sels.items():
            if odd is None or odd <= 1.0:
                continue
            if sel not in best or odd > best[sel][1]:
                best[sel] = (book, odd)
    return best


def evaluate_selection(p_model: float, odds: float, p_fair: float,
                       sample_ok: bool, models_agree: bool) -> dict:
    """Calcule EV/edge/niveau avec filtres de robustesse §34.

    Garde-fou crédibilité : si le modèle et le consensus du marché divergent de plus de
    MAX_CREDIBLE_EDGE (25 pts), l'écart signale presque toujours une donnée obsolète ou
    incohérente (équipe mal résolue, cote périmée…) — JAMAIS de la value réelle → NO_PICK.
    """
    ev = p_model * odds - 1.0
    edge = p_model - p_fair
    robust = sample_ok and models_agree
    if edge > LEVELS["MAX_CREDIBLE_EDGE"]:
        level = "NO_PICK"          # désaccord extrême modèle/marché → silence (§34/§37)
    elif ev < LEVELS["MIN_EV_POTENTIAL"]:
        level = "NO_VALUE"
    elif ev < LEVELS["MIN_EV_QUALIFIED"]:
        level = "POTENTIAL"
    elif ev < LEVELS["MIN_EV_STRONG"]:
        level = "QUALIFIED" if (robust and edge >= LEVELS["MIN_EDGE_QUALIFIED"]) else "POTENTIAL"
    else:
        level = "STRONG" if (robust and edge >= LEVELS["MIN_EDGE_QUALIFIED"]) else "QUALIFIED"
    return {"ev": ev, "edge": edge, "level": level, "robust": robust,
            "p_model": p_model, "p_fair": p_fair}
