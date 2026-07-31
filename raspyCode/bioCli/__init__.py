"""Inizializzazione del pacchetto bioCli: esposizione delle funzioni pure."""

from .assembly import (
    greedy_kmer_assembly,
    how_many_seq,
    longest_shared_seq,
    protein_stretch_finder,
)
from .io_utils import blast_output, fasta_sampler, seq_magic
from .search import grep_fastx, motif_find, n_glyc_motif, restriction_site
from .sequence import (
    base_count,
    dna_to_rna,
    gc_content,
    hamming_dist,
    rev_comp,
    rna_to_prot,
)
from .synthesis import synth_seq

__all__ = [
    "base_count",
    "blast_output",
    "dna_to_rna",
    "fasta_sampler",
    "gc_content",
    "greedy_kmer_assembly",
    "grep_fastx",
    "hamming_dist",
    "how_many_seq",
    "longest_shared_seq",
    "motif_find",
    "n_glyc_motif",
    "protein_stretch_finder",
    "restriction_site",
    "rev_comp",
    "rna_to_prot",
    "seq_magic",
    "synth_seq",
]
