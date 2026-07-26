#!/usr/bin/env python3
""" Locating Restriction Sites """
import argparse
from typing import List, NamedTuple, TextIO
from Bio import SeqIO

_COMP = str.maketrans('ACGTacgt', 'TGCAtgca')  

class Args(NamedTuple):
    file: TextIO

def get_args() -> Args:

    parser = argparse.ArgumentParser(
        description='Locating Restriction Sites',
        formatter_class=argparse.ArgumentDefaultsHelpFormatter)
    
    parser.add_argument('file', metavar='FILE',
                        type=argparse.FileType('rt'), help='Input FASTA file')
    
    args = parser.parse_args()
    
    return Args(args.file)

def revp(seq: str, k: int) -> List[int]:
    """ Return 1-based positions of reverse palindromes of length k """
    kmers = find_kmers(seq, k)
    return [
        pos + 1
        for pos, kmer in enumerate(kmers)
        if kmer == kmer.translate(_COMP)[::-1]
    ]

def find_kmers(seq: str, k: int) -> List[str]:
    """ Find k-mers in string """
    n = len(seq) - k + 1
    return [] if n < 1 else [seq[i:i + k] for i in range(n)]

def main() -> None:
    args = get_args()
    for rec in SeqIO.parse(args.file, 'fasta'):
        seq = str(rec.seq).upper()   
        for k in range(4, 13):
            for pos in revp(seq, k):
                print(pos, k)

def test_revp() -> None:
    assert revp('CGCATGCATTGA', 4) == [3, 5]
    assert revp('CGCATGCATTGA', 5) == []
    assert revp('CGCATGCATTGA', 6) == [2, 4]
    assert revp('CGCATGCATTGA', 7) == []
    assert revp('CCCGCATGCATT', 4) == [5, 7]
    assert revp('CCCGCATGCATT', 5) == []
    assert revp('CCCGCATGCATT', 6) == [4, 6]

if __name__ == '__main__':
    main()
