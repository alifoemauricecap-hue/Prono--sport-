"""Modèles de buts (§17) — estimation sur données réelles uniquement.

1. POISSON indépendant : attaque/défense relatives par équipe, moyenne ligue.
2. DIXON-COLES : correction rho sur les scores bas (0-0, 1-0, 0-1, 1-1), estimée par
   vraisemblance sur l'historique réel — formule DC(1997) standard.
3. Décroissance temporelle (§14) : poids phi = exp(-xi × jours/365), xi documenté.

Estimation par maximum de vraisemblance (scipy.optimize), ENTRAÎNÉE UNIQUEMENT sur les
matchs antérieurs à la date de prédiction (§22 : le timestamp est un argument obligatoire).
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

import numpy as np
from scipy.optimize import minimize
from scipy.stats import poisson

XI_TIME_DECAY = 0.0065      # xi par jour (documenté §14) — poids 50 % à ~107 jours
MAX_GOALS = 10


def tau_dc(x: int, y: int, lam: float, mu: float, rho: float) -> float:
    """Facteur de correction Dixon-Coles pour les scores bas."""
    if x == 0 and y == 0:
        return 1 - lam * mu * rho
    if x == 0 and y == 1:
        return 1 + lam * rho
    if x == 1 and y == 0:
        return 1 + mu * rho
    if x == 1 and y == 1:
        return 1 - rho
    return 1.0


@dataclass
class TeamStrengths:
    attack: dict[str, float]
    defense: dict[str, float]
    home_advantage: float
    league_avg_goals: float
    rho: float = 0.0
    model: str = "poisson"
    n_matches: int = 0
    trained_until: str | None = None

    def lambdas(self, home: str, away: str) -> tuple[float, float]:
        lam = self.league_avg_goals * self.attack[home] / self.defense[away] * np.exp(self.home_advantage)
        mu = self.league_avg_goals * self.attack[away] / self.defense[home]
        lam = float(max(0.05, min(lam, 5.0)))   # bornes de stabilité documentées
        mu = float(max(0.05, min(mu, 5.0)))
        return lam, mu


def _prepare(matches: list[tuple[str, str, int, int, datetime]], cutoff: datetime):
    """Filtre §22 : aucun match >= cutoff. Retourne tableaux NumPy + équipes."""
    past = [(h, a, hs, as_) for (h, a, hs, as_, d) in matches if d < cutoff]
    teams = sorted({m[0] for m in past} | {m[1] for m in past})
    return past, teams


def fit_poisson(matches, cutoff: datetime, now: datetime,
                min_matches: int = 30) -> TeamStrengths | None:
    """MLE : minimise -log vraisemblance Poisson bivariée indépendante pondérée temps."""
    past, teams = _prepare(matches, cutoff)
    if len(past) < min_matches or len(teams) < 4:
        return None
    idx = {t: i for i, t in enumerate(teams)}
    n = len(teams)
    # poids temporels §14 : decay exponentiel sur les dates complètes
    dates = [d for (h, a, hs, as_, d) in matches if d < cutoff]
    w = np.exp(-XI_TIME_DECAY * np.array([(now - d).days for d in dates], dtype=float))
    H = np.array([idx[h] for (h, a, hs, as_) in past])
    A = np.array([idx[a] for (h, a, hs, as_) in past])
    HS = np.array([hs for (h, a, hs, as_) in past], dtype=float)
    AS = np.array([as_ for (h, a, hs, as_) in past], dtype=float)
    avg = float((HS.mean() + AS.mean()) / 2.0)

    def neg_ll(params):
        att, dfc, home_adv = params[:n], params[n:2 * n], params[2 * n]
        lam = avg * np.exp(att[H] - dfc[A] + home_adv)
        mu = avg * np.exp(att[A] - dfc[H])
        ll_h = poisson.logpmf(HS, lam)
        ll_a = poisson.logpmf(AS, mu)
        penalty = 0.5 * (att.sum() ** 2 + dfc.sum() ** 2) / n  # identifiabilité : somme ~ 0
        return float(-(w * (ll_h + ll_a)).sum() + penalty)

    x0 = np.zeros(2 * n + 1)
    res = minimize(neg_ll, x0, method="L-BFGS-B",
                   options={"maxiter": 400, "ftol": 1e-7})
    att, dfc, home_adv = res.x[:n], res.x[n:2 * n], res.x[2 * n]
    attack = {t: float(np.exp(att[idx[t]])) for t in teams}
    defense = {t: float(np.exp(dfc[idx[t]])) for t in teams}
    return TeamStrengths(attack=attack, defense=defense,
                         home_advantage=float(home_adv),
                         league_avg_goals=avg, rho=0.0,
                         model="poisson", n_matches=len(past),
                         trained_until=cutoff.isoformat())


def fit_dixon_coles(base: TeamStrengths, matches, cutoff: datetime,
                    now: datetime) -> TeamStrengths:
    """Réutilise att/def Poisson, estime rho par vraisemblance DC sur scores bas (§17)."""
    past = [(h, a, hs, as_, d) for (h, a, hs, as_, d) in matches if d < cutoff]
    if base is None:
        return None
    dates = [d for (h, a, hs, as_, d) in past]
    w = np.exp(-XI_TIME_DECAY * np.array([(now - d).days for d in dates], dtype=float))

    def neg_ll_rho(rho: float) -> float:
        total = 0.0
        for (h, a, hs, as_), wi in zip([(p[0], p[1], p[2], p[3]) for p in past], w):
            if (h not in base.attack) or (a not in base.attack):
                continue
            lam, mu = base.lambdas(h, a)
            p = poisson.pmf(hs, lam) * poisson.pmf(as_, mu) * tau_dc(hs, as_, lam, mu, rho)
            total += wi * np.log(max(p, 1e-12))
        return -float(total)

    res = minimize(neg_ll_rho, x0=0.0, bounds=[(-0.15, 0.15)], method="L-BFGS-B")
    return TeamStrengths(attack=base.attack, defense=base.defense,
                         home_advantage=base.home_advantage,
                         league_avg_goals=base.league_avg_goals,
                         rho=float(res.x[0]), model="dixon-coles-poisson",
                         n_matches=base.n_matches,
                         trained_until=base.trained_until)


def score_matrix(strengths: TeamStrengths, home: str, away: str,
                 max_goals: int = MAX_GOALS) -> np.ndarray:
    """Matrice P(score i-j) via Poisson × correction DC (§17, §40 distribution complète)."""
    lam, mu = strengths.lambdas(home, away)
    px = poisson.pmf(np.arange(max_goals + 1), lam)
    py = poisson.pmf(np.arange(max_goals + 1), mu)
    M = np.outer(px, py)
    for i in range(2):
        for j in range(2):
            M[i, j] *= tau_dc(i, j, lam, mu, strengths.rho)
    M = M / M.sum()  # renormalisation documentée
    return M, lam, mu


def probabilities(M: np.ndarray) -> dict:
    """Marchés dérivés de la matrice de scores (§36, §81) — calcul exact, pas de Monte Carlo
    déguisé : le moteur expose la distribution exacte (§40)."""
    i_idx = np.arange(M.shape[0])[:, None]
    j_idx = np.arange(M.shape[1])[None, :]
    p_home = float(M[i_idx > j_idx].sum())
    p_draw = float(M[i_idx == j_idx].sum())
    p_away = float(M[i_idx < j_idx].sum())
    total = i_idx + j_idx
    out = {
        "1X2": {"H": p_home, "D": p_draw, "A": p_away,
                "1X": p_home + p_draw, "X2": p_away + p_draw, "12": p_home + p_away},
        "OU_2.5": {"Over": float(M[total >= 3].sum()), "Under": float(M[total <= 2].sum())},
        "OU_1.5": {"Over": float(M[total >= 2].sum()), "Under": float(M[total <= 1].sum())},
        "OU_3.5": {"Over": float(M[total >= 4].sum()), "Under": float(M[total <= 3].sum())},
        "BTTS": {"Yes": float(M[(i_idx >= 1) & (j_idx >= 1)].sum()),
                 "No": float(M[(i_idx == 0) | (j_idx == 0)].sum())},
        "DNB": {"H": p_home, "A": p_away},
    }
    return out


def most_probable_scores(M: np.ndarray, top: int = 5) -> list[dict]:
    flat = [(float(M[i, j]), i, j) for i in range(M.shape[0]) for j in range(M.shape[1])]
    flat.sort(reverse=True)
    return [{"score": f"{i}-{j}", "p": p} for p, i, j in flat[:top]]
