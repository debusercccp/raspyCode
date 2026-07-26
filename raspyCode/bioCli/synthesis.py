"""Generazione di sequenze sintetiche tramite catene di Markov."""

import random
from collections import Counter, defaultdict


def synth_seq(training_fasta: str, k: int, length: int, seed: int | None = None) -> str:
    """Genera una sequenza artificiale basata sulla frequenza dei k-mer di un file di addestramento."""
    if seed is not None:
        random.seed(seed)

    # 1. Parsing delle sequenze di addestramento
    lines = training_fasta.splitlines()
    full_text = "".join(line.strip().upper() for line in lines if line and not line.startswith(">"))
    
    if len(full_text) <= k:
        return "ATCG" * (length // 4)

    # 2. Costruzione della catena di Markov
    counts = defaultdict(Counter)
    for i in range(len(full_text) - k):
        context = full_text[i:i+k]
        next_base = full_text[i+k]
        counts[context][next_base] += 1

    chain = {}
    for context, counter in counts.items():
        population = list(counter.keys())
        weights = list(counter.values())
        chain[context] = (population, weights)

    # 3. Generazione della sequenza
    chain_keys = list(chain.keys())
    current_context = random.choice(chain_keys)
    generated = [current_context]
    
    while len("".join(generated)) < length:
        if current_context in chain:
            pop, w = chain[current_context]
            next_base = random.choices(pop, weights=w)[0]
            generated.append(next_base)
            current_context = (current_context + next_base)[1:]
        else:
            next_base = random.choice(chain_keys)
            generated.append(next_base)
            current_context = next_base

    return "".join(generated)[:length]
