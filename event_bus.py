"""
EventBus fan-out: ogni subscribe() restituisce una coda dedicata che riceve
una copia di ogni evento pubblicato. Necessario perche' in raspyCode piu'
servizi (LLMGateway, ToolExecutor, TFTDisplay, Frontend) devono osservare
lo stesso evento in parallelo (es. un LLMToolCallEvent va sia a ToolExecutor
per l'esecuzione, sia a TFTDisplay per il rendering di stato, sia al
Frontend per il log a schermo). Una singola asyncio.Queue condivisa tra
consumer concorrenti li farebbe competere per lo stesso evento invece di
farli cooperare.
"""
import asyncio

from .events import Event


class EventBus:
    def __init__(self) -> None:
        self._subscribers: list[asyncio.Queue] = []

    def subscribe(self) -> "asyncio.Queue[Event]":
        q: "asyncio.Queue[Event]" = asyncio.Queue()
        self._subscribers.append(q)
        return q

    async def publish(self, event: Event) -> None:
        for q in self._subscribers:
            await q.put(event)
