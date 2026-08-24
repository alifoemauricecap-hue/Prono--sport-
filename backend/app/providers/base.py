"""Contrat commun des fournisseurs + DTO normalisés (§3 : aucun fournisseur n'est irremplaçable)."""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Iterable


@dataclass
class TeamRef:
    name: str
    provider_id: str | None = None
    logo_url: str | None = None
    country: str | None = None


@dataclass
class OddsRef:
    bookmaker: str          # code canonical ex. B365, PINN, MAX, AVG
    market: str             # code canonical ex. 1X2
    selection: str          # H | D | A | Over | Under
    odds: float
    status: str = "ACTIVE"
    origin: str = "PROVIDER"


@dataclass
class RawFixture:
    """Fixture sortant d'un provider, AVANT validation (§7) et résolution d'entités (§5)."""
    provider: str
    provider_id: str
    provider_competition: str        # identifiant compétition chez le provider
    competition_name: str
    competition_area: str | None
    season_label: str | None
    kickoff_utc: datetime | None
    kickoff_time_known: bool
    status: str                       # une valeur de FIXTURE_STATUSES
    home: TeamRef
    away: TeamRef
    home_score: int | None = None
    away_score: int | None = None
    home_score_ht: int | None = None
    away_score_ht: int | None = None
    venue: str | None = None
    venue_city: str | None = None      # ville du stade (météo M7) — NULL si inconnue, jamais devinée
    clock: str | None = None           # minute affichée en LIVE ("67'", "MT") — source provider
    referee: str | None = None
    home_xg: float | None = None
    away_xg: float | None = None
    odds: list[OddsRef] = field(default_factory=list)
    source_url: str | None = None
    raw: dict | None = None


class Provider:
    """Interface de base. Chaque provider : name, fetch (HTTP), parse (→ RawFixture)."""

    name: str = "abstract"

    def fetch(self, **kwargs):
        raise NotImplementedError

    def parse(self, payload, **kwargs) -> Iterable[RawFixture]:
        raise NotImplementedError
