"""Elo dynamique (§16 TEAM POWER MODEL) — calculé sur l'historique réel.

Formule documentée :
- Rating initial : 1500
- Attendu : E = 1 / (1 + 10^(-(Ra - Rb + HFA) / 400)), HFA = 65 (avantage domicile)
- Résultat : victoire 1.0, nul 0.5, défaite 0.0
- Multiplicateur de marge (inspiré des pratiques publiques de ClubElo) :
    écart 1 but → 1.0 | 2 buts → 1.5 | 3+ buts → (11 + écart) / 8
- Mise à jour : R += K * ecart * (resultat - E), K = 60
- Tous les matchs FINISHED de la base (toutes compétitions) dans l'ordre chronologique.

Le rating d'une équipe ne reflète QUE les matchs réellement présents en base
(matches_rated = profondeur réelle de l'échantillon, §13 : profondeur affichée).
"""
from __future__ import annotations

from dataclasses import dataclass

K_FACTOR = 60.0
HOME_FIELD_ADVANTAGE = 65.0
INITIAL_RATING = 1500.0


def expected_score(ra: float, rb: float, home: bool = True) -> float:
    hfa = HOME_FIELD_ADVANTAGE if home else -HOME_FIELD_ADVANTAGE
    return 1.0 / (1.0 + 10 ** (-(ra - rb + hfa) / 400.0))


def margin_multiplier(goal_diff: int) -> float:
    gd = abs(goal_diff)
    if gd <= 1:
        return 1.0
    if gd == 2:
        return 1.5
    return (11.0 + gd) / 8.0


@dataclass
class EloState:
    ratings: dict[int, float]
    played: dict[int, int]


def compute_ratings(matches: list[tuple[int, int, int, int]]) -> EloState:
    """matches : liste chronologique de (home_team_id, away_team_id, home_score, away_score)."""
    ratings: dict[int, float] = {}
    played: dict[int, int] = {}
    for home_id, away_id, hs, as_ in matches:
        ra = ratings.get(home_id, INITIAL_RATING)
        rb = ratings.get(away_id, INITIAL_RATING)
        e_home = expected_score(ra, rb, home=True)
        if hs > as_:
            result = 1.0
        elif hs == as_:
            result = 0.5
        else:
            result = 0.0
        delta = K_FACTOR * margin_multiplier(hs - as_) * (result - e_home)
        ratings[home_id] = ra + delta
        ratings[away_id] = rb - delta
        played[home_id] = played.get(home_id, 0) + 1
        played[away_id] = played.get(away_id, 0) + 1
    return EloState(ratings=ratings, played=played)


def win_expectancy(ra: float, rb: float) -> float:
    """Probabilité Elo d'un succès à domicile (sans le nul) — usage affichage uniquement en M3."""
    return expected_score(ra, rb, home=True)
