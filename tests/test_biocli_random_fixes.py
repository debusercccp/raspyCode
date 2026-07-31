import random

import pytest

from raspyCode.bioCli import fastx_sampler, synth_seq

FASTA = ">seq1\nATGCGATCG\n>seq2\nATGGGGCCC\n"


@pytest.mark.parametrize("length", range(0, 12))
def test_synth_seq_fallback_respects_exact_length(length):
    # bug originale: "ATCG" * (length // 4) dava lunghezza sbagliata per
    # length non multiplo di 4 (0 per length<4, troncato per il resto).
    result = synth_seq(">t\nAT", k=5, length=length, seed=1)
    assert len(result) == length


def test_synth_seq_rejects_invalid_k():
    with pytest.raises(ValueError):
        synth_seq(">t\nATGC", k=0, length=10)


def test_synth_seq_rejects_negative_length():
    with pytest.raises(ValueError):
        synth_seq(">t\nATGC", k=2, length=-1)


def test_synth_seq_zero_length_returns_empty_string():
    assert synth_seq(">t\nATGC", k=2, length=0) == ""


def test_synth_seq_does_not_mutate_global_random_state():
    # bug originale: random.seed(seed) mutava lo stato globale del modulo
    # random, influenzando qualunque altro codice che lo usi nello stesso
    # processo (es. run_genetic_sim in tool_executor_service).
    random.seed(12345)
    expected_next = random.random()

    random.seed(12345)
    training = ">t\n" + "ATGCATGCATGCATGC" * 4
    synth_seq(training, k=3, length=10, seed=999)
    actual_next = random.random()

    assert actual_next == expected_next


def test_fastx_sampler_does_not_mutate_global_random_state():
    random.seed(54321)
    expected_next = random.random()

    random.seed(54321)
    fastx_sampler(FASTA, percent=50.0, seed=1)
    actual_next = random.random()

    assert actual_next == expected_next


def test_fastx_sampler_still_deterministic_with_seed():
    a = fastx_sampler(FASTA, percent=100.0, seed=7)
    b = fastx_sampler(FASTA, percent=100.0, seed=7)
    assert a == b
