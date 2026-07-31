"""ConnectivityService: healthcheck periodico verso Ollama sul Raspberry Pi."""

import asyncio
import contextlib

import httpx

from ..core.event_bus import EventBus
from ..core.events import ConnectionStatusEvent, ModelListEvent, PiConfigEvent

CHECK_INTERVAL_SECONDS = 5.0
TIMEOUT_SECONDS = 2.0


class ConnectivityService:
    def __init__(self, bus: EventBus, pi_ip: str) -> None:
        self._bus = bus
        self._queue = bus.subscribe()
        self._pi_ip = pi_ip

    async def run(self) -> None:
        watch_task = asyncio.create_task(self._watch_config())
        try:
            async with httpx.AsyncClient(timeout=TIMEOUT_SECONDS) as client:
                while True:
                    await self._check_once(client)
                    await asyncio.sleep(CHECK_INTERVAL_SECONDS)
        finally:
            # Se run() viene cancellato (shutdown dell'app) o esce per
            # qualunque motivo, _watch_config() non deve restare orfano
            # a girare per sempre in background, ancora sottoscritto al bus.
            watch_task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await watch_task

    async def _watch_config(self) -> None:
        while True:
            event = await self._queue.get()
            if isinstance(event, PiConfigEvent):
                self._pi_ip = event.pi_ip
            self._queue.task_done()

    async def _check_once(self, client: httpx.AsyncClient) -> None:
        url = f"http://{self._pi_ip}:11434/api/tags"
        try:
            resp = await client.get(url)
            resp.raise_for_status()
            data = resp.json()
            models = [
                m.get("name", "") for m in data.get("models", []) if m.get("name")
            ]
            await self._bus.publish(ConnectionStatusEvent(connected=True))
            await self._bus.publish(ModelListEvent(models=models))
        except (httpx.HTTPError, ValueError):
            await self._bus.publish(
                ConnectionStatusEvent(
                    connected=False, detail=f"Pi non raggiungibile su {url}"
                )
            )
