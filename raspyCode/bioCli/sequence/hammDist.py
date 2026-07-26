#! /usr/bin/env python3

import argparse
from itertools import zip_longest
from typing import NamedTuple
 
class Args(NamedTuple):
    seq1: str
    seq2: str
 
def get_args() -> Args:
   
    parser = argparse.ArgumentParser(
        description='Hamming distance',
        formatter_class=argparse.ArgumentDefaultsHelpFormatter)
    
    parser.add_argument('seq1', metavar='str', help='Sequence 1')
    parser.add_argument('seq2', metavar='str', help='Sequence 2')
    
    args = parser.parse_args()
    return Args(args.seq1, args.seq2)
 
def hamming(seq1: str, seq2: str) -> int:
    return sum(a != b for a, b in zip_longest(seq1.upper(), seq2.upper()))
 
def main() -> None:
    args = get_args()
    print(hamming(args.seq1, args.seq2))
 
if __name__ == '__main__':
    main()
 
