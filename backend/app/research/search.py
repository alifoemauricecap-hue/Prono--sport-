"""RECHERCHE GLOBALE (§81) — équipes, joueurs, compétitions, matchs, pays.

Deux volets, tous deux réels :
1. Recherche locale dans la base PRONO SPORT (équipes, compétitions, matchs).
2. Recherche en ligne via Wikipedia (source publique fiable, 0 €, attribution CC BY-SA).

Aucun résultat inventé : si rien n'est trouvé, la réponse le dit explicitement.
"""
from __future__ import annotations

from sqlalchemy import or_
from sqlalchemy.orm import Session

from ..db.models import Competition, Fixture, Player, Team
from ..ingest.resolution import normalize_name
from . import wikipedia


def search_global(session: Session, q: str, limit: int = 8) -> dict:
    q = (q or "").strip()
    out: dict = {"query": q, "teams": [], "competitions": [], "fixtures": [],
                 "web": []}
    if len(q) < 2:
        return out
    nq = normalize_name(q)

    # --- 1. Équipes (nom + alias) ---
    teams = (session.query(Team)
             .filter(or_(Team.name.ilike(f"%{q}%")))
             .limit(limit).all())
    if not teams:
        from ..db.models import TeamAlias
        alias_hits = (session.query(TeamAlias)
                      .filter(TeamAlias.alias.ilike(f"%{q}%")).limit(limit).all())
        ids = {a.team_id for a in alias_hits}
        teams = (session.query(Team).filter(Team.id.in_(ids or {0})).limit(limit).all())
    out["teams"] = [{"id": t.id, "name": t.name, "country": t.country,
                     "logo_url": t.logo_url} for t in teams]

    # --- 2. Compétitions ---
    comps = (session.query(Competition)
             .filter(or_(Competition.name.ilike(f"%{q}%"),
                         Competition.area.ilike(f"%{q}%"),
                         Competition.code.ilike(f"%{q}%")))
             .limit(limit).all())
    out["competitions"] = [{"id": c.id, "code": c.code, "name": c.name,
                           "area": c.area} for c in comps]

    # --- 3. Matchs (domicile/extérieur/compétition) ---
    from sqlalchemy.orm import aliased
    TH, TA = aliased(Team), aliased(Team)
    fx_rows = (session.query(Fixture, TH, TA, Competition)
               .outerjoin(TH, Fixture.home_team_id == TH.id)
               .outerjoin(TA, Fixture.away_team_id == TA.id)
               .outerjoin(Competition, Fixture.competition_id == Competition.id)
               .filter(or_(TH.name.ilike(f"%{q}%"), TA.name.ilike(f"%{q}%")))
               .limit(limit * 4).all())
    seen: set[int] = set()
    fxs = []
    for fx, h, a, c in fx_rows:
        if fx.id in seen:
            continue
        seen.add(fx.id)
        fxs.append({
            "id": fx.id, "status": fx.status,
            "kickoff_utc": fx.kickoff_utc.isoformat() if fx.kickoff_utc else None,
            "home": h.name if h else "?", "away": a.name if a else "?",
            "score": [fx.home_score, fx.away_score] if fx.status == "FINISHED" else None,
            "competition": c.name if c else None,
        })
        if len(fxs) >= limit:
            break
    out["fixtures"] = fxs

    # --- 4. Recherche en ligne (Wikipedia — source fiable, 0 €) ---
    web = wikipedia.search_wikipedia(q, "fr", limit=4)
    out["web"] = web
    out["web_source"] = "Wikipedia (FR) — CC BY-SA" if web else None
    return out
