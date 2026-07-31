from raspyCode.bioCli import (
    base_count,
    blast_output,
    fastx_sampler,
    genome_assembly,
    grep_fastx,
    how_many_seq,
    longest_shared_seq,
    motif_find,
    n_glyc_motif,
    orf_finder,
    restriction_site,
    rna_to_prot,
    seq_magic,
    synth_seq,
)

FASTA = ">seq1 primo record\nATGCGATCG\n>seq2 secondo record\nATGGGGCCC\n"


# --- assembly.py -------------------------------------------------------


def test_orf_finder_finds_open_reading_frames():
    assert orf_finder("MKV*MTT*") == ["MKV*", "MTT*"]
    assert orf_finder("kv") == []


def test_how_many_seq_counts_fasta_records():
    assert how_many_seq(FASTA) == 2
    assert how_many_seq("") == 0


def test_longest_shared_seq_finds_common_substring():
    assert longest_shared_seq(["GATTACA", "TACAG", "ATACAT"]) == "TACA"
    assert longest_shared_seq([]) == ""


def test_genome_assembly_greedy_overlap():
    assert genome_assembly(["AAA", "AAT", "ATG", "TGG"]) == "AAATGG"
    assert genome_assembly([]) == ""


# --- io_utils.py ---------------------------------------------------------


def test_seq_magic_computes_stats_per_record():
    stats = seq_magic(FASTA)
    assert stats["seq1"]["len"] == 9
    assert round(stats["seq1"]["gc"], 2) == round(5 / 9 * 100.0, 2)
    assert "seq2" in stats


def test_fastx_sampler_is_deterministic_with_seed():
    result_a = fastx_sampler(FASTA, percent=100.0, seed=1)
    result_b = fastx_sampler(FASTA, percent=100.0, seed=1)
    assert result_a == result_b
    assert "seq1" in result_a and "seq2" in result_a

    assert fastx_sampler(FASTA, percent=0.0, seed=1) == ""


def test_blast_output_parses_tabular_rows():
    line = "q1\ts1\t98.5\t120\t2\t0\t1\t120\t5\t124\t1e-50\t210.0"
    rows = blast_output(line)
    assert len(rows) == 1
    assert rows[0]["qseqid"] == "q1"
    assert rows[0]["pident"] == 98.5
    assert rows[0]["length"] == 120

    assert blast_output("# comment\n\n") == []


# --- search.py -----------------------------------------------------------


def test_motif_find_returns_1_based_positions():
    assert motif_find("GC", "ATGCGC") == [3, 5]
    assert motif_find("XX", "ATGC") == []


def test_n_glyc_motif_detects_pattern():
    # N-X-[ST]-X con X diverso da P: "NAT G" -> "NATG" e' un match a pos 1
    assert n_glyc_motif("NATGAAA") == [1]
    assert n_glyc_motif("NPTG") == []  # P subito dopo N: non valido


def test_restriction_site_finds_palindromes():
    sites = restriction_site("GAATTC")
    assert (1, 6) in sites  # l'intera sequenza e' palindromica (EcoRI)


def test_grep_fastx_filters_matching_records():
    result = grep_fastx("seq1", FASTA)
    assert len(result) == 1
    assert "seq1" in result[0]
    assert grep_fastx("nessunmatch", FASTA) == []


# --- synthesis.py ----------------------------------------------------------


def test_synth_seq_is_deterministic_with_seed_and_respects_length():
    training = ">t\n" + "ATGCATGCATGCATGC" * 4
    seq_a = synth_seq(training, k=3, length=20, seed=42)
    seq_b = synth_seq(training, k=3, length=20, seed=42)
    assert seq_a == seq_b
    assert len(seq_a) == 20


def test_synth_seq_falls_back_on_short_training_data():
    assert synth_seq(">t\nAT", k=5, length=8, seed=1) == "ATCG" * 2


# --- sequence.py (righe residue non coperte da test_biocli.py) -------------


def test_rna_to_prot_stops_at_first_stop_codon():
    assert rna_to_prot("AUGUUUUAA") == "MF"
    assert rna_to_prot("AUG") == "M"


def test_base_count_counts_each_base():
    assert base_count("ATGCGCAT") == {"A": 2, "T": 2, "G": 2, "C": 2}
