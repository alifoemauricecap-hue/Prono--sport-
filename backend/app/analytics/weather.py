"""M7 — Météo du stade via Open-Meteo (API 100 % GRATUITE, sans clé, usage non commercial OK).

Deux appels publics :
- geocoding-api.open-meteo.com/v1/search  → coordonnées de la VILLE du stade (depuis ESPN venue.city)
- api.open-meteo.com/v1/forecast          → température / pluie / vent à l'heure du kickoff

Règle §1 : si la ville est inconnue ou non résolue → None (DONNÉE NON DISPONIBLE affiché).
Cache mémoire TTL 6 h (les prévisions évoluent ; aucune écriture DB requise).
"""
from __future__ import annotations

import time
from datetime import datetime, timezone

import httpx

from ..config import HTTP_USER_AGENT

GEO_URL = "https://geocoding-api.open-meteo.com/v1/search"
FCST_URL = "https://api.open-meteo.com/v1/forecast"
TTL_SECONDS = 6 * 3600
HEADERS = {"User-Agent": HTTP_USER_AGENT}

_geo_cache: dict[str, tuple[float, tuple[float, float] | None]] = {}
_fcst_cache: dict[str, tuple[float, dict | None]] = {}


def geocode_city(city: str) -> tuple[float, float] | None:
    key = city.strip().lower()
    hit = _geo_cache.get(key)
    if hit and time.time() - hit[0] < TTL_SECONDS:
        return hit[1]
    try:
        r = httpx.get(GEO_URL, params={"name": city, "count": 1, "language": "fr", "format": "json"},
                      timeout=8.0, headers=HEADERS)
        results = (r.json() or {}).get("results") or []
        coords = (results[0]["latitude"], results[0]["longitude"]) if results else None
    except Exception:
        coords = None
    _geo_cache[key] = (time.time(), coords)
    return coords


def forecast_at(city: str, when_utc: datetime) -> dict | None:
    """Météo prévue (ou observée si passé récent) à l'heure du match — ou None."""
    if when_utc.tzinfo is None:
        when_utc = when_utc.replace(tzinfo=timezone.utc)
    if abs((when_utc - datetime.now(timezone.utc)).days) > 14:
        return None   # hors horizon prévision fiable → silence honnête (§1)
    key = f"{city.strip().lower()}|{when_utc:%Y-%m-%dT%H}"
    hit = _fcst_cache.get(key)
    if hit and time.time() - hit[0] < TTL_SECONDS:
        return hit[1]
    coords = geocode_city(city)
    if coords is None:
        return None
    lat, lon = coords
    try:
        r = httpx.get(FCST_URL, params={
            "latitude": lat, "longitude": lon,
            "hourly": "temperature_2m,precipitation_probability,precipitation,wind_speed_10m",
            "timezone": "UTC",
            "start_date": when_utc.date().isoformat(), "end_date": when_utc.date().isoformat(),
        }, timeout=8.0, headers=HEADERS)
        hourly = (r.json() or {}).get("hourly") or {}
        times = hourly.get("time") or []
        target = when_utc.strftime("%Y-%m-%dT%H:00")
        idx = times.index(target) if target in times else min(
            range(len(times)), key=lambda i: abs(datetime.fromisoformat(times[i])
                                                 .replace(tzinfo=timezone.utc) - when_utc)) if times else None
        if idx is None:
            out = None
        else:
            out = {
                "city": city, "source": "Open-Meteo (gratuit, sans clé)",
                "temperature_c": _at(hourly.get("temperature_2m"), idx),
                "precipitation_mm": _at(hourly.get("precipitation"), idx),
                "precipitation_prob_pct": _at(hourly.get("precipitation_probability"), idx),
                "wind_kmh": _at(hourly.get("wind_speed_10m"), idx),
                "forecast_for": target,
            }
    except Exception:
        out = None
    _fcst_cache[key] = (time.time(), out)
    return out


def _at(series, idx):
    if not series or idx >= len(series):
        return None
    return series[idx]
