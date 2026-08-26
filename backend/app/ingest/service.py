"""INGESTION PIPELINE : RawFixture → validation → résolution → upsert idempotent.

Garanties :
- Idempotence : relancer le même ingest ne crée aucun doublon (clé provider+event, §6).
- Rejets audités (table ingestion_rejects).
- data_status : 'VERIFIED' pour fduk (source historique établie), 'UNVERIFIED' pour ESPN
  tant qu'aucune 2ᵉ source ne confirme (§1, §4).
"""
from __future__ import annotations

import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Iterable

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from ..db.models import (
    Bookmaker,
    EntityMapping,
    Fixture,
    IngestionReject,
    Market,
    OddsSnapshot,
    ProviderHealth,
    Season,
)
from ..providers.base import Provider, RawFixture
from .resolution import resolve_competition, resolve_team, season_bounds
from .validation import validate_fixture

# Niveau de confiance natif par source (§4) : fduk = source historique établie ;
# les autres attendent une confirmation croisée (consistency engine) pour monter en VERIFIED.
DATA_STATUS_BY_PROVIDER = {
    "fduk": "VERIFIED",
    "espn": "UNVERIFIED",
    "openligadb": "UNVERIFIED",
    "tsdb": "UNVERIFIED",
    "fdorg": "UNVERIFIED",
}


@dataclass
class IngestReport:
    provider: str
    received: int = 0
    created: int = 0
    updated: int = 0
    skipped_unchanged: int = 0
    rejected: int = 0
    odds_rows: int = 0
    errors: list[str] = field(default_factory=list)
    latency_ms: float | None = None

    def as_dict(self) -> dict:
        return {
            "provider": self.provider,
            "received": self.received,
            "created": self.created,
            "updated": self.updated,
            "skipped_unchanged": self.skipped_unchanged,
            "rejected": self.rejected,
            "odds_rows": self.odds_rows,
            "errors": self.errors,
            "latency_ms": self.latency_ms,
        }


def _get_or_create(session: Session, model, defaults: dict, **lookup):
    obj = session.query(model).filter_by(**lookup).one_or_none()
    if obj is None:
        obj = model(**lookup, **defaults)
        session.add(obj)
        session.flush()
    return obj


def _get_or_create_season(session: Session, competition_id: int, label: str) -> Season:
    start, end = season_bounds(label)
    return _get_or_create(
        session, Season,
        defaults={"start_year": start, "end_year": end},
        competition_id=competition_id, label=label,
    )


def _naive_utc(dt: datetime | None) -> datetime | None:
    """Normalisation UTC naïve — SQLite ne conserve pas le fuseau à la relecture,
    PostgreSQL si. Comparer naïf↔naïf évite les faux 'changements' (idempotence §9)."""
    if dt is None:
        return None
    if dt.tzinfo is not None:
        return dt.astimezone(timezone.utc).replace(tzinfo=None)
    return dt


def _fixture_changed(fx: Fixture, raw: RawFixture) -> bool:
    """Comparaison champ à champ — un re-téléchargement identique ne touche pas last_updated_at (§9)."""
    checks = [
        fx.status != raw.status,
        fx.home_score != raw.home_score,
        fx.away_score != raw.away_score,
        fx.home_score_ht != raw.home_score_ht,
        fx.away_score_ht != raw.away_score_ht,
        fx.venue != raw.venue,
        fx.venue_city != raw.venue_city,
        fx.clock != raw.clock,
        fx.referee != raw.referee,
        fx.home_xg != raw.home_xg,
        fx.away_xg != raw.away_xg,
        _naive_utc(fx.kickoff_utc) != _naive_utc(raw.kickoff_utc),
    ]
    return any(checks)


def ingest_one(session: Session, raw: RawFixture, report: IngestReport) -> None:
    report.received += 1
    errors = validate_fixture(raw)
    if errors:
        report.rejected += 1
        session.add(IngestionReject(
            provider=raw.provider, provider_id=raw.provider_id,
            reasons=errors, payload=(raw.raw or {}) | {"home": raw.home.name, "away": raw.away.name},
        ))
        return

    now = datetime.now(timezone.utc)
    comp, _ = resolve_competition(session, raw)
    season = _get_or_create_season(session, comp.id, raw.season_label) if raw.season_label else None
    home_team, _ = resolve_team(session, raw.home, raw.provider)
    away_team, _ = resolve_team(session, raw.away, raw.provider)

    fx = (
        session.query(Fixture)
        .filter_by(source_provider=raw.provider, source_event_id=raw.provider_id)
        .one_or_none()
    )

    if fx is None:
        fx = Fixture(
            competition_id=comp.id,
            season_id=season.id if season else None,
            home_team_id=home_team.id,
            away_team_id=away_team.id,
            kickoff_utc=raw.kickoff_utc,
            kickoff_time_known=raw.kickoff_time_known,
            status=raw.status,
            home_score=raw.home_score,
            away_score=raw.away_score,
            home_score_ht=raw.home_score_ht,
            away_score_ht=raw.away_score_ht,
            venue=raw.venue,
            venue_city=raw.venue_city,
            clock=raw.clock,
            referee=raw.referee,
            home_xg=raw.home_xg,
            away_xg=raw.away_xg,
            data_status=DATA_STATUS_BY_PROVIDER.get(raw.provider, "UNVERIFIED"),
            source_provider=raw.provider,
            source_event_id=raw.provider_id,
            source_url=raw.source_url,
            raw_payload=raw.raw,
            fetched_at=now,
            last_updated_at=now,
        )
        session.add(fx)
        try:
            session.flush()
        except IntegrityError:
            session.rollback()
            report.errors.append(f"conflit_unicite:{raw.provider_id}")
            report.rejected += 1
            return
        session.add(EntityMapping(entity_type="fixture", entity_id=fx.id,
                                  provider=raw.provider, provider_id=raw.provider_id))
        report.created += 1
    else:
        if _fixture_changed(fx, raw):
            fx.status = raw.status
            fx.home_score = raw.home_score
            fx.away_score = raw.away_score
            fx.home_score_ht = raw.home_score_ht
            fx.away_score_ht = raw.away_score_ht
            fx.venue = raw.venue if raw.venue is not None else fx.venue
            fx.venue_city = raw.venue_city if raw.venue_city is not None else fx.venue_city
            fx.clock = raw.clock   # NULL hors LIVE : la minute expirée ne doit pas persister (§1)
            fx.referee = raw.referee if raw.referee is not None else fx.referee
            fx.home_xg = raw.home_xg if raw.home_xg is not None else fx.home_xg
            fx.away_xg = raw.away_xg if raw.away_xg is not None else fx.away_xg
            fx.kickoff_utc = raw.kickoff_utc
            fx.raw_payload = raw.raw
            fx.last_updated_at = now
            report.updated += 1
        else:
            report.skipped_unchanged += 1

    _ingest_odds(session, fx, raw, now, report)


def attach_odds_to_fixture(session: Session, fx: Fixture, odds: list,
                           provider_name: str, now: datetime | None = None) -> int:
    """Insère les snapshots de cotes d'un fixture (append-only, idempotent par valeur).

    Utilisé par l'ingestion classique ET par les providers de cotes dédiés
    (ex. The Odds API) qui associent leurs cotes à un match déjà en base.
    Retourne le nombre de nouveaux snapshots.
    """
    now = now or datetime.now(timezone.utc)
    report = IngestReport(provider=provider_name)
    holder = type("_RawOdds", (), {"odds": odds})()
    _ingest_odds(session, fx, holder, now, report)
    return report.odds_rows


def _ingest_odds(session: Session, fx: Fixture, raw: RawFixture, now: datetime, report: IngestReport) -> None:
    """Append-only (§30) : on n'insère un snapshot que s'il est nouveau (valeur différente
    du dernier snapshot connu pour ce bookmaker/marché/sélection)."""
    for o in raw.odds:
        bm = _get_or_create(session, Bookmaker, defaults={"name": o.bookmaker}, code=o.bookmaker)
        if bm.name == o.bookmaker:  # nom d'affichage amélioré si connu
            from ..providers.football_data_uk import BOOKMAKER_NAMES
            bm.name = BOOKMAKER_NAMES.get(o.bookmaker, o.bookmaker)
        mk = _get_or_create(session, Market, defaults={"name": o.market}, code=o.market)
        last = (
            session.query(OddsSnapshot)
            .filter_by(fixture_id=fx.id, bookmaker_id=bm.id, market_id=mk.id,
                       selection=o.selection, origin=o.origin)
            .order_by(OddsSnapshot.captured_at.desc())
            .first()
        )
        if last is not None and abs(last.odds - o.odds) < 1e-9:
            continue
        session.add(OddsSnapshot(
            fixture_id=fx.id, bookmaker_id=bm.id, market_id=mk.id,
            selection=o.selection, odds=o.odds, status=o.status,
            captured_at=now, origin=o.origin,
        ))
        report.odds_rows += 1


def run_ingestion(session: Session, provider: Provider, payloads: Iterable[RawFixture]) -> IngestReport:
    report = IngestReport(provider=provider.name)
    t0 = time.perf_counter()
    for raw in payloads:
        try:
            ingest_one(session, raw, report)
        except Exception as exc:  # jamais d'échec silencieux (§66) : rollback + tracé
            session.rollback()
            report.errors.append(f"{type(exc).__name__}: {exc}")
    report.latency_ms = round((time.perf_counter() - t0) * 1000, 1)
    _record_health(session, provider.name, report)
    session.commit()
    return report


def _record_health(session: Session, provider_name: str, report: IngestReport) -> None:
    ph = session.query(ProviderHealth).filter_by(provider=provider_name).one_or_none()
    if ph is None:
        ph = ProviderHealth(provider=provider_name)
        session.add(ph)
    ph.status = "OK" if not report.errors else "DEGRADED"
    ph.latency_ms = report.latency_ms
    ph.detail = (f"received={report.received} created={report.created} "
                 f"updated={report.updated} rejected={report.rejected}")
    ph.checked_at = datetime.now(timezone.utc)
