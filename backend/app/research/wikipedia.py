"""Wikipedia (FR/EN) — API REST publique, gratuite, sans clé (0 €).

Utilisation pour la RECHERCHE APPROFONDIE :
- search_wikipedia() : opensearch pour trouver les articles pertinents.
- wikipedia_summary() : extrait du résumé d'un article (contexte historique,
  palmarès, effectif) — JAMAIS de donnée chiffrée de match (ce n'est pas sa mission,
  §45 : l'IA/recherche contextualise, les modèles calculent).

Attribution requise (CC BY-SA) → chaque résultat porte sa source + licence.
Cache mémoire TTL 24 h (les articles ne bougent pas à l'échelle d'un match).
"""
from __future__ import annotations

import time

import httpx

from ..config import HTTP_USER_AGENT

BASE_FR = "https://fr.wikipedia.org"
BASE_EN = "https://en.wikipedia.org"
TTL_SECONDS = 24 * 3600
TIMEOUT = 10.0
HEADERS = {"User-Agent": HTTP_USER_AGENT}

_cache: dict[str, tuple[float, object]] = {}


def _cached(key: str, ttl: int = TTL_SECONDS):
    hit = _cache.get(key)
    if hit and time.time() - hit[0] < ttl:
        return hit[1]
    return None


def _store(key: str, value) -> None:
    _cache[key] = (time.time(), value)


def _clean(text: str | None) -> str | None:
    if not text:
        return None
    import re
    txt = re.sub(r"\[\d+\]", "", text)          # supprime les notes [1]
    txt = re.sub(r"\{\{[^}]*\}\}", "", txt)     # supprime les modèles
    txt = " ".join(txt.split())
    return txt[:1500] or None


def wikipedia_summary(title: str, lang: str = "fr") -> dict | None:
    """Résumé d'un article (extract, url, image) — None si introuvable."""
    key = f"sum|{lang}|{title}"
    hit = _cached(key)
    if hit is not None:
        return hit
    base = BASE_FR if lang == "fr" else BASE_EN
    try:
        r = httpx.get(
            f"{base}/api/rest_v1/page/summary/{title.replace(' ', '_')}",
            timeout=TIMEOUT,
            headers=HEADERS,
        )
        if r.status_code != 200:
            _store(key, None)
            return None
        data = r.json()
        if data.get("type") != "standard" or not data.get("extract"):
            _store(key, None)
            return None
        out = {
            "title": data.get("title"),
            "extract": _clean(data.get("extract")),
            "url": data.get("content_urls", {}).get("desktop", {}).get("page"),
            "thumbnail": (data.get("thumbnail") or {}).get("source"),
            "source": f"Wikipedia ({lang}) — CC BY-SA",
            "license": "CC BY-SA 4.0",
        }
        _store(key, out)
        return out
    except Exception:
        return None  # réseau indisponible → silence honnête, jamais de fabrication


def search_wikipedia(query: str, lang: str = "fr", limit: int = 5) -> list[dict]:
    """Recherche d'articles (opensearch) — pour le moteur de recherche global."""
    key = f"srch|{lang}|{query}"
    hit = _cached(key)
    if hit is not None:
        return hit[:limit]
    base = BASE_FR if lang == "fr" else BASE_EN
    try:
        r = httpx.get(
            f"{base}/w/api.php",
            params={
                "action": "opensearch", "search": query,
                "limit": str(limit), "namespace": "0",
                "format": "json", "origin": "*", "redirects": "1",
            },
            timeout=TIMEOUT,
            headers=HEADERS,
        )
        r.raise_for_status()
        data = r.json()
        titles = data[1] if isinstance(data, list) else []
        out = []
        for t in titles:
            out.append({
                "title": t,
                "url": f"{base}/wiki/{t.replace(' ', '_')}",
                "source": f"Wikipedia ({lang}) — CC BY-SA",
                "license": "CC BY-SA 4.0",
            })
        _store(key, out)
        return out
    except Exception:
        return []


def context_for_team(team_name: str) -> dict | None:
    """Contexte historique d'une équipe (article FR, sinon EN)."""
    s = wikipedia_summary(team_name, "fr")
    if s and s.get("extract"):
        return s
    return wikipedia_summary(team_name, "en")


_FOOTBALL_TITLE_HINTS = ("football", "soccer", "ligue")
_FOOTBALL_TEXT_HINTS = ("football", "soccer", "championnat", "championship",
                        "association football", "coupe")


def _is_football_article(title: str, extract: str) -> bool:
    """Un article de ligue de football porte des marques football dans son
    titre ou son extrait (élimine fléchettes, basket, réunions…)."""
    t = (title or "").lower()
    x = (extract or "").lower()
    return any(k in t for k in _FOOTBALL_TITLE_HINTS) or \
        any(k in x for k in _FOOTBALL_TEXT_HINTS)


def _score_hit(hit_title: str, s: dict | None, country: str | None) -> int:
    """Score de pertinence d'un hit opensearch pour une ligue de football."""
    if not s or not s.get("extract"):
        return -1
    score = 0
    t = (hit_title or "").lower()
    if any(k in t for k in _FOOTBALL_TITLE_HINTS):
        score += 3
    if _is_football_article(hit_title, s["extract"]):
        score += 2
    if country and (country.lower() in t or country.lower() in (s.get("extract") or "").lower()):
        score += 2
    return score


def competition_context(comp_name: str, season_label: str | None = None,
                        country: str | None = None) -> dict | None:
    """Contexte d'une compétition (option. saison/pays) — robuste aux homonymies.

    Stratégie (0 €, sources publiques) :
    1. résumé direct « {nom} {saison} » puis « {nom} » (FR → EN),
       filtré : l'article doit bien être du football (sinon homonymie)
    2. opensearch « {nom} {pays} » puis « {nom} » : le hit le mieux scoré
       (marques football + pays) gagne (ex. « Premier League (football) »).
    """
    candidates = []
    if season_label:
        candidates.append(f"{comp_name} {season_label}")
    candidates.append(comp_name)
    for c in candidates:
        for lang in ("fr", "en"):
            s = wikipedia_summary(c, lang)
            if s and s.get("extract") and _is_football_article(c, s["extract"]):
                return s
    best, best_score = None, 1
    for query in ([f"{comp_name} {country}"] if country else []) + [comp_name]:
        for lang in ("fr", "en"):
            for hit in search_wikipedia(query, lang, limit=5):
                if hit["title"] == comp_name:
                    continue  # homonymie probable → articles spécialisés
                s = wikipedia_summary(hit["title"], lang)
                sc = _score_hit(hit["title"], s, country)
                if sc > best_score:
                    best, best_score = s, sc
    return best


def context_for_competition(comp_name: str, season_label: str | None = None) -> dict | None:
    """Contexte d'une compétition (option. saison) — alias de competition_context."""
    return competition_context(comp_name, season_label)
