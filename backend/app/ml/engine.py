"""M4 — PREDICTION ENGINE : entraîne Poisson + Dixon-Coles + Elo (ensemble §19),
produit les probabilités des prochains matchs, et qualifie les Value Bets sur cotes réelles.

Règles d'honneur implémentées :
- §22 : entraînement strictement antérieur à 'now' (cutoff) — aucune donnée future.
- §82 : équipe sans historique suffisant → pas de prédiction (jamais de fiction).
- §37/§85 : si aucune sélection robuste → NO QUALIFIED PICK (enregistré comme tel).
- §73 : chaque prédiction embarque input_snapshot (forces utilisées) → reproductible.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone

from sqlalchemy.orm import Session

from ..db.models import (
    Bookmaker,
    Fixture,
    Market,
    ModelVersion,
    OddsSnapshot,
    Prediction,
    Season,
    Team,
    ValueBet,
)
from ..ingest.resolution import normalize_name
from ..analytics.elo import compute_ratings, expected_score as elo_expected_home
from .dc_models import fit_dixon_coles, fit_poisson, most_probable_scores, probabilities, score_matrix
from .odds_math import LEVELS, best_odds_per_selection, evaluate_selection, fair_probabilities

MODEL_ID = "ensemble-dc-poisson-elo"
MODEL_VERSION_STR = "v1"
DATASET_LABEL = "fixtures réelles toutes saisons en base"


def _norm_dt(dt: datetime | None) -> datetime | None:
    if dt is None:
        return None
    return dt.replace(tzinfo=timezone.utc) if dt.tzinfo is None else dt


def _team_key(name: str) -> str:
    return normalize_name(name)


@dataclass
class PredictReport:
    competition_code: str | None = None
    trained_models: int = 0
    matches_1x2: int = 0
    predictions: int = 0
    value_bets: dict = field(default_factory=lambda: {"NO_VALUE": 0, "POTENTIAL": 0, "QUALIFIED": 0, "STRONG": 0, "NO_PICK": 0})
    skipped_no_model: int = 0

    def as_dict(self):
        return {"competition": self.competition_code, "trained_models": self.trained_models,
                "history_matches_used": self.matches_1x2, "predictions": self.predictions,
                "value_bets": self.value_bets, "skipped_no_model": self.skipped_no_model,
                "model_version": f"{MODEL_ID}:{MODEL_VERSION_STR}"}


def _history(session: Session, competition_id: int | None) -> tuple[list, dict[int, str]]:
    """Historique FINISHED : (home_name_norm, away_name_norm, hs, as_, date)."""
    q = session.query(Fixture, Team, Team, Season, ) \
        .join(Team, Fixture.home_team_id == Team.id) \
        .join(Season, Fixture.season_id == Season.id, isouter=True)
    rows = session.query(Fixture).filter(
        Fixture.status == "FINISHED", Fixture.home_score.isnot(None))
    if competition_id:
        rows = rows.filter(Fixture.competition_id == competition_id)
    rows = rows.all()
    team_ids = {r.home_team_id for r in rows} | {r.away_team_id for r in rows}
    teams = {t.id: t for t in session.query(Team).filter(Team.id.in_(team_ids or {0}))}
    # DÉDUP cross-provider (§4, §41) : le même match physique peut être rapporté par
    # ESPN + fduk + OpenLigaDB → un seul exemplaire par (domicile, extérieur, date).
    # Scores : majorité entre sources concordantes, sinon premier rapport tracé.
    votes: dict[tuple, list[tuple[int, int, datetime]]] = {}
    for r in rows:
        dt = _norm_dt(r.kickoff_utc)
        if dt is None:
            continue
        h, a = teams.get(r.home_team_id), teams.get(r.away_team_id)
        if not h or not a:
            continue
        key = (_team_key(h.name), _team_key(a.name), dt.date().isoformat())
        votes.setdefault(key, []).append((r.home_score, r.away_score, dt))
    matches = []
    for (hk, ak, _d), vs in votes.items():
        tally: dict[tuple[int, int], int] = {}
        for hs, as_, _dt in vs:
            tally[(hs, as_)] = tally.get((hs, as_), 0) + 1
        (hs, as_), _n = max(tally.items(), key=lambda kv: (kv[1], -kv[0][0] - kv[0][1]))
        dt = min(v[2] for v in vs)
        matches.append((hk, ak, hs, as_, dt))
    return matches, teams


def train_models(session: Session, now: datetime,
                 min_matches: int = 30) -> tuple[dict, ModelVersion]:
    """Entraîne 1 modèle (Poisson + DC) par compétition + Elo global de secours.
    Retourne {competition_id: {"dc": strengths, "teams": {...}}} + ModelVersion persisté."""
    from ..db.models import Competition
    models: dict[int, dict] = {}
    total_hist = 0
    for comp in session.query(Competition).all():
        hist, _ = _history(session, comp.id)
        if len(hist) < min_matches:
            continue
        base = fit_poisson(hist, now, now, min_matches=min_matches)
        if base is None:
            continue
        dc = fit_dixon_coles(base, hist, now, now)
        models[comp.id] = {"dc": dc, "hist_len": len(hist)}
        total_hist = max(total_hist, len(hist))
    mv = session.query(ModelVersion).filter_by(model_id=MODEL_ID,
                                               version=MODEL_VERSION_STR).one_or_none()
    if mv is None:
        mv = ModelVersion(model_id=MODEL_ID, version=MODEL_VERSION_STR)
        session.add(mv)
    mv.dataset_version = DATASET_LABEL
    mv.features_version = "v1"
    mv.date_training = now
    mv.params = {"xi_time_decay": 0.0065, "K_elo": 60, "hfa_elo": 65,
                 "min_matches": min_matches, "dixon_coles_rho_bounds": [-0.15, 0.15],
                 "levels": LEVELS}
    session.commit()
    return models, mv


def _elo_global(session: Session):
    hist, _ = _history(session, None)
    seq = []
    name2id = {}
    for tid, tname in session.query(Team.id, Team.name).all():
        name2id[_team_key(tname)] = tid
    for (h, a, hs, as_, dt) in sorted(hist, key=lambda m: m[4]):
        hi, ai = name2id.get(h), name2id.get(a)
        if hi and ai:
            seq.append((hi, ai, hs, as_))
    state = compute_ratings(seq)
    id2name = {v: k for k, v in name2id.items()}
    return state, name2id, id2name


def predict_upcoming(session: Session, now: datetime | None = None,
                     competition_code: str | None = None,
                     min_matches: int = 30) -> list[PredictReport]:
    from ..db.models import Competition, OddsSnapshot as _OS  # noqa: F401
    now = now or datetime.now(timezone.utc)
    cutoff = now - timedelta(hours=2, minutes=30)   # un match dure ~2 h : au-delà, plus de prédiction utile

    # PURGE §1/§38 : toute prédiction / value bet d'un match passé ou terminé est supprimée
    # (les marchés réels sont clos ; garder ces lignes serait trompeur).
    stale_ids = [r[0] for r in session.query(Fixture.id).filter(
        (Fixture.kickoff_utc < cutoff) | (Fixture.status == "FINISHED")).all()]
    if stale_ids:
        session.query(ValueBet).filter(ValueBet.fixture_id.in_(stale_ids)).delete(synchronize_session=False)
        session.query(Prediction).filter(Prediction.fixture_id.in_(stale_ids)).delete(synchronize_session=False)
        session.commit()

    # IDEMPOTENCE : les VB/prédictions des matchs À VENIR sont entièrement recalculées —
    # on repart de zéro pour que les règles courantes s'appliquent à toutes les lignes
    # (sinon une valeur calculée avec d'anciens seuils survivrait indéfiniment).
    fut_ids = [r[0] for r in session.query(Fixture.id).filter(
        Fixture.status.in_(["SCHEDULED", "UPCOMING", "LINEUPS_PENDING", "LINEUPS_CONFIRMED"]),
        Fixture.kickoff_utc >= cutoff).all()]
    if fut_ids:
        session.query(ValueBet).filter(ValueBet.fixture_id.in_(fut_ids)).delete(synchronize_session=False)
        session.query(Prediction).filter(Prediction.fixture_id.in_(fut_ids)).delete(synchronize_session=False)
        session.commit()

    models, mv = train_models(session, now, min_matches=min_matches)
    elo_state, name2id, id2name = _elo_global(session)

    reports: list[PredictReport] = []
    q = session.query(Fixture).filter(
        Fixture.status.in_(["SCHEDULED", "UPCOMING", "LINEUPS_PENDING", "LINEUPS_CONFIRMED"]),
        Fixture.kickoff_utc >= cutoff)   # anti-leakage §22 : uniquement de vrais matchs à venir
    if competition_code:
        comp = session.query(Competition).filter_by(code=competition_code).one()
        q = q.filter(Fixture.competition_id == comp.id)
    fixtures = q.all()
    teams = {t.id: t for t in session.query(Team).all()}
    by_comp: dict[int, PredictReport] = {}

    # dédup : 1 prédiction par (compétition, équipes, jour)
    seen: set[tuple] = set()
    for fx in fixtures:
        dt = _norm_dt(fx.kickoff_utc)
        home, away = teams.get(fx.home_team_id), teams.get(fx.away_team_id)
        if not home or not away or dt is None:
            continue
        key = (fx.competition_id, fx.home_team_id, fx.away_team_id, dt.date().isoformat())
        if key in seen:
            continue
        seen.add(key)
        comp_rep = by_comp.setdefault(fx.competition_id, PredictReport(
            competition_code=None))

        bundle = models.get(fx.competition_id)
        hk, ak = _team_key(home.name), _team_key(away.name)
        if bundle is None or hk not in bundle["dc"].attack or ak not in bundle["dc"].attack:
            comp_rep.skipped_no_model += 1   # §82 : historique insuffisant → rien
            continue
        dc = bundle["dc"]
        comp_rep.trained_models = 1
        comp_rep.matches_1x2 = max(comp_rep.matches_1x2, bundle["hist_len"])

        M, lam, mu = score_matrix(dc, hk, ak)
        probs = probabilities(M)
        # ENSEMBLE §19 : DC (goals) + Elo (strengths) — moyenne pondérée documentée 70/30
        elo_home_p = None
        hi, ai = name2id.get(hk), name2id.get(ak)
        if hi in elo_state.ratings and ai in elo_state.ratings:
            elo_home_p = elo_expected_home(elo_state.ratings[hi], elo_state.ratings[ai])
        if elo_home_p is not None:
            e_dc = probs["1X2"]["H"] + 0.5 * probs["1X2"]["D"]
            e_elo = elo_home_p
            e_mix = 0.7 * e_dc + 0.3 * e_elo
            scale = e_mix / max(e_dc, 1e-9)
            h_new = probs["1X2"]["H"] * scale
            a_new = probs["1X2"]["A"] / max(1e-9, (1 - e_dc)) * (1 - e_mix) if e_dc < 1 else probs["1X2"]["A"]
            d_new = max(0.0, 1.0 - h_new - a_new)
            probs["1X2_ensemble"] = {"H": h_new, "D": d_new, "A": a_new}
            disagreement = abs((probs["1X2"]["H"] + 0.5 * probs["1X2"]["D"]) - elo_home_p)
        else:
            probs["1X2_ensemble"] = {"H": probs["1X2"]["H"], "D": probs["1X2"]["D"], "A": probs["1X2"]["A"]}
            disagreement = None

        snapshot = {
            "home_attack": round(dc.attack[hk], 4), "home_defense": round(dc.defense[hk], 4),
            "away_attack": round(dc.attack[ak], 4), "away_defense": round(dc.defense[ak], 4),
            "home_advantage": round(dc.home_advantage, 4), "league_avg": round(dc.league_avg_goals, 4),
            "rho": round(dc.rho, 4), "history_matches": bundle["hist_len"],
            "elo_home": elo_state.ratings.get(hi) if hi is not None else None,
            "elo_away": elo_state.ratings.get(ai) if ai is not None else None,
            "ensemble": {"dc_weight": 0.7, "elo_weight": 0.3},
            "model_disagreement_1x2H": disagreement,
        }
        pred = Prediction(
            fixture_id=fx.id, model_version_id=mv.id,
            feature_version="v1", input_snapshot=snapshot,
            probabilities={**probs, "top_scores": most_probable_scores(M)},
            expected_goals={"home": round(lam, 3), "away": round(mu, 3)},
        )
        session.add(pred)
        session.flush()
        comp_rep.predictions += 1
        _value_scan(session, fx, pred, probs, snapshot, home.name, away.name, comp_rep)

    for comp_id, rep in by_comp.items():
        from ..db.models import Competition as C
        comp = session.get(C, comp_id)
        rep.competition_code = comp.code if comp else str(comp_id)
        reports.append(rep)
    session.commit()
    return reports


def _value_scan(session: Session, fx: Fixture, pred: Prediction, probs: dict,
                snapshot: dict, home_name: str, away_name: str, rep: PredictReport) -> None:
    """VALUE BET ENGINE §33-37 : scanne TOUS les marchés disponibles avec cotes réelles."""
    snap_q = (
        session.query(OddsSnapshot, Bookmaker, Market)
        .join(Bookmaker, OddsSnapshot.bookmaker_id == Bookmaker.id)
        .join(Market, OddsSnapshot.market_id == Market.id)
        .filter(OddsSnapshot.fixture_id == fx.id, OddsSnapshot.status == "ACTIVE")
        .order_by(OddsSnapshot.captured_at.desc())
    )
    book_odds: dict[str, dict[str, dict[str, float]]] = {}   # {market: {book: {sel: odd}}}
    avg_odds: dict[str, dict[str, list[float]]] = {}
    for snap, bm, mk in snap_q.all():
        if mk.code not in ("1X2", "OU_2.5"):   # marchés scannés v1 (BTTS : pas de cote source → §1)
            continue
        book_odds.setdefault(mk.code, {}).setdefault(bm.code, {})[snap.selection] = snap.odds
        avg_odds.setdefault(mk.code, {}).setdefault(snap.selection, []).append(snap.odds)

    hist_ok = snapshot.get("history_matches", 0) >= LEVELS["MIN_SAMPLE_PER_TEAM"] * 2
    disagree = snapshot.get("model_disagreement_1x2H")
    models_agree = disagree is None or disagree <= LEVELS["MAX_MODEL_DISAGREEMENT"]

    # ---------- marché 1X2 ----------
    best = best_odds_per_selection(book_odds.get("1X2", {}))
    fair = fair_probabilities({s: sum(v) / len(v) for s, v in avg_odds.get("1X2", {}).items()})
    if len(best) >= 3 and len(fair) >= 3:
        p_ens = probs.get("1X2_ensemble", probs["1X2"])
        picks = []
        for sel in ("H", "D", "A"):
            if sel not in best or sel not in fair:
                continue
            p_m = p_ens[sel]
            p_f = fair[sel]
            res = evaluate_selection(p_m, best[sel][1], p_f, hist_ok, models_agree)
            picks.append((sel, res, best[sel]))
            if res["level"] in ("POTENTIAL", "QUALIFIED", "STRONG"):   # §37 : NO_VALUE/NO_PICK jamais persistés
                session.add(ValueBet(
                    fixture_id=fx.id, prediction_id=pred.id,
                    market="1X2", selection=sel,
                    odds_reference=best[sel][1], bookmaker_ref=best[sel][0],
                    p_model=p_m, p_market_fair=p_f,
                    edge=res["edge"], ev=res["ev"], level=res["level"],
                    confidence="ÉLEVÉE" if (hist_ok and models_agree) else "MOYENNE",
                ))
        qualified = [p for p in picks if p[1]["level"] in ("QUALIFIED", "STRONG")]
        for _, res, _ in picks:
            rep.value_bets[res["level"]] = rep.value_bets.get(res["level"], 0) + (0 if res["level"] == "NO_VALUE" else 1)
        if not qualified:
            all_zero = all(p[1]["level"] == "NO_VALUE" for p in picks)
            rep.value_bets["NO_PICK"] += 1 if all_zero else 0

    # ---------- marché O/U 2.5 (M5) : cotes réelles fduk uniquement ----------
    best_ou = best_odds_per_selection(book_odds.get("OU_2.5", {}))
    fair_ou = fair_probabilities({s: sum(v) / len(v) for s, v in avg_odds.get("OU_2.5", {}).items()})
    if len(best_ou) >= 2 and len(fair_ou) >= 2 and "OU_2.5" in probs:
        for sel in ("Over", "Under"):
            if sel not in best_ou or sel not in fair_ou:
                continue
            p_m = probs["OU_2.5"][sel]
            p_f = fair_ou[sel]
            res = evaluate_selection(p_m, best_ou[sel][1], p_f, hist_ok, models_agree)
            if res["level"] in ("POTENTIAL", "QUALIFIED", "STRONG"):
                session.add(ValueBet(
                    fixture_id=fx.id, prediction_id=pred.id,
                    market="OU_2.5", selection=sel,
                    odds_reference=best_ou[sel][1], bookmaker_ref=best_ou[sel][0],
                    p_model=p_m, p_market_fair=p_f,
                    edge=res["edge"], ev=res["ev"], level=res["level"],
                    confidence="ÉLEVÉE" if (hist_ok and models_agree) else "MOYENNE",
                ))
            rep.value_bets[res["level"]] = rep.value_bets.get(res["level"], 0) + (0 if res["level"] == "NO_VALUE" else 1)
    return
