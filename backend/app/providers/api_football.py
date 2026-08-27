"""Adapter API-Football (API-Sports) — §21/§22/§23.

Clé GRATUITE (~100 requêtes/jour) : 0 €. N'est actif que si `API_FOOTBALL_KEY`
est définie dans l'environnement ; sinon `available()` = False et le worker
affiche MISSING DEPENDENCY (jamais de simulation, §95).

Données :
- fixtures + compositions officielles : GET /fixtures?date=X&lineups=X (1 appel/jour-type)
- blessures : GET /injuries?date=X (1 appel/jour)

Tous les appels passent par le cache intelligent (PS_CACHE_DIR) : zéro
re-téléchargement inutile, et si le réseau tombe, la dernière donnée RÉELLE
reste servie.
"""
from __future__ import annotations

import os
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Iterable

import httpx

from ..config import HTTP_TIMEOUT_SECONDS
from ..ingest.resolution import normalize_name
from .base import Provider, RawFixture, TeamRef
from .cache import http_get_json

PROVIDER = "apifootball"
BASE = "https://v3.football.api-sports.io"
TTL_FIXTURES_MIN = 45
TTL_INJURIES_H = 6


def key() -> str | None:
    return os.environ.get("API_FOOTBALL_KEY") or None


def available() -> bool:
    """True si la clé gratuite est fournie (sinon le worker affiche MISSING DEPENDENCY)."""
    return bool(key())


@dataclass
class LineupPlayer:
    player_id: int | None
    name: str
    number: int | None
    position: str | None
    starting: bool


@dataclass
class FixtureLineup:
    """Composition d'une équipe pour un match (provider_id = ID fixture API-Football)."""
    fixture_provider_id: int
    team_name: str
    team_provider_id: int | None
    side: str  # "home" | "away"
    players: list[LineupPlayer] = field(default_factory=list)


@dataclass
class InjuryInfo:
    player_name: str
    team_name: str
    status: str  # INJURED | DOUBTFUL | RETURNING
    detail: str | None
    expected_return: datetime | None


class ApiFootballProvider(Provider):
    name = PROVIDER

    def available(self) -> bool:
        return bool(key())

    # ---------------------------------------------------------------- fixtures
    def fixtures_url(self, date: str) -> str:
        return f"{BASE}/fixtures?date={date}&lineups={date}"

    def fetch(self, date: str) -> dict:
        k = key()
        if not k:
            raise RuntimeError("MISSING DEPENDENCY : API_FOOTBALL_KEY absente "
                               "(clé gratuite à créer sur api-sports.io)")
        data, _origin = http_get_json(
            self.fixtures_url(date),
            timeout=HTTP_TIMEOUT_SECONDS,
            ttl_seconds=TTL_FIXTURES_MIN * 60,
            headers={"x-apisports-key": k},
        )
        return data

    def parse(self, payload: dict, date: str, source_url: str | None = None) -> Iterable[RawFixture]:
        for fx in payload.get("response") or []:
            home = (fx.get("home") or {}).get("team") or {}
            away = (fx.get("away") or {}).get("team") or {}
            status = (fx.get("status") or {}).get("short") or "NS"
            kickoff_s = fx.get("date")
            kickoff = None
            if kickoff_s:
                try:
                    kickoff = datetime.fromisoformat(kickoff_s.replace("Z", "+00:00"))
                    if kickoff.tzinfo is None:
                        kickoff = kickoff.replace(tzinfo=timezone.utc)
                except ValueError:
                    kickoff = None
            if not home.get("name") or not away.get("name"):
                continue
            status_map = {
                "NS": "SCHEDULED", "1H": "LIVE", "HT": "HALFTIME", "2H": "LIVE",
                "ET": "EXTRA_TIME", "BT": "PENALTIES", "FT": "FINISHED",
                "AET": "FINISHED", "P": "POSTPONED", "C": "CANCELLED",
                "SUSP": "SUSPENDED", "ABD": "ABANDONED",
            }
            def goals(side: str) -> int | None:
                g = (fx.get(side) or {}).get("goals")
                try:
                    return int(g)
                except (TypeError, ValueError):
                    return None
            yield RawFixture(
                provider=PROVIDER,
                provider_id=str(fx.get("id")),
                provider_competition="global",
                competition_name=(fx.get("league") or {}).get("name") or "Football (API-Football)",
                competition_area=None,
                season_label=None,
                kickoff_utc=kickoff,
                kickoff_time_known=kickoff is not None,
                status=status_map.get(status, "UNKNOWN"),
                home=TeamRef(name=home["name"], provider_id=str(home.get("id")) if home.get("id") else None),
                away=TeamRef(name=away["name"], provider_id=str(away.get("id")) if away.get("id") else None),
                home_score=goals("home"),
                away_score=goals("away"),
                raw={"api_football_id": fx.get("id"), "status_short": status},
                source_url=source_url or self.fixtures_url(date),
            )

    # ---------------------------------------------------------------- lineups
    def fetch_lineups(self, date: str) -> list[FixtureLineup]:
        """COMPOSITIONS OFFICIELLES (§23) — une seule requête (fixtures&lineups).
        Retourne [] si les compositions ne sont pas encore publiées (jamais inventées)."""
        payload = self.fetch(date)
        out: list[FixtureLineup] = []
        for fx in payload.get("response") or []:
            for lu in fx.get("lineups") or []:
                team = lu.get("team") or {}
                side = "home" if team.get("id") == ((fx.get("home") or {}).get("team") or {}).get("id") else "away"
                players = [
                    LineupPlayer(
                        player_id=p.get("id"),
                        name=(p.get("name") or "?")[:120],
                        number=p.get("number"),
                        position=(p.get("position") or None),
                        starting=bool(p.get("starting", True)),
                    )
                    for p in lu.get("players") or []
                ]
                if team.get("name") and players:
                    out.append(FixtureLineup(
                        fixture_provider_id=fx.get("id"),
                        team_name=team["name"],
                        team_provider_id=team.get("id"),
                        side=side,
                        players=players,
                    ))
        return out

    # ---------------------------------------------------------------- injuries
    def fetch_injuries(self, date: str) -> list[InjuryInfo]:
        """Blessures réelles (§22) — jamais d'absence inventée."""
        k = key()
        if not k:
            raise RuntimeError("MISSING DEPENDENCY : API_FOOTBALL_KEY absente")
        url = f"{BASE}/injuries?date={date}"
        data, _origin = http_get_json(
            url, timeout=HTTP_TIMEOUT_SECONDS, ttl_seconds=TTL_INJURIES_H * 3600,
            headers={"x-apisports-key": k})
        out: list[InjuryInfo] = []
        for row in data.get("response") or []:
            player = row.get("player") or {}
            team = (row.get("team") or {})
            status = (row.get("status") or "INJURED").upper()
            if status not in ("INJURED", "DOUBTFUL", "RETURNING"):
                continue
            ret = row.get("return_time")
            ret_dt = None
            if ret:
                try:
                    ret_dt = datetime.fromisoformat(str(ret).replace("Z", "+00:00"))
                except ValueError:
                    ret_dt = None
            if player.get("name"):
                out.append(InjuryInfo(
                    player_name=player["name"][:120],
                    team_name=(team.get("name") or "")[:80],
                    status=status,
                    detail=(row.get("injury") or row.get("description") or "")[:255] or None,
                    expected_return=ret_dt,
                ))
        return out
