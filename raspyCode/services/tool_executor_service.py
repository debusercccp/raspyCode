"""ToolExecutorService: esegue il tool-calling locale via chiamate a funzioni pure."""

import asyncio
import os
import random
import shlex
from pathlib import Path
from typing import Any

from .. import bioCli
from ..core.event_bus import EventBus
from ..core.events import LLMToolCallEvent, StatusEvent, ToolResultEvent

SYSTEM_CMD_ALLOWLIST = {
    "ls",
    "cat",
    "df",
    "free",
    "uname",
    "whoami",
    "pwd",
    "head",
    "tail",
    "wc",
}

# L'allow-list protegge quale BINARIO puo' girare, non quali DATI e' in
# grado di leggere: "cat" e' innocuo in astratto, ma "cat ~/.ssh/id_rsa" o
# "cat /etc/shadow" non lo sono. Limitiamo gli argomenti che sembrano path a
# questa radice, cosi' i comandi restano utilizzabili sui file del progetto
# ma non sull'intero filesystem leggibile dall'utente.
SYSTEM_CMD_ALLOWED_ROOT = Path.cwd().resolve()

# Limite alla dimensione dell'output di system_run_cmd: un comando come
# "cat" su un file enorme non deve ne' saturare la memoria ne' gonfiare a
# dismisura il prompt rispedito al modello.
MAX_OUTPUT_BYTES = 64_000

# Timeout massimo (secondi) per qualunque esecuzione di tool: sia subprocess
# (system_run_cmd) sia chiamate in-process potenzialmente lente (es. synth_seq
# su training set grandi). Evita che un singolo tool blocchi l'intero
# ToolExecutorService (e a cascata la UI) su hardware limitato come il Pi.
TOOL_TIMEOUT_SECONDS = 10.0


class ToolExecutorService:
    def __init__(self, bus: EventBus) -> None:
        self._bus = bus
        self._queue = bus.subscribe()

    async def run(self) -> None:
        while True:
            event = await self._queue.get()
            if isinstance(event, LLMToolCallEvent):
                await self._bus.publish(
                    StatusEvent(
                        text=f"[TOOL RUNNING]\n{event.tool_name}...", level="info"
                    )
                )
                await self._execute(event)
            self._queue.task_done()

    async def _execute(self, event: LLMToolCallEvent) -> None:
        is_error = False
        output = ""

        try:
            if event.tool_name == "system_run_cmd":
                # system_run_cmd gestisce il proprio timeout internamente
                # (deve poter killare il subprocess sul timeout: un
                # wait_for esterno lo cancellerebbe "da fuori" prima che
                # riesca a fare kill(), lasciando un processo orfano).
                output, is_error = await self._run_system_cmd(event.arguments)
            else:
                # Tool in-process (bioCli): nessuna risorsa OS da ripulire,
                # un wait_for esterno basta a limitare l'attesa lato bus.
                output, is_error = await asyncio.wait_for(
                    self._dispatch(event), timeout=TOOL_TIMEOUT_SECONDS
                )
        except asyncio.TimeoutError:
            output = (
                f"Timeout: il tool '{event.tool_name}' ha superato "
                f"{TOOL_TIMEOUT_SECONDS:.0f}s di esecuzione ed e' stato interrotto."
            )
            is_error = True
        except Exception as exc:
            output = f"Errore esecuzione tool '{event.tool_name}': {exc}"
            is_error = True

        await self._bus.publish(
            StatusEvent(text="IDLE - in attesa di query...", level="info")
        )
        await self._bus.publish(
            ToolResultEvent(
                call_id=event.call_id,
                tool_name=event.tool_name,
                result_output=output,
                is_error=is_error,
            )
        )

    async def _dispatch(self, event: LLMToolCallEvent) -> tuple[str, bool]:
        """Smista la chiamata al tool corrispondente. Ogni branch qui presente
        DEVE avere un tool corrispondente dichiarato in TOOL_SCHEMAS
        (llm_gateway_service.py) e viceversa: i due elenchi vanno tenuti
        allineati manualmente finche' non esiste un manifest condiviso."""
        args = event.arguments.get("args", [])

        if event.tool_name == "biotoolkit_gc_content":
            return f"Contenuto GC: {bioCli.gc_content(args[0] if args else '')}%", False
        if event.tool_name == "biotoolkit_rev_comp":
            return (
                f"Reverse Complement: {bioCli.rev_comp(args[0] if args else '')}",
                False,
            )
        if event.tool_name == "biotoolkit_dna_to_rna":
            return (
                f"Trascrizione RNA: {bioCli.dna_to_rna(args[0] if args else '')}",
                False,
            )
        if event.tool_name == "biotoolkit_rna_to_prot":
            return (
                f"Traduzione Proteina: {bioCli.rna_to_prot(args[0] if args else '')}",
                False,
            )
        if event.tool_name == "biotoolkit_base_count":
            return (
                f"Conteggio basi: {bioCli.base_count(args[0] if args else '')}",
                False,
            )
        if event.tool_name == "biotoolkit_hamming_dist":
            dist = bioCli.hamming_dist(args[0], args[1]) if len(args) > 1 else 0
            return f"Distanza di Hamming: {dist}", False
        if event.tool_name == "biotoolkit_orf_finder":
            return f"ORF trovati: {bioCli.orf_finder(args[0] if args else '')}", False
        if event.tool_name == "biotoolkit_how_many_seq":
            return (
                f"Numero di sequenze: {bioCli.how_many_seq(args[0] if args else '')}",
                False,
            )
        if event.tool_name == "biotoolkit_longest_shared_seq":
            return (
                f"Sottosequenza condivisa più lunga: {bioCli.longest_shared_seq(args)}",
                False,
            )
        if event.tool_name == "biotoolkit_genome_assembly":
            return f"Genoma assemblato: {bioCli.genome_assembly(args)}", False
        if event.tool_name == "biotoolkit_grep_fastx":
            if len(args) < 2:
                return "Servono 2 argomenti: pattern, contenuto_fasta", True
            return f"Record trovati: {bioCli.grep_fastx(args[0], args[1])}", False
        if event.tool_name == "biotoolkit_motif_find":
            if len(args) < 2:
                return "Servono 2 argomenti: pattern, sequenza", True
            return f"Posizioni motivo: {bioCli.motif_find(args[0], args[1])}", False
        if event.tool_name == "biotoolkit_n_glyc_motif":
            return (
                f"Posizioni N-glicosilazione: {bioCli.n_glyc_motif(args[0] if args else '')}",
                False,
            )
        if event.tool_name == "biotoolkit_restriction_site":
            return (
                f"Siti di restrizione: {bioCli.restriction_site(args[0] if args else '')}",
                False,
            )
        if event.tool_name == "biotoolkit_fastx_sampler":
            if not args:
                return (
                    "Serve almeno 1 argomento: contenuto_fasta[, percentuale, seed]",
                    True,
                )
            content = args[0]
            percent = float(args[1]) if len(args) > 1 else 10.0
            seed = int(args[2]) if len(args) > 2 else None
            return bioCli.fastx_sampler(content, percent, seed), False
        if event.tool_name == "biotoolkit_seq_magic":
            return (
                f"Statistiche per record: {bioCli.seq_magic(args[0] if args else '')}",
                False,
            )
        if event.tool_name == "biotoolkit_blast_output":
            return (
                f"Righe BLAST parsate: {bioCli.blast_output(args[0] if args else '')}",
                False,
            )
        if event.tool_name == "biotoolkit_synth_seq":
            if len(args) < 3:
                return (
                    "Servono almeno 3 argomenti: training_fasta, k, length[, seed]",
                    True,
                )
            training, k, length = args[0], int(args[1]), int(args[2])
            seed = int(args[3]) if len(args) > 3 else None
            return bioCli.synth_seq(training, k, length, seed), False
        if event.tool_name == "biotoolkit_run_genetic_sim":
            return self._run_genetic_sim(event.arguments), False
        # system_run_cmd e' gestito direttamente in _execute (vedi commento
        # li'), non passa da qui.

        return f"Tool non riconosciuto: {event.tool_name}", True

    @staticmethod
    def _run_genetic_sim(arguments: dict[str, Any]) -> str:
        rng = random.SystemRandom()
        seed = rng.random()
        generations = arguments.get("generations", 100)
        return f"[biotoolkit] Sim Gen x{generations} completata. Seed isolato: {seed}"

    @staticmethod
    def _is_safe_path_arg(arg: str) -> bool:
        """True se arg, interpretato come percorso, resta dentro
        SYSTEM_CMD_ALLOWED_ROOT (dopo aver espanso '~' e risolto '..'/symlink)."""
        expanded = os.path.expanduser(arg)
        candidate = Path(expanded)
        resolved = (
            candidate.resolve()
            if candidate.is_absolute()
            else (SYSTEM_CMD_ALLOWED_ROOT / candidate).resolve()
        )
        try:
            resolved.relative_to(SYSTEM_CMD_ALLOWED_ROOT)
            return True
        except ValueError:
            return False

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

        # L'allow-list limita il binario; qui limitiamo anche i dati
        # accessibili, rifiutando qualunque argomento non-flag che punti
        # fuori dalla directory di lavoro (es. '~/.ssh/id_rsa', '/etc/shadow').
        for arg in parts[1:]:
            if arg.startswith("-"):
                continue
            if not ToolExecutorService._is_safe_path_arg(arg):
                return (
                    f"Percorso '{arg}' non consentito: system_run_cmd puo' "
                    f"accedere solo a file dentro {SYSTEM_CMD_ALLOWED_ROOT}.",
                    True,
                )

        proc = await asyncio.create_subprocess_exec(
            *parts,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            cwd=str(SYSTEM_CMD_ALLOWED_ROOT),
        )
        try:
            stdout, stderr = await asyncio.wait_for(
                proc.communicate(), timeout=TOOL_TIMEOUT_SECONDS
            )
        except asyncio.TimeoutError:
            proc.kill()
            await proc.wait()
            return (
                f"Comando '{command}' interrotto: timeout di "
                f"{TOOL_TIMEOUT_SECONDS:.0f}s superato.",
                True,
            )
        text = (
            stdout.decode(errors="replace") + stderr.decode(errors="replace")
        ).strip()
        text_bytes = text.encode(errors="replace")
        if len(text_bytes) > MAX_OUTPUT_BYTES:
            text = (
                text_bytes[:MAX_OUTPUT_BYTES].decode(errors="replace")
                + f"\n... [output troncato a {MAX_OUTPUT_BYTES} byte]"
            )
        return text, proc.returncode != 0
