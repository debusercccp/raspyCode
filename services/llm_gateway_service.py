"""LLMGatewayService: client verso Ollama (endpoint /api/chat).

Instrada di default verso il Raspberry Pi (pi_ip:11434). Quando
ConnectivityService segnala un FallbackModeEvent(active=True) - dopo che il
Pi e' risultato irraggiungibile per piu' healthcheck consecutivi - lo
switch avviene su Ollama in esecuzione in locale sul laptop
(127.0.0.1:11434), senza dimenticare l'IP del Pi configurato dall'utente:
al ripristino della connettivita' il routing torna automaticamente su
quest'ultimo.
"""
import asyncio
import json
import re
import uuid
from typing import Any

import httpx

from ..core.event_bus import EventBus
from ..core.events import (
    AssistantTokenEvent,
    FallbackModeEvent,
    LLMToolCallEvent,
    ModelSelectedEvent,
    PiConfigEvent,
    StatusEvent,
    ToolResultEvent,
    UserMessageEvent,
)
from ..tools import build_default_registry
from ..tools.file import write_file
from .session_service import save_session

SYSTEM_PROMPT = (
    "Sei raspyCode, un agente locale per bioinformatica. L'utente e' 'noya'. "
    "Usa i tool biotoolkit_* per analisi su sequenze/file FASTA/FASTQ quando "
    "pertinente, e system_run_cmd solo per ispezioni di sistema innocue. "
    "La working directory del processo e' il workspace dell'utente: i tool file_write, "
    "file_read e file_list operano solo li'. Quando l'utente chiede di creare, farmi, "
    "scrivere o salvare uno script/file, DEVI usare file_write per crearlo realmente "
    "nel workspace, invece di limitarti a mostrare il codice in chat. Scegli un nome "
    "di file sensato con estensione appropriata e comunica il percorso relativo creato. "
    "Rispondi in italiano, in modo conciso e tecnico."
)

# Host di Ollama in locale sul laptop, usato come fallback quando il Pi non
# e' raggiungibile.
LOCAL_OLLAMA_HOST = "127.0.0.1"
LOCAL_OLLAMA_PORT = 11434
OLLAMA_HTTP_TIMEOUT = httpx.Timeout(30.0, connect=10.0, read=120.0, write=30.0, pool=10.0)
MAX_HISTORY_MESSAGES = 50
GATEWAY_TOOL_TIMEOUT_SECONDS = 60.0

_BIOTOOLKIT_TOOL_NAMES = [
    "biotoolkit_gc_content", "biotoolkit_rev_comp", "biotoolkit_dna_to_rna",
    "biotoolkit_rna_to_prot", "biotoolkit_base_count", "biotoolkit_hamming_dist",
    "biotoolkit_orf_finder", "biotoolkit_genome_assembly", "biotoolkit_how_many_seq",
    "biotoolkit_longest_shared_seq", "biotoolkit_grep_fastx", "biotoolkit_motif_find",
    "biotoolkit_n_glyc_motif", "biotoolkit_restriction_site", "biotoolkit_fastx_sampler",
    "biotoolkit_seq_magic", "biotoolkit_blast_output", "biotoolkit_synth_seq",
    "biotoolkit_pipeline",
]

TOOL_SCHEMAS: list[dict[str, Any]] = [
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


async def build_tool_schemas(mcp_client: Any | None = None) -> list[dict[str, Any]]:
    """Costruisce la lista di schema tool da esporre al modello.

    Se `mcp_client` e' connesso, gli schema dei tool biotoolkit_* vengono
    richiesti direttamente al server MCP via `list_tools()`: cosi' la
    "verita'" su nome/descrizione/parametri di ogni tool vive in un solo
    posto (`biotoolkit_dispatch.py`, esposto dal server MCP) invece di
    essere duplicata a mano qui. Se MCP non e' disponibile (client None, non
    connesso, o list_tools() fallisce/torna vuoto) si ricade sugli schema
    statici hardcoded (TOOL_SCHEMAS) cosi' l'agente resta operativo anche
    senza server MCP in esecuzione.

    In entrambi i casi lo schema di `system_run_cmd` viene sempre aggiunto a
    parte: e' un tool "di sistema" gestito esclusivamente dal routing locale
    di ToolExecutorService e non deve mai essere esposto/eseguito via MCP.
    """
    system_cmd_schema = next(
        s for s in TOOL_SCHEMAS if s["function"]["name"] == "system_run_cmd"
    )

    if mcp_client is not None and getattr(mcp_client, "connected", False):
        try:
            mcp_schemas = await mcp_client.list_tools()
        except Exception:
            mcp_schemas = []
        if mcp_schemas:
            return mcp_schemas + [system_cmd_schema]

    return build_default_registry().ollama_schemas()


class LLMGatewayService:
    def __init__(
        self,
        bus: EventBus,
        pi_ip: str = "10.42.0.2",
        model: str | None = None,
        tool_schemas: list[dict[str, Any]] | None = None,
        initial_history: list[dict[str, Any]] | None = None,
    ) -> None:
        self._bus = bus
        self._queue = bus.subscribe()
        self.pi_ip = pi_ip
        self._local_fallback_active = False
        self.base_url = f"http://{pi_ip}:11434"
        self.model: str | None = model
        self.tool_schemas: list[dict[str, Any]] = (
            tool_schemas if tool_schemas is not None else list(TOOL_SCHEMAS)
        )
        self.history: list[dict[str, Any]] = initial_history or [{"role": "system", "content": SYSTEM_PROMPT}]
        if not self.history or self.history[0].get("role") != "system":
            self.history.insert(0, {"role": "system", "content": SYSTEM_PROMPT})
        self._pending_tool_calls: dict[str, asyncio.Future[ToolResultEvent]] = {}
        self.current_model: str | None = model
        self._client = httpx.AsyncClient(timeout=OLLAMA_HTTP_TIMEOUT, trust_env=False)

    def _save_session(self) -> None:
        try:
            save_session(history=self.history, model=self.model, pi_ip=self.pi_ip)
        except (OSError, TypeError, ValueError):
            pass

    async def run(self) -> None:
        try:
            while True:
                event = await self._queue.get()
                try:
                    await self._handle_event(event)
                except Exception as exc:
                    await self._bus.publish(
                        StatusEvent(text=f"Errore gestione evento gateway: {exc}", level="error")
                    )
                finally:
                    self._queue.task_done()
        finally:
            self._save_session()
            await self._client.aclose()

    async def _handle_event(self, event: Any) -> None:
        if isinstance(event, ModelSelectedEvent):
            previous = self.current_model
            self.current_model = event.model
            self.model = event.model
            if previous and previous != event.model:
                try:
                    await self._client.post(
                        f"{self.base_url}/api/generate",
                        json={"model": previous, "prompt": "", "keep_alive": 0},
                    )
                except Exception:
                    pass
            self._save_session()
            await self._bus.publish(StatusEvent(
                text=f"Modello selezionato: {event.model}", level="info"
            ))
        elif isinstance(event, UserMessageEvent):
            await self._on_user_message(event)
        elif isinstance(event, ToolResultEvent):
            fut = self._pending_tool_calls.pop(event.call_id, None)
            if fut and not fut.done():
                fut.set_result(event)
        elif isinstance(event, PiConfigEvent):
            await self._on_pi_config(event)
        elif isinstance(event, FallbackModeEvent):
            await self._on_fallback_mode(event)

    def _trim_history(self) -> None:
        if len(self.history) <= MAX_HISTORY_MESSAGES:
            return
        system = self.history[0] if self.history and self.history[0].get("role") == "system" else None
        rest = self.history[1:] if system else self.history
        rest = rest[-(MAX_HISTORY_MESSAGES - (1 if system else 0)):]
        self.history = ([system] if system else []) + rest

    async def _on_pi_config(self, event: PiConfigEvent) -> None:
        self.pi_ip = event.pi_ip
        if self._local_fallback_active:
            # Il fallback locale e' attivo: teniamo comunque traccia del
            # nuovo IP ma non tocchiamo il routing corrente, altrimenti
            # torneremmo a puntare a un Pi che risulta ancora irraggiungibile.
            await self._bus.publish(
                StatusEvent(
                    text=(
                        f"IP Pi aggiornato a {event.pi_ip}: verra' applicato al "
                        "ripristino della connessione (fallback locale attivo)."
                    ),
                    level="info",
                )
            )
            return
        self.base_url = f"http://{event.pi_ip}:11434"
        await self._bus.publish(
            StatusEvent(text=f"Routing aggiornato: {self.base_url}", level="info")
        )

    async def _on_fallback_mode(self, event: FallbackModeEvent) -> None:
        self._local_fallback_active = event.active
        if event.active:
            self.base_url = f"http://{LOCAL_OLLAMA_HOST}:{LOCAL_OLLAMA_PORT}"
            await self._bus.publish(
                StatusEvent(
                    text=f"Pi non raggiungibile: fallback su Ollama locale ({self.base_url}).",
                    level="warning",
                )
            )
        else:
            self.base_url = f"http://{self.pi_ip}:11434"
            await self._bus.publish(
                StatusEvent(text=f"Routing ripristinato verso il Pi: {self.base_url}", level="info")
            )

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
        self._trim_history()
        self._save_session()
        await self._converse()

    async def _auto_save_script(self, user_request: str, assistant_content: str, tool_calls: list[dict[str, Any]]) -> None:
        """Fallback: salva automaticamente uno script anche se il modello non usa file_write.

        Il percorso resta confinato alla working directory e viene creato solo quando
        la richiesta e' chiaramente di creazione/salvataggio di uno script e la risposta
        contiene un blocco di codice. Se il modello ha gia' chiamato file_write non duplica
        il file.
        """
        request = user_request.lower()
        script_words = ("script", "file", "salva", "salvare", "crea", "creare", "scrivi", "scrivere", "fammi")
        if not any(word in request for word in script_words):
            return
        if any(
            isinstance(call, dict)
            and isinstance(call.get("function"), dict)
            and call["function"].get("name") == "file_write"
            for call in tool_calls
        ):
            return
        match = re.search(r"```(?:python|py|bash|sh|shell|javascript|js|typescript|ts|json|yaml|yml|text|txt)?\s*\n?(.*?)```", assistant_content, re.IGNORECASE | re.DOTALL)
        if not match:
            return
        content = match.group(1).strip("\n")
        if not content:
            return
        filename_match = re.search(r"(?:^|\s)([A-Za-z0-9_.-]+\.(?:py|sh|bash|js|ts|json|yaml|yml|txt|md))\b", user_request, re.IGNORECASE)
        if filename_match:
            filename = filename_match.group(1)
        else:
            lang_match = re.search(r"```([A-Za-z0-9_+-]+)", assistant_content)
            lang = (lang_match.group(1).lower() if lang_match else "")
            extensions = {"python": "py", "py": "py", "bash": "sh", "sh": "sh", "shell": "sh", "javascript": "js", "js": "js", "typescript": "ts", "ts": "ts", "json": "json", "yaml": "yml", "yml": "yml", "text": "txt", "txt": "txt"}
            filename = f"script.{extensions.get(lang, 'txt')}"
        output, is_error = await write_file({"args": [filename, content]})
        if not is_error:
            await self._bus.publish(StatusEvent(text=f"Script creato automaticamente: {filename}", level="info"))
        else:
            await self._bus.publish(StatusEvent(text=f"Impossibile creare automaticamente lo script: {output}", level="error"))

    async def _converse(self) -> None:
        await self._bus.publish(StatusEvent(text="Interrogazione modello...", level="info"))

        while True:
            payload = {
                "model": self.model,
                "messages": self.history,
                "tools": self.tool_schemas,
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
                    StatusEvent(text=f"Errore comunicazione Ollama ({self.base_url}): {exc}", level="error")
                )
                await self._bus.publish(AssistantTokenEvent(content="", done=True))
                return

            if assistant_content:
                await self._bus.publish(AssistantTokenEvent(content="", done=True))

            if not tool_calls:
                user_request = next(
                    (m.get("content", "") for m in reversed(self.history) if m.get("role") == "user"),
                    "",
                )
                await self._auto_save_script(user_request, assistant_content, tool_calls)
                self.history.append({"role": "assistant", "content": assistant_content})
                self._save_session()
                return

            self.history.append(
                {"role": "assistant", "content": assistant_content, "tool_calls": tool_calls}
            )

            await self._handle_tool_calls(tool_calls)

    async def _handle_tool_calls(self, tool_calls: list[dict[str, Any]]) -> None:
        """Gestisce anche tool-call malformate e timeout dell'executor."""
        for call in tool_calls:
            call_id = call.get("id") or str(uuid.uuid4())
            fn = call.get("function")
            if not isinstance(fn, dict) or not fn.get("name"):
                content = f"Tool call malformato (id={call_id}): manca function/name."
                self.history.append({"role": "tool", "tool_call_id": call_id, "content": content})
                self._save_session()
                continue
            try:
                args = fn.get("arguments", {})
                if isinstance(args, str):
                    args = json.loads(args or "{}")
                if not isinstance(args, dict):
                    raise ValueError("arguments deve essere un oggetto JSON")
            except (json.JSONDecodeError, TypeError, ValueError) as exc:
                content = f"Tool call malformato (id={call_id}): arguments non validi ({exc})."
                self.history.append({"role": "tool", "tool_call_id": call_id, "content": content})
                self._save_session()
                continue

            fut: asyncio.Future[ToolResultEvent] = asyncio.get_running_loop().create_future()
            self._pending_tool_calls[call_id] = fut
            await self._bus.publish(
                LLMToolCallEvent(call_id=call_id, tool_name=fn["name"], arguments=args)
            )
            try:
                result_event = await asyncio.wait_for(fut, timeout=GATEWAY_TOOL_TIMEOUT_SECONDS)
                content = result_event.result_output
            except asyncio.TimeoutError:
                content = f"Timeout: il tool '{fn['name']}' non ha risposto entro {GATEWAY_TOOL_TIMEOUT_SECONDS:.0f}s."
            finally:
                self._pending_tool_calls.pop(call_id, None)
            self.history.append({"role": "tool", "tool_call_id": call_id, "content": content})
            self._save_session()
