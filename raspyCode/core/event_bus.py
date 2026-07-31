"""EventBus fan-out: ogni subscribe() restituisce una coda dedicata che riceve

una copia di ogni evento pubblicato (o, se si passano dei tipi, solo degli
eventi di quei tipi).
"""

import asyncio

from .events import Event

# Dimensione massima di ogni coda per-subscriber. asyncio.Queue senza
# maxsize cresce senza limite: se un subscriber si blocca o e' piu' lento
# di quanto vengano pubblicati eventi, gli eventi si accumulano in memoria
# indefinitamente. Con un maxsize, publish() applica vera backpressure
# (attende che ci sia spazio) invece di accumulare per sempre. Non risolve
# la distinzione fine tra eventi "lossless" vs "ultimo stato valido" (per
# quello servirebbero politiche per-tipo-di-evento), ma limita il caso
# peggiore.
DEFAULT_MAX_QUEUE_SIZE = 2000


class EventBus:
    def __init__(self, max_queue_size: int = DEFAULT_MAX_QUEUE_SIZE) -> None:
        self._max_queue_size = max_queue_size
        # ogni subscriber e' una coppia (coda, tipi_di_interesse). tipi_di_interesse
        # None = riceve tutto (comportamento storico, retrocompatibile).
        self._subscribers: list[
            tuple[asyncio.Queue, tuple[type[Event], ...] | None]
        ] = []

    def subscribe(self, *event_types: type[Event]) -> asyncio.Queue[Event]:
        """Senza argomenti: comportamento storico, riceve ogni evento.
        Con uno o piu' tipi (es. subscribe(UserMessageEvent, ToolResultEvent)):
        riceve solo eventi di quei tipi, riducendo il rumore di broadcast
        globale per i subscriber che sanno gia' cosa gli interessa."""
        q: asyncio.Queue[Event] = asyncio.Queue(maxsize=self._max_queue_size)
        self._subscribers.append((q, event_types or None))
        return q

    def unsubscribe(self, queue: asyncio.Queue) -> None:
        """Rimuove un subscriber dal bus. Da chiamare quando un componente
        viene ricreato/riavviato, per non accumulare code morte per sempre."""
        self._subscribers = [(q, t) for q, t in self._subscribers if q is not queue]

    async def publish(self, event: Event) -> None:
        for q, types in self._subscribers:
            if types is None or isinstance(event, types):
                await q.put(event)
