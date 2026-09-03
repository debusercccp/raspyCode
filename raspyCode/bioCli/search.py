"""Funzioni per il pattern matching, ricerca di motivi e siti di restrizione."""

import re

_N_GLYC_REGEX = re.compile(r"(?=(N[^P][ST][^P]))")


def motif_find(pattern: str, seq: str) -> list[int]:
    """Trova gli indici di inizio (1-based) di un motivo regex o letterale dentro una sequenza."""
    regex = re.compile(f"(?=({pattern.upper()}))")
    return [m.start() + 1 for m in regex.finditer(seq.upper())]


def n_glyc_motif(seq: str) -> list[int]:
    """Individua le posizioni 1-based del motivo di N-glicosificazione (N{P}[ST]{P})."""
    return [m.start() + 1 for m in _N_GLYC_REGEX.finditer(seq.upper())]


def restriction_site(seq: str) -> list[tuple[int, int]]:
    """Trova i siti di restrizione (palindromi inversi di lunghezza compresa tra 4 e 12)."""
    from .sequence import rev_comp

    seq = seq.upper()
    results = []
    n = len(seq)
    for length in range(4, 13):
        for i in range(n - length + 1):
            sub = seq[i : i + length]
            if sub == rev_comp(sub):
                results.append((i + 1, length))
    return sorted(results)


def grep_fastx(pattern: str, fasta_content: str) -> list[str]:
    """Filtra le intestazioni o record FASTA che matchano un determinato pattern."""
    lines = fasta_content.splitlines()
    results = []
    current_record = []
    match_found = False

    for line in lines:
        if line.startswith(">"):
            if current_record and match_found:
                results.append("\n".join(current_record))
            current_record = [line]
            match_found = bool(re.search(pattern, line, re.IGNORECASE))
        else:
            current_record.append(line)
            if not match_found and re.search(pattern, line, re.IGNORECASE):
                match_found = True

    if current_record and match_found:
        results.append("\n".join(current_record))
    return results
