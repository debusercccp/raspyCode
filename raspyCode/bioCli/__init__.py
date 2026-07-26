"""Inizializzazione del pacchetto bioCli: esposizione delle funzioni pure."""

from .assembly import genome_assembly, how_many_seq, longest_shared_seq, orf_finder
from .io_utils import blast_output, fastx_sampler, seq_magic
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
    "fastx_sampler",
    "gc_content",
    "genome_assembly",
    "grep_fastx",
    "hamming_dist",
    "how_many_seq",
    "longest_shared_seq",
    "motif_find",
    "n_glyc_motif",
    "orf_finder",
    "restriction_site",
    "rev_comp",
    "rna_to_prot",
    "seq_magic",
    "synth_seq",
]
