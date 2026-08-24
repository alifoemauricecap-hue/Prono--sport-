"""Adapter football-data.co.uk (fduk) — CSV publics gratuits.

Données : résultats, scores MT, arbitre (selon CSV), xG (colonnes HxG/AxG quand présentes),
cotes 1X2 + O/U 2.5 multi-bookmakers (B365, PSH/Pinnacle…), y compris colonnes "C" (closing).
Donnée de marché = CONSENSUS : on n'attribue JAMAIS une cote à un bookmaker sans colonne explicite.
"""
from __future__ import annotations

import csv
import io
from datetime import datetime, timezone
from typing import Iterable

import httpx

from ..config import HTTP_TIMEOUT_SECONDS, HTTP_USER_AGENT
from .base import OddsRef, Provider, RawFixture, TeamRef

PROVIDER = "fduk"
BASE_URL = "https://www.football-data.co.uk/mmz4281"

# Couverture déclarée — uniquement les divisions dont le CSV existe effectivement (§97).
DIVISIONS: dict[str, tuple[str, str]] = {
    "E0": ("Angleterre", "Premier League"),
    "E1": ("Angleterre", "Championship"),
    "E2": ("Angleterre", "League One"),
    "E3": ("Angleterre", "League Two"),
    "EC": ("Angleterre", "Conference"),
    "SC0": ("Écosse", "Premiership"),
    "SC1": ("Écosse", "Championship"),
    "SC2": ("Écosse", "League One"),
    "SC3": ("Écosse", "League Two"),
    "D1": ("Allemagne", "Bundesliga"),
    "D2": ("Allemagne", "2. Bundesliga"),
    "I1": ("Italie", "Serie A"),
    "I2": ("Italie", "Serie B"),
    "SP1": ("Espagne", "La Liga"),
    "SP2": ("Espagne", "La Liga 2"),
    "F1": ("France", "Ligue 1"),
    "F2": ("France", "Ligue 2"),
    "N1": ("Pays-Bas", "Eredivisie"),
    "B1": ("Belgique", "Pro League"),
    "P1": ("Portugal", "Liga Portugal"),
    "T1": ("Turquie", "Süper Lig"),
    "G1": ("Grèce", "Super League"),
}

# Colonnes de cotes → (bookmaker, sélection). Colonnes "C" = closing (origin=CLOSING).
ODDS_1X2 = {
    "B365": ("B365H", "B365D", "B365A"),
    "BW": ("BWH", "BWD", "BWA"),
    "PINN": ("PSH", "PSD", "PSA"),
    "MAX": ("MaxH", "MaxD", "MaxA"),
    "AVG": ("AvgH", "AvgD", "AvgA"),
}
ODDS_1X2_CLOSING = {
    "PINN": ("PSCH", "PSCD", "PSCA"),
    "MAX": ("MaxCH", "MaxCD", "MaxCA"),
    "AVG": ("AvgCH", "AvgCD", "AvgCA"),
}
ODDS_OU25 = {"B365": ("B365>2.5", "B365<2.5"), "MAX": ("Max>2.5", "Max<2.5"), "AVG": ("Avg>2.5", "Avg<2.5")}
ODDS_OU25_CLOSING = {"MAX": ("MaxC>2.5", "MaxC<2.5"), "AVG": ("AvgC>2.5", "AvgC<2.5")}

BOOKMAKER_NAMES = {
    "B365": "Bet365", "BW": "Betway", "PINN": "Pinnacle",
    "MAX": "Consensus MAX (meilleure cote du marché)",
    "AVG": "Consensus AVG (cote moyenne du marché)",
}


def season_years(code: str) -> tuple[int, int, str]:
    """'2627' → (2026, 2027, '2026-2027'); '9394' → (1993, 1994, ...)."""
    y1 = int(code[:2])
    y2 = int(code[2:])
    full1 = 2000 + y1 if y1 < 50 else 1900 + y1
    full2 = 2000 + y2 if y2 < 50 else 1900 + y2
    return full1, full2, f"{full1}-{full2}"


def _f(value: str | None) -> float | None:
    if value is None or value.strip() == "":
        return None
    try:
        return float(value)
    except ValueError:
        return None


def _i(value: str | None) -> int | None:
    f = _f(value)
    return int(f) if f is not None else None


def _parse_dt(date_s: str, time_s: str | None) -> tuple[datetime | None, bool]:
    """Retourne (datetime UTC, heure_connue). Heure absente → 12:00 UTC marqué kickoff_time_known=False."""
    for fmt in ("%d/%m/%Y", "%d/%m/%y", "%Y-%m-%d"):
        try:
            d = datetime.strptime(date_s.strip(), fmt)
            break
        except ValueError:
            continue
    else:
        return None, False
    known = bool(time_s and time_s.strip())
    hh, mm = 12, 0
    if known:
        try:
            hh, mm = map(int, time_s.strip().split(":")[:2])
        except ValueError:
            known = False
    return datetime(d.year, d.month, d.day, hh, mm, tzinfo=timezone.utc), known


class FootballDataUKProvider(Provider):
    name = PROVIDER

    def url_for(self, div: str, season: str) -> str:
        return f"{BASE_URL}/{season}/{div}.csv"

    def fetch_fixtures_all(self) -> str:
        """fixtures.csv : TOUS les matchs À VENIR + COTES ACTUELLES réelles (~10 bookmakers,
        consensus Max/Avg) — la clé du Value Bet pré-match M4 (§30/§83)."""
        r = httpx.get(
            "https://www.football-data.co.uk/fixtures.csv",
            timeout=HTTP_TIMEOUT_SECONDS,
            follow_redirects=True,
            headers={"User-Agent": HTTP_USER_AGENT},
        )
        r.raise_for_status()
        return r.text

    def parse_fixtures_csv(self, payload: str,
                           source_url: str = "https://www.football-data.co.uk/fixtures.csv"
                           ) -> Iterable[RawFixture]:
        # .lstrip du BOM éventuel (\ufeffDiv ≠ Div — mesuré en ingestion réelle)
        reader = csv.DictReader(io.StringIO(payload.lstrip("\ufeff")))
        for row in reader:
            home_name = (row.get("HomeTeam") or "").strip()
            away_name = (row.get("AwayTeam") or "").strip()
            div = (row.get("Div") or "").strip()
            if not home_name or not away_name or not div:
                continue
            area, comp_name = DIVISIONS.get(div, ("?", div))
            kickoff, time_known = _parse_dt(row.get("Date") or "", row.get("Time"))
            if kickoff is None:
                continue
            start = kickoff.year if kickoff.month >= 7 else kickoff.year - 1
            odds: list[OddsRef] = []
            for bm, cols in {
                "B365": ("B365H", "B365D", "B365A"), "BW": ("BWH", "BWD", "BWA"),
                "PINN": ("PPH", "PPD", "PPA"), "MAX": ("MaxH", "MaxD", "MaxA"),
                "AVG": ("AvgH", "AvgD", "AvgA"),
            }.items():
                for sel, col in zip(("H", "D", "A"), cols):
                    v = _f(row.get(col))
                    if v is not None:
                        odds.append(OddsRef(bookmaker=bm, market="1X2", selection=sel, odds=v))
            for bm, cols in {"B365": ("B365>2.5", "B365<2.5"),
                             "MAX": ("Max>2.5", "Max<2.5"), "AVG": ("Avg>2.5", "Avg<2.5")}.items():
                for sel, col in zip(("Over", "Under"), cols):
                    v = _f(row.get(col))
                    if v is not None:
                        odds.append(OddsRef(bookmaker=bm, market="OU_2.5", selection=sel, odds=v))
            provider_id = f"{div}:{start}-{start+1}:{row.get('Date','').strip()}:{home_name}:{away_name}"
            yield RawFixture(
                provider=PROVIDER,
                provider_id=provider_id,
                provider_competition=div,
                competition_name=comp_name,
                competition_area=area,
                season_label=f"{start}-{start + 1}",
                kickoff_utc=kickoff,
                kickoff_time_known=time_known,
                status="SCHEDULED",
                home=TeamRef(name=home_name, provider_id=home_name, country=area),
                away=TeamRef(name=away_name, provider_id=away_name, country=area),
                odds=odds,
                source_url=source_url,
                raw={k: v for k, v in row.items() if k},
            )

    def fetch(self, div: str, season: str) -> str:
        r = httpx.get(
            self.url_for(div, season),
            timeout=HTTP_TIMEOUT_SECONDS,
            follow_redirects=True,
            headers={"User-Agent": HTTP_USER_AGENT},
        )
        r.raise_for_status()
        return r.text

    def parse(self, payload: str, div: str, season: str, source_url: str | None = None) -> Iterable[RawFixture]:
        area, comp_name = DIVISIONS.get(div, ("?", div))
        _, _, season_label = season_years(season)
        reader = csv.DictReader(io.StringIO(payload))
        for row in reader:
            home_name = (row.get("HomeTeam") or "").strip()
            away_name = (row.get("AwayTeam") or "").strip()
            if not home_name or not away_name:
                continue
            kickoff, time_known = _parse_dt(row.get("Date") or "", row.get("Time"))
            fthg, ftag = _i(row.get("FTHG")), _i(row.get("FTAG"))
            played = fthg is not None and ftag is not None
            odds: list[OddsRef] = []

            def add_triplet(spec, market: str, closing: bool, cols) -> None:
                book = spec[0]
                for sel, col in zip(("H", "D", "A") if market == "1X2" else ("Over", "Under"), cols):
                    v = _f(row.get(col))
                    if v is not None:
                        odds.append(OddsRef(bookmaker=book, market=market, selection=sel, odds=v,
                                            origin="CLOSING" if closing else "PROVIDER"))

            for bm, cols in ODDS_1X2.items():
                add_triplet((bm,), "1X2", False, cols)
            for bm, cols in ODDS_1X2_CLOSING.items():
                add_triplet((bm,), "1X2", True, cols)
            for bm, cols in ODDS_OU25.items():
                add_triplet((bm,), "OU_2.5", False, cols)
            for bm, cols in ODDS_OU25_CLOSING.items():
                add_triplet((bm,), "OU_2.5", True, cols)

            provider_id = f"{div}:{season}:{row.get('Date','').strip()}:{home_name}:{away_name}"
            yield RawFixture(
                provider=PROVIDER,
                provider_id=provider_id,
                provider_competition=div,
                competition_name=comp_name,
                competition_area=area,
                season_label=season_label,
                kickoff_utc=kickoff,
                kickoff_time_known=time_known,
                status="FINISHED" if played else "SCHEDULED",
                home=TeamRef(name=home_name, provider_id=home_name, country=area),
                away=TeamRef(name=away_name, provider_id=away_name, country=area),
                home_score=fthg,
                away_score=ftag,
                home_score_ht=_i(row.get("HTHG")),
                away_score_ht=_i(row.get("HTAG")),
                referee=(row.get("Referee") or "").strip() or None,
                home_xg=_f(row.get("HxG")),
                away_xg=_f(row.get("AxG")),
                odds=odds,
                source_url=source_url,
                raw={k: v for k, v in row.items() if k},
            )
