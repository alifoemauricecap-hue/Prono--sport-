"""CATALOGUE MONDIAL DES LIGUES — source unique de vérité (0 €).

Architecture de couverture mondiale :
  1. **ESPN** (API publique, sans clé) : haute qualité (live, minute, logos) sur le
     catalogue ci-dessous — slugs VÉRIFIÉS via l'API publique le 2026-08-26
     (les anciens du 2026-08-24 sont conservés, testés en production 2.0).
  2. **TheSportsDB `eventsday`** (clé publique gratuite "3") : **TOUS les matchs du
     monde en 1 requête/jour** — couvre les ligues hors catalogue ESPN (Afrique,
     Moyen-Orient, 2ᵉ divisions lointaines…). C'est la GARANTIE de couverture
     mondiale : aucune ligue n'est oubliée, les compétitions sont créées à la volée.
  3. **football-data.co.uk** : historique profond + cotes multi-bookmakers (top divisions).
  4. **Wikipedia (FR/EN, CC BY-SA)** : recherche approfondie par LIGUE et par MATCH
     (voir research/league.py et research/engine.py).

Honnêteté (§1) : une ligue du catalogue qui répondrait 404 à l'ingestion est journalisée
et passée — jamais bloquante, jamais simulée. Les ligues hors catalogue existent dès
qu'une source les livre (TSDB world).
"""
from __future__ import annotations

from dataclasses import dataclass

VERIFIE = "VÉRIFIÉ"      # slug confirmé via l'API publique (2026-08-24 ou 2026-08-26)
DECLARE = "DÉCLARÉ"      # slug attendu mais non vérifié ce jour — échec journalisé, non bloquant


@dataclass(frozen=True)
class WorldLeague:
    espn: str       # slug ESPN (ex. "eng.1")
    code: str       # code canonique interne (ex. "ENG-E0")
    name: str       # nom d'affichage (français)
    country: str    # pays (français)
    conf: str       # confédération : UEFA / CONMEBOL / CONCACAF / AFC / CAF / OFC / INTERNATIONAL
    level: int      # 1 = D1, 2 = D2, …, 9 = coupe / tournoi
    status: str = VERIFIE
    verified_on: str = "2026-08-24"


WORLD_LEAGUES: list[WorldLeague] = [
    # ------------------------- ANGLETERRE (UEFA) -------------------------
    WorldLeague("eng.1", "ENG-E0", "Premier League", "Angleterre", "UEFA", 1),
    WorldLeague("eng.2", "ENG-E1", "Championship", "Angleterre", "UEFA", 2),
    WorldLeague("eng.3", "ENG-E2", "League One", "Angleterre", "UEFA", 3),
    WorldLeague("eng.4", "ENG-E3", "League Two", "Angleterre", "UEFA", 4),
    WorldLeague("eng.5", "ENG-EC", "National League", "Angleterre", "UEFA", 5),
    WorldLeague("eng.fa", "ENG-FA", "FA Cup", "Angleterre", "UEFA", 9),
    WorldLeague("eng.league_cup", "ENG-LC", "Carabao Cup", "Angleterre", "UEFA", 9),
    # ------------------------- ESPAGNE (UEFA) -------------------------
    WorldLeague("esp.1", "ESP-SP1", "La Liga", "Espagne", "UEFA", 1),
    WorldLeague("esp.2", "ESP-SP2", "La Liga 2", "Espagne", "UEFA", 2),
    # ------------------------- ALLEMAGNE (UEFA) -------------------------
    WorldLeague("ger.1", "GER-D1", "Bundesliga", "Allemagne", "UEFA", 1),
    WorldLeague("ger.2", "GER-D2", "2. Bundesliga", "Allemagne", "UEFA", 2),
    # ------------------------- ITALIE (UEFA) -------------------------
    WorldLeague("ita.1", "ITA-I1", "Serie A", "Italie", "UEFA", 1),
    WorldLeague("ita.2", "ITA-I2", "Serie B", "Italie", "UEFA", 2),
    # ------------------------- FRANCE (UEFA) -------------------------
    WorldLeague("fra.1", "FRA-F1", "Ligue 1", "France", "UEFA", 1),
    WorldLeague("fra.2", "FRA-F2", "Ligue 2", "France", "UEFA", 2),
    # ------------------------- EUROPE (UEFA) -------------------------
    WorldLeague("por.1", "POR-P1", "Primeira Liga", "Portugal", "UEFA", 1),
    WorldLeague("ned.1", "NED-N1", "Eredivisie", "Pays-Bas", "UEFA", 1),
    WorldLeague("tur.1", "TUR-T1", "Süper Lig", "Turquie", "UEFA", 1),
    WorldLeague("bel.1", "BEL-B1", "Pro League", "Belgique", "UEFA", 1),
    WorldLeague("sco.1", "SCO-SC0", "Premiership", "Écosse", "UEFA", 1),
    WorldLeague("sui.1", "SUI-1", "Super League", "Suisse", "UEFA", 1),
    WorldLeague("gre.1", "GRE-G1", "Super League", "Grèce", "UEFA", 1),
    WorldLeague("aut.1", "AUT-1", "Bundesliga", "Autriche", "UEFA", 1),
    WorldLeague("den.1", "DEN-1", "Superliga", "Danemark", "UEFA", 1),
    WorldLeague("nor.1", "NOR-1", "Eliteserien", "Norvège", "UEFA", 1),
    WorldLeague("swe.1", "SWE-1", "Allsvenskan", "Suède", "UEFA", 1),
    WorldLeague("cze.1", "CZE-1", "Championnat tchèque", "Tchéquie", "UEFA", 1),
    WorldLeague("rou.1", "ROU-1", "Liga 1", "Roumanie", "UEFA", 1),
    # ------------------------- AMÉRIQUE DU SUD (CONMEBOL) -------------------------
    WorldLeague("bra.1", "BRA-1", "Série A", "Brésil", "CONMEBOL", 1),
    WorldLeague("bra.2", "BRA-2", "Série B", "Brésil", "CONMEBOL", 2),
    WorldLeague("arg.1", "ARG-1", "Liga Profesional", "Argentine", "CONMEBOL", 1),
    WorldLeague("col.1", "COL-1", "Primera A", "Colombie", "CONMEBOL", 1),
    WorldLeague("chi.1", "CHI-1", "Primera División", "Chili", "CONMEBOL", 1),
    WorldLeague("uru.1", "URU-1", "Liga AUF", "Uruguay", "CONMEBOL", 1),
    WorldLeague("ecu.1", "ECU-1", "LigaPro", "Équateur", "CONMEBOL", 1),
    WorldLeague("per.1", "PER-1", "Liga 1", "Pérou", "CONMEBOL", 1),
    WorldLeague("ven.1", "VEN-1", "Primera División", "Venezuela", "CONMEBOL", 1),
    # ------------------------- AMÉRIQUE NORD/CENTRE (CONCACAF) -------------------------
    WorldLeague("usa.1", "USA-MLS", "MLS", "États-Unis", "CONCACAF", 1),
    WorldLeague("mex.1", "MEX-1", "Liga MX", "Mexique", "CONCACAF", 1),
    # ------------------------- ASIE (AFC) -------------------------
    WorldLeague("ksa.1", "KSA-1", "Saudi Pro League", "Arabie Saoudite", "AFC", 1),
    WorldLeague("jpn.1", "JPN-1", "J.League", "Japon", "AFC", 1),
    WorldLeague("chn.1", "CHN-1", "Super League", "Chine", "AFC", 1),
    WorldLeague("aus.1", "AUS-1", "A-League", "Australie", "AFC", 1),
    WorldLeague("ind.1", "IND-1", "Super League", "Inde", "AFC", 1),
    WorldLeague("idn.1", "IDN-1", "Indonesian Super League", "Indonésie", "AFC", 1,
                verified_on="2026-08-26"),
    # ------------------------- AFRIQUE (CAF) -------------------------
    WorldLeague("rsa.1", "RSA-1", "Premiership", "Afrique du Sud", "CAF", 1,
                verified_on="2026-08-26"),
    # ------------------------- TOURNOIS INTERNATIONAUX -------------------------
    WorldLeague("uefa.champions", "UEFA-UCL", "Ligue des Champions", "Europe", "INTERNATIONAL", 9),
    WorldLeague("uefa.europa", "UEFA-UEL", "Ligue Europa", "Europe", "INTERNATIONAL", 9),
    WorldLeague("conmebol.libertadores", "CONMEBOL-LIB", "Copa Libertadores", "Amérique du Sud", "INTERNATIONAL", 9),
    WorldLeague("conmebol.sudamericana", "CONMEBOL-SUD", "Copa Sudamericana", "Amérique du Sud", "INTERNATIONAL", 9),
    WorldLeague("concacaf.champions", "CONCACAF-CCL", "Champions Cup", "CONCACAF", "INTERNATIONAL", 9),
    WorldLeague("fifa.worldq.uefa", "FIFA-WCQ-UEFA", "Qualif. Coupe du Monde UEFA", "Monde", "INTERNATIONAL", 9),
    WorldLeague("fifa.worldq.caf", "FIFA-WCQ-CAF", "Qualif. Coupe du Monde CAF", "Monde", "INTERNATIONAL", 9),
    WorldLeague("fifa.worldq.conmebol", "FIFA-WCQ-CONMEBOL", "Qualif. Coupe du Monde CONMEBOL", "Monde", "INTERNATIONAL", 9),
    WorldLeague("fifa.worldq.concacaf", "FIFA-WCQ-CONCACAF", "Qualif. Coupe du Monde CONCACAF", "Monde", "INTERNATIONAL", 9),
    WorldLeague("fifa.worldq.afc", "FIFA-WCQ-AFC", "Qualif. Coupe du Monde AFC", "Monde", "INTERNATIONAL", 9),
    WorldLeague("fifa.friendly", "FIFA-FRIENDLY", "Matchs amicaux internationaux", "Monde", "INTERNATIONAL", 9),
]

CONFEDERATIONS = ["UEFA", "CONMEBOL", "CONCACAF", "AFC", "CAF", "OFC", "INTERNATIONAL"]

_BY_SLUG: dict[str, WorldLeague] = {l.espn: l for l in WORLD_LEAGUES}
_BY_CODE: dict[str, WorldLeague] = {l.code: l for l in WORLD_LEAGUES}


def slug_meta(slug: str) -> WorldLeague | None:
    """Slug ESPN → entrée du catalogue (None si hors catalogue)."""
    return _BY_SLUG.get(slug)


def code_meta(code: str) -> WorldLeague | None:
    return _BY_CODE.get(code)


def slugs(conf: str | None = None, country: str | None = None) -> list[str]:
    """Slugs ESPN à ingérer (filtres optionnels confédération / pays)."""
    out = [l.espn for l in WORLD_LEAGUES
           if (conf is None or l.conf == conf)
           and (country is None or l.country == country)]
    return out


def by_country() -> dict[str, list[WorldLeague]]:
    out: dict[str, list[WorldLeague]] = {}
    for l in WORLD_LEAGUES:
        out.setdefault(l.country, []).append(l)
    return out


def by_confederation() -> dict[str, list[WorldLeague]]:
    out: dict[str, list[WorldLeague]] = {}
    for l in WORLD_LEAGUES:
        out.setdefault(l.conf, []).append(l)
    return out


def espn_leagues_dict() -> dict[str, tuple[str, str, str]]:
    """Format attendu par providers/espn.py : slug → (code, nom, zone)."""
    return {l.espn: (l.code, l.name, l.country) for l in WORLD_LEAGUES}
