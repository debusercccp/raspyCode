"""LLMGatewayService: client verso Ollama (endpoint /api/chat) sul Raspberry Pi."""

import asyncio
import json
import uuid
from typing import Any

import httpx

from ..core.event_bus import EventBus
from ..core.events import (
    AssistantTokenEvent,
    LLMToolCallEvent,
    ModelSelectedEvent,
    PiConfigEvent,
    StatusEvent,
    ToolResultEvent,
    UserMessageEvent,
)
from ..tools import build_default_registry

SYSTEM_PROMPT = (
    "Sei raspyCode, un agente locale per bioinformatica. L'utente e' 'noya'. "
    "Usa i tool biotoolkit_* per analisi su sequenze/file FASTA/FASTQ quando "
    "pertinente, e system_run_cmd solo per ispezioni di sistema innocue. "
    "Rispondi in italiano, in modo conciso e tecnico."
)

# Margine di sicurezza sull'attesa del risultato di un tool: ToolExecutorService
# applica gia' un proprio timeout (10s per i tool bio in-process, 15s per
# system_run_cmd - vedi raspyCode/tools/) e pubblica SEMPRE un ToolResultEvent
# (successo o errore). Questo timeout qui e' una rete di sicurezza per il
# caso in cui l'executor non risponda affatto (crash, cancellazione, tool_name
# non riconosciuto che pero' non pubblica - scenario che oggi non si verifica
# ma che non va assunto per sempre vero): senza, il Gateway resterebbe
# bloccato su `await fut` per sempre. Tenuto sopra il piu' lento dei timeout
# lato executor (15s) per lasciare margine anche nel caso peggiore.
GATEWAY_TOOL_TIMEOUT_SECONDS = 20.0

# httpx.AsyncClient(timeout=None) e' timeout infinito: se Ollama si blocca
# o smette di rispondere a meta' streaming, il Gateway resta appeso per
# sempre. `read` resta generoso perche' l'inferenza su Pi puo' essere lenta,
# ma non deve essere illimitato.
OLLAMA_HTTP_TIMEOUT = httpx.Timeout(connect=5.0, read=300.0, write=10.0, pool=10.0)

# Limite alla history della conversazione: senza, cresce per sempre e il
# prompt inviato a ogni turno diventa via via piu' grande (piu' lento, piu'
# RAM, rischio di superare il context window del modello). Il messaggio di
# sistema viene sempre preservato; si trimma solo il resto.
MAX_HISTORY_MESSAGES = 24

_DEFAULT_REGISTRY = build_default_registry()

# Derivato dal ToolRegistry condiviso (raspyCode.tools), la stessa fonte di
# verita' usata da ToolExecutorService per l'esecuzione: prima queste erano
# due liste separate (questa qui e gli if/elif dell'Executor) tenute
# allineate manualmente, con il rischio di dichiarare al modello un tool che
# l'Executor non sapeva eseguire (o viceversa).
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
        self.history: list[dict[str, Any]] = [
            {"role": "system", "content": SYSTEM_PROMPT}
        ]
        self._pending_tool_calls: dict[str, asyncio.Future[ToolResultEvent]] = {}
        self._client = httpx.AsyncClient(timeout=OLLAMA_HTTP_TIMEOUT)

    def _trim_history(self) -> None:
        """Limita la history a MAX_HISTORY_MESSAGES messaggi, preservando
        sempre il/i messaggio/i di sistema. Chiamato solo all'inizio di un
        nuovo turno (_converse()), mai a meta' di una sequenza di tool call:
        troncare tra un messaggio assistant con tool_calls e i corrispondenti
        messaggi tool romperebbe la struttura attesa dal protocollo chat."""
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
                if isinstance(event, UserMessageEvent):
                    await self._on_user_message(event)
                elif isinstance(event, ToolResultEvent):
                    fut = self._pending_tool_calls.pop(event.call_id, None)
                    if fut and not fut.done():
                        fut.set_result(event)
                elif isinstance(event, ModelSelectedEvent):
                    self.model = event.model
                    await self._bus.publish(
                        StatusEvent(
                            text=f"Modello selezionato: {event.model}", level="info"
                        )
                    )
                elif isinstance(event, PiConfigEvent):
                    self.pi_ip = event.pi_ip
                    self.base_url = f"http://{event.pi_ip}:11434"
                    await self._bus.publish(
                        StatusEvent(
                            text=f"Routing aggiornato: {self.base_url}", level="info"
                        )
                    )
                self._queue.task_done()
        finally:
            await self._client.aclose()

    async def _on_user_message(self, event: UserMessageEvent) -> None:
        if not self.model:
            await self._bus.publish(
                StatusEvent(
                    text="Nessun modello selezionato. Apri le impostazioni (Ctrl+S) per sceglierne uno.",
                    level="warning",
                )
            )
            return
        self.history.append({"role": "user", "content": event.content})
        await self._converse()

    async def _converse(self) -> None:
        await self._bus.publish(
            StatusEvent(text="Interrogazione modello...", level="info")
        )
        self._trim_history()

        while True:
            payload = {
                "model": self.model,
                "messages": self.history,
                "tools": TOOL_SCHEMAS,
                "stream": True,
            }
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
        """Esegue ogni tool call pubblicando LLMToolCallEvent e attendendo il
        ToolResultEvent corrispondente, poi appende il risultato a self.history.

        Isolato da _converse() per essere testabile senza dover mockare lo
        streaming HTTP verso Ollama: basta costruire una lista di tool_calls
        e un EventBus (reale o con un finto ToolExecutor collegato).
        """
        for call in tool_calls:
            call_id = call.get("id") or str(uuid.uuid4())

            # Parsing difensivo: una risposta malformata dal modello (JSON
            # non valido negli argomenti, 'function' mancante, ecc.) non
            # deve propagare un'eccezione non gestita che ucciderebbe
            # silenziosamente l'intero _converse()/run() del Gateway.
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
                # Va rimosso sempre: se non arriva mai un ToolResultEvent per
                # questo call_id, un entry orfano in _pending_tool_calls
                # resterebbe in memoria per sempre.
                self._pending_tool_calls.pop(call_id, None)

            self.history.append(
                {
                    "role": "tool",
                    "tool_call_id": call_id,
                    "content": tool_output,
                }
            )
