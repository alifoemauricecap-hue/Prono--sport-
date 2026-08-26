"""Registre des providers actifs (§3-4). PRINCIPE : aucune dépendance vitale à une source —
chaque donnée critique vise ≥ 2 sources indépendantes, recoupées par le Consistency Engine."""
from __future__ import annotations

from ..db.models import DataSource
from .base import Provider
from .espn import PROVIDER as ESPN
from .espn import EspnProvider
from .football_data_uk import PROVIDER as FDUK
from .football_data_uk import FootballDataUKProvider
from .football_data_org import PROVIDER as FDORG
from .football_data_org import FootballDataOrgProvider
from .openligadb import PROVIDER as OLDB
from .openligadb import OpenLigaDBProvider
from .thesportsdb import PROVIDER as TSDB
from .thesportsdb import TheSportsDBProvider
from .api_football import PROVIDER as AFOOT, ApiFootballProvider
from .odds_api import PROVIDER as ODDSAPI, OddsApiProvider

PROVIDERS: dict[str, type[Provider]] = {
    FDUK: FootballDataUKProvider,
    ESPN: EspnProvider,
    OLDB: OpenLigaDBProvider,
    TSDB: TheSportsDBProvider,
    FDORG: FootballDataOrgProvider,
    AFOOT: ApiFootballProvider,
    ODDSAPI: OddsApiProvider,
}

# Métadonnées déclaratives — insérées dans data_sources au bootstrap.
DATA_SOURCES: list[dict] = [
    {"name": FDUK, "kind": "football_data+odds", "base_url": "https://www.football-data.co.uk/mmz4281"},
    {"name": ESPN, "kind": "football_data", "base_url": "https://site.api.espn.com/apis/site/v2/sports/soccer"},
    {"name": OLDB, "kind": "football_data", "base_url": "https://api.openligadb.de"},
    {"name": TSDB, "kind": "football_data+media", "base_url": "https://www.thesportsdb.com/api/v1/json"},
    {"name": FDORG, "kind": "football_data", "base_url": "https://api.football-data.org/v4"},
    {"name": AFOOT, "kind": "football_data+lineups+players", "base_url": "https://v3.football.api-sports.io"},
    {"name": ODDSAPI, "kind": "odds", "base_url": "https://api.the-odds-api.com/v4"},
]


def get_provider(name: str) -> Provider:
    if name not in PROVIDERS:
        raise KeyError(f"Provider inconnu : {name!r}. Disponibles : {sorted(PROVIDERS)}")
    return PROVIDERS[name]()


def seed_data_sources(session) -> int:
    created = 0
    for meta in DATA_SOURCES:
        exists = session.query(DataSource).filter_by(name=meta["name"]).one_or_none()
        if not exists:
            session.add(DataSource(**meta))
            created += 1
    return created
