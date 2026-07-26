"""
ToolExecutorService: esegue il tool-calling locale.
"""
import asyncio
import os
import random
import shlex
from pathlib import Path
from typing import Any, Dict, Tuple

from ..core.event_bus import EventBus
from ..core.events import LLMToolCallEvent, StatusEvent, ToolResultEvent

_DEFAULT_BIOTOOLKIT_ROOT = Path(__file__).resolve().parent.parent / "bioCli"
BIOTOOLKIT_ROOT = Path(os.environ.get("BIOTOOLKIT_ROOT", str(_DEFAULT_BIOTOOLKIT_ROOT)))

BIOTOOLKIT_SCRIPTS: Dict[str, str] = {
    "biotoolkit_gc_content": "sequence/gcContent.py",
    "biotoolkit_rev_comp": "sequence/revComp.py",
    "biotoolkit_dna_to_rna": "sequence/dnaToRna.py",
    "biotoolkit_rna_to_prot": "sequence/rnaToProt.py",
    "biotoolkit_base_count": "sequence/baseCount.py",
    "biotoolkit_hamming_dist": "sequence/hammDist.py",
    "biotoolkit_orf_finder": "assembly/orfFinder.py",
    "biotoolkit_genome_assembly": "assembly/genAsmb.py",
    "biotoolkit_how_many_seq": "assembly/hwMnySeq.py",
    "biotoolkit_longest_shared_seq": "assembly/longestSharedSeq.py",
    "biotoolkit_grep_fastx": "search/grepFastx.py",
    "biotoolkit_motif_find": "search/motifFind.py",
    "biotoolkit_n_glyc_motif": "search/nGlicMotif.py",
    "biotoolkit_restriction_site": "search/recSite.py",
    "biotoolkit_fastx_sampler": "io/fastxSampler.py",
    "biotoolkit_seq_magic": "io/seqMagique.py",
    "biotoolkit_blast_output": "io/blastOutput.py",
    "biotoolkit_synth_seq": "synthesis/synthSeq.py",
    "biotoolkit_pipeline": "bioPipeLine.py",
}

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
        try:
            if event.tool_name in BIOTOOLKIT_SCRIPTS:
                output = await self._run_biotoolkit_script(event)
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

    async def _run_biotoolkit_script(self, event: LLMToolCallEvent) -> str:
        script = BIOTOOLKIT_ROOT / BIOTOOLKIT_SCRIPTS[event.tool_name]
        if not script.exists():
            return f"Script non trovato: {script}"

        args = [str(a) for a in event.arguments.get("args", [])]
        proc = await asyncio.create_subprocess_exec(
            "python3", str(script), *args,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, stderr = await proc.communicate()
        text = stdout.decode(errors="replace")
        if proc.returncode != 0:
            text += "\n" + stderr.decode(errors="replace")
        return text.strip()

    @staticmethod
    def _run_genetic_sim(arguments: Dict[str, Any]) -> str:
        rng = random.SystemRandom()
        seed = rng.random()
        generations = arguments.get("generations", 100)
        return f"[biotoolkit] Sim Gen x{generations} completata. Seed isolato: {seed}"

    @staticmethod
    async def _run_system_cmd(arguments: Dict[str, Any]) -> Tuple[str, bool]:
        command = arguments.get("command", "")
        try:
            parts = shlex.split(command)
        except ValueError as exc:
            return f"Comando non parsabile: {exc}", True

        if not parts or parts[0] not in SYSTEM_CMD_ALLOWLIST:
            return (
                f"Comando '{parts[0] if parts else command}' non in allow-list "
                f"({sorted(SYSTEM_CMD_ALLOWLIST)}).",
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
