"""Funzioni per l'assemblaggio di genomi e l'ispezione di ORF."""

import re

_ORF_REGEX = re.compile(r"M[A-Z]*?\*")


def orf_finder(aa_seq: str) -> list[str]:
    """Trova tutte le Open Reading Frames (ORF) in una sequenza amminoacidica."""
    return _ORF_REGEX.findall(aa_seq.upper())


def how_many_seq(fasta_content: str) -> int:
    """Conta quante sequenze in formato FASTA sono presenti in una stringa di testo."""
    return fasta_content.count(">")


def longest_shared_seq(seqs: list[str]) -> str:
    """Trova la più lunga sottosequenza comune (Longest Common Substring) tra n sequenze."""
    if not seqs:
        return ""
    shortest = min(seqs, key=len)
    length = len(shortest)
    for w in range(length, 0, -1):
        for i in range(length - w + 1):
            kmer = shortest[i:i+w]
            if all(kmer in s for s in seqs):
                return kmer
    return ""


def genome_assembly(kmers: list[str]) -> str:
    """Esegue un assemblaggio greedy primario basato sulle sovrapposizioni dei k-mer."""
    if not kmers:
        return ""
    # Corretto: rimosso il list() superfluo dentro sorted()
    kmers = sorted(set(kmers))
    overlap_graph = kmers[0]
    for kmer in kmers[1:]:
        for i in range(len(kmer), 0, -1):
            if overlap_graph.endswith(kmer[:i]):
                overlap_graph += kmer[i:]
                break
        else:
            overlap_graph += kmer
    return overlap_graph
