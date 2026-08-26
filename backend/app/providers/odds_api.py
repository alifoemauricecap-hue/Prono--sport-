"""Adapter The Odds API — §37/§38/§39 (cotes réelles multi-bookmakers).

Clé GRATUITE (500 crédits/mois ≈ 16 req/jour) : 0 €. Actif uniquement si
`ODDS_API_KEY` est définie ; sinon MISSING DEPENDENCY (§95), jamais de simulation.

Stratégie d'association (honnêteté §1) :
- L'API ne fournit pas la compétition : chaque événement est associé à un
  fixture DÉJÀ présent en base par (noms d'équipes normalisés + kickoff ± 90 min).
- Un événement sans correspondance en base est ignoré (jamais de match inventé,
  jamais de pseudo-compétition).
- Les cotes sont snapshotées (append-only) sur le fixture interne → la tendance
  (§38) et la value (§40) s'appliquent ensuite comme pour n'importe quelle cote.
"""
from __future__ import annotations

import os
from datetime import datetime, timedelta, timezone
from typing import Iterable

from ..db.models import Fixture, Team
from ..ingest.resolution import normalize_name
from .base import OddsRef, Provider
from .cache import http_get_json

PROVIDER = "oddsapi"
BASE = "https://api.the-odds-api.com/v4"
TTL_MIN = 45  # le worker tourne toutes les ~3 h : 8-16 appels/jour, ~2 crédits/appel


def key() -> str | None:
    return os.environ.get("ODDS_API_KEY") or None


def available() -> bool:
    """True si la clé gratuite est fournie (sinon le worker affiche MISSING DEPENDENCY)."""
    return bool(key())


class OddsApiProvider:
    """Pas un Provider fixtures classique : c'est un ODDS PROVIDER (§68)."""
    name = PROVIDER

    def available(self) -> bool:
        return bool(key())

    def url(self) -> str:
        return (f"{BASE}/sports?sports=soccer&regions=eu,uk&"
                f"markets=h2h,totals&oddsFormat=decimal&dateFormat=iso")

    def fetch(self) -> list[dict]:
        k = key()
        if not k:
            raise RuntimeError("MISSING DEPENDENCY : ODDS_API_KEY absente "
                               "(clé gratuite à créer sur the-odds-api.com)")
        data, _origin = http_get_json(
            self.url(), params={"apiKey": k}, timeout=30, ttl_seconds=TTL_MIN * 60)
        return data or []

    def parse_odds(self, event: dict) -> tuple[str, str, datetime | None, list[OddsRef]]:
        """(home, away, kickoff, cotes) pour un événement soccer de l'API."""
        home = event.get("home_team") or "?"
        away = event.get("away_team") or "?"
        kickoff = None
        try:
            kickoff = datetime.fromisoformat(event.get("commence_time", "").replace("Z", "+00:00"))
        except ValueError:
            kickoff = None
        odds: list[OddsRef] = []
        for bm in event.get("bookmakers") or []:
            code = (bm.get("key") or bm.get("title") or "?")[:30]
            for m in bm.get("markets") or []:
                mkey = m.get("key")
                if mkey == "h2h":
                    outs = m.get("outcomes") or []
                    # soccer 1X2 : home / draw / away (l'ordre n'est pas garanti)
                    for outc in outs:
                        name = (outc.get("name") or "")
                        price = outc.get("price")
                        if price is None:
                            continue
                        if name == home:
                            sel = "H"
                        elif name == away:
                            sel = "A"
                        elif len(outs) == 3:
                            sel = "D"   # 3ᵉ issue du 1X2 = match nul
                        else:
                            continue   # moneyline 2 issues (books US) → pas de 1X2
                        odds.append(OddsRef(bookmaker=code, market="1X2",
                                             selection=sel, odds=float(price)))
                elif mkey == "totals":
                    # le point du total (ex. 2.5) est au niveau du marché, pas de l'outcome
                    if (m.get("point") or 0) != 2.5:
                        continue
                    for outc in m.get("outcomes") or []:
                        price = outc.get("price")
                        if price is None:
                            continue
                        if (outc.get("name") or "").lower().startswith("over"):
                            odds.append(OddsRef(bookmaker=code, market="OU_2.5",
                                                selection="Over", odds=float(price)))
                        else:
                            odds.append(OddsRef(bookmaker=code, market="OU_2.5",
                                                selection="Under", odds=float(price)))
        return home, away, kickoff, odds

    def match_fixture(self, session, home: str, away: str,
                      kickoff: datetime | None) -> Fixture | None:
        """Associe un événement à un fixture interne (noms normalisés ± 90 min)."""
        nh, na = normalize_name(home), normalize_name(away)
        if not nh or not na:
            return None
        teams = {t.id: t for t in session.query(Team).all()}
        norm_to_ids: dict[str, set[int]] = {}
        for tid, t in teams.items():
            norm_to_ids.setdefault(normalize_name(t.name), set()).add(tid)
        if nh not in norm_to_ids or na not in norm_to_ids:
            return None
        candidates = []
        for hid in norm_to_ids[nh]:
            for aid in norm_to_ids[na]:
                if hid == aid:
                    continue
                candidates.append((hid, aid))
        for hid, aid in candidates:
            rows = session.query(Fixture).filter(
                Fixture.home_team_id == hid, Fixture.away_team_id == aid).all()
            for fx in rows:
                if kickoff is None or fx.kickoff_utc is None:
                    continue
                if abs((fx.kickoff_utc - kickoff).total_seconds()) > 90 * 60:
                    continue
                return fx
        # dernière chance : sans kickoff connu côté API, on prend le prochain match
        for hid, aid in candidates:
            fx = session.query(Fixture).filter(
                Fixture.home_team_id == hid, Fixture.away_team_id == aid,
                Fixture.status.in_(["SCHEDULED", "UPCOMING"])).first()
            if fx is not None:
                return fx
        return None
