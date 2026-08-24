"""Features versionnées (§21) — calculées sur l'historique réel, avec décroissance temporelle (§14).

DECAY : un match plus ancien pèse moins : poids = DECAY^rang (rang 0 = plus récent).
form5   : séquence des 5 derniers résultats ("W"/"D"/"L", plus récent d'abord)
gf5/ga5 : buts pour/contre par match, moyenne PONDÉRÉE sur les 5 derniers.
"""
from __future__ import annotations

DECAY = 0.85  # §14 : fonction de decay temporelle documentée


def _weights(n: int) -> list[float]:
    w = [DECAY ** i for i in range(n)]
    s = sum(w)
    return [x / s for x in w]


def team_form(matches: list[tuple[int, int]]) -> tuple[str, int, float, float]:
    """matches du plus récent au plus ancien : (buts_marqués, buts_encaissés).
    Retourne (form5, points5, gf5_pondéré, ga5_pondéré). Moins de 5 matchs = séquence tronquée."""
    seq, pts, gf, ga = [], 0, [], []
    for i, (for_, against) in enumerate(matches[:5]):
        if for_ > against:
            seq.append("W"); pts += 3
        elif for_ == against:
            seq.append("D"); pts += 1
        else:
            seq.append("L")
        gf.append(float(for_)); ga.append(float(against))
    n = len(matches[:5])
    if n == 0:
        return "", 0, 0.0, 0.0
    w = _weights(n)
    gf_w = sum(g * wi for g, wi in zip(gf, w))
    ga_w = sum(g * wi for g, wi in zip(ga, w))
    return "".join(seq), pts, gf_w, ga_w
