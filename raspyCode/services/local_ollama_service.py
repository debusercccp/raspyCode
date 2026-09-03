"""Gestione automatica di Ollama locale sul laptop.

Ollama locale viene avviato solo quando il Raspberry Pi non e' raggiungibile.
Il servizio non usa una shell, verifica prima /api/tags e conserva il processo
avviato per terminarlo alla chiusura dell'app.
"""
from __future__ import annotations

import asyncio
import os
import shutil
from typing import Any

import httpx

from ..core.event_bus import EventBus
from ..core.events import ConnectionStatusEvent, FallbackModeEvent, ModelListEvent, StatusEvent

LOCAL_OLLAMA_HOST = "127.0.0.1"
LOCAL_OLLAMA_PORT = 11434
LOCAL_OLLAMA_URL = f"http://{LOCAL_OLLAMA_HOST}:{LOCAL_OLLAMA_PORT}"
LOCAL_OLLAMA_TIMEOUT = 2.0


class LocalOllamaService:
    """Avvia Ollama automaticamente sul laptop quando il Pi non risponde."""

    def __init__(self, bus: EventBus) -> None:
        self._bus = bus
        self._queue = bus.subscribe()
        self._process: asyncio.subprocess.Process | None = None
        self._start_lock = asyncio.Lock()

    async def run(self) -> None:
        try:
            while True:
                event = await self._queue.get()
                try:
                    if isinstance(event, ConnectionStatusEvent) and not event.connected:
                        await self.ensure_running()
                    elif isinstance(event, FallbackModeEvent) and event.active:
                        await self.ensure_running()
                    elif isinstance(event, FallbackModeEvent) and not event.active:
                        # Il Pi e' tornato disponibile: Ollama locale non serve piu'.
                        await self.stop_if_started()
                finally:
                    self._queue.task_done()
        finally:
            await self.stop_if_started()

    async def _is_available(self) -> bool:
        try:
            async with httpx.AsyncClient(timeout=LOCAL_OLLAMA_TIMEOUT) as client:
                response = await client.get(f"{LOCAL_OLLAMA_URL}/api/tags")
                response.raise_for_status()
                return True
        except (httpx.HTTPError, ValueError):
            return False

    async def ensure_running(self) -> bool:
        """Assicura che l'API locale sia disponibile, avviando `ollama serve` se necessario."""
        async with self._start_lock:
            if await self._is_available():
                await self._publish_models()
                return True

            executable = shutil.which("ollama")
            if not executable:
                await self._bus.publish(
                    StatusEvent(
                        text="Raspberry Pi non raggiungibile e Ollama non e' installato sul laptop.",
                        level="warning",
                    )
                )
                await self._bus.publish(ModelListEvent(models=[]))
                return False

            if self._process is None or self._process.returncode is not None:
                env = os.environ.copy()
                env.setdefault("OLLAMA_HOST", f"{LOCAL_OLLAMA_HOST}:{LOCAL_OLLAMA_PORT}")
                try:
                    self._process = await asyncio.create_subprocess_exec(
                        executable,
                        "serve",
                        cwd=os.getcwd(),
                        env=env,
                        stdin=asyncio.subprocess.DEVNULL,
                        stdout=asyncio.subprocess.DEVNULL,
                        stderr=asyncio.subprocess.DEVNULL,
                        start_new_session=True,
                    )
                except OSError as exc:
                    self._process = None
                    await self._bus.publish(
                        StatusEvent(text=f"Impossibile avviare Ollama locale: {exc}", level="error")
                    )
                    return False

                await self._bus.publish(
                    StatusEvent(text="Ollama locale avviato automaticamente sul laptop.", level="info")
                )

            # Attende che il server apra la porta, senza bloccare l'UI.
            for _ in range(20):
                if await self._is_available():
                    await self._publish_models()
                    return True
                await asyncio.sleep(0.25)

            await self._bus.publish(
                StatusEvent(text="Ollama locale avviato ma API non ancora disponibile.", level="warning")
            )
            await self._bus.publish(ModelListEvent(models=[]))
            return False

    async def _publish_models(self) -> None:
        try:
            async with httpx.AsyncClient(timeout=LOCAL_OLLAMA_TIMEOUT) as client:
                response = await client.get(f"{LOCAL_OLLAMA_URL}/api/tags")
                response.raise_for_status()
                data: dict[str, Any] = response.json()
            models = [m.get("name", "") for m in data.get("models", []) if m.get("name")]
        except (httpx.HTTPError, ValueError):
            models = []
        await self._bus.publish(ModelListEvent(models=models))

    async def stop_if_started(self) -> None:
        process = self._process
        self._process = None
        if process is None or process.returncode is not None:
            return
        try:
            process.terminate()
            await asyncio.wait_for(process.wait(), timeout=3.0)
        except (asyncio.TimeoutError, ProcessLookupError):
            try:
                process.kill()
                await process.wait()
            except ProcessLookupError:
                pass
