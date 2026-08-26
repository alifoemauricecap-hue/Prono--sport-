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
    """Registre des fournisseurs (§3-4, table data_sources §12).

    3.0 — extension du moteur de découverte : chaque source suit un cycle de vie
    DISCOVERED → TESTING → VALIDATED → APPROVED / REJECTED / NOT_ALLOWED / DOWN.
    La fiabilité est TOUJOURS calculée à partir de l'observé (sync_jobs, provider_health)
    — une source nouvelle a reliability_score = NULL (« jamais inventée », §8).
    """
    __tablename__ = "data_sources"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(50), unique=True)
    kind: Mapped[str] = mapped_column(String(30))  # football_data | odds | weather | news | research
    base_url: Mapped[str] = mapped_column(String(255))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    # --- 3.0 : cycle de vie & découverte ---
    status: Mapped[str | None] = mapped_column(String(20), nullable=True)
    # DISCOVERED | TESTING | VALIDATED | APPROVED | REJECTED | NOT_ALLOWED | DOWN
    data_categories: Mapped[list | None] = mapped_column(JSON, nullable=True)
    coverage: Mapped[str | None] = mapped_column(String(255), nullable=True)
    update_frequency: Mapped[str | None] = mapped_column(String(60), nullable=True)
    reliability_score: Mapped[float | None] = mapped_column(Float, nullable=True)  # 0-100, NULL = non mesurable
    availability_status: Mapped[str | None] = mapped_column(String(20), nullable=True)  # OK | DEGRADED | DOWN
    terms_status: Mapped[str | None] = mapped_column(String(20), nullable=True)  # OK | TO_VERIFY | FORBIDDEN
    attribution_required: Mapped[bool | None] = mapped_column(nullable=True)
    requires_key: Mapped[bool | None] = mapped_column(nullable=True, default=False)
    last_checked: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_successful_fetch: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_failed_fetch: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


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


# =============================================================================
# PRONO SPORT 3.0 — tables ajoutées (schéma cible : 33 tables)
# =============================================================================

class Continent(Base):
    """§87 couverture mondiale : continents réels (dérivés des compétitions, jamais hardcodés)."""
    __tablename__ = "continents"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(60), unique=True)


class Country(Base):
    """§87 : pays réels (depuis l'area des compétitions / pays des équipes)."""
    __tablename__ = "countries"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(80), unique=True)
    continent_id: Mapped[int | None] = mapped_column(ForeignKey("continents.id"), nullable=True)

    continent: Mapped["Continent | None"] = relationship()


class Round(Base):
    """§18 : journée/manche réelle lorsqu'une source la fournit."""
    __tablename__ = "rounds"

    id: Mapped[int] = mapped_column(primary_key=True)
    competition_id: Mapped[int] = mapped_column(ForeignKey("competitions.id"))
    season_id: Mapped[int | None] = mapped_column(ForeignKey("seasons.id"), nullable=True)
    round_num: Mapped[int | None] = mapped_column(Integer, nullable=True)
    label: Mapped[str | None] = mapped_column(String(80), nullable=True)
    source: Mapped[str | None] = mapped_column(String(50), nullable=True)

    __table_args__ = (
        UniqueConstraint("competition_id", "season_id", "round_num", "label",
                         name="uq_round"),
    )


class Venue(Base):
    """§50 Match Center : stades réels (depuis les sources), avec coordonnées pour la météo."""
    __tablename__ = "venues"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(160))
    city: Mapped[str | None] = mapped_column(String(120), nullable=True)
    country: Mapped[str | None] = mapped_column(String(80), nullable=True)
    capacity: Mapped[int | None] = mapped_column(Integer, nullable=True)  # NULL si jamais fournie
    latitude: Mapped[float | None] = mapped_column(Float, nullable=True)
    longitude: Mapped[float | None] = mapped_column(Float, nullable=True)
    source: Mapped[str | None] = mapped_column(String(50), nullable=True)


class Player(Base):
    """§21 : joueurs — uniquement si une source réelle les fournit (sinon table vide)."""
    __tablename__ = "players"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(120))
    team_id: Mapped[int | None] = mapped_column(ForeignKey("teams.id"), nullable=True)
    position: Mapped[str | None] = mapped_column(String(40), nullable=True)
    country: Mapped[str | None] = mapped_column(String(80), nullable=True)
    logo_url: Mapped[str | None] = mapped_column(String(255), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class PlayerAlias(Base):
    __tablename__ = "player_aliases"

    id: Mapped[int] = mapped_column(primary_key=True)
    player_id: Mapped[int] = mapped_column(ForeignKey("players.id"))
    alias: Mapped[str] = mapped_column(String(120), unique=True)


class Lineup(Base):
    """§23 : compositions officielles uniquement — jamais inventées."""
    __tablename__ = "lineups"

    id: Mapped[int] = mapped_column(primary_key=True)
    fixture_id: Mapped[int] = mapped_column(ForeignKey("fixtures.id"))
    team_id: Mapped[int] = mapped_column(ForeignKey("teams.id"))
    player_id: Mapped[int | None] = mapped_column(ForeignKey("players.id"), nullable=True)
    player_name: Mapped[str | None] = mapped_column(String(120), nullable=True)
    number: Mapped[int | None] = mapped_column(Integer, nullable=True)
    position: Mapped[str | None] = mapped_column(String(40), nullable=True)
    is_starting: Mapped[bool] = mapped_column(default=True)
    source: Mapped[str | None] = mapped_column(String(50), nullable=True)
    fetched_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    __table_args__ = (Index("ix_lineup_fixture", "fixture_id", "team_id"),)


class Injury(Base):
    """§22 PLAYER AVAILABILITY — statuts réels, jamais inventés."""
    __tablename__ = "injuries"

    id: Mapped[int] = mapped_column(primary_key=True)
    player_id: Mapped[int] = mapped_column(ForeignKey("players.id"))
    status: Mapped[str] = mapped_column(String(20))  # INJURED | DOUBTFUL | RETURNING
    detail: Mapped[str | None] = mapped_column(String(255), nullable=True)
    expected_return: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    source: Mapped[str | None] = mapped_column(String(50), nullable=True)
    fetched_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class Suspension(Base):
    __tablename__ = "suspensions"

    id: Mapped[int] = mapped_column(primary_key=True)
    player_id: Mapped[int] = mapped_column(ForeignKey("players.id"))
    reason: Mapped[str | None] = mapped_column(String(120), nullable=True)
    matches: Mapped[int | None] = mapped_column(Integer, nullable=True)
    source: Mapped[str | None] = mapped_column(String(50), nullable=True)
    fetched_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class WeatherSnapshot(Base):
    """§29 : météo réelle d'une ville/stade à un instant (Open-Meteo), horodatée."""
    __tablename__ = "weather_snapshots"

    id: Mapped[int] = mapped_column(primary_key=True)
    city: Mapped[str] = mapped_column(String(120))
    at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    temperature: Mapped[float | None] = mapped_column(Float, nullable=True)
    precipitation: Mapped[float | None] = mapped_column(Float, nullable=True)
    wind_speed: Mapped[float | None] = mapped_column(Float, nullable=True)
    humidity: Mapped[int | None] = mapped_column(Integer, nullable=True)
    condition: Mapped[str | None] = mapped_column(String(80), nullable=True)
    source: Mapped[str] = mapped_column(String(50), default="open-meteo")
    fetched_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    __table_args__ = (Index("ix_weather_city_at", "city", "at"),)


class FixtureEvent(Base):
    """§16 : événements de match — observés ou déduits de changements de score réels
    (un but est déduit d'un delta de score entre deux lectures source : CALCULATED DATA,
    jamais inventé si le score n'a pas bougé)."""
    __tablename__ = "fixture_events"

    id: Mapped[int] = mapped_column(primary_key=True)
    fixture_id: Mapped[int] = mapped_column(ForeignKey("fixtures.id"))
    minute: Mapped[int | None] = mapped_column(Integer, nullable=True)
    type: Mapped[str] = mapped_column(String(20))  # GOAL | STATUS_CHANGE | LINEUP | ODDS
    team_id: Mapped[int | None] = mapped_column(ForeignKey("teams.id"), nullable=True)
    detail: Mapped[str | None] = mapped_column(String(255), nullable=True)
    origin: Mapped[str] = mapped_column(String(20), default="OBSERVED")  # OBSERVED | DERIVED
    source: Mapped[str | None] = mapped_column(String(50), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    __table_args__ = (Index("ix_fxevent_fixture", "fixture_id", "created_at"),)


class TeamStat(Base):
    """§20 : statistiques d'équipe par match, horodatées (as_of) et sourcées."""
    __tablename__ = "team_statistics"

    id: Mapped[int] = mapped_column(primary_key=True)
    fixture_id: Mapped[int] = mapped_column(ForeignKey("fixtures.id"))
    team_id: Mapped[int] = mapped_column(ForeignKey("teams.id"))
    as_of: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    possession: Mapped[int | None] = mapped_column(Integer, nullable=True)
    shots: Mapped[int | None] = mapped_column(Integer, nullable=True)
    shots_on_target: Mapped[int | None] = mapped_column(Integer, nullable=True)
    corners: Mapped[int | None] = mapped_column(Integer, nullable=True)
    fouls: Mapped[int | None] = mapped_column(Integer, nullable=True)
    yellow_cards: Mapped[int | None] = mapped_column(Integer, nullable=True)
    red_cards: Mapped[int | None] = mapped_column(Integer, nullable=True)
    source: Mapped[str | None] = mapped_column(String(50), nullable=True)

    __table_args__ = (Index("ix_teamstat_fixture", "fixture_id", "team_id"),)


class SyncJob(Base):
    """§14/§63 : journal des workers — idempotence, erreurs, latence, records."""
    __tablename__ = "sync_jobs"

    id: Mapped[int] = mapped_column(primary_key=True)
    worker: Mapped[str] = mapped_column(String(40))
    provider: Mapped[str | None] = mapped_column(String(50), nullable=True)
    status: Mapped[str] = mapped_column(String(20))  # OK | DEGRADED | FAILED
    records: Mapped[int | None] = mapped_column(Integer, nullable=True)
    created: Mapped[int | None] = mapped_column(Integer, nullable=True)
    updated: Mapped[int | None] = mapped_column(Integer, nullable=True)
    rejected: Mapped[int | None] = mapped_column(Integer, nullable=True)
    latency_ms: Mapped[float | None] = mapped_column(Float, nullable=True)
    errors: Mapped[list | None] = mapped_column(JSON, nullable=True)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    __table_args__ = (Index("ix_syncjob_worker", "worker", "started_at"),)


class DataQuality(Base):
    """§47 DATA QUALITY SCORE par compétition — calculé, jamais affirmé."""
    __tablename__ = "data_quality"

    id: Mapped[int] = mapped_column(primary_key=True)
    competition_id: Mapped[int] = mapped_column(ForeignKey("competitions.id"), unique=True)
    score: Mapped[float | None] = mapped_column(Float, nullable=True)  # 0-100
    fixtures: Mapped[int | None] = mapped_column(Integer, nullable=True)
    verified_pct: Mapped[float | None] = mapped_column(Float, nullable=True)
    n_sources: Mapped[int | None] = mapped_column(Integer, nullable=True)
    history_from: Mapped[int | None] = mapped_column(Integer, nullable=True)  # 1re saison en base
    history_to: Mapped[int | None] = mapped_column(Integer, nullable=True)    # dernière saison
    freshness_min: Mapped[float | None] = mapped_column(Float, nullable=True)  # âge du dernier match, min
    missing: Mapped[list | None] = mapped_column(JSON, nullable=True)         # catégories absentes
    computed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class AnalysisReport(Base):
    """§46 EXPERT MATCH REPORT — rapport de recherche approfondie, horodaté et sourcé."""
    __tablename__ = "analysis_reports"

    id: Mapped[int] = mapped_column(primary_key=True)
    fixture_id: Mapped[int] = mapped_column(ForeignKey("fixtures.id"), unique=True)
    sections: Mapped[dict] = mapped_column(JSON)
    sources_used: Mapped[list] = mapped_column(JSON)
    data_quality_score: Mapped[float | None] = mapped_column(Float, nullable=True)
    model_version: Mapped[str | None] = mapped_column(String(60), nullable=True)
    generated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    __table_args__ = (Index("ix_report_fixture", "fixture_id"),)


class PredictionSnapshot(Base):
    """§53 LIVE PREDICTION : probabilités AVANT → APRÈS un événement, inmutables."""
    __tablename__ = "prediction_snapshots"

    id: Mapped[int] = mapped_column(primary_key=True)
    prediction_id: Mapped[int] = mapped_column(ForeignKey("predictions.id"))
    fixture_id: Mapped[int] = mapped_column(ForeignKey("fixtures.id"))
    minute: Mapped[int | None] = mapped_column(Integer, nullable=True)
    trigger: Mapped[str] = mapped_column(String(40))  # GOAL | RED_CARD | HALFTIME | ...
    before: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    after: Mapped[dict] = mapped_column(JSON)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    __table_args__ = (Index("ix_psnap_fixture", "fixture_id", "created_at"),)


class PredictionResult(Base):
    """§54 : résultat d'un pronostic APRÈS le match — la prédiction originale
    est conservée à l'identique (résolution non-destructive)."""
    __tablename__ = "prediction_results"

    id: Mapped[int] = mapped_column(primary_key=True)
    prediction_id: Mapped[int] = mapped_column(ForeignKey("predictions.id"))
    fixture_id: Mapped[int] = mapped_column(ForeignKey("fixtures.id"))
    market: Mapped[str] = mapped_column(String(20), default="1X2")
    selection: Mapped[str | None] = mapped_column(String(10), nullable=True)
    actual: Mapped[str | None] = mapped_column(String(10), nullable=True)
    result: Mapped[str] = mapped_column(String(10))  # WIN | LOSS | VOID | PENDING
    final_score: Mapped[str | None] = mapped_column(String(10), nullable=True)
    resolved_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    __table_args__ = (Index("ix_presult_fixture", "fixture_id"),)


class Notification(Base):
    """§83 : notifications réelles (événement observé en base)."""
    __tablename__ = "notifications"

    id: Mapped[int] = mapped_column(primary_key=True)
    user: Mapped[str] = mapped_column(String(40), default="local")
    type: Mapped[str] = mapped_column(String(30))  # MATCH_START | GOAL | MATCH_END | VALUE_BET | ODDS_CHANGE | LIVE
    fixture_id: Mapped[int | None] = mapped_column(ForeignKey("fixtures.id"), nullable=True)
    message: Mapped[str] = mapped_column(String(300))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    read: Mapped[bool] = mapped_column(default=False)

    __table_args__ = (Index("ix_notif_user", "user", "created_at"),)


class Favorite(Base):
    """§82 : favoris (équipes, compétitions, matchs)."""
    __tablename__ = "favorites"

    id: Mapped[int] = mapped_column(primary_key=True)
    user: Mapped[str] = mapped_column(String(40), default="local")
    kind: Mapped[str] = mapped_column(String(20))  # team | competition | fixture | player
    ref_id: Mapped[int] = mapped_column(Integer)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    __table_args__ = (
        UniqueConstraint("user", "kind", "ref_id", name="uq_favorite"),
    )


class User(Base):
    """§63 : utilisateurs (admin optionnel ; par défaut utilisateur « local »)."""
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(60), unique=True)
    role: Mapped[str] = mapped_column(String(20), default="viewer")  # viewer | admin
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
