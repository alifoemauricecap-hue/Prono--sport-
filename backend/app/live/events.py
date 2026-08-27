"""Détection d'événements live + résolution des pronostics.

PHILOSOPHIE : on ne JAMAIS invente un événement.
- Un BUT est DÉRIVÉ (origin=DERIVED) d'un CHANGEMENT DE SCORE observé entre deux
  lectures successives d'une source réelle. Si le score n'a pas bougé → aucun événement.
- Les transitions de statut (LIVE, HALFTIME, FINISHED…) sont des faits source.
- La minute est la minute réelle de la source (clock) ou NULL si inconnue.
"""
from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy.orm import Session

from ..db.models import Fixture, FixtureEvent, Notification, Prediction, ValueBet

LIVE_STATUSES = {"LIVE", "HALFTIME", "EXTRA_TIME", "PENALTIES"}
FINISHED = "FINISHED"


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _minute(fx: Fixture) -> int | None:
    """Minute réelle : depuis le clock source si présent, sinon NULL (jamais devinée)."""
    clock = (fx.clock or "").strip()
    if not clock:
        return None
    try:
        return int("".join(c for c in clock if c.isdigit())[:2])
    except ValueError:
        return None


def detect_events(session: Session, fx: Fixture,
                  prev_score: tuple[int | None, int | None],
                  prev_status: str | None) -> list[dict]:
    """Compare l'état courant du match à l'état connu précédent ; crée les événements.

    `prev_score`/`prev_status` : état AVANT la dernière ingestion (None si premier vu).
    Retourne la liste des événements émis (pour le SSE).
    """
    emitted: list[dict] = []
    now = _now()
    minute = _minute(fx)
    hs, aws = fx.home_score, fx.away_score

    # --- Transition de statut ---
    if prev_status is not None and prev_status != fx.status:
        if fx.status == "LIVE" and prev_status not in LIVE_STATUSES:
            _add_event(session, fx, minute, "STATUS_CHANGE", None,
                       f"Match démarré (LIVE)", "OBSERVED")
            _notify(session, fx, "MATCH_START", "Match démarré")
            emitted.append({"type": "MATCH_START", "fixture_id": fx.id})
        elif fx.status == "HALFTIME" and prev_status != "HALFTIME":
            _add_event(session, fx, minute, "STATUS_CHANGE", None,
                       "Mi-temps", "OBSERVED")
            emitted.append({"type": "HALFTIME", "fixture_id": fx.id})
        elif fx.status == FINISHED and prev_status != FINISHED:
            _add_event(session, fx, minute, "STATUS_CHANGE", None,
                       "Match terminé", "OBSERVED")
            _notify(session, fx, "MATCH_END", "Match terminé")
            emitted.append({"type": "MATCH_END", "fixture_id": fx.id})

    # --- Buts : déduits du delta de score observé (jamais inventés) ---
    if hs is not None and aws is not None and prev_score is not None:
        ph, pa = prev_score
        if ph is not None and pa is not None:
            if hs > ph:
                delta = hs - ph
                for _ in range(delta):
                    _add_event(session, fx, minute, "GOAL", fx.home_team_id,
                               f"But du domicile ({hs}−{aws})", "DERIVED")
                    _notify(session, fx, "GOAL", f"But du domicile ({hs}−{aws})")
                    emitted.append({"type": "GOAL", "fixture_id": fx.id,
                                    "team": "home", "minute": minute})
            if aws > pa:
                delta = aws - pa
                for _ in range(delta):
                    _add_event(session, fx, minute, "GOAL", fx.away_team_id,
                               f"But de l'extérieur ({hs}−{aws})", "DERIVED")
                    _notify(session, fx, "GOAL", f"But de l'extérieur ({hs}−{aws})")
                    emitted.append({"type": "GOAL", "fixture_id": fx.id,
                                    "team": "away", "minute": minute})
    session.flush()
    return emitted


def _add_event(session: Session, fx: Fixture, minute: int | None, type_: str,
               team_id: int | None, detail: str, origin: str) -> None:
    # Idempotence : ne pas dupliquer un événement identique émis il y a < 90 s
    cutoff = _now() - __import__("datetime").timedelta(seconds=90)
    exists = (session.query(FixtureEvent)
              .filter(FixtureEvent.fixture_id == fx.id,
                      FixtureEvent.type == type_,
                      FixtureEvent.team_id == team_id,
                      FixtureEvent.created_at >= cutoff)
              .first())
    if exists:
        return
    session.add(FixtureEvent(
        fixture_id=fx.id, minute=minute, type=type_, team_id=team_id,
        detail=detail, origin=origin, source=fx.source_provider,
        created_at=_now(),
    ))


def _notify(session: Session, fx: Fixture, type_: str, message: str) -> None:
    session.add(Notification(
        user="local", type=type_, fixture_id=fx.id,
        message=message, created_at=_now(), read=False,
    ))


def resolve_predictions(session: Session, fx: Fixture) -> dict:
    """§54/§17 : à la fin du match, résout les pronostics (WIN/LOSS/VOID/PENDING).

    La prédiction originale n'est JAMAIS modifiée — on note seulement le résultat
    (void si le marché est annulé, pending si le score est incomplet).
    """
    from ..db.models import Team
    if fx.status != FINISHED or fx.home_score is None or fx.away_score is None:
        return {"fixture_id": fx.id, "resolved": 0, "note": "match non terminé"}
    preds = (session.query(Prediction)
             .filter(Prediction.fixture_id == fx.id).all())
    if not preds:
        return {"fixture_id": fx.id, "resolved": 0, "note": "aucune prédiction"}
    home = session.get(Team, fx.home_team_id)
    away = session.get(Team, fx.away_team_id)
    actual = "H" if fx.home_score > fx.away_score else (
        "A" if fx.away_score > fx.home_score else "D")
    resolved = 0
    for p in preds:
        p1x2 = (p.probabilities or {}).get("1X2", {})
        # le "pick" du modèle = la probabilité max (on ne modifie pas la prédiction)
        if p1x2:
            pick = max(p1x2, key=p1x2.get)
            result = "WIN" if pick == actual else "LOSS"
        else:
            result = "PENDING"
        # on enregistre le résultat dans une table de suivi (non-destructif)
        session.add(PredictionResult(
            prediction_id=p.id, fixture_id=fx.id,
            market="1X2", selection=pick if p1x2 else None,
            actual=actual, result=result,
            final_score=f"{fx.home_score}-{fx.away_score}",
            resolved_at=_now(),
        ))
        resolved += 1
    session.commit()
    return {"fixture_id": fx.id, "resolved": resolved,
            "actual": actual, "home": home.name if home else "?",
            "away": away.name if away else "?"}


# Modèle de suivi des résultats (non-destructif) — importé ici pour éviter les cycles
from ..db.models import PredictionResult  # noqa: E402
