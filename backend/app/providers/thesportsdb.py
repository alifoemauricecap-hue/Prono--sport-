"""Adapter TheSportsDB (TSDB) — clé publique gratuite "3" (tier gratuit limité).

Rôle dans l'architecture : média (badges/stades, §57) + source de contre-vérification
des prochains matchs. Le tier gratuit limite les volumes → jamais source unique (§4).
"""
from __future__ import annotations

import os
from datetime import datetime, timezone
from typing import Iterable

import httpx

from ..config import HTTP_TIMEOUT_SECONDS
from .base import Provider, RawFixture, TeamRef

PROVIDER = "tsdb"
BASE = "https://www.thesportsdb.com/api/v1/json"

# Ligues déclarées : id TSDB → (code canonique interne, nom, zone)
LEAGUES: dict[str, tuple[str, str, str]] = {
    "4328": ("ENG-E0", "Premier League", "Angleterre"),
    "4329": ("ENG-E1", "Championship", "Angleterre"),
    "4335": ("ESP-SP1", "La Liga", "Espagne"),
    "4332": ("ITA-I1", "Serie A", "Italie"),
    "4334": ("FRA-F1", "Ligue 1", "France"),
}

STATUS_MAP = {
    "FT": "FINISHED", "AET": "FINISHED", "PEN": "FINISHED",
    "1H": "LIVE", "2H": "LIVE", "HT": "HALFTIME", "LIVE": "LIVE",
    "Not Started": "SCHEDULED", "": "SCHEDULED",
    "Postponed": "POSTPONED", "Cancelled": "CANCELLED", "Suspended": "SUSPENDED",
    "Abandoned": "ABANDONED",
}


def _key() -> str:
    return os.environ.get("THESPORTSDB_KEY", "3")  # "3" = clé publique gratuite du projet TSDB


def _parse_dt(ts: str | None, date_s: str | None) -> datetime | None:
    if ts:
        try:
            return datetime.fromisoformat(ts).replace(tzinfo=timezone.utc)
        except ValueError:
            pass
    if date_s:
        try:
            d = datetime.fromisoformat(date_s)
            return datetime(d.year, d.month, d.day, 12, 0, tzinfo=timezone.utc)
        except ValueError:
            return None
    return None


def _score(v) -> int | None:
    try:
        return int(v)
    except (TypeError, ValueError):
        return None


class TheSportsDBProvider(Provider):
    name = PROVIDER

    def _get(self, path: str, params: dict | None = None) -> dict:
        r = httpx.get(f"{BASE}/{_key()}/{path}", params=params or {}, timeout=HTTP_TIMEOUT_SECONDS)
        r.raise_for_status()
        return r.json()

    def fetch(self, league_id: str, season: str | None = None) -> dict:
        if season:
            return self._get(f"eventsseason.php", {"id": league_id, "s": season})
        return self._get("eventsnextleague.php", {"id": league_id})

    def fetch_teams(self, league_name: str) -> dict:
        return self._get("search_all_teams.php", {"l": league_name})

    def parse(self, payload: dict, league_id: str, source_url: str | None = None) -> Iterable[RawFixture]:
        canon, comp_name, area = LEAGUES.get(league_id, (None, None, None))
        for e in payload.get("events") or []:
            kickoff = _parse_dt(e.get("strTimestamp"), e.get("dateEvent"))
            if kickoff is None:
                continue
            status = STATUS_MAP.get(e.get("strStatus") or "", "UNKNOWN")
            hs, as_ = _score(e.get("intHomeScore")), _score(e.get("intAwayScore"))
            if status in {"SCHEDULED", "UPCOMING", "POSTPONED", "CANCELLED"}:
                hs, as_ = None, None  # jamais de faux 0 (§1)
            season_label = e.get("strSeason")
            # Backbone MONDIAL : le payload eventsday porte le NOM RÉEL de la ligue
            # et le PAYS par événement — une ligue hors catalogue ne doit jamais
            # s'appeler son ID (transparence §1/§4).
            ev_league = (e.get("strLeague") or "").strip() or comp_name or league_id
            ev_area = (e.get("strCountry") or "").strip() or area
            yield RawFixture(
                provider=PROVIDER,
                provider_id=str(e.get("idEvent")),
                provider_competition=league_id,
                competition_name=comp_name or ev_league,
                competition_area=ev_area,
                season_label=season_label,
                kickoff_utc=kickoff,
                kickoff_time_known=bool(e.get("strTimestamp")),
                status=status,
                home=TeamRef(name=(e.get("strHomeTeam") or "?").strip(),
                             provider_id=str(e.get("idHomeTeam") or ""),
                             logo_url=e.get("strHomeTeamBadge") or None,
                             country=ev_area or None),
                away=TeamRef(name=(e.get("strAwayTeam") or "?").strip(),
                             provider_id=str(e.get("idAwayTeam") or ""),
                             logo_url=e.get("strAwayTeamBadge") or None,
                             country=ev_area or None),
                home_score=hs,
                away_score=as_,
                venue=e.get("strVenue") or None,
                venue_city=e.get("strCity") or None,
                raw={"idEvent": e.get("idEvent"), "strStatus": e.get("strStatus"),
                     "strLeague": e.get("strLeague"), "strCountry": e.get("strCountry"),
                     "strPoster": e.get("strPoster")},
                source_url=source_url,
            )

    def parse_teams(self, payload: dict, area: str | None = None) -> list[TeamRef]:
        out = []
        for t in payload.get("teams") or []:
            out.append(TeamRef(
                name=(t.get("strTeam") or "").strip(),
                provider_id=str(t.get("idTeam") or ""),
                logo_url=t.get("strBadge"),
                country=area,
            ))
        return out
