#!/usr/bin/env python3

import argparse
import os
from typing import NamedTuple
 
_COMP = str.maketrans('ACGTacgt', 'TGCAtgca')   # module-level
 
class Args(NamedTuple):
    dna: str
 
def get_args() -> Args:

    parser = argparse.ArgumentParser(
        description='Print the reverse complement of DNA',
        formatter_class=argparse.ArgumentDefaultsHelpFormatter)

    parser.add_argument('dna', metavar='DNA', help='Input sequence or file')

    args = parser.parse_args()

    if os.path.isfile(args.dna):
        with open(args.dna) as fh:
            args.dna = fh.read().rstrip()
    return Args(args.dna)
 
def reverse_complement(seq: str) -> str:
    return seq.translate(_COMP)[::-1]
 
def main() -> None:
    args = get_args()
    print(reverse_complement(args.dna))
 
if __name__ == '__main__':
    main()
 
