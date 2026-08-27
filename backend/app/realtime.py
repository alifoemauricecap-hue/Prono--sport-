"""BUS D'ÉVÉNEMENTS TEMPS RÉEL (SSE).

Pub/Sub en mémoire : les workers publient (buts, statuts, value bets, sources, jobs),
l'endpoint GET /v1/events pousse aux clients connectés (Server-Sent Events).
Chaque client a sa file ; un heartbeat toutes les 25 s garde la connexion vivante
traversant les proxies gratuits (Koyeb/HF).
"""
from __future__ import annotations

import asyncio
import json
import time


class EventBus:
    def __init__(self) -> None:
        self._subscribers: list[asyncio.Queue] = []

    def subscribe(self) -> asyncio.Queue:
        q: asyncio.Queue = asyncio.Queue(maxsize=256)
        self._subscribers.append(q)
        return q

    def unsubscribe(self, q: asyncio.Queue) -> None:
        if q in self._subscribers:
            self._subscribers.remove(q)

    def publish(self, event: dict) -> None:
        """Synchron (appelable depuis n'importe quel thread/task). Non bloquant :
        une file pleine = événement perdu pour CE client (jamais de blocage du serveur)."""
        for q in list(self._subscribers):
            try:
                q.put_nowait(event)
            except asyncio.QueueFull:
                pass

    @property
    def n_subscribers(self) -> int:
        return len(self._subscribers)


BUS = EventBus()


def emit(event_type: str, **payload) -> dict:
    ev = {"type": event_type, "ts": time.time(), **payload}
    BUS.publish(ev)
    return ev
