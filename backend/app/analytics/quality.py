"""DATA QUALITY SCORE (§47) — par compétition, CALCULÉ sur l'état réel de la base.

Composantes (toutes observables) :
- couverture : nombre de matchs en base (0 → score 0)
- vérification : % de matchs VERIFIED (≥2 sources concordantes)
- redondance : nombre de sources distinctes ayant fourni des matchs
- profondeur historique : saisons réellement stockées (1 → 2+ → 5+)
- fraîcheur : âge du dernier match synchronisé

Jamais de score affirmé sans données : compétition vide → score NULL (NON MESURABLE).
"""
from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import func
from sqlalchemy.orm import Session

from ..db.models import Competition, DataQuality, Fixture, Season

LIVE_STATUSES = {"LIVE", "HALFTIME", "EXTRA_TIME", "PENALTIES"}


def _as_utc(dt: datetime) -> datetime:
    """SQLite restitue des datetimes naive — normalise pour comparer à now (aware)."""
    return dt.replace(tzinfo=timezone.utc) if dt.tzinfo is None else dt


def compute_quality(session: Session) -> dict:
    now = datetime.now(timezone.utc)
    out: dict[str, dict] = {}
    for comp in session.query(Competition).all():
        rows = session.query(Fixture).filter(Fixture.competition_id == comp.id).all()
        if not rows:
            row = session.query(DataQuality).filter_by(competition_id=comp.id).one_or_none()
            if row is None:
                row = DataQuality(competition_id=comp.id)
                session.add(row)
            row.score = None  # non mesurable (jamais inventée)
            row.fixtures = 0
            row.computed_at = now
            out[comp.code] = {"code": comp.code, "name": comp.name, "score": None,
                              "note": "Aucun match en base — qualité non mesurable"}
            continue

        verified = sum(1 for r in rows if r.data_status == "VERIFIED")
        contradictory = sum(1 for r in rows if r.data_status == "CONTRADICTORY")
        n_sources = len({r.source_provider for r in rows})
        seasons = (session.query(Season)
                   .filter(Season.competition_id == comp.id).count())
        last_updates = [_as_utc(r.last_updated_at) for r in rows if r.last_updated_at]
        age_h = ((now - max(last_updates)).total_seconds() / 3600
                 if last_updates else None)
        n_live = sum(1 for r in rows if r.status in LIVE_STATUSES)

        # score pondéré (documenté, reproductible)
        s_coverage = min(100, 20 * (1 if len(rows) >= 10 else len(rows) / 10))
        s_verified = 100 * verified / len(rows)
        s_sources = min(100, 50 * n_sources)
        s_history = 25 if seasons == 1 else (50 if seasons < 5 else 100)
        s_fresh = max(0.0, 100 * (1 - (age_h or 999) / 24)) if age_h is not None else 40.0
        score = round(0.25 * s_coverage + 0.30 * s_verified + 0.15 * s_sources +
                      0.15 * s_history + 0.15 * s_fresh, 1)

        missing = []
        if not any(r.home_xg is not None for r in rows):
            missing.append("xG")
        if not any(r.referee for r in rows):
            missing.append("arbitre")
        if not any(r.venue_city for r in rows):
            missing.append("ville du stade")

        row = session.query(DataQuality).filter_by(competition_id=comp.id).one_or_none()
        if row is None:
            row = DataQuality(competition_id=comp.id)
            session.add(row)
        row.score = score
        row.fixtures = len(rows)
        row.verified_pct = round(100 * verified / len(rows), 1)
        row.n_sources = n_sources
        seasons_rows = (session.query(Season)
                        .filter(Season.competition_id == comp.id).all())
        if seasons_rows:
            row.history_from = min(min(x.start_year, x.end_year) for x in seasons_rows)
            row.history_to = max(max(x.start_year, x.end_year) for x in seasons_rows)
        row.freshness_min = round(age_h / 60, 1) if age_h is not None else None
        row.missing = missing
        row.computed_at = now
        out[comp.code] = {
            "code": comp.code, "name": comp.name, "score": score,
            "fixtures": len(rows), "verified_pct": round(100 * verified / len(rows), 1),
            "contradictory": contradictory, "n_sources": n_sources,
            "seasons": seasons, "live": n_live,
            "freshness_min": round(age_h / 60, 1) if age_h is not None else None,
            "missing": missing,
        }
    session.commit()
    return out
