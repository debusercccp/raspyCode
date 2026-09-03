"""ToolExecutorService: esegue il tool-calling.

I tool biotoolkit_* vengono eseguiti in-process (percorso veloce, nessun
overhead di processo/IPC) tramite il dispatch condiviso in
`biotoolkit_dispatch.py` — lo stesso usato dal server MCP in
`mcp_server.py`, cosi' i due percorsi non possono divergere.

Se viene passato un `mcp_client` (MCPToolClient gia' connesso), qualunque
tool NON riconosciuto localmente (es. tool custom esposti solo da un server
MCP esterno, non presenti in bioCli) viene inoltrato li' prima di arrendersi
con "Tool non riconosciuto". Il fallback e' opzionale e best-effort: se
`mcp_client` e' None o non connesso, il comportamento e' identico a prima.
"""
import asyncio
import random
import shlex
from typing import Any

from ..core.event_bus import EventBus
from ..core.events import LLMToolCallEvent, StatusEvent, ToolResultEvent
from .biotoolkit_dispatch import BIOTOOLKIT_TOOL_NAMES, run_biotoolkit
from .mcp_client_service import MCPToolClient
from ..tools.file import write_file, read_file, list_files
from ..tools.external_bio import run_bio_cli

TOOL_TIMEOUT_SECONDS = 30.0

SYSTEM_CMD_ALLOWLIST = {
    "ls", "cat", "df", "free", "uname", "whoami", "pwd", "head", "tail", "wc",
}


class ToolExecutorService:
    def __init__(self, bus: EventBus, mcp_client: MCPToolClient | None = None) -> None:
        self._bus = bus
        self._queue = bus.subscribe()
        self._mcp_client = mcp_client

    async def run(self) -> None:
        while True:
            event = await self._queue.get()
            if isinstance(event, LLMToolCallEvent):
                await self._bus.publish(
                    StatusEvent(text=f"[TOOL RUNNING]\n{event.tool_name}...", level="info")
                )
                await self._execute(event)
            self._queue.task_done()

    async def _execute(self, event: LLMToolCallEvent) -> None:
        is_error = False
        output = ""
        args = event.arguments.get("args", [])

        try:
            if event.tool_name in BIOTOOLKIT_TOOL_NAMES:
                output = run_biotoolkit(event.tool_name, args)
            elif event.tool_name == "biotoolkit_run_genetic_sim":
                output = self._run_genetic_sim(event.arguments)
            elif event.tool_name == "file_write":
                output, is_error = await write_file(event.arguments)
            elif event.tool_name == "file_read":
                output, is_error = await read_file(event.arguments)
            elif event.tool_name == "file_list":
                output, is_error = await list_files(event.arguments)
            elif event.tool_name == "biotoolkit_samtools":
                output, is_error = await run_bio_cli("samtools", event.arguments)
            elif event.tool_name == "biotoolkit_bcftools":
                output, is_error = await run_bio_cli("bcftools", event.arguments)
            elif event.tool_name == "system_run_cmd":
                # system_run_cmd resta escluso a priori dal fallback MCP:
                # non deve mai essere raggiungibile da un client esterno,
                # solo dal routing locale con allow-list.
                output, is_error = await self._run_system_cmd(event.arguments)
            elif self._mcp_client is not None and self._mcp_client.connected:
                output, is_error = await self._mcp_client.call_tool(
                    event.tool_name, event.arguments
                )
            else:
                output = f"Tool non riconosciuto: {event.tool_name}"
                is_error = True
        except Exception as exc:
            output = f"Errore esecuzione tool '{event.tool_name}': {exc}"
            is_error = True

        await self._bus.publish(StatusEvent(text="IDLE - in attesa di query...", level="info"))
        await self._bus.publish(
            ToolResultEvent(
                call_id=event.call_id,
                tool_name=event.tool_name,
                result_output=output,
                is_error=is_error,
            )
        )

    @staticmethod
    def _run_genetic_sim(arguments: dict[str, Any]) -> str:
        rng = random.SystemRandom()
        seed = rng.random()
        generations = arguments.get("generations", 100)
        return f"[biotoolkit] Sim Gen x{generations} completata. Seed isolato: {seed}"

    @staticmethod
    async def _run_system_cmd(arguments: dict[str, Any]) -> tuple[str, bool]:
        # Mantiene il timeout configurabile dal service (e retrocompatibile
        # con TOOL_TIMEOUT_SECONDS) anche per il tool system_run_cmd, che
        # gestisce internamente kill/wait del subprocess.
        from ..tools import system as system_tools
        system_tools.SYSTEM_CMD_TIMEOUT_SECONDS = TOOL_TIMEOUT_SECONDS
        return await system_tools.run_system_cmd(arguments)
