"""ToolExecutorService: esegue il tool-calling locale via chiamate a funzioni pure."""
import asyncio
import random
import shlex
from typing import Any

from .. import bioCli
from ..core.event_bus import EventBus
from ..core.events import LLMToolCallEvent, StatusEvent, ToolResultEvent

SYSTEM_CMD_ALLOWLIST = {
    "ls", "cat", "df", "free", "uname", "whoami", "pwd", "head", "tail", "wc",
}


class ToolExecutorService:
    def __init__(self, bus: EventBus) -> None:
        self._bus = bus
        self._queue = bus.subscribe()

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
            if event.tool_name == "biotoolkit_gc_content":
                output = f"Contenuto GC: {bioCli.gc_content(args[0] if args else '')}%"
            elif event.tool_name == "biotoolkit_rev_comp":
                output = f"Reverse Complement: {bioCli.rev_comp(args[0] if args else '')}"
            elif event.tool_name == "biotoolkit_dna_to_rna":
                output = f"Trascrizione RNA: {bioCli.dna_to_rna(args[0] if args else '')}"
            elif event.tool_name == "biotoolkit_rna_to_prot":
                output = f"Traduzione Proteina: {bioCli.rna_to_prot(args[0] if args else '')}"
            elif event.tool_name == "biotoolkit_base_count":
                output = f"Conteggio basi: {bioCli.base_count(args[0] if args else '')}"
            elif event.tool_name == "biotoolkit_hamming_dist":
                output = f"Distanza di Hamming: {bioCli.hamming_dist(args[0], args[1]) if len(args) > 1 else 0}"
            elif event.tool_name == "biotoolkit_orf_finder":
                output = f"ORF trovati: {bioCli.orf_finder(args[0] if args else '')}"
            elif event.tool_name == "biotoolkit_how_many_seq":
                output = f"Numero di sequenze: {bioCli.how_many_seq(args[0] if args else '')}"
            elif event.tool_name == "biotoolkit_longest_shared_seq":
                output = f"Sottosequenza condivisa più lunga: {bioCli.longest_shared_seq(args)}"
            elif event.tool_name == "biotoolkit_genome_assembly":
                output = f"Genoma assemblato: {bioCli.genome_assembly(args)}"
            elif event.tool_name == "biotoolkit_run_genetic_sim":
                output = self._run_genetic_sim(event.arguments)
            elif event.tool_name == "system_run_cmd":
                output, is_error = await self._run_system_cmd(event.arguments)
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
        command = arguments.get("command", "")
        try:
            parts = shlex.split(command)
        except ValueError as exc:
            return f"Comando non parsabile: {exc}", True

        if not parts or parts[0] not in SYSTEM_CMD_ALLOWLIST:
            allowlist_str = ", ".join(sorted(SYSTEM_CMD_ALLOWLIST))
            return (
                f"Comando '{parts[0] if parts else command}' non in allow-list ({allowlist_str}).",
                True,
            )

        proc = await asyncio.create_subprocess_exec(
            *parts,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, stderr = await proc.communicate()
        text = (stdout.decode(errors="replace") + stderr.decode(errors="replace")).strip()
        return text, proc.returncode != 0
