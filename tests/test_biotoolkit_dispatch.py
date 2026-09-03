import pytest

from raspyCode.services.biotoolkit_dispatch import BIOTOOLKIT_TOOL_NAMES, run_biotoolkit


def test_gc_content():
    assert "50.0" in run_biotoolkit("biotoolkit_gc_content", ["ATGC"])


def test_rev_comp():
    assert "GCAT" in run_biotoolkit("biotoolkit_rev_comp", ["ATGC"])


def test_dna_to_rna():
    assert "AUCGu" in run_biotoolkit("biotoolkit_dna_to_rna", ["ATCGt"])


def test_rna_to_prot():
    assert "MF" in run_biotoolkit("biotoolkit_rna_to_prot", ["AUGUUUUAA"])


def test_base_count():
    assert "'A': 2" in run_biotoolkit("biotoolkit_base_count", ["AATT"])


def test_hamming_dist():
    assert "1" in run_biotoolkit("biotoolkit_hamming_dist", ["ABC", "ABD"])


def test_orf_finder():
    assert "MKV*" in run_biotoolkit("biotoolkit_orf_finder", ["MKV*"])


def test_how_many_seq():
    assert "2" in run_biotoolkit("biotoolkit_how_many_seq", [">a\nATG\n>b\nCGT\n"])


def test_longest_shared_seq():
    assert "TACA" in run_biotoolkit("biotoolkit_longest_shared_seq", ["GATTACA", "TACAG"])


def test_genome_assembly():
    assert "ATGCA" in run_biotoolkit("biotoolkit_genome_assembly", ["ATG", "TGC", "GCA"])


def test_grep_fastx():
    fasta = ">seq1 x\nATGC\n>seq2 y\nGGCC\n"
    result = run_biotoolkit("biotoolkit_grep_fastx", ["seq1", fasta])
    assert "seq1" in result


def test_motif_find():
    result = run_biotoolkit("biotoolkit_motif_find", ["GC", "ATGCGC"])
    assert "3" in result and "5" in result


def test_n_glyc_motif():
    result = run_biotoolkit("biotoolkit_n_glyc_motif", ["NATGAAA"])
    assert "1" in result


def test_restriction_site():
    result = run_biotoolkit("biotoolkit_restriction_site", ["GAATTC"])
    assert "(1, 6)" in result


def test_fastx_sampler_full_percent_keeps_everything():
    fasta = ">seq1\nATGC\n>seq2\nGGCC\n"
    result = run_biotoolkit("biotoolkit_fastx_sampler", [fasta, "100"])
    assert "seq1" in result and "seq2" in result


def test_seq_magic():
    result = run_biotoolkit("biotoolkit_seq_magic", [">seq1\nATGC\n"])
    assert "seq1" in result


def test_blast_output():
    line = "q1\ts1\t98.5\t120\t2\t0\t1\t120\t5\t124\t1e-50\t210.0"
    result = run_biotoolkit("biotoolkit_blast_output", [line])
    assert "q1" in result


def test_synth_seq_respects_length():
    training = ">t\n" + "ATGCATGCATGCATGC" * 4
    result = run_biotoolkit("biotoolkit_synth_seq", [training, "3", "20"])
    assert len(result) == 20


def test_unknown_tool_raises_keyerror():
    with pytest.raises(KeyError):
        run_biotoolkit("biotoolkit_non_esistente", [])


def test_all_declared_tool_names_are_dispatchable():
    """Ogni nome in BIOTOOLKIT_TOOL_NAMES deve essere gestito dal dispatch:
    altrimenti il server MCP genererebbe un tool che fallisce sempre."""
    for name in BIOTOOLKIT_TOOL_NAMES:
        try:
            run_biotoolkit(name, [])
        except KeyError:
            pytest.fail(f"'{name}' e' in BIOTOOLKIT_TOOL_NAMES ma non gestito da run_biotoolkit")
        except Exception:
            # Args vuoti possono far fallire la funzione bioCli sottostante
            # (es. IndexError su hamming_dist): va bene, ci interessa solo
            # che il nome sia riconosciuto, non l'esito con args fittizi.
            pass
