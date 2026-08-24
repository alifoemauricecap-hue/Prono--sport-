"""Adapter OpenLigaDB (SR3) — API 100 % libre, sans clé, sans limite déclarée.

Données : saisons complètes Allemagne (bl1, bl2, bl3, etc.), scores MT/finale,
icônes d'équipes (Wikimedia), statuts de match.
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Iterable

import httpx

from ..config import HTTP_TIMEOUT_SECONDS
from .base import Provider, RawFixture, TeamRef

PROVIDER = "openligadb"
BASE = "https://api.openligadb.de"

LEAGUES: dict[str, tuple[str, str, str]] = {
    # raccourci OpenLigaDB → (code canonique interne, nom, zone)
    "bl1": ("GER-D1", "Bundesliga", "Allemagne"),
    "bl2": ("GER-D2", "2. Bundesliga", "Allemagne"),
    "bl3": ("GER-D3", "3. Liga", "Allemagne"),
}


def _parse_dt(s: str | None) -> datetime | None:
    if not s:
        return None
    try:
        return datetime.fromisoformat(s.replace("Z", "+00:00"))
    except ValueError:
        return None


def _result(match: dict, type_id: int) -> tuple[int | None, int | None]:
    """resultTypeID 1 = mi-temps, 2 = résultat final (schéma documenté OpenLigaDB)."""
    for r in match.get("matchResults") or []:
        if r.get("resultTypeID") == type_id:
            return r.get("pointsTeam1"), r.get("pointsTeam2")
    return None, None


class OpenLigaDBProvider(Provider):
    name = PROVIDER

    def fetch(self, league: str, year: int) -> list[dict]:
        r = httpx.get(f"{BASE}/getmatchdata/{league}/{year}", timeout=HTTP_TIMEOUT_SECONDS)
        r.raise_for_status()
        return r.json()

    def parse(self, payload: list[dict], league: str, **kwargs) -> Iterable[RawFixture]:
        canon, comp_name, area = LEAGUES.get(league, (league.upper(), league, None))
        now = datetime.now(timezone.utc)
        for m in payload:
            kickoff = _parse_dt(m.get("matchDateTimeUTC"))
            if kickoff is None:
                continue
            team1, team2 = m.get("team1") or {}, m.get("team2") or {}
            if not team1.get("teamName") or not team2.get("teamName"):
                continue
            ft_h, ft_a = _result(m, 2)
            ht_h, ht_a = _result(m, 1)
            if m.get("matchIsFinished"):
                status = "FINISHED"
            elif kickoff <= now:
                status = "LIVE" if (ft_h is not None or ht_h is not None) else "UNKNOWN"
            else:
                status = "SCHEDULED"
            start_year = kickoff.year if kickoff.month >= 7 else kickoff.year - 1
            yield RawFixture(
                provider=PROVIDER,
                provider_id=str(m.get("matchID")),
                provider_competition=league,
                competition_name=comp_name,
                competition_area=area,
                season_label=f"{start_year}-{start_year + 1}",
                kickoff_utc=kickoff,
                kickoff_time_known=True,
                status=status,
                home=TeamRef(name=team1["teamName"], provider_id=str(team1.get("teamId")),
                             logo_url=team1.get("teamIconUrl"), country=area),
                away=TeamRef(name=team2["teamName"], provider_id=str(team2.get("teamId")),
                             logo_url=team2.get("teamIconUrl"), country=area),
                home_score=ft_h,
                away_score=ft_a,
                home_score_ht=ht_h,
                away_score_ht=ht_a,
                venue=(m.get("location") or {}).get("locationStadium"),
                raw={"matchID": m.get("matchID"), "leagueName": m.get("leagueName"),
                     "group": (m.get("group") or {}).get("groupName"),
                     "lastUpdate": m.get("lastUpdateDateTime")},
            )
