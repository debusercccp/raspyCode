"""ConnectivityService: healthcheck periodico verso Ollama sul Raspberry Pi,
con fallback automatico su Ollama locale (127.0.0.1) se il Pi non risponde."""
import asyncio

import httpx

from ..core.event_bus import EventBus
from ..core.events import (
    BackendSourceEvent,
    ConnectionStatusEvent,
    ModelListEvent,
    PiConfigEvent,
)

CHECK_INTERVAL_SECONDS = 5.0
TIMEOUT_SECONDS = 2.0


class ConnectivityService:
    def __init__(self, bus: EventBus, pi_ip: str, local_ip: str = "127.0.0.1") -> None:
        self._bus = bus
        self._queue = bus.subscribe()
        self._pi_ip = pi_ip
        self._local_ip = local_ip

    async def run(self) -> None:
        watch_task = asyncio.create_task(self._watch_config())

        try:
            async with httpx.AsyncClient(timeout=TIMEOUT_SECONDS) as client:
                while True:
                    await self._check_once(client)
                    await asyncio.sleep(CHECK_INTERVAL_SECONDS)
        finally:
            watch_task.cancel()
            try:
                await watch_task
            except asyncio.CancelledError:
                pass

    async def _watch_config(self) -> None:
        while True:
            event = await self._queue.get()
            if isinstance(event, PiConfigEvent):
                self._pi_ip = event.pi_ip
            self._queue.task_done()

    async def _fetch_models(self, client: httpx.AsyncClient, host: str) -> list[str] | None:
        """Ritorna la lista modelli se `host:11434` risponde, altrimenti None."""
        url = f"http://{host}:11434/api/tags"
        try:
            resp = await client.get(url)
            resp.raise_for_status()
            data = resp.json()
            return [m.get("name", "") for m in data.get("models", []) if m.get("name")]
        except (httpx.HTTPError, ValueError):
            return None

    async def _check_once(self, client: httpx.AsyncClient) -> None:
        # 1. Prova il Raspberry Pi
        models = await self._fetch_models(client, self._pi_ip)
        if models is not None:
            await self._bus.publish(ConnectionStatusEvent(connected=True))
            await self._bus.publish(BackendSourceEvent(host=self._pi_ip, is_local=False))
            await self._bus.publish(ModelListEvent(models=models))
            return

        # 2. Fallback su Ollama locale
        local_models = await self._fetch_models(client, self._local_ip)
        if local_models is not None:
            await self._bus.publish(
                ConnectionStatusEvent(
                    connected=False,
                    detail=f"Pi non raggiungibile su {self._pi_ip}, uso Ollama locale",
                )
            )
            await self._bus.publish(BackendSourceEvent(host=self._local_ip, is_local=True))
            await self._bus.publish(ModelListEvent(models=local_models))
            return

        # 3. Nessuno dei due risponde
        await self._bus.publish(
            ConnectionStatusEvent(
                connected=False,
                detail=f"Ne' il Pi ({self._pi_ip}) ne' Ollama locale ({self._local_ip}) sono raggiungibili",
            )
        )
        await self._bus.publish(ModelListEvent(models=[]))
