"""Schéma PRONO SPORT v1 — Module 1 (schéma §12 du cahier des charges, périmètre fondation).

Principes :
- Toute donnée externe garde sa provenance (source_provider, source_event_id, fetched_at, raw_payload).
- Aucune donnée inventée : champs absents = NULL + data_status explicite (§1).
- Identifiants internes uniques ; correspondances fournisseurs via entity_mappings (§5-6).
"""
from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import (
    JSON,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .base import Base


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


# --- Statuts fixture (§8), vocabulaire de qualité de donnée (§1) ---
FIXTURE_STATUSES = {
    "SCHEDULED", "UPCOMING", "LINEUPS_PENDING", "LINEUPS_CONFIRMED",
    "LIVE", "HALFTIME", "EXTRA_TIME", "PENALTIES", "FINISHED",
    "POSTPONED", "CANCELLED", "SUSPENDED", "ABANDONED", "UNKNOWN",
}

# DONNÉE NON VÉRIFIÉE / DONNÉES CONTRADICTOIRES / ÉCHANTILLON INSUFFISANT ↔ codes DB
DATA_STATUSES = {"VERIFIED", "UNVERIFIED", "CONTRADICTORY", "INSUFFICIENT_SAMPLE"}


class DataSource(Base):
    """Registre des fournisseurs (§3-4, table data_sources §12)."""
    __tablename__ = "data_sources"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(50), unique=True)
    kind: Mapped[str] = mapped_column(String(30))  # football_data | odds | weather | news
    base_url: Mapped[str] = mapped_column(String(255))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class ProviderHealth(Base):
    """Santé fournisseur — dashboard DATA HEALTH (§75)."""
    __tablename__ = "provider_health"

    id: Mapped[int] = mapped_column(primary_key=True)
    provider: Mapped[str] = mapped_column(String(50), unique=True)
    status: Mapped[str] = mapped_column(String(20))  # OK / DEGRADED / DOWN
    latency_ms: Mapped[float | None] = mapped_column(Float, nullable=True)
    detail: Mapped[str | None] = mapped_column(Text, nullable=True)
    checked_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)


class Competition(Base):
    __tablename__ = "competitions"

    id: Mapped[int] = mapped_column(primary_key=True)
    code: Mapped[str] = mapped_column(String(30), unique=True)  # code canonique interne ex. ENG-E0
    name: Mapped[str] = mapped_column(String(120))
    area: Mapped[str | None] = mapped_column(String(80), nullable=True)
    logo_url: Mapped[str | None] = mapped_column(String(255), nullable=True)  # §57 source autorisée
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    seasons: Mapped[list["Season"]] = relationship(back_populates="competition")


class Season(Base):
    __tablename__ = "seasons"

    id: Mapped[int] = mapped_column(primary_key=True)
    competition_id: Mapped[int] = mapped_column(ForeignKey("competitions.id"))
    label: Mapped[str] = mapped_column(String(20))  # ex. 2026-2027
    start_year: Mapped[int] = mapped_column(Integer)
    end_year: Mapped[int] = mapped_column(Integer)

    __table_args__ = (UniqueConstraint("competition_id", "label", name="uq_season_comp_label"),)

    competition: Mapped[Competition] = relationship(back_populates="seasons")


class Team(Base):
    __tablename__ = "teams"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(120))            # nom d'affichage canonique
    country: Mapped[str | None] = mapped_column(String(80), nullable=True)
    logo_url: Mapped[str | None] = mapped_column(String(255), nullable=True)  # §57 : source autorisée
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    aliases: Mapped[list["TeamAlias"]] = relationship(back_populates="team", cascade="all, delete-orphan")


class TeamAlias(Base):
    """Autres noms/abréviations d'une même équipe — jamais de fusion sur le nom seul (§5)."""
    __tablename__ = "team_aliases"

    id: Mapped[int] = mapped_column(primary_key=True)
    team_id: Mapped[int] = mapped_column(ForeignKey("teams.id"))
    alias: Mapped[str] = mapped_column(String(120), unique=True)  # forme normalisée

    team: Mapped[Team] = relationship(back_populates="aliases")


class EntityMapping(Base):
    """Correspondance ID interne ↔ ID fournisseur (§5-6 : PRONO_SPORT_*_ID + provider_*_id)."""
    __tablename__ = "entity_mappings"

    id: Mapped[int] = mapped_column(primary_key=True)
    entity_type: Mapped[str] = mapped_column(String(20))  # team | competition | fixture
    entity_id: Mapped[int] = mapped_column(Integer)       # ID interne
    provider: Mapped[str] = mapped_column(String(50))
    provider_id: Mapped[str] = mapped_column(String(80))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    __table_args__ = (
        UniqueConstraint("entity_type", "provider", "provider_id", name="uq_mapping_provider_id"),
        Index("ix_mapping_entity", "entity_type", "entity_id"),
    )


class Fixture(Base):
    __tablename__ = "fixtures"

    id: Mapped[int] = mapped_column(primary_key=True)
    competition_id: Mapped[int] = mapped_column(ForeignKey("competitions.id"))
    season_id: Mapped[int | None] = mapped_column(ForeignKey("seasons.id"), nullable=True)
    home_team_id: Mapped[int] = mapped_column(ForeignKey("teams.id"))
    away_team_id: Mapped[int] = mapped_column(ForeignKey("teams.id"))

    kickoff_utc: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    kickoff_time_known: Mapped[bool] = mapped_column(default=True)  # False = heure inconnue (jamais inventée silencieusement)
    status: Mapped[str] = mapped_column(String(20))                 # §8
    home_score: Mapped[int | None] = mapped_column(Integer, nullable=True)
    away_score: Mapped[int | None] = mapped_column(Integer, nullable=True)
    home_score_ht: Mapped[int | None] = mapped_column(Integer, nullable=True)
    away_score_ht: Mapped[int | None] = mapped_column(Integer, nullable=True)
    venue: Mapped[str | None] = mapped_column(String(160), nullable=True)
    venue_city: Mapped[str | None] = mapped_column(String(120), nullable=True)  # M7 météo
    clock: Mapped[str | None] = mapped_column(String(12), nullable=True)        # M6 minute live
    referee: Mapped[str | None] = mapped_column(String(160), nullable=True)
    home_xg: Mapped[float | None] = mapped_column(Float, nullable=True)  # source fduk HxG ou NULL
    away_xg: Mapped[float | None] = mapped_column(Float, nullable=True)

    data_status: Mapped[str] = mapped_column(String(20), default="UNVERIFIED")  # §1
    source_provider: Mapped[str] = mapped_column(String(50))
    source_event_id: Mapped[str] = mapped_column(String(120))
    source_url: Mapped[str | None] = mapped_column(String(255), nullable=True)
    raw_payload: Mapped[dict | None] = mapped_column(JSON, nullable=True)       # traçabilité §47
    fetched_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    last_updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    __table_args__ = (
        UniqueConstraint("source_provider", "source_event_id", name="uq_fixture_provider_event"),
        Index("ix_fixture_natural", "kickoff_utc", "home_team_id", "away_team_id"),
        Index("ix_fixture_status", "status"),
    )


class Bookmaker(Base):
    __tablename__ = "bookmakers"

    id: Mapped[int] = mapped_column(primary_key=True)
    code: Mapped[str] = mapped_column(String(30), unique=True)
    name: Mapped[str] = mapped_column(String(120))


class Market(Base):
    __tablename__ = "markets"

    id: Mapped[int] = mapped_column(primary_key=True)
    code: Mapped[str] = mapped_column(String(30), unique=True)  # 1X2 | OU_2.5 | BTTS…
    name: Mapped[str] = mapped_column(String(120))


class OddsSnapshot(Base):
    """Historique des cotes (§30) : append-only, chaque snapshot horodaté."""
    __tablename__ = "odds_snapshots"

    id: Mapped[int] = mapped_column(primary_key=True)
    fixture_id: Mapped[int] = mapped_column(ForeignKey("fixtures.id"))
    bookmaker_id: Mapped[int] = mapped_column(ForeignKey("bookmakers.id"))
    market_id: Mapped[int] = mapped_column(ForeignKey("markets.id"))
    selection: Mapped[str] = mapped_column(String(10))  # H | D | A | Over | Under
    odds: Mapped[float] = mapped_column(Float)
    status: Mapped[str] = mapped_column(String(20), default="ACTIVE")  # §42 : SUSPENDED exclu
    captured_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    origin: Mapped[str] = mapped_column(String(20), default="PROVIDER")  # PROVIDER | CLOSING (à confirmer)

    __table_args__ = (Index("ix_odds_fixture", "fixture_id", "market_id"),)


class IngestionReject(Base):
    """Données rejetées par la validation (§7) — auditables, jamais silencieusement perdues."""
    __tablename__ = "ingestion_rejects"

    id: Mapped[int] = mapped_column(primary_key=True)
    provider: Mapped[str] = mapped_column(String(50))
    provider_id: Mapped[str | None] = mapped_column(String(120), nullable=True)
    reasons: Mapped[list] = mapped_column(JSON)
    payload: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class ModelVersion(Base):
    """MODEL GOVERNANCE (§20) : aucune modification silencieuse d'un modèle en production."""
    __tablename__ = "model_versions"

    id: Mapped[int] = mapped_column(primary_key=True)
    model_id: Mapped[str] = mapped_column(String(50))          # poisson-dc
    version: Mapped[str] = mapped_column(String(30))           # v1
    date_training: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    dataset_version: Mapped[str] = mapped_column(String(60))   # ex. "fduk+espn 2025/26+2026/27"
    features_version: Mapped[str] = mapped_column(String(20), default="v1")
    metrics: Mapped[dict | None] = mapped_column(JSON, nullable=True)   # logloss, brier (§68) si calculés
    params: Mapped[dict | None] = mapped_column(JSON, nullable=True)    # hyperparamètres documentés
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    __table_args__ = (UniqueConstraint("model_id", "version", name="uq_model_version"),)


class Prediction(Base):
    """Prédiction + reproductibilité totale (§73) : on peut reconstruire POURQUOI."""
    __tablename__ = "predictions"

    id: Mapped[int] = mapped_column(primary_key=True)
    fixture_id: Mapped[int] = mapped_column(ForeignKey("fixtures.id"))
    model_version_id: Mapped[int] = mapped_column(ForeignKey("model_versions.id"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    feature_version: Mapped[str] = mapped_column(String(20))
    input_snapshot: Mapped[dict] = mapped_column(JSON)   # forces att/def utilisées, échantillons
    probabilities: Mapped[dict] = mapped_column(JSON)    # {"1X2": {...}, "OU_2.5": {...}, "BTTS": {...}}
    expected_goals: Mapped[dict | None] = mapped_column(JSON, nullable=True)  # λ domicile/extérieur

    __table_args__ = (Index("ix_pred_fixture", "fixture_id"),)


class ValueBet(Base):
    """Value Bet qualifiée (§33-39) : UNIQUEMENT sur cotes réelles et modèle calibré.
    Niveaux §35 : NO_VALUE | POTENTIAL | QUALIFIED | STRONG."""
    __tablename__ = "value_bets"

    id: Mapped[int] = mapped_column(primary_key=True)
    fixture_id: Mapped[int] = mapped_column(ForeignKey("fixtures.id"))
    prediction_id: Mapped[int] = mapped_column(ForeignKey("predictions.id"))
    market: Mapped[str] = mapped_column(String(20))
    selection: Mapped[str] = mapped_column(String(10))
    odds_reference: Mapped[float] = mapped_column(Float)   # meilleure cote réelle (MAX)
    bookmaker_ref: Mapped[str] = mapped_column(String(30))
    p_model: Mapped[float] = mapped_column(Float)
    p_market_fair: Mapped[float] = mapped_column(Float)      # marge retirée (§32)
    edge: Mapped[float] = mapped_column(Float)               # p_model − p_fair (points)
    ev: Mapped[float] = mapped_column(Float)                 # p × O − 1 (§33)
    level: Mapped[str] = mapped_column(String(12))           # NO_VALUE|POTENTIAL|QUALIFIED|STRONG
    confidence: Mapped[str] = mapped_column(String(12), default="MOYENNE")  # §39
    computed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    __table_args__ = (Index("ix_vb_fixture", "fixture_id"),)


class TeamAnalytics(Base):
    """Sorties du moteur analytique M3 (§16 TEAM POWER, §21 feature store).

    Toutes les valeurs sont CALCULÉES depuis les fixtures réelles en base —
    traçables (features_version, computed_at) et reproductibles (§72-73).
    Aucune valeur n'est inventée : sans historique, la ligne n'existe pas.
    """
    __tablename__ = "team_analytics"

    id: Mapped[int] = mapped_column(primary_key=True)
    team_id: Mapped[int] = mapped_column(ForeignKey("teams.id"), unique=True)
    elo: Mapped[float | None] = mapped_column(Float, nullable=True)          # §16 TEAM STRENGTH SCORE
    matches_rated: Mapped[int] = mapped_column(Integer, default=0)           # profondeur réelle de l'échantillon
    form5: Mapped[str | None] = mapped_column(String(5), nullable=True)      # ex. "WWDLL" (W=win) plus récent d'abord
    points5: Mapped[int | None] = mapped_column(Integer, nullable=True)      # points sur les 5 derniers matchs
    gf5: Mapped[float | None] = mapped_column(Float, nullable=True)          # buts marqués / match (5 derniers, décay §14)
    ga5: Mapped[float | None] = mapped_column(Float, nullable=True)          # buts encaissés / match (idem)
    features_version: Mapped[str] = mapped_column(String(20), default="v1")  # versioning §21/§72
    model_version: Mapped[str] = mapped_column(String(30), default="elo-v1") # gouvernance §20
    computed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
