"""Enrichissement : compositions (§23) + blessures/suspensions (§22) depuis
une source réelle (API-Football). Rien n'est inventé : si la source ne publie
pas la donnée, la table reste vide et l'UI affiche DONNÉE INDISPONIBLE.
"""
from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy.orm import Session

from ..db.models import (
    EntityMapping, Fixture, Injury, Lineup, Player, Suspension, Team,
)


def _fixture_for_provider(session: Session, provider: str, provider_id: str) -> Fixture | None:
    m = (session.query(EntityMapping)
         .filter_by(entity_type="fixture", provider=provider,
                    provider_id=str(provider_id)).one_or_none())
    if m is None:
        return None
    return session.get(Fixture, m.entity_id)


def ingest_lineups(session: Session, provider: str,
                   lineups: list) -> int:
    """Upsert idempotent des compositions officielles. Retourne le nb de joueurs écrits."""
    written = 0
    for lu in lineups:
        fx = _fixture_for_provider(session, provider, lu.fixture_provider_id)
        if fx is None:
            continue  # match pas encore en base → on saute (pas de fixture inventé)
        # quelle équipe (domicile/extérieur) ?
        if lu.side == "home":
            team_id = fx.home_team_id
        else:
            team_id = fx.away_team_id
        # purge de l'ancienne version de CETTE source pour ce (fixture, team)
        (session.query(Lineup)
             .filter(Lineup.fixture_id == fx.id, Lineup.team_id == team_id,
                     Lineup.source == provider)
             .delete())
        for p in lu.players:
            # résolution/joueurs : par (team, nom normalisé) — sinon création
            from .resolution import normalize_name
            norm = normalize_name(p.name)
            existing = (session.query(Player)
                        .filter(Player.team_id == team_id,
                                Player.name == p.name).one_or_none())
            if existing is None:
                for pl in session.query(Player).filter(Player.team_id == team_id).all():
                    if normalize_name(pl.name) == norm:
                        existing = pl
                        break
            if existing is None:
                existing = Player(name=p.name, team_id=team_id,
                                  position=p.position)
                session.add(existing)
                session.flush()
            session.add(Lineup(
                fixture_id=fx.id, team_id=team_id, player_id=existing.id,
                player_name=p.name, number=p.number, position=p.position,
                is_starting=p.starting, source=provider,
                fetched_at=datetime.now(timezone.utc),
            ))
            written += 1
    session.commit()
    return written


def ingest_injuries(session: Session, provider: str, injuries: list) -> int:
    """Upsert idempotent des blessures réelles (status INJURED/DOUBTFUL/RETURNING)."""
    written = 0
    from .resolution import normalize_name
    for inj in injuries:
        # équipe ciblée (nom normalisé) → team_id (si connu)
        team = None
        if inj.team_name:
            tnorm = normalize_name(inj.team_name)
            for t in session.query(Team).all():
                if normalize_name(t.name) == tnorm:
                    team = t
                    break
        player = None
        if team is not None:
            pnorm = normalize_name(inj.player_name)
            for pl in session.query(Player).filter(Player.team_id == team.id).all():
                if normalize_name(pl.name) == pnorm:
                    player = pl
                    break
            if player is None:
                player = Player(name=inj.player_name, team_id=team.id)
                session.add(player)
                session.flush()
        if player is None:
            continue  # équipe inconnue → on ne crée pas de joueur orphelin
        # purge de l'ancienne entrée (même joueur, même source)
        (session.query(Injury)
             .filter(Injury.player_id == player.id, Injury.source == provider)
             .delete())
        session.add(Injury(
            player_id=player.id, status=inj.status, detail=inj.detail,
            expected_return=inj.expected_return, source=provider,
            fetched_at=datetime.now(timezone.utc),
        ))
        written += 1
    session.commit()
    return written
