#!/usr/bin/env python3
""" Infer mRNA from Protein """
import argparse
import math
import os
from typing import NamedTuple

# Conteggi precalcolati a livello modulo: zero overhead a runtime
_CODON_COUNTS = {
    'A': 4, 'C': 2, 'D': 2, 'E': 2, 'F': 2, 'G': 4, 'H': 2, 'I': 3,
    'K': 2, 'L': 6, 'M': 1, 'N': 2, 'P': 4, 'Q': 2, 'R': 6, 'S': 6,
    'T': 4, 'V': 4, 'W': 1, 'Y': 2, '*': 3,
}

class Args(NamedTuple):
    protein: str
    modulo:  int

def get_args() -> Args:
    parser = argparse.ArgumentParser(
        description='Infer mRNA from Protein',
        formatter_class=argparse.ArgumentDefaultsHelpFormatter)

    parser.add_argument('protein', metavar='protein', type=str,
                        help='Input protein or file')
    
    parser.add_argument('-m', '--modulo', metavar='int', type=int,
                        default=1_000_000, help='Modulo value')
    
    args = parser.parse_args()
    
    if os.path.isfile(args.protein):
        with open(args.protein) as fh:
            args.protein = fh.read().rstrip()
    
    return Args(args.protein.upper(), args.modulo)  

def main() -> None:
    args = get_args()
    nums = [_CODON_COUNTS[aa] for aa in args.protein + '*']
    print(math.prod(nums) % args.modulo)

if __name__ == '__main__':
    main()
