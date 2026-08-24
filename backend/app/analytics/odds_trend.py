"""M5.2 — Tendance des cotes (mouvement du marché entre 1ère et dernière observation).

Aucune invention : on ne compare que des snapshots réellement enregistrés (append-only §30)
du consensus (moyenne des bookmakers présents) → delta de probabilité fair en points.
"""
from __future__ import annotations

from collections import defaultdict

from sqlalchemy.orm import Session

from ..db.models import Bookmaker, Market, OddsSnapshot
from ..ml.odds_math import fair_probabilities

MIN_POINTS = 0.5   # en dessous de ±0,5 pt, on considère le marché stable (bruit)


def odds_trends(session: Session, fixture_ids: list[int]) -> dict[int, dict]:
    """{fixture_id: {"H": +2.1, "D": -0.4, "A": -1.7, "snapshots": n}} en points de %."""
    if not fixture_ids:
        return {}
    rows = (
        session.query(OddsSnapshot, Market.code)
        .join(Market, OddsSnapshot.market_id == Market.id)
        .filter(OddsSnapshot.fixture_id.in_(fixture_ids), Market.code == "1X2",
                OddsSnapshot.status == "ACTIVE")
        .order_by(OddsSnapshot.captured_at.asc(), OddsSnapshot.id.asc())
        .all()
    )
    # regroupe par fixture puis par "époque" (captured_at) : consensus par époque
    by_fx: dict[int, dict] = defaultdict(lambda: defaultdict(list))
    for snap, _code in rows:
        by_fx[snap.fixture_id][snap.captured_at].append((snap.selection, snap.odds))

    out: dict[int, dict] = {}
    for fx_id, epochs in by_fx.items():
        times = sorted(epochs)
        if len(times) < 2:
            continue
        def fair_at(t):
            by_sel: dict[str, list[float]] = defaultdict(list)
            for sel, odd in epochs[t]:
                by_sel[sel].append(odd)
            consensus = {s: sum(v) / len(v) for s, v in by_sel.items()}
            return fair_probabilities(consensus)
        first, last = fair_at(times[0]), fair_at(times[-1])
        delta = {}
        for sel in ("H", "D", "A"):
            if sel in first and sel in last:
                d = (last[sel] - first[sel]) * 100.0
                delta[sel] = round(d, 1) if abs(d) >= MIN_POINTS else 0.0
        if delta:
            out[fx_id] = {**delta, "snapshots": len(times)}
    return out
