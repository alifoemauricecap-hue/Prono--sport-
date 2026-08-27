"""BACKTEST LAB (§36) — validation walk-forward sur données RÉELLES uniquement.

Méthode (anti-leakage §34) :
- Les matchs FINISHED d'une compétition sont triés par date.
- Chaque match est prédit avec un modèle entraÎné UNIQUEMENT sur les matchs
  antérieurs (le modèle ne voit jamais l'avenir).
- Les `min_history` premiers matchs ne sont pas prédits (insuffisance d'historique
  → pas de fiction).

Mesures (§35) :
- Brier Score 1X2  : Σ (p_i − 1{résultat i})² / N   (plus c'est bas, mieux c'est)
- Log Loss 1X2     : −Σ log(p_résultat) / N
- Top-1 accuracy   : % de fois où le favori du modèle = vainqueur réel
- Comparaison modèle vs MARCHÉ : les cotes réelles (marge retirée) servent de
  référence — si le modèle n'atteint pas le marché, c'est affiché tel quel.

Résultat persisté dans model_versions (model_id="backtest-walkforward-v1").
"""
from __future__ import annotations

import math
from datetime import datetime, timezone

from sqlalchemy.orm import Session, aliased

from ..db.models import Bookmaker, Competition, Fixture, Market, ModelVersion, OddsSnapshot, Team
from .dc_models import fit_dixon_coles, fit_poisson, probabilities, score_matrix
from ..analytics.elo import compute_ratings, expected_score as elo_expected_home
from .engine import _norm_dt, _team_key
from .odds_math import fair_probabilities

MODEL_ID = "backtest-walkforward-v1"
MIN_HISTORY = 30


def _matches(session: Session, competition_id: int):
    """Historique FINISHED dédupliqué, trié par date — (home_key, away_key, hs, as_, dt)."""
    TH, TA = aliased(Team), aliased(Team)
    rows = (session.query(Fixture, TH, TA)
            .join(TH, Fixture.home_team_id == TH.id)
            .join(TA, Fixture.away_team_id == TA.id)
            .filter(Fixture.competition_id == competition_id,
                    Fixture.status == "FINISHED",
                    Fixture.home_score.isnot(None),
                    Fixture.away_score.isnot(None))
            .all())
    votes: dict[tuple, list[tuple[int, int, datetime]]] = {}
    for fx, h, a in rows:
        dt = _norm_dt(fx.kickoff_utc)
        if dt is None:
            continue
        key = (_team_key(h.name), _team_key(a.name), dt.date().isoformat())
        votes.setdefault(key, []).append((fx.home_score, fx.away_score, dt))
    out = []
    for (hk, ak, _d), vs in votes.items():
        tally: dict[tuple[int, int], int] = {}
        for hs, as_, _dt in vs:
            tally[(hs, as_)] = tally.get((hs, as_), 0) + 1
        (hs, as_), _n = max(tally.items(), key=lambda kv: (kv[1], -kv[0][0] - kv[0][1]))
        out.append((hk, ak, hs, as_, min(v[2] for v in vs)))
    out.sort(key=lambda m: m[4])
    return out


def _market_probs(session: Session, fixture_id: int) -> dict[str, float] | None:
    """Probabilités du MARCHÉ réel (marge retirée) pour un match — None si pas de cotes."""
    snaps = (session.query(OddsSnapshot, Bookmaker, Market)
             .join(Bookmaker, OddsSnapshot.bookmaker_id == Bookmaker.id)
             .join(Market, OddsSnapshot.market_id == Market.id)
             .filter(OddsSnapshot.fixture_id == fixture_id,
                     OddsSnapshot.status == "ACTIVE",
                     Market.code == "1X2").all())
    if not snaps:
        return None
    by_sel: dict[str, list[float]] = {}
    for _s, _b, _m in snaps:
        by_sel.setdefault(_s.selection, []).append(_s.odds)
    if len(by_sel) < 3:
        return None
    return fair_probabilities({s: sum(v) / len(v) for s, v in by_sel.items()})


def _brier_logloss_acc(probs: dict[str, float], actual: str,
                       acc_state: list[float]) -> tuple[float, float]:
    brier = sum((probs.get(sel, 0.0) - (1.0 if sel == actual else 0.0)) ** 2
                for sel in ("H", "D", "A"))
    p_actual = max(probs.get(actual, 0.0), 1e-6)
    logloss = -math.log(p_actual)
    acc_state[0] += 1.0 if max(probs, key=probs.get) == actual else 0.0
    return brier, logloss


def run_backtest(session: Session, min_history: int = MIN_HISTORY) -> dict:
    """Exécute le backtest walk-forward sur toutes les compétitions de la base."""
    now = datetime.now(timezone.utc)
    comps_out = []
    tot = {"n": 0, "brier_m": 0.0, "ll_m": 0.0, "acc_m": 0.0,
           "n_mkt": 0, "brier_k": 0.0, "ll_k": 0.0, "acc_k": 0.0}

    for comp in session.query(Competition).order_by(Competition.name).all():
        matches = _matches(session, comp.id)
        if len(matches) <= min_history:
            comps_out.append({"code": comp.code, "name": comp.name,
                              "matches_total": len(matches), "matches_backtested": 0,
                              "note": f"Historique insuffisant (< {min_history} matchs) — "
                                      "aucun backtest, jamais de fiction."})
            continue

        brier_m = ll_m = acc_m = 0.0
        brier_k = ll_k = acc_k = 0.0
        n = n_mkt = 0
        fixture_ids_by_idx: dict[int, int] = {}

        # mapping (home_key, away_key, date) → fixture_id (pour les cotes)
        TH2, TA2 = aliased(Team), aliased(Team)
        rows = (session.query(Fixture.id, TH2.name, TA2.name, Fixture.kickoff_utc)
                .join(TH2, Fixture.home_team_id == TH2.id)
                .join(TA2, Fixture.away_team_id == TA2.id)
                .filter(Fixture.competition_id == comp.id,
                        Fixture.status == "FINISHED").all())
        id_map: dict[tuple, int] = {}
        for fid, hn, an, dt in rows:
            if dt is None:
                continue
            id_map[(_team_key(hn), _team_key(an), _norm_dt(dt).date().isoformat())] = fid

        for i in range(min_history, len(matches)):
            hk, ak, hs, as_, _dt = matches[i]
            actual = "H" if hs > as_ else ("A" if as_ > hs else "D")
            hist = matches[:i]
            try:
                base = fit_poisson(hist, now, now, min_matches=10)
                if base is None:
                    continue
                dc = fit_dixon_coles(base, hist, now, now)
                if hk not in dc.attack or ak not in dc.attack:
                    continue
                M, _l, _m = score_matrix(dc, hk, ak)
                probs = probabilities(M)
                # ensemble DC/Elo sur le même historique (cohérent avec la production)
                seq = []
                name2id: dict[str, int] = {}
                for j, (h, a, _h2, _a2, _d2) in enumerate(hist):
                    name2id.setdefault(h, 1000 + j * 2)
                    name2id.setdefault(a, 1001 + j * 2)
                seq = [(name2id[h], name2id[a], h2, a2) for (h, a, h2, a2, _d) in hist]
                elo = compute_ratings(seq)
                e_dc = probs["1X2"]["H"] + 0.5 * probs["1X2"]["D"]
                e_elo = elo_expected_home(elo.ratings[name2id[hk]], elo.ratings[name2id[ak]])
                e_mix = 0.7 * e_dc + 0.3 * e_elo
                scale = e_mix / max(e_dc, 1e-9)
                h_new = probs["1X2"]["H"] * scale
                a_new = probs["1X2"]["A"] / max(1e-9, (1 - e_dc)) * (1 - e_mix) if e_dc < 1 else probs["1X2"]["A"]
                d_new = max(0.0, 1.0 - h_new - a_new)
                p_model = {"H": h_new, "D": d_new, "A": a_new}
            except Exception:
                continue  # un match non modélisable n'entache pas le reste (auditable)

            n += 1
            b, ll = _brier_logloss_acc(p_model, actual, [0.0])
            brier_m += b
            ll_m += ll
            acc_m += 1.0 if max(p_model, key=p_model.get) == actual else 0.0

            fid = id_map.get((hk, ak, _norm_dt(_dt).date().isoformat()))
            if fid is not None:
                fixture_ids_by_idx[i] = fid
                p_mkt = _market_probs(session, fid)
                if p_mkt and all(s in p_mkt for s in ("H", "D", "A")):
                    n_mkt += 1
                    bk, llk = _brier_logloss_acc(p_mkt, actual, [0.0])
                    brier_k += bk
                    ll_k += llk
                    acc_k += 1.0 if max(p_mkt, key=p_mkt.get) == actual else 0.0

        if n == 0:
            comps_out.append({"code": comp.code, "name": comp.name,
                              "matches_total": len(matches), "matches_backtested": 0,
                              "note": "Aucun match n'a pu être modélisé en walk-forward."})
            continue

        comps_out.append({
            "code": comp.code, "name": comp.name,
            "matches_total": len(matches), "matches_backtested": n,
            "min_history": min_history,
            "brier_model": round(brier_m / n, 4),
            "logloss_model": round(ll_m / n, 4),
            "accuracy_top1_model": round(acc_m / n, 4),
            "market": (None if n_mkt == 0 else {
                "matches_with_odds": n_mkt,
                "brier_market": round(brier_k / n_mkt, 4),
                "logloss_market": round(ll_k / n_mkt, 4),
                "accuracy_top1_market": round(acc_k / n_mkt, 4),
            }),
            "note": None,
        })
        tot["n"] += n
        tot["brier_m"] += brier_m
        tot["ll_m"] += ll_m
        tot["acc_m"] += acc_m
        tot["n_mkt"] += n_mkt
        tot["brier_k"] += brier_k
        tot["ll_k"] += ll_k
        tot["acc_k"] += acc_k

    report = {
        "model_id": MODEL_ID,
        "method": "walk-forward : chaque match prédit avec un modèle (Poisson + Dixon-Coles "
                  "+ Elo, ensemble 70/30) entraîné sur les matchs antérieurs uniquement "
                  "(anti-leakage). Le marché = cotes réelles multi-bookmakers, marge retirée.",
        "generated_at": now.isoformat(),
        "competitions": comps_out,
        "overall": {
            "matches_backtested": tot["n"],
            "brier_model": round(tot["brier_m"] / tot["n"], 4) if tot["n"] else None,
            "logloss_model": round(tot["ll_m"] / tot["n"], 4) if tot["n"] else None,
            "accuracy_top1_model": round(tot["acc_m"] / tot["n"], 4) if tot["n"] else None,
            "matches_with_market": tot["n_mkt"],
            "brier_market": round(tot["brier_k"] / tot["n_mkt"], 4) if tot["n_mkt"] else None,
            "accuracy_top1_market": round(tot["acc_k"] / tot["n_mkt"], 4) if tot["n_mkt"] else None,
        },
    }

    # persistance (model governance §20)
    mv = session.query(ModelVersion).filter_by(model_id=MODEL_ID, version="v1").one_or_none()
    if mv is None:
        mv = ModelVersion(model_id=MODEL_ID, version="v1",
                          dataset_version="matchs FINISHED réels en base",
                          features_version="v1")
        session.add(mv)
    mv.date_training = now
    mv.metrics = report
    session.commit()
    return report


def load_last_backtest(session: Session) -> dict | None:
    mv = session.query(ModelVersion).filter_by(model_id=MODEL_ID, version="v1").one_or_none()
    return mv.metrics if mv and mv.metrics else None
