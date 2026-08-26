"""RECHERCHE APPROFONDIE PAR LIGUE (0 €, Wikipedia FR/EN CC BY-SA).

Un dossier de recherche par ligue : contexte historique, format, palmarès —
récupéré par l'application elle-même auprès de sources publiques fiables.

Transparence (§1/§45) :
- statut SOURCE  → article réellement trouvé (titre, extrait, URL, licence)
- statut UNAVAILABLE → « DONNÉE INDISPONIBLE » (réseau coupé ou article absent)
- cache base 7 jours (table league_research) : pas de re-téléchargement inutile
- le dossier est RÉGÉNÉRÉ (refresh) quand il est indisponible ou à la demande.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

from sqlalchemy.orm import Session

from ..db.models import Competition, LeagueResearch
from . import wikipedia

RESEARCH_TTL = timedelta(days=7)


def _as_utc(dt: datetime | None) -> datetime | None:
    if dt is None:
        return None
    return dt.replace(tzinfo=timezone.utc) if dt.tzinfo is None else dt


def league_research(session: Session, competition: Competition,
                    season_label: str | None = None,
                    refresh: bool = False) -> dict:
    """Dossier de recherche approfondie d'une ligue (0 €).

    Retourne :
      {status: "SOURCE", title, extract, url, thumbnail, lang, source, license,
       cached: bool, generated_at: iso}
    ou :
      {status: "UNAVAILABLE", note: "..."} — jamais de donnée inventée.
    """
    now = datetime.now(timezone.utc)
    existing = (session.query(LeagueResearch)
                .filter_by(competition_id=competition.id).one_or_none())

    # --- cache (7 jours) ---
    if not refresh and existing and existing.extract:
        gen = _as_utc(existing.generated_at)
        if gen and (now - gen) < RESEARCH_TTL:
            return {"status": "SOURCE", "title": existing.title, "extract": existing.extract,
                    "url": existing.url, "thumbnail": existing.thumbnail, "lang": existing.lang,
                    "source": existing.source, "license": existing.license,
                    "cached": True,
                    "generated_at": gen.isoformat()}

    # --- recherche en ligne réelle (Wikipedia FR → EN, robuste aux homonymies) ---
    # Noms candidats : nom en base + nom du catalogue mondial (si différent),
    # ex. « Conference » (source) → « National League » (catalogue).
    from ..world import code_meta
    names = [competition.name]
    meta = code_meta(competition.code)
    if meta and meta.name and meta.name not in names:
        names.append(meta.name)
    country = meta.country if meta else None
    ctx = None
    for nm in names:
        ctx = wikipedia.competition_context(nm, season_label, country)
        if ctx and ctx.get("extract"):
            break

    if not ctx or not ctx.get("extract"):
        # réseau coupé ou article inexistant → absence honnête, pas de cache
        if existing:
            session.delete(existing)
            session.commit()
        return {"status": "UNAVAILABLE",
                "note": "Aucun article trouvé ou réseau indisponible — "
                        "réessayez plus tard (aucun contexte inventé)."}

    # --- persistance du dossier (source réelle) ---
    lang = "fr" if ctx.get("source", "").startswith("Wikipedia (fr)") else "en"
    if existing:
        existing.title = ctx.get("title")
        existing.extract = ctx["extract"]
        existing.url = ctx.get("url")
        existing.thumbnail = ctx.get("thumbnail")
        existing.lang = lang
        existing.source = ctx.get("source")
        existing.license = ctx.get("license")
        existing.generated_at = now
    else:
        session.add(LeagueResearch(
            competition_id=competition.id, title=ctx.get("title"), extract=ctx["extract"],
            url=ctx.get("url"), thumbnail=ctx.get("thumbnail"), lang=lang,
            source=ctx.get("source"), license=ctx.get("license"), generated_at=now))
    session.commit()

    return {"status": "SOURCE", "title": ctx.get("title"), "extract": ctx["extract"],
            "url": ctx.get("url"), "thumbnail": ctx.get("thumbnail"), "lang": lang,
            "source": ctx.get("source"), "license": ctx.get("license"),
            "cached": False, "generated_at": now.isoformat()}
