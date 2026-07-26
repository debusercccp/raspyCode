"""
LLMGatewayService: client verso Ollama (endpoint /api/chat) sul Raspberry Pi.
Il modello NON ha piu' un default hardcoded: se l'utente non ne ha scelto
uno dalle impostazioni (o via RASPY_MODEL), un messaggio utente produce uno
StatusEvent che lo dice esplicitamente invece di tentare comunque la
richiesta. Reagisce a ModelSelectedEvent e PiConfigEvent per aggiornare
modello e routing a runtime.
"""
import asyncio
import json
import uuid
from typing import Any, Dict, List, Optional

import httpx

from .event_bus import EventBus
from .events import (
    AssistantTokenEvent,
    LLMToolCallEvent,
    ModelSelectedEvent,
    PiConfigEvent,
    StatusEvent,
    ToolResultEvent,
    UserMessageEvent,
)

SYSTEM_PROMPT = (
    "Sei raspyCode, un agente locale per bioinformatica. L'utente e' 'noya'. "
    "Usa i tool biotoolkit_* per analisi su sequenze/file FASTA/FASTQ quando "
    "pertinente, e system_run_cmd solo per ispezioni di sistema innocue. "
    "Rispondi in italiano, in modo conciso e tecnico."
)

_BIOTOOLKIT_TOOL_NAMES = [
    "biotoolkit_gc_content", "biotoolkit_rev_comp", "biotoolkit_dna_to_rna",
    "biotoolkit_rna_to_prot", "biotoolkit_base_count", "biotoolkit_hamming_dist",
    "biotoolkit_orf_finder", "biotoolkit_genome_assembly", "biotoolkit_how_many_seq",
    "biotoolkit_longest_shared_seq", "biotoolkit_grep_fastx", "biotoolkit_motif_find",
    "biotoolkit_n_glyc_motif", "biotoolkit_restriction_site", "biotoolkit_fastx_sampler",
    "biotoolkit_seq_magic", "biotoolkit_blast_output", "biotoolkit_synth_seq",
    "biotoolkit_pipeline",
]

TOOL_SCHEMAS: List[Dict[str, Any]] = [
    {
        "type": "function",
        "function": {
            "name": name,
            "description": f"Esegue lo script biotoolkit '{name}' passando args come CLI.",
            "parameters": {
                "type": "object",
                "properties": {
                    "args": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "Argomenti a riga di comando per lo script.",
                    }
                },
                "required": ["args"],
            },
        },
    }
    for name in _BIOTOOLKIT_TOOL_NAMES
] + [
    {
        "type": "function",
        "function": {
            "name": "biotoolkit_run_genetic_sim",
            "description": "Esegue una simulazione genetica randomica per N generazioni.",
            "parameters": {
                "type": "object",
                "properties": {"generations": {"type": "integer"}},
                "required": ["generations"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "system_run_cmd",
            "description": "Esegue un comando di sistema in allow-list (ls, cat, df, free, uname, ecc).",
            "parameters": {
                "type": "object",
                "properties": {"command": {"type": "string"}},
                "required": ["command"],
            },
        },
    },
]


class LLMGatewayService:
    def __init__(
        self,
        bus: EventBus,
        pi_ip: str = "10.42.0.2",
        model: Optional[str] = None,
    ) -> None:
        self._bus = bus
        self._queue = bus.subscribe()
        self.pi_ip = pi_ip
        self.base_url = f"http://{pi_ip}:11434"
        self.model: Optional[str] = model
        self.history: List[Dict[str, Any]] = [{"role": "system", "content": SYSTEM_PROMPT}]
        self._pending_tool_calls: Dict[str, "asyncio.Future[ToolResultEvent]"] = {}
        self._client = httpx.AsyncClient(timeout=None)

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
                        StatusEvent(text=f"Modello selezionato: {event.model}", level="info")
                    )
                elif isinstance(event, PiConfigEvent):
                    self.pi_ip = event.pi_ip
                    self.base_url = f"http://{event.pi_ip}:11434"
                    await self._bus.publish(
                        StatusEvent(text=f"Routing aggiornato: {self.base_url}", level="info")
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
        await self._bus.publish(StatusEvent(text="Interrogazione modello...", level="info"))

        while True:
            payload = {
                "model": self.model,
                "messages": self.history,
                "tools": TOOL_SCHEMAS,
                "stream": True,
            }
            assistant_content = ""
            tool_calls: List[Dict[str, Any]] = []

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
                    StatusEvent(text=f"Errore comunicazione Ollama ({self.base_url}): {exc}", level="error")
                )
                await self._bus.publish(AssistantTokenEvent(content="", done=True))
                return

            if assistant_content:
                await self._bus.publish(AssistantTokenEvent(content="", done=True))

            if not tool_calls:
                self.history.append({"role": "assistant", "content": assistant_content})
                return

            self.history.append(
                {"role": "assistant", "content": assistant_content, "tool_calls": tool_calls}
            )

            for call in tool_calls:
                call_id = call.get("id") or str(uuid.uuid4())
                fn = call["function"]
                args = fn.get("arguments", {})
                if isinstance(args, str):
                    args = json.loads(args or "{}")

                fut: "asyncio.Future[ToolResultEvent]" = asyncio.get_running_loop().create_future()
                self._pending_tool_calls[call_id] = fut

                await self._bus.publish(
                    LLMToolCallEvent(call_id=call_id, tool_name=fn["name"], arguments=args)
                )

                result_event = await fut
                self.history.append(
                    {
                        "role": "tool",
                        "tool_call_id": call_id,
                        "content": result_event.result_output,
                    }
                )
