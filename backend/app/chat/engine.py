"""M8 — Assistant PRONO SPORT : chat en français, réponses construites UNIQUEMENT
sur les données réelles de la base (§1 : le chat n'invente jamais un chiffre).

Aucun service externe payant : moteur d'intentions déterministe + résolution d'équipes
par noms/alias. Chaque réponse cite sa source (modèle, bookmaker, date de capture).
"""
from __future__ import annotations

import re
from datetime import datetime, timezone

from sqlalchemy.orm import Session

from ..db.models import Competition, Fixture, Team, TeamAlias, TeamAnalytics, ValueBet
from ..ingest.resolution import normalize_name

DISCLAIMER = "⚠️ Probabilité ≠ certitude — analyse probabiliste, jamais une garantie (§38/§86)."
SEL_TXT = {"H": "Victoire de {home}", "D": "Match nul", "A": "Victoire de {away}",
           "Over": "Plus de 2,5 buts", "Under": "Moins de 2,5 buts"}


def _norm(txt: str) -> str:
    return normalize_name(txt)


def find_team(session: Session, token: str) -> Team | None:
    """Résout UNE équipe par nom ou alias (jamais sur sous-chaîne ambiguë courte)."""
    tkn = _norm(token)
    if len(tkn) < 3:
        return None
    exact = session.query(Team).all()
    for t in exact:
        if _norm(t.name) == tkn:
            return t
    alias_rows = session.query(TeamAlias).all()
    for a in alias_rows:
        if _norm(a.alias) == tkn:
            return session.get(Team, a.team_id)
    # sous-chaîne stricte (contient le token entier), une seule réponse sinon ambiguïté
    cands = [t for t in exact if tkn in _norm(t.name)]
    return cands[0] if len(cands) == 1 else None


_INTENT_WORDS = re.compile(
    r"\b(prono|pronostic|prediction|prédictions?|analyse|analyser|match|score|scores|"
    r"qui gagne|gagne|resultat|résultat|cote|donne(?:moi)?|le|la|les|du|de|des)\b", re.IGNORECASE)


def _split_two_teams(session: Session, text: str) -> tuple[Team, Team] | None:
    cleaned = _INTENT_WORDS.sub(" ", text)
    cleaned = re.sub(r"\s+", " ", cleaned)
    m = re.split(r"\s+(?:vs\.?|contre|–|-|v)\s+", cleaned, flags=re.IGNORECASE)
    if len(m) != 2:
        return None
    t1, t2 = find_team(session, m[0].strip()), find_team(session, m[1].strip())
    return (t1, t2) if t1 and t2 else None


def answer(session: Session, question: str) -> dict:
    q = (question or "").strip()
    ql = q.lower()
    now = datetime.now(timezone.utc)

    # ---------- intent : value bets ----------
    if re.search(r"value|value bet|valuebet|value bets|pari value|cote value", ql):
        rows = (session.query(ValueBet, Fixture)
                .join(Fixture, ValueBet.fixture_id == Fixture.id)
                .filter(Fixture.status.in_(["SCHEDULED", "UPCOMING", "LINEUPS_PENDING",
                                            "LINEUPS_CONFIRMED"]))
                .order_by(ValueBet.ev.desc()).limit(8).all())
        if not rows:
            txt = ("Aucune value bet qualifiée en ce moment — **NO QUALIFIED PICK** : "
                   "le moteur ne force jamais un pari quand le marché est efficient (§37/§85).")
        else:
            lines = ["Voici les value bets actives, calculées sur **cotes réelles** :\n"]
            for vb, fx in rows:
                h = session.get(Team, fx.home_team_id)
                a = session.get(Team, fx.away_team_id)
                sel = SEL_TXT.get(vb.selection, vb.selection).format(home=h.name, away=a.name)
                lines.append(
                    f"• **{h.name} – {a.name}** ({fx.kickoff_utc:%d/%m %H:%M} UTC) — "
                    f"{sel} @ **{vb.odds_reference:.2f}** ({vb.bookmaker_ref}) · "
                    f"EV +{vb.ev*100:.1f} % · niveau **{vb.level}** · confiance {vb.confidence}")
            txt = "\n".join(lines)
        return {"answer": txt + "\n\n" + DISCLAIMER,
                "sources": ["value_bets (cotes réelles snapshots)", "modèle ensemble-dc-poisson-elo:v1"]}

    # ---------- intent : prédiction d'un match X vs Y ----------
    pair = _split_two_teams(session, q)
    if pair and re.search(r"prono|prédict|predic|qui gagne|pronostic|score|analyse|match", ql) or (pair and len(ql) < 60):
        t1, t2 = pair
        fx = (session.query(Fixture)
              .filter(Fixture.status.in_(["SCHEDULED", "UPCOMING", "LINEUPS_PENDING",
                                          "LINEUPS_CONFIRMED", "LIVE", "HALFTIME"]),
                      Fixture.home_team_id.in_([t1.id, t2.id]),
                      Fixture.away_team_id.in_([t1.id, t2.id]),
                      Fixture.home_team_id != Fixture.away_team_id)
              .order_by(Fixture.kickoff_utc.asc()).first())
        if fx is None:
            txt = (f"Aucun match à venir **{t1.name} – {t2.name}** en base — "
                   "DONNÉE NON DISPONIBLE (je n'invente pas un match, §1).")
            return {"answer": txt, "sources": ["fixtures"]}
        from ..db.models import Prediction
        pred = (session.query(Prediction).filter_by(fixture_id=fx.id)
                .order_by(Prediction.created_at.desc()).first())
        h = session.get(Team, fx.home_team_id)
        a = session.get(Team, fx.away_team_id)
        if pred is None:
            txt = (f"Match trouvé : **{h.name} – {a.name}** ({fx.kickoff_utc:%d/%m %H:%M} UTC), "
                   "mais historique insuffisant pour modéliser — PAS DE PRÉDICTION (§82).")
            return {"answer": txt, "sources": ["fixtures"]}
        p = pred.probabilities.get("1X2_ensemble") or pred.probabilities["1X2"]
        ou = pred.probabilities.get("OU_2.5", {})
        tops = pred.probabilities.get("top_scores", [])[:3]
        txt = (f"**{h.name} – {a.name}** · {fx.kickoff_utc:%d/%m %H:%M} UTC\n\n"
               f"• Victoire {h.name} : **{p['H']*100:.0f} %**\n"
               f"• Nul : **{p['D']*100:.0f} %**\n"
               f"• Victoire {a.name} : **{p['A']*100:.0f} %**\n"
               f"• +2,5 buts : {ou.get('Over', 0)*100:.0f} % · -2,5 : {ou.get('Under', 0)*100:.0f} %\n"
               f"• Buts attendus : {pred.expected_goals['home']} – {pred.expected_goals['away']}\n"
               f"• Scores les + probables : " +
               ", ".join(f"{t['score']} ({t['p']*100:.0f} %)" for t in tops) +
               f"\n\n_Modèle ensemble Dixon-Coles × Elo, historique "
               f"{pred.input_snapshot.get('history_matches', '?')} matchs réels._\n\n" + DISCLAIMER)
        return {"answer": txt, "fixture_id": fx.id,
                "sources": ["predictions (ensemble v1)", "historique fixtures réelles"]}

    # ---------- intent : forme / elo d'une équipe ----------
    m = re.search(r"(?:forme|elo|classement elo)\s+(?:de\s+|d')?(.+)", ql)
    if m:
        t = find_team(session, m.group(1).strip())
        if t:
            an = session.query(TeamAnalytics).filter_by(team_id=t.id).one_or_none()
            if an is None or an.matches_rated == 0:
                txt = (f"**{t.name}** : pas encore assez de matchs réels enregistrés pour calculer "
                       "un Elo — DONNÉE NON DISPONIBLE (§13).")
            else:
                form = an.form5 or "?"
                txt = (f"**{t.name}**\n\n• Elo : **{an.elo:.0f}** (sur {an.matches_rated} matchs réels)\n"
                       f"• 5 derniers matchs : **{form}**\n"
                       f"• Rendement offensif/défensif sur 5 matchs (moyenne pondérée, "
                       f"les plus récents comptent plus) : {an.gf5 if an.gf5 is not None else '—'} "
                       f"marqués / {an.ga5 if an.ga5 is not None else '—'} encaissés\n\n"
                       "_Elo interne K=60, avantage domicile 65 pts — recalculé après chaque journée._")
            return {"answer": txt, "sources": ["team_analytics (Elo interne v1)"]}
        return {"answer": f"Équipe introuvable : « {m.group(1).strip()} » — vérifie l'orthographe "
                          "ou donne le nom le plus courant.", "sources": ["teams", "team_aliases"]}

    # ---------- intent : prochains matchs d'une équipe ----------
    m = re.search(r"(?:prochains? matchs?|calendrier|prochain)\s+(?:de\s+|d'|du\s+)?(.+)", ql)
    if m:
        t = find_team(session, m.group(1).strip())
        if t:
            rows = (session.query(Fixture)
                    .filter(Fixture.status.in_(["SCHEDULED", "UPCOMING"]),
                            Fixture.kickoff_utc >= now.replace(tzinfo=None),
                            (Fixture.home_team_id == t.id) | (Fixture.away_team_id == t.id))
                    .order_by(Fixture.kickoff_utc.asc()).limit(5).all())
            if not rows:
                txt = f"Aucun match programmé pour **{t.name}** — DONNÉE NON DISPONIBLE."
            else:
                lines = [f"Prochains matchs de **{t.name}** :\n"]
                for fx in rows:
                    h, a = session.get(Team, fx.home_team_id), session.get(Team, fx.away_team_id)
                    comp = session.get(Competition, fx.competition_id)
                    lines.append(f"• {fx.kickoff_utc:%a %d/%m %H:%M} UTC — **{h.name} – {a.name}** "
                                 f"({comp.name if comp else '?'})")
                txt = "\n".join(lines)
            return {"answer": txt, "sources": ["fixtures"]}
        return {"answer": "Équipe introuvable — précise le nom.", "sources": ["teams"]}

    # ---------- fallback : capacités ----------
    return {"answer": (
        "Je réponds UNIQUEMENT à partir des données réelles de PRONO SPORT. Exemples :\n\n"
        "• « value bets du jour »\n"
        "• « prono Arsenal vs Chelsea »\n"
        "• « prédiction Real Madrid - Barça »\n"
        "• « forme de Liverpool » / « elo de PSG »\n"
        "• « prochains matchs de Marseille »\n\n"
        "Je ne donne jamais de chiffre inventé : si la donnée manque, je le dis.\n\n" + DISCLAIMER),
        "sources": ["fixtures", "predictions", "value_bets", "team_analytics"]}
