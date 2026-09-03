"""ConnectivityService: healthcheck periodico verso Ollama sul Raspberry Pi.

Oltre al semplice ConnectionStatusEvent (stato "grezzo" di ogni singolo
healthcheck, usato dalla status bar per "Pi collegato/non collegato"), tiene
un contatore di fallimenti/successi consecutivi e pubblica un
FallbackModeEvent debounced quando il Pi risulta irraggiungibile per piu'
healthcheck di fila: LLMGatewayService lo intercetta e instrada le richieste
verso Ollama in locale (127.0.0.1:11434) finche' il Pi non torna stabilmente
raggiungibile.

Quando il fallback e' attivo, ModelListEvent viene popolato interrogando
Ollama in locale (invece che il Pi): altrimenti la SettingsScreen resterebbe
vuota — nessun modello selezionabile — anche se in locale ce ne sono di
disponibili, perche' il Pi (unica fonte di ModelListEvent finora) e'
irraggiungibile.
"""
import asyncio

import httpx

from ..core.event_bus import EventBus
from ..core.events import (
    ConnectionStatusEvent,
    FallbackModeEvent,
    ModelListEvent,
    PiConfigEvent,
)

CHECK_INTERVAL_SECONDS = 5.0
TIMEOUT_SECONDS = 2.0

# Debounce: quanti healthcheck falliti/riusciti consecutivi servono prima di
# cambiare stato di fallback. Evita che un singolo pacchetto perso o un
# breve flicker del link Ethernet triggerino inutilmente lo switch.
FAILURE_THRESHOLD = 3
RECOVERY_THRESHOLD = 2

# Host/porta di Ollama in locale sul laptop, stessi usati da
# LLMGatewayService per il fallback (services/llm_gateway_service.py).
LOCAL_OLLAMA_HOST = "127.0.0.1"
LOCAL_OLLAMA_PORT = 11434


class ConnectivityService:
    def __init__(self, bus: EventBus, pi_ip: str) -> None:
        self._bus = bus
        self._queue = bus.subscribe()
        self._pi_ip = pi_ip
        self._consecutive_failures = 0
        self._consecutive_successes = 0
        self._fallback_active = False

    async def run(self) -> None:
        watch_task = asyncio.create_task(self._watch_config())
        try:
            async with httpx.AsyncClient(timeout=TIMEOUT_SECONDS) as client:
                while True:
                    await self._check_once(client)
                    await asyncio.sleep(CHECK_INTERVAL_SECONDS)
        finally:
            watch_task.cancel()
            await asyncio.gather(watch_task, return_exceptions=True)

    async def _watch_config(self) -> None:
        while True:
            event = await self._queue.get()
            if isinstance(event, PiConfigEvent):
                self._pi_ip = event.pi_ip
                # Un nuovo IP impostato manualmente riparte da zero col
                # debounce: merita la possibilita' di dimostrarsi
                # raggiungibile prima di essere giudicato.
                self._consecutive_failures = 0
                self._consecutive_successes = 0
            self._queue.task_done()

    async def _check_once(self, client: httpx.AsyncClient) -> None:
        url = f"http://{self._pi_ip}:11434/api/tags"
        try:
            resp = await client.get(url)
            resp.raise_for_status()
            data = resp.json()
            models = [m.get("name", "") for m in data.get("models", []) if m.get("name")]
            await self._bus.publish(ConnectionStatusEvent(connected=True))
            await self._on_check_success()
            if not self._fallback_active:
                # Se siamo appena rientrati dal fallback (_on_check_success
                # lo ha appena disattivato), i modelli del Pi tornano ad
                # essere la fonte valida per la SettingsScreen.
                await self._bus.publish(ModelListEvent(models=models))
        except (httpx.HTTPError, ValueError):
            await self._bus.publish(
                ConnectionStatusEvent(connected=False, detail=f"Pi non raggiungibile su {url}")
            )
            await self._on_check_failure()

        if self._fallback_active:
            await self._publish_local_models(client)

    async def _publish_local_models(self, client: httpx.AsyncClient) -> None:
        """Interroga Ollama in locale (fallback) e pubblica i suoi modelli.

        Best-effort: se anche Ollama locale non risponde, pubblica una
        lista vuota cosi' la SettingsScreen mostra il messaggio "nessun
        modello disponibile" invece di restare bloccata sull'ultima lista
        del Pi (che a questo punto non e' piu' raggiungibile).
        """
        url = f"http://{LOCAL_OLLAMA_HOST}:{LOCAL_OLLAMA_PORT}/api/tags"
        try:
            resp = await client.get(url)
            resp.raise_for_status()
            data = resp.json()
            models = [m.get("name", "") for m in data.get("models", []) if m.get("name")]
        except (httpx.HTTPError, ValueError):
            models = []
        await self._bus.publish(ModelListEvent(models=models))

    async def _on_check_failure(self) -> None:
        self._consecutive_successes = 0
        self._consecutive_failures += 1
        if not self._fallback_active and self._consecutive_failures >= FAILURE_THRESHOLD:
            self._fallback_active = True
            await self._bus.publish(
                FallbackModeEvent(
                    active=True,
                    detail=(
                        f"Pi irraggiungibile per {self._consecutive_failures} healthcheck "
                        "consecutivi: fallback su Ollama locale (127.0.0.1:11434)."
                    ),
                )
            )

    async def _on_check_success(self) -> None:
        self._consecutive_failures = 0
        self._consecutive_successes += 1
        if self._fallback_active and self._consecutive_successes >= RECOVERY_THRESHOLD:
            self._fallback_active = False
            await self._bus.publish(
                FallbackModeEvent(
                    active=False,
                    detail="Pi di nuovo raggiungibile: routing ripristinato verso il Pi.",
                )
            )
