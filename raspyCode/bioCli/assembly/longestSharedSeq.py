#!/usr/bin/env python3
""" Longest Common Substring """
import argparse
from collections import Counter
from functools import partial
from itertools import chain
from typing import Callable, List, NamedTuple, TextIO
from Bio import SeqIO

class Args(NamedTuple):
    """ Command-line arguments """
    file: TextIO

# --------------------------------------------------
def get_args() -> Args:
    
    parser = argparse.ArgumentParser(
        description='Longest Common Substring',
        formatter_class=argparse.ArgumentDefaultsHelpFormatter)
    
    parser.add_argument('file', help='Input FASTA', metavar='FILE',
                        type=argparse.FileType('rt'))
    
    args = parser.parse_args()
    
    return Args(args.file)

# --------------------------------------------------
def find_kmers(seq: str, k: int) -> List[str]:
    """ Find k-mers in string """
    n = len(seq) - k + 1
    return [] if n < 1 else [seq[i:i + k] for i in range(n)]

# --------------------------------------------------
def common_kmers(seqs: List[str], k: int) -> List[str]:
    """ Find k-mers common to all sequences """
    n = len(seqs)
    counts = Counter(chain.from_iterable(set(find_kmers(seq, k)) for seq in seqs))
    return [kmer for kmer, freq in counts.items() if freq == n]

# --------------------------------------------------
def binary_search(f: Callable, low: int, high: int) -> int:
    """ Binary search — base case fix: evita ricorsione infinita """
    if low >= high:
        return low if f(low) else -1
    hi, lo = f(high), f(low)
    if hi and lo:
        return high
    mid = (high + low) // 2
    if lo and not hi:
        return binary_search(f, low, mid)
    if hi and not lo:
        return binary_search(f, mid + 1, high)  # mid+1: evita loop su high=low+1
    return -1

# --------------------------------------------------
def main() -> None:
    args = get_args()
    seqs = [str(rec.seq).upper() for rec in SeqIO.parse(args.file, 'fasta')]  # case-insensitive
    if not seqs:
        print('No sequences found.')
        return

    shortest = min(map(len, seqs))
    common = partial(common_kmers, seqs)
    start = binary_search(common, 1, shortest)

    if start < 0:
        print('No common subsequence.')
        return

    # Hill climb dal punto di partenza trovato dalla binary search
    best = ''
    for k in range(start, shortest + 1):
        if kmers := common(k):
            best = kmers[0]   # deterministico: primo della lista
        else:
            break
    
    # Replaces print(best)
    print(f"Processed {len(seqs)} sequence(s).")
    print(f"Longest common substring length: {len(best)}")
    
    if len(best) > 80:
        # Truncate the output if it's too long
        print(f"Match: {best[:40]}...{best[-40:]}")
    else:
        print(f"Match: {best}")

# --------------------------------------------------
# Tests
def test_find_kmers() -> None:
    assert find_kmers('', 1) == []
    assert find_kmers('ACTG', 1) == ['A', 'C', 'T', 'G']
    assert find_kmers('ACTG', 2) == ['AC', 'CT', 'TG']
    assert find_kmers('ACTG', 3) == ['ACT', 'CTG']
    assert find_kmers('ACTG', 4) == ['ACTG']
    assert find_kmers('ACTG', 5) == []

def test_common_kmers() -> None:
    seqs = ['GATTACA', 'TAGACCA', 'ATACA']
    assert common_kmers(seqs, 5) == []
    assert sorted(common_kmers(seqs, 2)) == ['AC', 'CA', 'TA']

def test_binary_search() -> None:
    seqs1 = ['GATTACA', 'TAGACCA', 'ATACA']
    f1 = partial(common_kmers, seqs1)
    assert binary_search(f1, 1, 5) == 2

    seqs2 = ['GATTACTA', 'TAGACTCA', 'ATACTA']
    f2 = partial(common_kmers, seqs2)
    assert binary_search(f2, 1, 6) == 3

    # Test base case: low >= high
    seqs3 = ['AAAA', 'BBBB']
    f3 = partial(common_kmers, seqs3)
    assert binary_search(f3, 1, 1) == -1

# --------------------------------------------------
if __name__ == '__main__':
    main()
