#!/usr/bin/env python3
import argparse
import logging
from collections import defaultdict
from itertools import product
from pprint import pformat
from typing import List, NamedTuple, TextIO
from Bio import SeqIO
 
class Args(NamedTuple):
    file: TextIO
    k: int
    debug: bool
 
def get_args() -> Args:

    parser = argparse.ArgumentParser(
        description='Overlap Graphs',
        formatter_class=argparse.ArgumentDefaultsHelpFormatter)

    parser.add_argument('file', metavar='FILE',
                        type=argparse.FileType('rt'), help='FASTA file')

    parser.add_argument('-k', '--overlap', metavar='size',
                        type=int, default=3, help='Size of overlap')

    parser.add_argument('-d', '--debug', action='store_true', help='Debug')

    args = parser.parse_args()

    if args.overlap < 1:
        parser.error(f'-k "{args.overlap}" must be > 0')

    return Args(args.file, args.overlap, args.debug)
 
def find_kmers(seq: str, k: int) -> List[str]:
    n = len(seq) - k + 1
    return [] if n < 1 else [seq[i:i + k] for i in range(n)]
 
def test_find_kmers() -> None:
    assert find_kmers('', 1) == []
    assert find_kmers('ACTG', 1) == ['A', 'C', 'T', 'G']
    assert find_kmers('ACTG', 2) == ['AC', 'CT', 'TG']
    assert find_kmers('ACTG', 3) == ['ACT', 'CTG']
    assert find_kmers('ACTG', 4) == ['ACTG']
    assert find_kmers('ACTG', 5) == []
 
def main() -> None:
    args = get_args()
    logging.basicConfig(
        filename='.log', filemode='w',
        level=logging.DEBUG if args.debug else logging.CRITICAL)
    logging.debug('input file = "%s"', args.file.name)
 
    start, end = defaultdict(list), defaultdict(list)
    for rec in SeqIO.parse(args.file, 'fasta'):
        if kmers := find_kmers(str(rec.seq).upper(), args.k):  
            start[kmers[0]].append(rec.id)
            end[kmers[-1]].append(rec.id)
 
    logging.debug('STARTS\n%s', pformat(start))
    logging.debug('ENDS\n%s', pformat(end))
 
    for kmer in set(start).intersection(end):
        for a, b in product(end[kmer], start[kmer]):
            if a != b:                                       
                print(a, b)
 
if __name__ == '__main__':
    main()
 
