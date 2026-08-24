"""Adapter ESPN — API publique gratuite (alimente espn.com).

Données : scoreboard (fixtures + scores + statuts), équipes (ids stables, logos).
Statut de confiance : UNVERIFIED (source non contractuelle) tant qu'aucune 2ᵉ source ne confirme (§4).
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Iterable

import httpx

from ..config import HTTP_TIMEOUT_SECONDS
from .base import Provider, RawFixture, TeamRef

PROVIDER = "espn"
BASE = "https://site.api.espn.com/apis/site/v2/sports/soccer"

# Ligues mondiales ESPN VÉRIFIÉES en direct le 2026-08-24 :
# slug ESPN → (code canonique interne, nom d'affichage, zone)
LEAGUES: dict[str, tuple[str, str, str]] = {
    # Angleterre
    "eng.1": ("ENG-E0", "Premier League", "Angleterre"),
    "eng.2": ("ENG-E1", "Championship", "Angleterre"),
    "eng.3": ("ENG-E2", "League One", "Angleterre"),
    "eng.4": ("ENG-E3", "League Two", "Angleterre"),
    "eng.5": ("ENG-EC", "National League", "Angleterre"),
    "eng.fa": ("ENG-FA", "FA Cup", "Angleterre"),
    "eng.league_cup": ("ENG-LC", "Carabao Cup", "Angleterre"),
    # Espagne / Allemagne / Italie / France
    "esp.1": ("ESP-SP1", "La Liga", "Espagne"),
    "esp.2": ("ESP-SP2", "La Liga 2", "Espagne"),
    "ger.1": ("GER-D1", "Bundesliga", "Allemagne"),
    "ger.2": ("GER-D2", "2. Bundesliga", "Allemagne"),
    "ita.1": ("ITA-I1", "Serie A", "Italie"),
    "ita.2": ("ITA-I2", "Serie B", "Italie"),
    "fra.1": ("FRA-F1", "Ligue 1", "France"),
    "fra.2": ("FRA-F2", "Ligue 2", "France"),
    # Autres championnats européens
    "por.1": ("POR-P1", "Primeira Liga", "Portugal"),
    "ned.1": ("NED-N1", "Eredivisie", "Pays-Bas"),
    "tur.1": ("TUR-T1", "Süper Lig", "Turquie"),
    "bel.1": ("BEL-B1", "Pro League", "Belgique"),
    "sco.1": ("SCO-SC0", "Premiership", "Écosse"),
    "sui.1": ("SUI-1", "Super League", "Suisse"),
    "gre.1": ("GRE-G1", "Super League", "Grèce"),
    "aut.1": ("AUT-1", "Bundesliga", "Autriche"),
    "den.1": ("DEN-1", "Superliga", "Danemark"),
    "nor.1": ("NOR-1", "Eliteserien", "Norvège"),
    "swe.1": ("SWE-1", "Allsvenskan", "Suède"),
    "cze.1": ("CZE-1", "Championnat tchèque", "Tchéquie"),
    "rou.1": ("ROU-1", "Liga 1", "Roumanie"),
    # Amériques
    "usa.1": ("USA-MLS", "MLS", "États-Unis"),
    "mex.1": ("MEX-1", "Liga MX", "Mexique"),
    "arg.1": ("ARG-1", "Liga Profesional", "Argentine"),
    "bra.1": ("BRA-1", "Série A", "Brésil"),
    "bra.2": ("BRA-2", "Série B", "Brésil"),
    "col.1": ("COL-1", "Primera A", "Colombie"),
    "chi.1": ("CHI-1", "Primera División", "Chili"),
    "uru.1": ("URU-1", "Liga AUF", "Uruguay"),
    "ecu.1": ("ECU-1", "LigaPro", "Équateur"),
    "per.1": ("PER-1", "Liga 1", "Pérou"),
    "ven.1": ("VEN-1", "Primera División", "Venezuela"),
    # Asie / Océanie
    "ksa.1": ("KSA-1", "Saudi Pro League", "Arabie Saoudite"),
    "jpn.1": ("JPN-1", "J.League", "Japon"),
    "chn.1": ("CHN-1", "Super League", "Chine"),
    "aus.1": ("AUS-1", "A-League", "Australie"),
    "ind.1": ("IND-1", "Super League", "Inde"),
    # Coupes internationales
    "uefa.champions": ("UEFA-UCL", "Ligue des Champions", "Europe"),
    "uefa.europa": ("UEFA-UEL", "Ligue Europa", "Europe"),
    "conmebol.libertadores": ("CONMEBOL-LIB", "Copa Libertadores", "Amérique du Sud"),
    "conmebol.sudamericana": ("CONMEBOL-SUD", "Copa Sudamericana", "Amérique du Sud"),
    "concacaf.champions": ("CONCACAF-CCL", "Champions Cup", "CONCACAF"),
    "fifa.worldq.uefa": ("FIFA-WCQ-UEFA", "Qualif. Coupe du Monde UEFA", "Monde"),
    "fifa.worldq.caf": ("FIFA-WCQ-CAF", "Qualif. Coupe du Monde CAF", "Afrique"),
    "fifa.worldq.conmebol": ("FIFA-WCQ-CONMEBOL", "Qualif. Coupe du Monde CONMEBOL", "Amérique du Sud"),
    "fifa.worldq.concacaf": ("FIFA-WCQ-CONCACAF", "Qualif. Coupe du Monde CONCACAF", "CONCACAF"),
    "fifa.worldq.afc": ("FIFA-WCQ-AFC", "Qualif. Coupe du Monde AFC", "Asie"),
    "fifa.friendly": ("FIFA-FRIENDLY", "Matchs amicaux internationaux", "Monde"),
}

# Sous-ensemble rafraîchi automatiquement (cyclet live) ; le reste via CLI world.
AUTO_WATCH_LEAGUES = [
    "eng.1", "eng.2", "esp.1", "ger.1", "ita.1", "fra.1",
    "por.1", "ned.1", "tur.1", "uefa.champions", "uefa.europa",
    "conmebol.libertadores", "bra.1", "arg.1", "usa.1", "mex.1",
    "fifa.worldq.caf", "fifa.worldq.uefa",
]

STATUS_MAP = {
    "STATUS_SCHEDULED": "SCHEDULED",
    "STATUS_IN_PROGRESS": "LIVE",
    "STATUS_HALFTIME": "HALFTIME",
    "STATUS_SECOND_HALF": "LIVE",
    "STATUS_FULL_TIME": "FINISHED",
    "STATUS_FINAL": "FINISHED",
    "STATUS_FINAL_AET": "FINISHED",   # après prolongations
    "STATUS_FINAL_PEN": "FINISHED",   # après tirs au but
    "STATUS_POSTPONED": "POSTPONED",
    "STATUS_CANCELED": "CANCELLED",
    "STATUS_DELAYED": "UPCOMING",
}


def _season_label_for(dt: datetime) -> str:
    """Saison football européenne : août→mai. 2026-08 → '2026-2027', 2027-03 → idem."""
    start = dt.year if dt.month >= 7 else dt.year - 1
    return f"{start}-{start + 1}"


def _parse_iso(date_str: str | None) -> datetime | None:
    if not date_str:
        return None
    try:
        d = datetime.fromisoformat(date_str.replace("Z", "+00:00"))
        return d if d.tzinfo else d.replace(tzinfo=timezone.utc)
    except ValueError:
        return None


def _score(comp: dict) -> int | None:
    s = comp.get("score")
    if s in (None, ""):
        return None
    try:
        return int(s)
    except (ValueError, TypeError):
        return None


class EspnProvider(Provider):
    name = PROVIDER

    def scoreboard_url(self, league: str) -> str:
        return f"{BASE}/{league}/scoreboard"

    def fetch(self, league: str, limit: int = 200, date: str | None = None) -> dict:
        # NB (mesuré à l'ingestion) : le front public ESPN rejette les User-Agent
        # personnalisés (403) ; l'UA httpx par défaut passe (200). Ne pas en forcer un.
        params = {"limit": str(limit)}
        if date:
            params["dates"] = date  # format YYYYMMDD — une requête par jour
        r = httpx.get(
            self.scoreboard_url(league),
            params=params,
            timeout=HTTP_TIMEOUT_SECONDS,
        )
        r.raise_for_status()
        return r.json()

    def parse(self, payload: dict, league: str, source_url: str | None = None) -> Iterable[RawFixture]:
        canon_code, comp_name, area = LEAGUES.get(league, (f"ESPN-{league}", league, None))
        # Nom/zona de secours directement depuis le payload (source primaire, §46).
        lg = (payload.get("leagues") or [{}])[0]
        if league not in LEAGUES and lg.get("name"):
            comp_name = lg["name"]
        for event in payload.get("events", []) or []:
            comps = event.get("competitions") or []
            if not comps:
                continue
            comp = comps[0]
            competitors = comp.get("competitors") or []
            home = next((c for c in competitors if c.get("homeAway") == "home"), None)
            away = next((c for c in competitors if c.get("homeAway") == "away"), None)
            if not home or not away:
                continue
            kickoff = _parse_iso(event.get("date"))
            venue = (comp.get("venue") or {}).get("fullName")
            venue_city = ((comp.get("venue") or {}).get("address") or {}).get("city")
            espn_status = ((event.get("status") or {}).get("type") or {}).get("name") or ""
            status_type = (event.get("status") or {}).get("type") or {}
            clock = (event.get("status") or {}).get("displayClock")
            status = STATUS_MAP.get(espn_status, "UNKNOWN")
            # La minute n'a de sens qu'en cours de jeu (§1 : sinon NULL, jamais d'affichage faux).
            if status not in {"LIVE", "HALFTIME", "EXTRA_TIME", "PENALTIES"}:
                clock = None
            # Sémantique ESPN : un match non joué porte score "0" ≠ un vrai 0.
            # Normalisé NULL (jamais de fausse donnée, §1) ; scores réels conservés en LIVE/FINISHED.
            if status in {"SCHEDULED", "UPCOMING", "POSTPONED", "CANCELLED", "ABANDONED", "UNKNOWN"}:
                home_score, away_score = None, None
            else:
                home_score, away_score = _score(home), _score(away)

            def teamref(c: dict) -> TeamRef:
                t = c.get("team") or {}
                logos = t.get("logos") or []
                return TeamRef(
                    name=t.get("displayName") or t.get("name") or "?",
                    provider_id=str(t.get("id")) if t.get("id") is not None else None,
                    logo_url=logos[0].get("href") if logos else None,
                    country=area,
                )

            yield RawFixture(
                provider=PROVIDER,
                provider_id=str(event.get("id")),
                provider_competition=league,
                competition_name=comp_name,
                competition_area=area,
                season_label=_season_label_for(kickoff) if kickoff else None,
                kickoff_utc=kickoff,
                kickoff_time_known=True,
                status=status,
                home=teamref(home),
                away=teamref(away),
                home_score=home_score,
                away_score=away_score,
                venue=venue,
                venue_city=venue_city,
                clock=clock,
                raw={
                    "espn_event_id": event.get("id"),
                    "espn_status": espn_status,
                    "venue": venue,
                    "name": event.get("name"),
                },
                source_url=source_url,
            )
