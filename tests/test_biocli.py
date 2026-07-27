from raspyCode.bioCli import dna_to_rna, gc_content, hamming_dist, rev_comp


def test_gc_content_logic():
    assert gc_content("ATGC") == 50.0
    assert gc_content("GGCC") == 100.0
    assert gc_content("") == 0.0


def test_reverse_complement_logic():
    assert rev_comp("ATGC") == "GCAT"
    assert rev_comp("AATTCCGG") == "CCGGAATT"


def test_hamming_distance_logic():
    assert hamming_dist("GAGCCTACTAACGGGAT", "CATCGTAATGACGGCCT") == 7
    assert hamming_dist("ABC", "ABC") == 0


def test_dna_to_rna_translation():
    assert dna_to_rna("ATCGt") == "AUCGu"
