#!/usr/bin/env python3
""" Create synthetic DNA using Markov chain """
import argparse
import random
import sys
from collections import defaultdict, Counter
from itertools import count
from typing import Dict, Iterator, List, NamedTuple, Optional, TextIO, Tuple
from Bio import SeqIO

# WeightedChoice: precalcolato come tuple (population, weights) per random.choices
WeightedChoice = Tuple[List[str], List[float]]
Chain = Dict[str, WeightedChoice]

class Args(NamedTuple):
    files:       List[TextIO]
    outfile:     TextIO
    file_format: str
    num:         int
    min_len:     int
    max_len:     int
    k:           int
    seed:        Optional[int]

# --------------------------------------------------
def get_args() -> Args:
    parser = argparse.ArgumentParser(
        description='Create synthetic DNA using Markov chain',
        formatter_class=argparse.ArgumentDefaultsHelpFormatter)

    parser.add_argument('file', metavar='FILE', nargs='+',
                        type=argparse.FileType('rt'), help='Training file(s)')

    parser.add_argument('-o', '--outfile', metavar='FILE',
                        type=argparse.FileType('wt'), default='out.fa',
                        help='Output filename')

    parser.add_argument('-f', '--format', metavar='format',
                        choices=['fasta', 'fastq'], default='fasta',
                        help='Input file format')

    parser.add_argument('-n', '--num', metavar='number', type=int, default=100,
                        help='Number of sequences to create')

    parser.add_argument('-x', '--max_len', metavar='max', type=int, default=75,
                        help='Maximum sequence length')

    parser.add_argument('-m', '--min_len', metavar='min', type=int, default=50,
                        help='Minimum sequence length')

    parser.add_argument('-k', '--kmer', metavar='kmer', type=int, default=10,
                        help='Size of kmers')

    parser.add_argument('-s', '--seed', metavar='seed', type=int, default=None,
                        help='Random seed value')

    args = parser.parse_args()

    return Args(files=args.file,
                outfile=args.outfile,
                file_format=args.format,
                num=args.num,
                min_len=args.min_len,
                max_len=args.max_len,
                k=args.kmer,
                seed=args.seed)

# --------------------------------------------------
def find_kmers(seq: str, k: int) -> Iterator[str]:
    """ Generator di k-mers: niente lista in memoria """
    n = len(seq) - k + 1
    for i in range(n):
        yield seq[i:i + k]

# --------------------------------------------------
def read_training(fhs: List[TextIO], file_format: str, k: int) -> Chain:
    """ Legge i file di training, ritorna chain con (population, weights) precalcolati """
    counts: Dict[str, Counter] = defaultdict(Counter)
    for fh in fhs:
        for rec in SeqIO.parse(fh, file_format):
            for kmer in find_kmers(str(rec.seq).upper(), k):  # case-insensitive
                counts[kmer[:k - 1]][kmer[-1]] += 1

    chain: Chain = {}
    for kmer, freqs in counts.items():
        total = sum(freqs.values())
        pop  = list(freqs.keys())
        wgts = [freq / total for freq in freqs.values()]
        chain[kmer] = (pop, wgts)   # precalcolato: niente conversione nel loop
    return chain

# --------------------------------------------------
def gen_seq(chain: Chain,
            chain_keys: List[str],
            k: int,
            min_len: int,
            max_len: int) -> Optional[str]:
    """ Genera una sequenza; chain_keys passata dall'esterno (precalcolata) """
    seq = random.choice(chain_keys)
    seq_len = random.randint(min_len, max_len)
    while len(seq) < seq_len:
        prev = seq[-(k - 1):]
        if choice := chain.get(prev):
            pop, wgts = choice
            seq += random.choices(pop, weights=wgts, k=1)[0]
        else:
            break
    return seq if len(seq) >= min_len else None

# --------------------------------------------------
def main() -> None:
    args = get_args()
    random.seed(args.seed)

    if chain := read_training(args.files, args.file_format, args.k):
        chain_keys = list(chain.keys())   # precalcolato una volta sola
        seqs: Iterator[Optional[str]] = (
            gen_seq(chain, chain_keys, args.k, args.min_len, args.max_len)
            for _ in count()
        )
        for i, seq in enumerate(filter(None, seqs), start=1):
            print(f'>{i}\n{seq}', file=args.outfile)
            if i == args.num:
                break
        print(f'Done, see output in "{args.outfile.name}".')
    else:
        sys.exit(f'No {args.k}-mers in input sequences.')

# --------------------------------------------------
if __name__ == '__main__':
    main()

