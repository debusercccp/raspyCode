"""Funzioni pure per la manipolazione di sequenze biologiche."""

from collections import Counter

_DNA_TO_RNA = str.maketrans("TtUu", "UuTt")
_COMP_DNA = str.maketrans("ATCGatcg", "TAGCtagc")
_CODON_TABLE = {
    "AUG": "M", "UUU": "F", "UUC": "F", "UUA": "L", "UUG": "L",
    "UCU": "S", "UCC": "S", "UCA": "S", "UCG": "S", "UAU": "Y",
    "UAC": "Y", "UGU": "C", "UGC": "C", "UGG": "W", "CUU": "L",
    "CUC": "L", "CUA": "L", "CUG": "L", "CCU": "P", "CCC": "P",
    "CCA": "P", "CCG": "P", "CAU": "H", "CAC": "H", "CAA": "Q",
    "CAG": "Q", "CGU": "R", "CGC": "R", "CGA": "R", "CGG": "R",
    "AUU": "I", "AUC": "I", "AUA": "I", "ACU": "T", "ACC": "T",
    "ACA": "T", "ACG": "T", "AAU": "N", "AAC": "N", "AAA": "K",
    "AAG": "K", "AGU": "S", "AGC": "S", "AGA": "R", "AGG": "R",
    "GUU": "V", "GUC": "V", "GUA": "V", "GUG": "V", "GCU": "A",
    "GCC": "A", "GCA": "A", "GCG": "A", "GAU": "D", "GAC": "D",
    "GAA": "E", "GAG": "E", "GGU": "G", "GGC": "G", "GGA": "G",
    "GGG": "G", "UAA": "*", "UAG": "*", "UGA": "*"
}


def gc_content(seq: str) -> float:
    """Calcola la percentuale di GC in una sequenza nucleotidica."""
    if not seq:
        return 0.0
    c = Counter(seq.upper())
    return ((c["G"] + c["C"]) / len(seq)) * 100.0


def rev_comp(seq: str) -> str:
    """Ritorna il reverse complement di una sequenza di DNA."""
    return seq.translate(_COMP_DNA)[::-1]


def dna_to_rna(seq: str) -> str:
    """Trascrive una sequenza di DNA in RNA."""
    return seq.translate(_DNA_TO_RNA)


def rna_to_prot(seq: str) -> str:
    """Traduce una sequenza di RNA in proteina arrestandosi al primo stop codon."""
    seq = seq.upper()
    proteins = []
    for i in range(0, len(seq) - 2, 3):
        codon = seq[i:i+3]
        amino = _CODON_TABLE.get(codon, "?")
        if amino == "*":
            break
        proteins.append(amino)
    return "".join(proteins)


def base_count(seq: str) -> dict[str, int]:
    """Ritorna il conteggio delle singole basi presenti nella sequenza."""
    return dict(Counter(seq.upper()))


def hamming_dist(seq1: str, seq2: str) -> int:
    """Calcola la distanza di Hamming tra due sequenze (inclusa disparità di lunghezza)."""
    dist = sum(1 for a, b in zip(seq1, seq2) if a != b)
    return dist + abs(len(seq1) - len(seq2))
