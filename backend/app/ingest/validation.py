"""DATA VALIDATION ENGINE (§7, §109) : un match n'entre en base que s'il passe les contrôles.
Rien n'est complété silencieusement — un échec = rejet tracé dans ingestion_rejects."""
from __future__ import annotations

from datetime import datetime

from ..db.models import FIXTURE_STATUSES
from ..providers.base import RawFixture


def validate_fixture(raw: RawFixture) -> list[str]:
    """Retourne la liste des violations ; vide = fixture valide."""
    errors: list[str] = []

    if not raw.provider or not raw.provider_id:
        errors.append("identifiant_fournisseur_manquant")

    if not raw.home.name or not raw.home.name.strip():
        errors.append("equipe_domicile_manquante")
    if not raw.away.name or not raw.away.name.strip():
        errors.append("equipe_exterieur_manquante")
    if raw.home.name.strip().casefold() == raw.away.name.strip().casefold():
        errors.append("meme_equipe_des_deux_cotes")

    if raw.kickoff_utc is None:
        errors.append("date_match_absente_ou_illisible")
    elif not isinstance(raw.kickoff_utc, datetime):
        errors.append("date_match_invalide")

    if raw.status not in FIXTURE_STATUSES:
        errors.append(f"statut_inconnu:{raw.status}")

    # Cohérence score/statut : FINISHED exige un score ; SCHEDULED n'en a pas.
    if raw.status == "FINISHED":
        if raw.home_score is None or raw.away_score is None:
            errors.append("termine_sans_score")
    if raw.status in {"SCHEDULED", "UPCOMING"} and (raw.home_score is not None or raw.away_score is not None):
        errors.append("score_present_sur_match_non_joue")

    for label, score in (("home", raw.home_score), ("away", raw.away_score)):
        if score is not None and not (0 <= score <= 99):
            errors.append(f"score_aberrant_{label}:{score}")

    for label, xg in (("home", raw.home_xg), ("away", raw.away_xg)):
        if xg is not None and not (0.0 <= xg <= 20.0):
            errors.append(f"xg_aberrant_{label}:{xg}")

    for o in raw.odds:
        if not (1.0 < o.odds <= 1000.0):
            errors.append(f"cote_aberrante:{o.bookmaker}:{o.selection}={o.odds}")

    if not (raw.home.provider_id or raw.home.name):
        errors.append("equipe_sans_identifiant_ni_nom")

    return errors
