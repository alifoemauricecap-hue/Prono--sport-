"""M7 — Head-to-Head : historique RÉEL des confrontations entre deux équipes internes.

Dédoublonné par date (les jumeaux multi-sources du même match comptent une fois, §41) ;
ordre décroissant de date ; jamais de données synthétiques.
"""
from __future__ import annotations

from collections import Counter

from sqlalchemy.orm import Session

from ..db.models import Fixture


def head_to_head(session: Session, home_team_id: int, away_team_id: int,
                 limit: int = 10) -> dict:
    q = (session.query(Fixture)
         .filter(Fixture.status == "FINISHED",
                 Fixture.home_score.isnot(None),
                 ((Fixture.home_team_id == home_team_id) & (Fixture.away_team_id == away_team_id))
                 | ((Fixture.home_team_id == away_team_id) & (Fixture.away_team_id == home_team_id)))
         .order_by(Fixture.kickoff_utc.desc()))
    by_date: dict[str, Counter] = {}
    best_by_date: dict[str, Fixture] = {}
    for fx in q.all():
        if not fx.kickoff_utc:
            continue
        d = fx.kickoff_utc.date().isoformat()
        # vote majoritaire sur le score si plusieurs sources (dédoublonnage §41)
        by_date.setdefault(d, Counter())[(fx.home_score, fx.away_score, fx.home_team_id)] += 1
        if d not in best_by_date:
            best_by_date[d] = fx
    meetings = []
    tally = {"home_wins": 0, "draws": 0, "away_wins": 0}
    for d in sorted(by_date, reverse=True)[:limit]:
        (hs, as_, hid), _n = by_date[d].most_common(1)[0]
        # perspective = équipe 'home_team_id' demandée (1 = victoire équipe analysée d'abord)
        if hid == home_team_id:
            res = "1" if hs > as_ else ("N" if hs == as_ else "2")
        else:
            res = "1" if as_ > hs else ("N" if as_ == hs else "2")
        meetings.append({"date": d, "home_team_id": hid,
                         "score": f"{hs}-{as_}",
                         "result_for_first_team": res})
        if res == "1":
            tally["home_wins"] += 1
        elif res == "N":
            tally["draws"] += 1
        else:
            tally["away_wins"] += 1
    return {"count": len(meetings), "meetings": meetings, "tally": tally,
            "note": None if meetings else "Aucune confrontation passée en base — DONNÉE NON DISPONIBLE"}
