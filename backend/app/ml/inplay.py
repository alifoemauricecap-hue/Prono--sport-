"""M6 — Modèle IN-PLAY (probabilités en cours de match).

Méthode documentée (§40 : calcul exact, pas d'invention) :
- Les forces pré-match (buts attendus lam/mu du moteur Dixon-Coles) sont supposées
  uniformément réparties sur 90 minutes.
- À la minute m avec le score (hs, as), les buts RESTANTS suivent des Poisson
  indépendantes de moyennes lam*(90-m)/90 et mu*(90-m)/90 (décroissance standard,
  sans facteur inventé : si non vérifiable, pas de paramètre magique — §1).
- Les probabilités 1X2 finales = score actuel + buts restants simulés par matrice exacte.

Limites affichées à l'utilisateur : pas de cartons, blessures, momentum — le modèle
in-play v1 est une extrapolation honnête du pré-match, signalée comme telle.
"""
from __future__ import annotations

import math

import numpy as np

MAX_GOALS = 8     # troncature de matrice (queue Poisson négligeable au-delà)
REGULATION_MINUTES = 90.0


def remaining_matrix(lam_rem: float, mu_rem: float) -> np.ndarray:
    """Matrice des probabilités exactes des buts restants (Poisson indépendantes)."""
    lam = max(lam_rem, 1e-6)
    mu = max(mu_rem, 1e-6)
    ph = [math.exp(-lam) * lam**i / math.factorial(i) for i in range(MAX_GOALS + 1)]
    pa = [math.exp(-mu) * mu**j / math.factorial(j) for j in range(MAX_GOALS + 1)]
    M = np.outer(ph, pa)
    return M / M.sum()    # renormalisation après troncature


def inplay_probabilities(lam_pre: float, mu_pre: float, minute: int,
                         home_score: int, away_score: int) -> dict:
    """Probas 1X2 finales + score le plus probable, à la minute donnée.

    minute ∈ [0, 90] : au-delà de 90 → distribution quasi dégénérée sur le score actuel.
    """
    minute = max(0, min(90, int(minute)))
    rest = max(REGULATION_MINUTES - minute, 0.0)
    lam_rem = lam_pre * rest / REGULATION_MINUTES
    mu_rem = mu_pre * rest / REGULATION_MINUTES
    M = remaining_matrix(lam_rem, mu_rem)
    i_idx = np.arange(M.shape[0])[:, None]
    j_idx = np.arange(M.shape[1])[None, :]
    fh, fa = home_score + i_idx, away_score + j_idx    # scores finaux possibles
    p_home = float(M[fh > fa].sum())
    p_draw = float(M[fh == fa].sum())
    p_away = float(M[fh < fa].sum())
    flat = np.argsort(M.ravel())[::-1]
    top = int(flat[0])
    likely = f"{home_score + top // (MAX_GOALS + 1)}-{away_score + top % (MAX_GOALS + 1)}"
    return {
        "1X2": {"H": p_home, "D": p_draw, "A": p_away},
        "most_likely_final": likely,
        "goals_remaining_expected": {"home": round(lam_rem, 3), "away": round(mu_rem, 3)},
        "model": "inplay-poisson-remaining:v1",
        "disclaimer": "Extrapolation du pré-match (forces réparties uniformément) — "
                      "pas de cartons/blessures/momentum. Probabilité ≠ certitude (§38).",
    }


def parse_clock_minute(clock: str | None) -> int | None:
    """'67' / '67:32' / '45+2' / 'HT' → minute entière. None si non interprétable (§1)."""
    if not clock:
        return None
    s = clock.strip().replace("'", "").replace("’", "").upper()
    if s in {"HT", "MT", "HALF-TIME", "HALFTIME"}:
        return 45
    total = 0
    parts = s.split("+")
    try:
        total = int(float(parts[0].split(":")[0]))
    except (ValueError, IndexError):
        return None
    if len(parts) > 1:
        try:
            total += int(parts[1])
        except ValueError:
            pass
    return min(total, 90)
