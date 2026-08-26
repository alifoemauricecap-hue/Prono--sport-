"""ENTITY RESOLUTION ENGINE (§5-6).

Règles :
- Jamais de correspondance sur le nom seul entre providers différents.
- Correspondance garantie : mapping provider_id ↔ ID interne (table entity_mappings).
- Croisement inter-providers : uniquement via (a) alias déjà rattaché + identité stricte du
  nom normalisé avec un contexte (même pays/zone) OU (b) action manuelle admin.
  En v1 : croisement automatique seulement si alias exact existant → sinon NOUVELLE équipe
  + mapping conservé (les doublons potentiels sont signalés, pas fusionnés en silence).
"""
from __future__ import annotations

import re
import unicodedata

from sqlalchemy.orm import Session

from ..db.models import Competition, EntityMapping, Team, TeamAlias
from ..providers.base import RawFixture, TeamRef

# ALIAS SEEDS — résolution MANUELLE admin (§5), auditable et réversible :
# abréviations utilisées par football-data.co.uk ↔ noms complets utilisés par ESPN/TSDB/OpenLigaDB.
# Chaque entrée a été vérifiée humainement ; elle rapproche uniquement deux orthographes de
# la MÊME équipe réelle au sein du MÊME pays. Jamais de fuzzy matching automatique.
ALIAS_SEEDS: dict[str, str] = {
    # angleterre (fduk → nom complet)
    "man city": "manchester city",
    "man united": "manchester united",
    "nott m forest": "nottingham forest",
    "nottm forest": "nottingham forest",
    "spurs": "tottenham hotspur",
    "wolves": "wolverhampton wanderers",
    "newcastle": "newcastle united",
    "west ham": "west ham united",
    "leeds": "leeds united",
    "brighton": "brighton and hove albion",
    "bournemouth": "afc bournemouth",
    "leicester": "leicester city",
    "qpr": "queens park rangers",
    "sheffield weds": "sheffield wednesday",
    "cardiff": "cardiff city",
    "norwich": "norwich city",
    # espagne (fduk → noms complets)
    "ath madrid": "atletico madrid",
    "atletico": "atletico madrid",
    "ath bilbao": "athletic club",
    "athletic bilbao": "athletic club",
    "la coruna": "deportivo la coruna",
    "dep la coruna": "deportivo la coruna",
}


def canonical_alias(alias: str) -> str:
    """Renvoie l'alias canonique (seed admin s'il existe, sinon l'alias inchangé)."""
    return ALIAS_SEEDS.get(alias, alias)


def season_bounds(label: str) -> tuple[int, int]:
    """'2026-2027' → (2026, 2027). Label non conforme → (0, 0) : jamais d'année inventée."""
    try:
        a, b = label.split("-")
        return int(a), int(b)
    except (ValueError, AttributeError):
        return 0, 0


def normalize_name(name: str) -> str:
    """Forme normalisée : minuscules, sans accents, sans ponctuation, espaces compactés."""
    n = unicodedata.normalize("NFKD", name.strip().casefold())
    n = "".join(c for c in n if not unicodedata.combining(c))
    n = re.sub(r"[^a-z0-9 ]", " ", n)
    return re.sub(r"\s+", " ", n).strip()


def _mapping(session: Session, entity_type: str, provider: str, provider_id: str) -> EntityMapping | None:
    return (
        session.query(EntityMapping)
        .filter_by(entity_type=entity_type, provider=provider, provider_id=provider_id)
        .one_or_none()
    )


def _countries_compatible(a: str | None, b: str | None) -> bool:
    """Lien inter-providers : alias strict identique ET pays compatibles.
    Les deux inconnus = compatible (cas intra-provider). Deux pays connus différents = REFUS
    (jamais de fusion sur le simple nom, §5)."""
    if not a or not b:
        return True
    return a.strip().casefold() == b.strip().casefold()


def _add_alias_if_free(session: Session, team_id: int, alias: str) -> None:
    if alias and not session.query(TeamAlias).filter_by(alias=alias).one_or_none():
        session.add(TeamAlias(team_id=team_id, alias=alias))


def resolve_team(session: Session, ref: TeamRef, provider: str) -> tuple[Team, bool]:
    """Retourne (team, created). Stratégie :
    1. mapping (provider, provider_id) → identité certaine.
    2. alias normalisé identique + pays compatibles → lien audité (mapping conservé,
       réversible ; signal fort : chaîne strictement égale + même contexte).
    3. sinon nouvelle équipe + mapping provider ; alias ajouté seulement si libre
       (zéro fusion implicite, aucun crash d'unicité).
    """
    pid = ref.provider_id or f"name:{normalize_name(ref.name)}"

    m = _mapping(session, "team", provider, pid)
    if m:
        team = session.get(Team, m.entity_id)
        if team is not None:
            _enrich(session, team, ref)
            return team, False

    alias = canonical_alias(normalize_name(ref.name))
    existing = session.query(TeamAlias).filter_by(alias=alias).one_or_none()
    if existing:
        team = session.get(Team, existing.team_id)
        if team is not None and _countries_compatible(team.country, ref.country):
            session.add(EntityMapping(entity_type="team", entity_id=team.id,
                                      provider=provider, provider_id=pid))
            _enrich(session, team, ref)
            return team, False
        # Alias identique mais pays incompatibles → équipe DISTINCTE traçable, pas de fusion.

    team = Team(name=ref.name.strip(), country=ref.country, logo_url=ref.logo_url)
    session.add(team)
    session.flush()  # team.id
    _add_alias_if_free(session, team.id, alias)
    session.add(EntityMapping(entity_type="team", entity_id=team.id, provider=provider, provider_id=pid))
    return team, True


def _enrich(session: Session, team: Team, ref: TeamRef) -> None:
    """Enrichissement non-destructif : un logo de source autorisée ne remplace jamais un logo existant."""
    if not team.logo_url and ref.logo_url:
        team.logo_url = ref.logo_url
    if not team.country and ref.country:
        team.country = ref.country
    _add_alias_if_free(session, team.id, canonical_alias(normalize_name(ref.name)))


def _build_canonical() -> dict[str, dict[str, str]]:
    """Correspondance (provider, compétition_provider) → code canonique interne,
    DÉRIVÉE des registres déclarés des providers (source unique de vérité)."""
    from ..providers.espn import LEAGUES as ESPN_LEAGUES
    from ..providers.football_data_uk import DIVISIONS as FDUK_DIVS
    from ..providers.openligadb import LEAGUES as OLDB_LEAGUES
    from ..providers.football_data_org import COMPETITIONS as FDORG_COMPS
    from ..providers.thesportsdb import LEAGUES as TSDB_LEAGUES

    canon: dict[str, dict[str, str]] = {}
    for slug, (code, name, area) in ESPN_LEAGUES.items():
        canon[f"espn:{slug}"] = {"code": code, "name": name, "area": area}
    prefix = {"E": "ENG", "SC": "SCO", "D": "GER", "I": "ITA", "SP": "ESP", "F": "FRA",
              "N": "NED", "B": "BEL", "P": "POR", "T": "TUR", "G": "GRE"}
    for div, (area, name) in FDUK_DIVS.items():
        # fduk : E0 → ENG-E0, E1 → ENG-E1, SC0 → SCO-SC0, D1 → GER-D1, SP1 → ESP-SP1…
        # ATTENTION : préfixes 2 lettres (SC, SP) avant le fallback 1 lettre (§5).
        prefix2 = {"SC": "SCO", "SP": "ESP"}
        if div == "EC":
            code = "ENG-EC"
        elif div[:2] in prefix2:
            code = f"{prefix2[div[:2]]}-{div}"
        else:
            code = f"{prefix.get(div[0], div)}-{div}"
        canon[f"fduk:{div}"] = {"code": code, "name": name, "area": area}
    for lg, (code, name, area) in OLDB_LEAGUES.items():
        canon[f"openligadb:{lg}"] = {"code": code, "name": name, "area": area}
    for c, (code, name, area) in FDORG_COMPS.items():
        canon[f"fdorg:{c}"] = {"code": code, "name": name, "area": area}
    for lid, (code, name, area) in TSDB_LEAGUES.items():
        canon[f"tsdb:{lid}"] = {"code": code, "name": name, "area": area}
    return canon


CANON_BY_PROVIDER_COMP: dict[str, dict[str, str]] = _build_canonical()


def resolve_competition(session: Session, raw: RawFixture) -> tuple[Competition, bool]:
    key = f"{raw.provider}:{raw.provider_competition}"
    canon = CANON_BY_PROVIDER_COMP.get(key)
    code = canon["code"] if canon else f"{raw.provider.upper()}-{raw.provider_competition}"
    name = canon["name"] if canon else raw.competition_name
    area = canon["area"] if canon else raw.competition_area

    comp = session.query(Competition).filter_by(code=code).one_or_none()
    created = False
    if not comp:
        comp = Competition(code=code, name=name, area=area)
        session.add(comp)
        session.flush()
        created = True
    m = _mapping(session, "competition", raw.provider, raw.provider_competition)
    if not m:
        session.add(EntityMapping(
            entity_type="competition", entity_id=comp.id,
            provider=raw.provider, provider_id=raw.provider_competition,
        ))
    return comp, created
