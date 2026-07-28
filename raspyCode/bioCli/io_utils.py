"""Funzioni di utilità I/O per record FASTA e report di allineamento."""

import random


def seq_magic(fasta_content: str) -> dict[str, dict[str, float | int]]:
    """Calcola statistiche chiave (lunghezza, basi, GC) per ogni record di una stringa FASTA."""
    lines = fasta_content.splitlines()
    stats = {}
    current_id = None
    current_seq = []

    def process_entry(rec_id: str, seq_list: list[str]):
        seq_str = "".join(seq_list).upper()
        total_len = len(seq_str)
        if total_len == 0:
            return
        g_count = seq_str.count("G")
        c_count = seq_str.count("C")
        stats[rec_id] = {
            "len": total_len,
            "gc": (g_count + c_count) / total_len * 100.0,
            "A": seq_str.count("A"),
            "T": seq_str.count("T"),
            "G": g_count,
            "C": c_count
        }

    for line in lines:
        if line.startswith(">"):
            if current_id:
                process_entry(current_id, current_seq)
            current_id = line[1:].split()[0]
            current_seq = []
        else:
            current_seq.append(line)

    if current_id:
        process_entry(current_id, current_seq)

    return stats


def fastx_sampler(fasta_content: str, percent: float, seed: int | None = None) -> str:
    """Campiona probabilisticamente i record di un file FASTA in base a una percentuale."""
    if seed is not None:
        random.seed(seed)

    lines = fasta_content.splitlines()
    sampled_records = []
    current_record = []
    keep_record = False

    for line in lines:
        if line.startswith(">"):
            if current_record and keep_record:
                sampled_records.append("\n".join(current_record))
            current_record = [line]
            keep_record = random.random() * 100.0 <= percent
        else:
            current_record.append(line)

    if current_record and keep_record:
        sampled_records.append("\n".join(current_record))

    return "\n".join(sampled_records)


def blast_output(blast_tabular_content: str) -> list[dict[str, str | float | int]]:
    """Parsa righe in formato tabulare standard BLAST (outfmt 6) in dizionari strutturati."""
    columns = ["qseqid", "sseqid", "pident", "length", "mismatch", "gapopen", "qstart", "qend", "sstart", "send", "evalue", "bitscore"]
    parsed_results = []

    for line in blast_tabular_content.splitlines():
        if not line.strip() or line.startswith("#"):
            continue
        parts = line.split("\t")
        if len(parts) >= 12:
            row = {
                columns[i]: (
                    float(parts[i]) if i in (2, 10, 11) else (int(parts[i]) if i in (3, 4, 5, 6, 7, 8, 9) else parts[i])
                ) for i in range(12)
            }
            parsed_results.append(row)

    return parsed_results
