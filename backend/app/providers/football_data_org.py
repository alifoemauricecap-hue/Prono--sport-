"""Adapter football-data.org (fdorg) — tier GRATUIT (clé à créer, 10 req/min).

La clé vient de l'environnement : FOOTBALL_DATA_ORG_TOKEN.
Sans clé → ProviderNotConfigured : le reste du système continue normalement (§64).
"""
from __future__ import annotations

import os
from datetime import datetime, timezone
from typing import Iterable

import httpx

from ..config import HTTP_TIMEOUT_SECONDS
from .base import Provider, RawFixture, TeamRef

PROVIDER = "fdorg"
BASE = "https://api.football-data.org/v4"

COMPETITIONS: dict[str, tuple[str, str, str]] = {
    "PL": ("ENG-E0", "Premier League", "Angleterre"),
    "ELC": ("ENG-E1", "Championship", "Angleterre"),
    "PD": ("ESP-SP1", "La Liga", "Espagne"),
    "BL1": ("GER-D1", "Bundesliga", "Allemagne"),
    "SA": ("ITA-I1", "Serie A", "Italie"),
    "FL1": ("FRA-F1", "Ligue 1", "France"),
    "CL": ("UEFA-UCL", "Ligue des Champions", "Europe"),
}

STATUS_MAP = {
    "SCHEDULED": "SCHEDULED", "TIMED": "SCHEDULED",
    "IN_PLAY": "LIVE", "PAUSED": "HALFTIME",
    "EXTRA_TIME": "EXTRA_TIME", "PENALTY_SHOOTOUT": "PENALTIES",
    "FINISHED": "FINISHED", "POSTPONED": "POSTPONED",
    "CANCELLED": "CANCELLED", "SUSPENDED": "SUSPENDED",
}


class ProviderNotConfigured(RuntimeError):
    pass


def token() -> str | None:
    t = os.environ.get("FOOTBALL_DATA_ORG_TOKEN", "").strip()
    return t or None


def configured() -> bool:
    return token() is not None


class FootballDataOrgProvider(Provider):
    name = PROVIDER

    def fetch(self, competition: str, season_year: int | None = None) -> dict:
        tk = token()
        if not tk:
            raise ProviderNotConfigured(
                "FOOTBALL_DATA_ORG_TOKEN absent — créez une clé gratuite sur football-data.org "
                "(2 min, sans carte bancaire) puis : export FOOTBALL_DATA_ORG_TOKEN=..."
            )
        params = {}
        if season_year:
            params["season"] = str(season_year)
        r = httpx.get(
            f"{BASE}/competitions/{competition}/matches",
            params=params, headers={"X-Auth-Token": tk}, timeout=HTTP_TIMEOUT_SECONDS,
        )
        r.raise_for_status()
        return r.json()

    def parse(self, payload: dict, competition: str, source_url: str | None = None) -> Iterable[RawFixture]:
        canon, comp_name, area = COMPETITIONS.get(competition, (competition, competition, None))
        for m in payload.get("matches") or []:
            kickoff = None
            try:
                kickoff = datetime.fromisoformat(m["utcDate"].replace("Z", "+00:00"))
            except (KeyError, ValueError):
                continue
            score = m.get("score") or {}
            ft = score.get("fullTime") or {}
            ht = score.get("halfTime") or {}
            status = STATUS_MAP.get(m.get("status"), "UNKNOWN")
            hs, as_ = ft.get("home"), ft.get("away")
            if status in {"SCHEDULED", "UPCOMING", "POSTPONED", "CANCELLED"}:
                hs, as_ = None, None
            home, away = m.get("homeTeam") or {}, m.get("awayTeam") or {}
            season = (m.get("season") or {})
            label = f"{season.get('startDate', '')[:4]}-{season.get('endDate', '')[:4]}"
            label = label if len(label) == 9 else None
            yield RawFixture(
                provider=PROVIDER,
                provider_id=str(m.get("id")),
                provider_competition=competition,
                competition_name=comp_name,
                competition_area=area,
                season_label=label,
                kickoff_utc=kickoff,
                kickoff_time_known=True,
                status=status,
                home=TeamRef(name=home.get("name") or "?", provider_id=str(home.get("id")),
                             logo_url=home.get("crest"), country=area),
                away=TeamRef(name=away.get("name") or "?", provider_id=str(away.get("id")),
                             logo_url=away.get("crest"), country=area),
                home_score=hs, away_score=as_,
                home_score_ht=ht.get("home"), away_score_ht=ht.get("away"),
                venue=(m.get("venue") or None),
                raw={"id": m.get("id"), "matchday": m.get("matchday"),
                     "stage": m.get("stage"), "lastUpdate": m.get("lastUpdated")},
                source_url=source_url,
            )
