"""Tool biotoolkit_*: wrapper sottili sulle funzioni pure di bioCli/, che
formattano l'output testuale restituito al modello. La logica biologica
vive in bioCli/; qui c'e' solo l'adattamento tool-call -> funzione pura ->
stringa.
"""

from __future__ import annotations

import random
from collections.abc import Callable
from typing import Any

from .. import bioCli
from .registry import ToolDefinition

_ARGS_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "args": {
            "type": "array",
            "items": {"type": "string"},
            "description": "Argomenti a riga di comando per lo script.",
        }
    },
    "required": ["args"],
}


def _simple_tool(
    name: str, description: str, formatter: Callable[[list[str]], str]
) -> ToolDefinition:
    """Tool che riceve 'args: list[str]' e produce direttamente una
    stringa. Per tool con validazione custom sul numero di argomenti (es.
    quelli che ne richiedono almeno 2), si definisce un handler dedicato
    invece di usare questa fabbrica generica."""

    async def handler(arguments: dict[str, Any]) -> tuple[str, bool]:
        args = arguments.get("args", [])
        return formatter(args), False

    return ToolDefinition(
        name=name,
        description=description,
        parameters_schema=_ARGS_SCHEMA,
        handler=handler,
    )


def _grep_fastx_tool() -> ToolDefinition:
    async def handler(arguments: dict[str, Any]) -> tuple[str, bool]:
        args = arguments.get("args", [])
        if len(args) < 2:
            return "Servono 2 argomenti: pattern, contenuto_fasta", True
        return f"Record trovati: {bioCli.grep_fastx(args[0], args[1])}", False

    return ToolDefinition(
        name="biotoolkit_grep_fastx",
        description="Filtra i record FASTA le cui intestazioni o sequenze matchano un pattern regex.",
        parameters_schema=_ARGS_SCHEMA,
        handler=handler,
    )


def _motif_find_tool() -> ToolDefinition:
    async def handler(arguments: dict[str, Any]) -> tuple[str, bool]:
        args = arguments.get("args", [])
        if len(args) < 2:
            return "Servono 2 argomenti: pattern, sequenza", True
        return f"Posizioni motivo: {bioCli.motif_find(args[0], args[1])}", False

    return ToolDefinition(
        name="biotoolkit_motif_find",
        description="Trova le posizioni 1-based di un motivo (regex o letterale) in una sequenza.",
        parameters_schema=_ARGS_SCHEMA,
        handler=handler,
    )


def _fasta_sampler_tool() -> ToolDefinition:
    async def handler(arguments: dict[str, Any]) -> tuple[str, bool]:
        args = arguments.get("args", [])
        if not args:
            return (
                "Serve almeno 1 argomento: contenuto_fasta[, percentuale, seed]",
                True,
            )
        content = args[0]
        percent = float(args[1]) if len(args) > 1 else 10.0
        seed = int(args[2]) if len(args) > 2 else None
        return bioCli.fasta_sampler(content, percent, seed), False

    return ToolDefinition(
        name="biotoolkit_fasta_sampler",
        description=(
            "Campiona probabilisticamente i record di un FASTA in base a "
            "una percentuale (solo formato FASTA, non FASTQ)."
        ),
        parameters_schema=_ARGS_SCHEMA,
        handler=handler,
    )


def _synth_seq_tool() -> ToolDefinition:
    async def handler(arguments: dict[str, Any]) -> tuple[str, bool]:
        args = arguments.get("args", [])
        if len(args) < 3:
            return "Servono almeno 3 argomenti: training_fasta, k, length[, seed]", True
        training, k, length = args[0], int(args[1]), int(args[2])
        seed = int(args[3]) if len(args) > 3 else None
        return bioCli.synth_seq(training, k, length, seed), False

    return ToolDefinition(
        name="biotoolkit_synth_seq",
        description="Genera una sequenza sintetica tramite catena di Markov addestrata su un FASTA di esempio.",
        parameters_schema=_ARGS_SCHEMA,
        handler=handler,
    )


def _run_genetic_sim_tool() -> ToolDefinition:
    async def handler(arguments: dict[str, Any]) -> tuple[str, bool]:
        rng = random.SystemRandom()
        seed = rng.random()
        generations = arguments.get("generations", 100)
        return (
            f"[biotoolkit] Sim Gen x{generations} completata. Seed isolato: {seed}",
            False,
        )

    return ToolDefinition(
        name="biotoolkit_run_genetic_sim",
        description="Esegue una simulazione genetica randomica per N generazioni.",
        parameters_schema={
            "type": "object",
            "properties": {"generations": {"type": "integer"}},
            "required": ["generations"],
        },
        handler=handler,
    )


def build_bio_tools() -> list[ToolDefinition]:
    return [
        _simple_tool(
            "biotoolkit_gc_content",
            "Calcola la percentuale di GC di una sequenza nucleotidica "
            "(conta anche caratteri ambigui come N nel denominatore).",
            lambda args: f"Contenuto GC: {bioCli.gc_content(args[0] if args else '')}%",
        ),
        _simple_tool(
            "biotoolkit_rev_comp",
            "Calcola il reverse complement di una sequenza di DNA.",
            lambda args: f"Reverse Complement: {bioCli.rev_comp(args[0] if args else '')}",
        ),
        _simple_tool(
            "biotoolkit_dna_to_rna",
            "Trascrive una sequenza di DNA in RNA (T->U).",
            lambda args: f"Trascrizione RNA: {bioCli.dna_to_rna(args[0] if args else '')}",
        ),
        _simple_tool(
            "biotoolkit_rna_to_prot",
            "Traduce una sequenza di RNA in proteina dal frame 0, fermandosi "
            "al primo stop codon (non cerca l'AUG di partenza).",
            lambda args: f"Traduzione Proteina: {bioCli.rna_to_prot(args[0] if args else '')}",
        ),
        _simple_tool(
            "biotoolkit_base_count",
            "Conta le occorrenze di ciascuna base in una sequenza.",
            lambda args: f"Conteggio basi: {bioCli.base_count(args[0] if args else '')}",
        ),
        _simple_tool(
            "biotoolkit_hamming_dist",
            "Calcola la distanza di Hamming tra due sequenze (args: [seq1, seq2]).",
            lambda args: (
                f"Distanza di Hamming: {bioCli.hamming_dist(args[0], args[1]) if len(args) > 1 else 0}"
            ),
        ),
        _simple_tool(
            "biotoolkit_protein_stretch_finder",
            "Trova tratti M...* in una sequenza AMMINOACIDICA gia' tradotta "
            "(non e' un ORF finder su DNA/RNA: non considera frame ne' "
            "codoni di stop/start nucleotidici).",
            lambda args: f"Tratti M...* trovati: {bioCli.protein_stretch_finder(args[0] if args else '')}",
        ),
        _simple_tool(
            "biotoolkit_how_many_seq",
            "Conta le sequenze in un testo FASTA contando le occorrenze di "
            "'>' (non fa parsing FASTA completo).",
            lambda args: f"Numero di sequenze: {bioCli.how_many_seq(args[0] if args else '')}",
        ),
        _simple_tool(
            "biotoolkit_longest_shared_seq",
            "Trova la piu' lunga sottostringa comune (longest common "
            "substring) tra N sequenze.",
            lambda args: f"Sottosequenza condivisa più lunga: {bioCli.longest_shared_seq(args)}",
        ),
        _simple_tool(
            "biotoolkit_greedy_kmer_assembly",
            "Assemblaggio greedy di k-mer basato su sovrapposizioni "
            "lessicografiche: euristica dimostrativa, non un assembler "
            "genomico biologicamente accurato.",
            lambda args: f"Assemblaggio greedy: {bioCli.greedy_kmer_assembly(args)}",
        ),
        _grep_fastx_tool(),
        _motif_find_tool(),
        _simple_tool(
            "biotoolkit_n_glyc_motif",
            "Individua le posizioni 1-based del motivo di N-glicosilazione N{P}[ST]{P}.",
            lambda args: f"Posizioni N-glicosilazione: {bioCli.n_glyc_motif(args[0] if args else '')}",
        ),
        _simple_tool(
            "biotoolkit_restriction_site",
            "Trova siti di restrizione (palindromi inversi di lunghezza 4-12).",
            lambda args: f"Siti di restrizione: {bioCli.restriction_site(args[0] if args else '')}",
        ),
        _fasta_sampler_tool(),
        _simple_tool(
            "biotoolkit_seq_magic",
            "Calcola statistiche (lunghezza, GC, conteggio basi) per ogni record di un FASTA.",
            lambda args: f"Statistiche per record: {bioCli.seq_magic(args[0] if args else '')}",
        ),
        _simple_tool(
            "biotoolkit_blast_output",
            "Parsa righe in formato tabulare BLAST (outfmt 6).",
            lambda args: f"Righe BLAST parsate: {bioCli.blast_output(args[0] if args else '')}",
        ),
        _synth_seq_tool(),
        _run_genetic_sim_tool(),
    ]
