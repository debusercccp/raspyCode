"""Inizializzazione del pacchetto bioCli: esposizione delle funzioni pure."""

from .sequence import gc_content, rev_comp, dna_to_rna, rna_to_prot, base_count, hamming_dist
from .assembly import orf_finder, how_many_seq, longest_shared_seq, genome_assembly
from .search import motif_find, n_glyc_motif, restriction_site, grep_fastx
from .io_utils import seq_magic, fastx_sampler, blast_output
from .synthesis import synth_seq

__all__ = [
    "gc_content",
    "rev_comp",
    "dna_to_rna",
    "rna_to_prot",
    "base_count",
    "hamming_dist",
    "orf_finder",
    "how_many_seq",
    "longest_shared_seq",
    "genome_assembly",
    "motif_find",
    "n_glyc_motif",
    "restriction_site",
    "grep_fastx",
    "seq_magic",
    "fastx_sampler",
    "blast_output",
    "synth_seq",
]
