"""Catalogue des sources CANDIDATES — toutes GRATUITES (0 €), aucune dépendance payante.

Chaque entrée décrit la source, ses données, sa couverture, sa fréquence,
si elle est temps réel, ses limites, l'obligation d'attribution, et — crucial —
son statut de vérification. `verified` = VRAIMENT testé et observé (date + trace).
Une source `verified=False` reste en DISCOVERED/TESTING jusqu'à son 1er test réel.

Catégories canoniques (data_categories) :
    fixtures | live | results | statistics | lineups | players | odds |
    weather | referees | history | standings | events
"""
from __future__ import annotations

from dataclasses import dataclass, field


CATEGORIES_FR: dict[str, str] = {
    "fixtures": "Matchs programmés",
    "live": "Données live",
    "results": "Résultats",
    "statistics": "Statistiques",
    "lineups": "Compositions",
    "players": "Joueurs",
    "odds": "Cotes",
    "weather": "Météo",
    "referees": "Arbitres",
    "history": "Historique",
    "standings": "Classements",
    "events": "Événements live",
    "research": "Recherche / contexte",
}


@dataclass
class SourceCandidate:
    name: str
    kind: str
    base_url: str
    data_categories: list[str]
    coverage: str
    update_frequency: str
    realtime: bool
    requires_key: bool
    key_env: str | None
    attribution_required: bool
    terms_status: str          # OK | TO_VERIFY | FORBIDDEN
    terms_note: str
    reliability_hints: dict = field(default_factory=dict)
    # Vérification réelle (remplie par le test de découverte, jamais supposée) :
    verified: bool = False
    verified_at: str | None = None
    verified_note: str | None = None
    # Check à exécuter : nom de fonction dans checker
    check: str = "http_get"

    def as_row(self) -> dict:
        return {
            "name": self.name,
            "kind": self.kind,
            "base_url": self.base_url,
            "data_categories": self.data_categories,
            "coverage": self.coverage,
            "update_frequency": self.update_frequency,
            "requires_key": self.requires_key,
            "attribution_required": self.attribution_required,
            "terms_status": self.terms_status,
            "status": "APPROVED" if self.verified else "DISCOVERED",
            "reliability_score": self.reliability_hints.get("initial"),
            "availability_status": None,
            "coverage_detail": self.coverage,
        }


def _note(date: str, txt: str) -> str:
    return f"[vérifié {date}] {txt}"


# ----------------------------------------------------------------------------
# SOURCES RÉELLEMENT EN PRODUCTION (2.0) — observées, non supposées
# ----------------------------------------------------------------------------
CANDIDATES: list[SourceCandidate] = [
    SourceCandidate(
        name="football-data.co.uk",
        kind="football_data",
        base_url="https://www.football-data.co.uk",
        data_categories=["fixtures", "results", "odds", "referees", "statistics", "history", "standings"],
        coverage="22 championnats européens (top 5 + divisions 2), historique complet",
        update_frequency="hebdomadaire (CSV) + fixtures.csv quotidien en saison",
        realtime=False,
        requires_key=False,
        key_env=None,
        attribution_required=False,
        terms_status="OK",
        terms_note="Données publiques pour usage personnel/analytique ; attribution appréciée.",
        reliability_hints={"initial": 90.0},
        verified=True,
        verified_at="2026-08-24",
        verified_note=_note("2026-08-24", "CSV résultats/cotes chargés, ~20 bookmakers, xG top 5."),
        check="http_get",
    ),
    SourceCandidate(
        name="ESPN",
        kind="football_data",
        base_url="https://site.api.espn.com/apis/site/v2/sports/soccer",
        data_categories=["fixtures", "live", "results", "events", "statistics"],
        coverage="~55 ligues mondiales + Coupes (UCL, Libertadores, Qualifs…)",
        update_frequency="temps réel (scoreboard)",
        realtime=True,
        requires_key=False,
        key_env=None,
        attribution_required=False,
        terms_status="TO_VERIFY",
        terms_note="API non officielle (endpoints publics du site) ; à utiliser avec mesure et cross-check.",
        reliability_hints={"initial": 75.0},
        verified=True,
        verified_at="2026-08-24",
        verified_note=_note("2026-08-24", "Scoreboard live + minute + logos sur 55 ligues testées."),
        check="espn_scoreboard",
    ),
    SourceCandidate(
        name="OpenLigaDB",
        kind="football_data",
        base_url="https://api.openligadb.de",
        data_categories=["fixtures", "results", "standings", "history"],
        coverage="Allemagne D1-D3 (Calendiers complets)",
        update_frequency="quotidien",
        realtime=False,
        requires_key=False,
        key_env=None,
        attribution_required=False,
        terms_status="OK",
        terms_note="Open data, usage libre.",
        reliability_hints={"initial": 85.0},
        verified=True,
        verified_at="2026-08-24",
        verified_note=_note("2026-08-24", "Calendriers D1 chargés sans clé."),
        check="openligadb",
    ),
    SourceCandidate(
        name="TheSportsDB",
        kind="football_data",
        base_url="https://www.thesportsdb.com/api/v1/json",
        data_categories=["fixtures", "results", "players", "lineups", "standings", "events"],
        coverage="Monde (méta + badges + joueurs) ; free key",
        update_frequency="quotidien",
        realtime=False,
        requires_key=True,
        key_env="TSDB_KEY",
        attribution_required=False,
        terms_status="OK",
        terms_note="Free key publique ('3'/'123') ; limites par méthode (ex. eventsday 3/j).",
        reliability_hints={"initial": 60.0},
        verified=True,
        verified_at="2026-08-24",
        verified_note=_note("2026-08-24", "Logos + eventsday cross-check opérationnels."),
        check="thesportsdb",
    ),
    SourceCandidate(
        name="Open-Meteo",
        kind="weather",
        base_url="https://api.open-meteo.com/v1/forecast",
        data_categories=["weather"],
        coverage="Météo mondiale par lat/long (ville du stade)",
        update_frequency="horodatée (prévisions à l'heure du match)",
        realtime=True,
        requires_key=False,
        key_env=None,
        attribution_required=True,
        terms_status="OK",
        terms_note="Gratuit sans clé, usage non-commercial ; attribution requise.",
        reliability_hints={"initial": 90.0},
        verified=True,
        verified_at="2026-08-24",
        verified_note=_note("2026-08-24", "Géocoding + prévisions stade opérationnels."),
        check="open_meteo",
    ),
    SourceCandidate(
        name="football-data.org",
        kind="football_data",
        base_url="https://api.football-data.org/v4",
        data_categories=["fixtures", "results", "standings", "lineups"],
        coverage="12 compétitions top (free tier), saison courante, scores delayés",
        update_frequency="10 req/min (free)",
        realtime=False,
        requires_key=True,
        key_env="FOOTBALL_DATA_ORG_TOKEN",
        attribution_required=False,
        terms_status="OK",
        terms_note="Clé gratuite à créer ; 12 compétitions, 10 req/min, pas de joueurs/cotes en free.",
        reliability_hints={"initial": 80.0},
        verified=True,
        verified_at="2026-08-26",
        verified_note=_note("2026-08-26", "Free tier confirmé : 12 compét., delayé, 10 req/min."),
        check="http_get",
    ),
    # ------------------------------------------------------------------------
    # SOURCES DE RECHERCHE APPROFONDI (recherche en ligne, 0 €, fiables)
    # ------------------------------------------------------------------------
    SourceCandidate(
        name="Wikipedia",
        kind="research",
        base_url="https://fr.wikipedia.org",
        data_categories=["research", "history"],
        coverage="Contexte équipes/compétitions/joueurs (articles FR/EN)",
        update_frequency="à la demande",
        realtime=False,
        requires_key=False,
        key_env=None,
        attribution_required=True,
        terms_status="OK",
        terms_note="API REST publique, contenu libre (CC BY-SA) ; attribution requise.",
        reliability_hints={"initial": 88.0},
        verified=True,
        verified_at="2026-08-26",
        verified_note=_note("2026-08-26", "REST /page/summary + opensearch testés, sans clé."),
        check="wikipedia",
    ),
    SourceCandidate(
        name="StatsBomb Open Data",
        kind="football_data",
        base_url="https://github.com/statsbomb/open-data",
        data_categories=["events", "lineups", "statistics", "history"],
        coverage="Compétitions sélectionnées (WSL, UCL, La Liga, WC F 2023) — JSON GitHub",
        update_frequency="statique (fichiers)",
        realtime=False,
        requires_key=False,
        key_env=None,
        attribution_required=True,
        terms_status="OK",
        terms_note="Open data GitHub, JSON ; usage recherche/analytique.",
        reliability_hints={"initial": 82.0},
        verified=True,
        verified_at="2026-08-26",
        verified_note=_note("2026-08-26", "competitions.json accessible, événements + xG."),
        check="github_json",
    ),
    # ------------------------------------------------------------------------
    # CANDIDATS À DÉCOUVRIR / À VALIDER — jamais fiables avant test réel
    # ------------------------------------------------------------------------
    SourceCandidate(
        name="API-Football (free)",
        kind="football_data",
        base_url="https://v3.football.api-sports.io",
        data_categories=["fixtures", "live", "results", "lineups", "players", "statistics", "standings"],
        coverage="Monde (free ~100 req/jour) — lineups & joueurs prioritaires",
        update_frequency="live (free 100 req/j)",
        realtime=True,
        requires_key=True,
        key_env="API_FOOTBALL_KEY",
        attribution_required=False,
        terms_status="TO_VERIFY",
        terms_note="Free key gratuite à créer ; ~100 req/jour. Activer seulement si une clé fournie.",
        reliability_hints={},
        verified=False,
        check="http_get",
    ),
    SourceCandidate(
        name="The Odds API (free)",
        kind="odds",
        base_url="https://api.the-odds-api.com/v4",
        data_categories=["odds"],
        coverage="~40 bookmakers, 20+ sports (free 500 crédits/mois)",
        update_frequency="polling (free ~16 req/j)",
        realtime=False,
        requires_key=True,
        key_env="ODDS_API_KEY",
        attribution_required=False,
        terms_status="TO_VERIFY",
        terms_note="Free key gratuite ; 500 crédits/mois. Activer seulement si une clé fournie.",
        reliability_hints={},
        verified=False,
        check="http_get",
    ),
    SourceCandidate(
        name="worldfootball.net",
        kind="football_data",
        base_url="https://www.worldfootball.net",
        data_categories=["history", "results", "standings"],
        coverage="Archives profondes mondiales (CSV/HTML)",
        update_frequency="hebdomadaire",
        realtime=False,
        requires_key=False,
        key_env=None,
        attribution_required=True,
        terms_status="TO_VERIFY",
        terms_note="Licence non explicite → extraction web NON autorisée par défaut (§5).",
        reliability_hints={},
        verified=False,
        check="http_get",
    ),
]


def by_name(name: str) -> SourceCandidate | None:
    for c in CANDIDATES:
        if c.name.lower() == name.lower():
            return c
    return None
