"""Generazione di sequenze sintetiche tramite catene di Markov."""

import random
from collections import Counter, defaultdict


def synth_seq(training_fasta: str, k: int, length: int, seed: int | None = None) -> str:
    """Genera una sequenza artificiale basata sulla frequenza dei k-mer di un file di addestramento."""
    if k < 1:
        raise ValueError(f"k deve essere >= 1, ricevuto: {k}")
    if length < 0:
        raise ValueError(f"length deve essere >= 0, ricevuto: {length}")
    if length == 0:
        return ""

    # random.Random locale invece di random.seed() globale: non muta lo
    # stato condiviso del modulo random, che altrove nel processo potrebbe
    # essere usato per tutt'altro (es. run_genetic_sim in parallelo).
    rng = random.Random(seed)

    # 1. Parsing delle sequenze di addestramento
    lines = training_fasta.splitlines()
    full_text = "".join(
        line.strip().upper() for line in lines if line and not line.startswith(">")
    )

    if len(full_text) <= k:
        # Training set troppo corto per costruire una catena di Markov:
        # fallback deterministico che rispetta SEMPRE la lunghezza richiesta
        # (il vecchio "ATCG" * (length // 4) troncava/azzerava per length
        # non multiplo di 4, es. length=5 dava 4 caratteri, length=1..3 ne
        # dava 0).
        pattern = "ATCG"
        return (pattern * ((length // len(pattern)) + 1))[:length]

    # 2. Costruzione della catena di Markov
    counts = defaultdict(Counter)
    for i in range(len(full_text) - k):
        context = full_text[i : i + k]
        next_base = full_text[i + k]
        counts[context][next_base] += 1

    chain = {}
    for context, counter in counts.items():
        population = list(counter.keys())
        weights = list(counter.values())
        chain[context] = (population, weights)

    # 3. Generazione della sequenza
    chain_keys = list(chain.keys())
    current_context = rng.choice(chain_keys)
    generated = [current_context]

    while len("".join(generated)) < length:
        if current_context in chain:
            pop, w = chain[current_context]
            next_base = rng.choices(pop, weights=w)[0]
            generated.append(next_base)
            current_context = (current_context + next_base)[1:]
        else:
            next_base = rng.choice(chain_keys)
            generated.append(next_base)
            current_context = next_base

    return "".join(generated)[:length]
