"""Funzioni per l'assemblaggio di genomi e l'ispezione di tratti proteici."""

import re

_PROTEIN_STRETCH_REGEX = re.compile(r"M[A-Z]*?\*")


def protein_stretch_finder(aa_seq: str) -> list[str]:
    """Trova tratti M...* in una sequenza AMMINOACIDICA gia' tradotta.

    Nota: nonostante il pattern M...* ricordi un ORF, questa NON e' una
    ricerca di Open Reading Frame su DNA/RNA: non considera frame di
    lettura, codoni di start/stop nucleotidici, ne' l'input e' nucleotidico.
    E' una ricerca di "tratto tra una M e il primo stop *" su una sequenza
    proteica gia' tradotta (es. l'output di rna_to_prot)."""
    return _PROTEIN_STRETCH_REGEX.findall(aa_seq.upper())


def how_many_seq(fasta_content: str) -> int:
    """Conta le occorrenze di '>' in un testo FASTA.

    Nota: non fa parsing FASTA completo (non valida che ogni '>' sia
    davvero l'inizio di un record ben formato); su input malformato o testo
    non-FASTA il conteggio puo' non corrispondere al numero reale di
    sequenze."""
    return fasta_content.count(">")


def longest_shared_seq(seqs: list[str]) -> str:
    """Trova la più lunga sottosequenza comune (Longest Common Substring) tra n sequenze."""
    if not seqs:
        return ""
    shortest = min(seqs, key=len)
    length = len(shortest)
    for w in range(length, 0, -1):
        for i in range(length - w + 1):
            kmer = shortest[i : i + w]
            if all(kmer in s for s in seqs):
                return kmer
    return ""


def greedy_kmer_assembly(kmers: list[str]) -> str:
    """Assemblaggio greedy di k-mer basato su sovrapposizioni lessicografiche.

    Nota: NON e' un assembler genomico biologicamente accurato (nessuna
    gestione di ripetizioni, errori di sequenziamento, o assemblaggio
    ottimale tramite grafo di De Bruijn/overlap); e' un'euristica greedy
    dimostrativa, sensibile all'ordine in cui i k-mer vengono processati."""
    if not kmers:
        return ""
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
