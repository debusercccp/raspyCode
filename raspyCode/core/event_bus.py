"""EventBus fan-out: ogni subscribe() restituisce una coda dedicata che riceve

una copia di ogni evento pubblicato.
"""
import asyncio

from .events import Event


class EventBus:
    def __init__(self) -> None:
        self._subscribers: list[asyncio.Queue] = []

    def subscribe(self) -> asyncio.Queue[Event]:
        q: asyncio.Queue[Event] = asyncio.Queue()
        self._subscribers.append(q)
        return q

    async def publish(self, event: Event) -> None:
        for q in self._subscribers:
            await q.put(event)
