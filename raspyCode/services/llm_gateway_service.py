"""LLMGatewayService: client verso Ollama (endpoint /api/chat) sul Raspberry Pi."""

import asyncio
import json
import uuid
from typing import Any

import httpx

from ..core.event_bus import EventBus
from ..core.events import (
    AssistantTokenEvent,
    BackendSourceEvent,
    ClearHistoryEvent,
    EnrichedChatEvent,
    LLMToolCallEvent,
    ModelSelectedEvent,
    PiConfigEvent,
    StatusEvent,
    ToolResultEvent,
    UserMessageEvent,
)
from ..tools import build_default_registry

SYSTEM_PROMPT = (
    "Sei raspyCode, l'assistente personale di 'noya', in esecuzione in locale "
    "su un Raspberry Pi. Sei il suo assistente per qualsiasi cosa: rispondi a "
    "domande di ogni genere (quotidiane, di studio, organizzative, tecniche, "
    "generiche) esattamente come farebbe un assistente generalista. "
    "Oltre a questo, hai una specializzazione approfondita in bioinformatica: "
    "quando la richiesta riguarda sequenze, file FASTA/FASTQ o analisi "
    "biologiche, usa i tool biotoolkit_* disponibili; usa system_run_cmd solo "
    "per ispezioni di sistema innocue. "
    "IMPORTANTE: la specializzazione in bioinformatica è un'aggiunta alle tue "
    "capacità, non un limite. Non rifiutare mai una richiesta solo perché non "
    "riguarda la bioinformatica: rispondi comunque nel modo più utile "
    "possibile, usando le tue conoscenze generali quando i tool non sono "
    "pertinenti. Se ricevi un contesto RAG recuperato da documenti locali, "
    "usalo per rispondere in modo più preciso, ma se il contesto è vuoto o "
    "irrilevante rispondi comunque basandoti su ciò che sai. "
    "Rispondi in italiano, in modo discorsivo per le domande generiche e "
    "conciso e tecnico quando si parla di scienza o bioinformatica."
)

GATEWAY_TOOL_TIMEOUT_SECONDS = 1790.0
OLLAMA_HTTP_TIMEOUT = httpx.Timeout(connect=10.0, read=1800.0, write=10.0, pool=10.0)
MAX_HISTORY_MESSAGES = 24
_DEFAULT_REGISTRY = build_default_registry()
TOOL_SCHEMAS: list[dict[str, Any]] = _DEFAULT_REGISTRY.ollama_schemas()


class LLMGatewayService:
    def __init__(
        self,
        bus: EventBus,
        pi_ip: str = "10.42.0.2",
        model: str | None = None,
    ) -> None:
        self._bus = bus
        self._queue = bus.subscribe()
        self.pi_ip = pi_ip
        self.base_url = f"http://{pi_ip}:11434"
        self.model: str | None = model
        # current_model rispecchia self.model ed e' usato dal branch
        # ModelSelectedEvent per sapere se serve scaricare (keep_alive=0)
        # il modello precedentemente caricato prima di attivarne uno nuovo.
        self.current_model: str | None = model
        self.history: list[dict[str, Any]] = [
            {"role": "system", "content": SYSTEM_PROMPT}
        ]
        self._pending_tool_calls: dict[str, asyncio.Future[ToolResultEvent]] = {}
        self._client = httpx.AsyncClient(timeout=OLLAMA_HTTP_TIMEOUT)

    def _trim_history(self) -> None:
        if len(self.history) <= MAX_HISTORY_MESSAGES:
            return
        system_msgs = [m for m in self.history if m.get("role") == "system"]
        other_msgs = [m for m in self.history if m.get("role") != "system"]
        keep = max(MAX_HISTORY_MESSAGES - len(system_msgs), 0)
        self.history = system_msgs + other_msgs[-keep:]

    async def run(self) -> None:
        try:
            while True:
                event = await self._queue.get()
                try:
                    await self._handle_event(event)
                except Exception as exc:
                    # Un bug in un singolo branch non deve piu' uccidere in
                    # silenzio l'intero task run(): logghiamo e continuiamo
                    # a drenare il bus invece di lasciar morire il gateway
                    # (regressione che ha causato la sparizione permanente
                    # di "Interrogazione modello..." dopo la selezione di
                    # un modello).
                    await self._bus.publish(
                        StatusEvent(
                            text=f"Errore interno nel gateway LLM: {exc}",
                            level="error",
                        )
                    )
                self._queue.task_done()
        finally:
            await self._client.aclose()

    async def _handle_event(self, event: Any) -> None:
        if isinstance(event, UserMessageEvent):
            await self._on_user_message(event)
        elif isinstance(event, EnrichedChatEvent):
            await self._on_enriched_chat(event)
        elif isinstance(event, ToolResultEvent):
            fut = self._pending_tool_calls.pop(event.call_id, None)
            if fut and not fut.done():
                fut.set_result(event)
        elif isinstance(event, ModelSelectedEvent):
            # 1. Se c'era un modello attivo, forziamo lo scaricamento prima di cambiare
            if self.current_model and self.current_model != event.model:
                await self._bus.publish(
                    StatusEvent(
                        text=f"Scaricamento modello precedente ({self.current_model})...",
                        level="info",
                    )
                )
                try:
                    # Mandiamo una richiesta vuota con keep_alive=0 per liberare la RAM
                    async with httpx.AsyncClient() as client:
                        await client.post(
                            f"{self.base_url}/api/chat",
                            json={
                                "model": self.current_model,
                                "messages": [],
                                "keep_alive": 0,
                            },
                            timeout=5.0,
                        )
                except Exception as exc:
                    # Loggiamo l'errore in modalità silente per non bloccare il caricamento del successivo
                    print(f"Errore durante l'unload: {exc}")

            # 2. Impostiamo il nuovo modello attivo (sia current_model,
            # usato per il tracking dell'unload, sia model, che e'
            # l'unico campo letto da _on_user_message/_converse)
            self.current_model = event.model
            self.model = event.model
            await self._bus.publish(
                StatusEvent(text=f"Modello impostato su: {event.model}", level="info")
            )
        elif isinstance(event, ClearHistoryEvent):
            self.history = [{"role": "system", "content": SYSTEM_PROMPT}]
            await self._bus.publish(
                StatusEvent(text="Cronologia chat e contesto svuotati.", level="info")
            )
        elif isinstance(event, BackendSourceEvent):
                    if self.pi_ip != event.host:
                        self.pi_ip = event.host
                        self.base_url = f"http://{event.host}:11434"
                        label = "Ollama locale" if event.is_local else f"Raspberry Pi ({event.host})"
                        await self._bus.publish(
                            StatusEvent(text=f"Backend attivo: {label}", level="info")
                        )
        elif isinstance(event, PiConfigEvent):
            self.pi_ip = event.pi_ip
            self.base_url = f"http://{event.pi_ip}:11434"
            await self._bus.publish(
                StatusEvent(text=f"Routing aggiornato: {self.base_url}", level="info")
            )

    async def _on_user_message(self, event: UserMessageEvent) -> None:
        await self._start_conversation_turn(event.content)

    async def _on_enriched_chat(self, event: EnrichedChatEvent) -> None:
        # Prodotto da RAGService: e' il prompt originale dell'utente
        # arricchito col contesto recuperato da SQLite (o, in caso di
        # fallback, il solo prompt originale se il recupero fallisce).
        await self._start_conversation_turn(event.prompt)

    async def _start_conversation_turn(self, content: str) -> None:
        if not self.model:
            await self._bus.publish(
                StatusEvent(
                    text="Nessun modello selezionato. Apri le impostazioni (Ctrl+S) per sceglierne uno.",
                    level="warning",
                )
            )
            return
        self.history.append({"role": "user", "content": content})
        await self._converse()

    async def _converse(self) -> None:
        await self._bus.publish(
            StatusEvent(text="Interrogazione modello...", level="info")
        )
        self._trim_history()
        enable_tools = True

        while True:
            payload = {
                "model": self.model,
                "messages": self.history,
                "stream": True,
            }
            if enable_tools:
                payload["tools"] = TOOL_SCHEMAS

            assistant_content = ""
            tool_calls: list[dict[str, Any]] = []
            try:
                async with self._client.stream(
                    "POST", f"{self.base_url}/api/chat", json=payload
                ) as resp:
                    resp.raise_for_status()
                    async for line in resp.aiter_lines():
                        if not line:
                            continue
                        chunk = json.loads(line)
                        message = chunk.get("message", {})
                        token = message.get("content", "")
                        if token:
                            assistant_content += token
                            await self._bus.publish(AssistantTokenEvent(content=token))
                        if message.get("tool_calls"):
                            tool_calls.extend(message["tool_calls"])
                        if chunk.get("done"):
                            break
            except httpx.HTTPStatusError as exc:
                # Se Ollama risponde 400 ed erano presenti i tool nel payload,
                # il modello (es. smollm2) non supporta le API di Tool Calling.
                # Disabilitiamo i tool e riproviamo subito in modalità solo testo.
                if exc.response.status_code == 400 and enable_tools:
                    await self._bus.publish(
                        StatusEvent(
                            text=f"Modello '{self.model}' senza tool-calling: fallback in modalità solo testo.",
                            level="warning",
                        )
                    )
                    enable_tools = False
                    continue

                msg = f"Errore comunicazione Ollama ({self.base_url}): {exc}"
                await self._bus.publish(StatusEvent(text=msg, level="error"))
                await self._bus.publish(AssistantTokenEvent(content="", done=True))
                return
            except httpx.HTTPError as exc:
                await self._bus.publish(
                    StatusEvent(
                        text=f"Errore comunicazione Ollama ({self.base_url}): {exc}",
                        level="error",
                    )
                )
                await self._bus.publish(AssistantTokenEvent(content="", done=True))
                return

            if assistant_content:
                await self._bus.publish(AssistantTokenEvent(content="", done=True))
            if not tool_calls:
                self.history.append({"role": "assistant", "content": assistant_content})
                return
            self.history.append(
                {
                    "role": "assistant",
                    "content": assistant_content,
                    "tool_calls": tool_calls,
                }
            )
            await self._handle_tool_calls(tool_calls)

    async def _handle_tool_calls(self, tool_calls: list[dict[str, Any]]) -> None:
        for call in tool_calls:
            call_id = call.get("id") or str(uuid.uuid4())
            try:
                fn = call["function"]
                tool_name = fn["name"]
                args = fn.get("arguments", {})
                if isinstance(args, str):
                    args = json.loads(args or "{}")
            except (KeyError, TypeError, json.JSONDecodeError) as exc:
                self.history.append(
                    {
                        "role": "tool",
                        "tool_call_id": call_id,
                        "content": f"Tool call malformato dal modello, ignorato: {exc}",
                    }
                )
                await self._bus.publish(
                    StatusEvent(
                        text=f"Tool call malformato ignorato: {exc}", level="warning"
                    )
                )
                continue
            fut: asyncio.Future[ToolResultEvent] = (
                asyncio.get_running_loop().create_future()
            )
            self._pending_tool_calls[call_id] = fut
            try:
                await self._bus.publish(
                    LLMToolCallEvent(
                        call_id=call_id, tool_name=tool_name, arguments=args
                    )
                )
                result_event = await asyncio.wait_for(
                    fut, timeout=GATEWAY_TOOL_TIMEOUT_SECONDS
                )
                tool_output = result_event.result_output
            except asyncio.TimeoutError:
                tool_output = (
                    f"Timeout: nessuna risposta dal Tool Executor per "
                    f"'{tool_name}' entro {GATEWAY_TOOL_TIMEOUT_SECONDS:.0f}s."
                )
            finally:
                self._pending_tool_calls.pop(call_id, None)
            self.history.append(
                {
                    "role": "tool",
                    "tool_call_id": call_id,
                    "content": tool_output,
                }
            )
