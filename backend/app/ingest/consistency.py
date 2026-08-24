"""CONSISTENCY ENGINE (§4) — SOURCE A + SOURCE B → vérification croisée.

Principe : un même match réel vu par ≥ 2 providers indépendants est comparé.
- Scores identiques   → data_status = VERIFIED sur les lignes UNVERIFIED.
- Scores différents   → data_status = CONTRADICTORY + trace dans ingestion_rejects
                        ("DONNÉES CONTRADICTOIRES — ANALYSE LIMITÉE", §1).
- Une seule source    → statut inchangé (VERIFIED natif fduk, UNVERIFIED sinon).

Le jumelage est strict : mêmes IDs d'équipes internes + même date UTC du coup d'envoi.
Jamais de fuzzy matching (§5).
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime

from sqlalchemy.orm import Session

from ..db.models import Fixture, IngestionReject


def _naive_utc_date(dt: datetime | None) -> str | None:
    if dt is None:
        return None
    if dt.tzinfo is not None:
        dt = dt.astimezone().replace(tzinfo=None)
    return dt.date().isoformat()


@dataclass
class ConsistencyReport:
    twins_checked: int = 0
    upgraded_to_verified: int = 0
    contradictions: int = 0
    details: list[str] = field(default_factory=list)

    def as_dict(self) -> dict:
        return {
            "twins_checked": self.twins_checked,
            "upgraded_to_verified": self.upgraded_to_verified,
            "contradictions": self.contradictions,
            "details": self.details[:50],
        }


def run_consistency(session: Session) -> ConsistencyReport:
    report = ConsistencyReport()
    fixtures = session.query(Fixture).all()

    groups: dict[tuple, list[Fixture]] = {}
    for fx in fixtures:
        d = _naive_utc_date(fx.kickoff_utc)
        if d is None:
            continue
        groups.setdefault((fx.home_team_id, fx.away_team_id, d), []).append(fx)

    for key, rows in groups.items():
        providers = {r.source_provider for r in rows}
        if len(providers) < 2:
            continue  # une seule source : rien à croiser, statut inchangé
        report.twins_checked += 1

        finished = [r for r in rows if r.status == "FINISHED" and r.home_score is not None]
        score_sets = {(r.home_score, r.away_score) for r in finished}

        if len(score_sets) > 1:
            # DONNÉES CONTRADICTOIRES — ANALYSE LIMITÉE (§1)
            report.contradictions += 1
            for r in rows:
                if r.data_status != "CONTRADICTORY":
                    r.data_status = "CONTRADICTORY"
            session.add(IngestionReject(
                provider="consistency_engine",
                provider_id=f"{key}",
                reasons=["scores_contradictoires_inter_sources"],
                payload={"match": str(key),
                         "scores": {r.source_provider: f"{r.home_score}-{r.away_score}"
                                   for r in finished}},
            ))
            report.details.append(f"CONTRADICTION {key}")
        elif len(providers) >= 2:
            # ≥ 2 SOURCES confirment la RENCONTRE (mêmes équipes internes + même jour).
            # Score concordant quand présent → VERIFIED pour toutes les lignes UNVERIFIED.
            # La carte API affiche "✓ VÉRIFIÉ (n sources)" ; un seul rapporteur resterait UNVERIFIED.
            for r in rows:
                if r.data_status == "UNVERIFIED":
                    r.data_status = "VERIFIED"
                    report.upgraded_to_verified += 1
    session.commit()
    return report


def sweep_stale(session: Session, now: datetime | None = None,
                grace_hours: float = 3.0) -> int:
    """Fraîcheur (§1, §64) : une fixture restée SCHEDULED/UPCOMING alors que son
    kickoff est dépassé depuis `grace_hours` n'est plus vérifiable en l'état.
    → statut UNKNOWN (DONNÉE NON VÉRIFIÉE) jusqu'à confirmation par une source ;
    la boucle ESPN (hier/aujourd'hui/demain) la repassera à FINISHED/SCHEDULED.

    Retourne le nombre de lignes balayées. Jamais de score inventé : seul le statut change.
    """
    from datetime import timedelta, timezone
    now = now or datetime.now(timezone.utc)
    limit = now - timedelta(hours=grace_hours)
    n = 0
    for fx in session.query(Fixture).filter(
            Fixture.status.in_(["SCHEDULED", "UPCOMING", "LINEUPS_PENDING", "LINEUPS_CONFIRMED"]),
            Fixture.kickoff_utc < limit.replace(tzinfo=None)).all():
        fx.status = "UNKNOWN"
        n += 1
    if n:
        session.commit()
    return n
