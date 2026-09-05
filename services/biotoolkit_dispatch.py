"""Dispatch condiviso per i tool biotoolkit_*.

Questo modulo e' la SINGOLA fonte di verita' per "che args si aspetta ogni
tool biotoolkit_* e come si chiama la funzione bioCli sottostante". Sia
`ToolExecutorService` (esecuzione locale in-process, percorso veloce) sia
`mcp_server.py` (esposizione via Model Context Protocol per client esterni)
importano `run_biotoolkit` da qui, cosi' i due percorsi non possono
divergere nel comportamento.
"""
from typing import Any

from .. import bioCli

BIOTOOLKIT_TOOL_NAMES: list[str] = [
    "biotoolkit_gc_content",
    "biotoolkit_rev_comp",
    "biotoolkit_dna_to_rna",
    "biotoolkit_rna_to_prot",
    "biotoolkit_base_count",
    "biotoolkit_hamming_dist",
    "biotoolkit_orf_finder",
    "biotoolkit_protein_stretch_finder",
    "biotoolkit_genome_assembly",
    "biotoolkit_greedy_kmer_assembly",
    "biotoolkit_how_many_seq",
    "biotoolkit_longest_shared_seq",
    "biotoolkit_grep_fastx",
    "biotoolkit_motif_find",
    "biotoolkit_n_glyc_motif",
    "biotoolkit_restriction_site",
    "biotoolkit_fastx_sampler",
    "biotoolkit_fasta_sampler",
    "biotoolkit_seq_magic",
    "biotoolkit_blast_output",
    "biotoolkit_synth_seq",
]


def run_biotoolkit(tool_name: str, args: list[Any]) -> str:
    """Esegue un tool biotoolkit_* dato il nome e gli argomenti posizionali.

    Solleva KeyError se `tool_name` non e' un tool biotoolkit_* noto: il
    chiamante (ToolExecutorService o mcp_server) decide come mappare questo
    caso sul proprio meccanismo di errore.
    """
    if tool_name == "biotoolkit_gc_content":
        return f"Contenuto GC: {bioCli.gc_content(args[0] if args else '')}%"
    if tool_name == "biotoolkit_rev_comp":
        return f"Reverse Complement: {bioCli.rev_comp(args[0] if args else '')}"
    if tool_name == "biotoolkit_dna_to_rna":
        return f"Trascrizione RNA: {bioCli.dna_to_rna(args[0] if args else '')}"
    if tool_name == "biotoolkit_rna_to_prot":
        return f"Traduzione Proteina: {bioCli.rna_to_prot(args[0] if args else '')}"
    if tool_name == "biotoolkit_base_count":
        return f"Conteggio basi: {bioCli.base_count(args[0] if args else '')}"
    if tool_name == "biotoolkit_hamming_dist":
        return f"Distanza di Hamming: {bioCli.hamming_dist(args[0], args[1]) if len(args) > 1 else 0}"
    if tool_name == "biotoolkit_orf_finder":
        return f"ORF trovati: {bioCli.orf_finder(args[0] if args else '')}"
    if tool_name == "biotoolkit_protein_stretch_finder":
        return f"Tratti M...* trovati: {bioCli.protein_stretch_finder(args[0] if args else '')}"
    if tool_name == "biotoolkit_how_many_seq":
        return f"Numero di sequenze: {bioCli.how_many_seq(args[0] if args else '')}"
    if tool_name == "biotoolkit_longest_shared_seq":
        return f"Sottosequenza condivisa più lunga: {bioCli.longest_shared_seq(args)}"
    if tool_name == "biotoolkit_genome_assembly":
        return f"Genoma assemblato: {bioCli.genome_assembly(args)}"
    if tool_name == "biotoolkit_greedy_kmer_assembly":
        return f"Assemblaggio greedy: {bioCli.greedy_kmer_assembly(args)}"
    if tool_name == "biotoolkit_grep_fastx":
        if len(args) < 2:
            raise ValueError("Servono 2 argomenti: pattern, contenuto_fasta")
        return f"Record trovati: {bioCli.grep_fastx(args[0], args[1])}"
    if tool_name == "biotoolkit_motif_find":
        if len(args) < 2:
            raise ValueError("Servono 2 argomenti: pattern, sequenza")
        return f"Posizioni motivo: {bioCli.motif_find(args[0], args[1])}"
    if tool_name == "biotoolkit_n_glyc_motif":
        return f"Posizioni N-glicosilazione: {bioCli.n_glyc_motif(args[0] if args else '')}"
    if tool_name == "biotoolkit_restriction_site":
        return f"Siti di restrizione: {bioCli.restriction_site(args[0] if args else '')}"
    if tool_name in {"biotoolkit_fastx_sampler", "biotoolkit_fasta_sampler"}:
        percent = float(args[1]) if len(args) > 1 else 100.0
        seed = int(args[2]) if len(args) > 2 else None
        return bioCli.fasta_sampler(args[0] if args else "", percent, seed)
    if tool_name == "biotoolkit_seq_magic":
        return f"Statistiche: {bioCli.seq_magic(args[0] if args else '')}"
    if tool_name == "biotoolkit_blast_output":
        return f"Righe BLAST parsate: {bioCli.blast_output(args[0] if args else '')}"
    if tool_name == "biotoolkit_synth_seq":
        if len(args) < 3:
            raise ValueError("Servono 3 argomenti: training_fasta, k, length")
        k = int(args[1])
        length = int(args[2])
        seed = int(args[3]) if len(args) > 3 else None
        return bioCli.synth_seq(args[0], k, length, seed)

    raise KeyError(f"Tool biotoolkit sconosciuto: {tool_name}")
