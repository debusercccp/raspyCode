from raspyCode.bioCli.sequence.dnaToRna import _DNA_TO_RNA
from raspyCode.bioCli.sequence.gcContent import gc_percent
from raspyCode.bioCli.sequence.hammDist import hamming
from raspyCode.bioCli.sequence.revComp import reverse_complement

def test_gc_content_logic():
    assert gc_percent("ATGC") == 50.0
    assert gc_percent("GGCC") == 100.0
    assert gc_percent("") == 0.0

def test_reverse_complement_logic():
    assert reverse_complement("ATGC") == "GCAT"
    assert reverse_complement("AATTCCGG") == "CCGGAATT"

def test_hamming_distance_logic():
    assert hamming("GAGCCTACTAACGGGAT", "CATCGTAATGACGGCCT") == 7
    assert hamming("ABC", "ABC") == 0

def test_dna_to_rna_translation():
    assert "ATCGt".translate(_DNA_TO_RNA) == "AUCGu"
