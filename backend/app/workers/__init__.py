"""WORKERS PRONO SPORT 3.0 (§14).

Chaque worker est :
- Nommé (syncFixtures, syncLiveMatches, syncResults, syncOdds, syncWeather,
  syncHistorical, discoverSources)
- Idempotent (ré-exécuter = même état, zéro doublon)
- Journalisé (table sync_jobs : statut, records, latence, erreurs)
- Tolérant aux erreurs (une source morte ≠ crash ; failover + DATA UNAVAILABLE)

Ordre de priorité de collecte (§10) :
P1 live → P2 fixtures proches → P3 résultats → P4 compositions → P5 cotes →
P6 contexte/météo → P7 historique → P8 découverte de sources.
"""
from .definitions import (
    WORKERS,
    run_discover,
    run_fixtures,
    run_historical,
    run_live,
    run_lineups,
    run_odds_live,
    run_results,
    run_weather,
)

__all__ = ["WORKERS", "run_fixtures", "run_live", "run_results", "run_lineups",
           "run_odds_live", "run_weather", "run_historical", "run_discover"]
