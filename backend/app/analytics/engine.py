"""ANALYTICS ENGINE (M3) : recalcule Elo + forme depuis les fixtures FINISHED réelles.

Séparation Quantitative Brain (§101-102) : ce module calcule, il ne raconte pas.
Versionné (model_version/features_version) + horodaté (computed_at) → reproductible §72-73.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone

from sqlalchemy.orm import Session

from ..db.models import Fixture, Team, TeamAnalytics
from .elo import compute_ratings
from .features import team_form

MODEL_VERSION = "elo-v1"
FEATURES_VERSION = "v1"
MIN_MATCHES_FORM = 2  # en dessous : form5/gf5/ga5 = NULL («ÉCHANTILLON INSUFFISANT», §1)


@dataclass
class AnalyticsReport:
    fixtures_used: int = 0
    teams_rated: int = 0
    rows_written: int = 0

    def as_dict(self) -> dict:
        return {"fixtures_used": self.fixtures_used, "teams_rated": self.teams_rated,
                "rows_written": self.rows_written, "model_version": MODEL_VERSION,
                "features_version": FEATURES_VERSION}


def compute_all(session: Session) -> AnalyticsReport:
    report = AnalyticsReport()
    now = datetime.now(timezone.utc)

    finished = (
        session.query(Fixture)
        .filter(Fixture.status == "FINISHED",
                Fixture.home_score.isnot(None), Fixture.away_score.isnot(None))
        .order_by(Fixture.kickoff_utc.asc())
        .all()
    )
    report.fixtures_used = len(finished)

    seq = [(f.home_team_id, f.away_team_id, f.home_score, f.away_score) for f in finished]
    state = compute_ratings(seq)

    by_team_recent: dict[int, list[tuple[int, int]]] = {}
    for f in reversed(finished):  # plus récent d'abord
        by_team_recent.setdefault(f.home_team_id, []).append((f.home_score, f.away_score))
        by_team_recent.setdefault(f.away_team_id, []).append((f.away_score, f.home_score))

    team_ids = set(state.ratings) | set(by_team_recent)
    for tid in team_ids:
        team = session.get(Team, tid)
        if team is None:
            continue
        recent = by_team_recent.get(tid, [])
        form, pts, gf5, ga5 = team_form(recent)
        enough = len(recent) >= MIN_MATCHES_FORM

        row = session.query(TeamAnalytics).filter_by(team_id=tid).one_or_none()
        if row is None:
            row = TeamAnalytics(team_id=tid)
            session.add(row)
        row.elo = state.ratings.get(tid)
        row.matches_rated = state.played.get(tid, 0)
        row.form5 = form if enough else None           # NULL = échantillon insuffisant (§1)
        row.points5 = pts if enough else None
        row.gf5 = round(gf5, 3) if enough else None
        row.ga5 = round(ga5, 3) if enough else None
        row.features_version = FEATURES_VERSION
        row.model_version = MODEL_VERSION
        row.computed_at = now
        report.rows_written += 1

    report.teams_rated = len(team_ids)
    session.commit()
    return report
