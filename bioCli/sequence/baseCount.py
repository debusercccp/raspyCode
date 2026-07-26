#!/usr/bin/env python3

import argparse
import os
from typing import NamedTuple
 
class Args(NamedTuple):
    dna: str
 
def get_args() -> Args:

    parser = argparse.ArgumentParser(
        description='Tetranucleotide frequency',
        formatter_class=argparse.ArgumentDefaultsHelpFormatter)
    
    parser.add_argument('dna', metavar='DNA', help='Input DNA sequence or file')
    
    args = parser.parse_args()
    
    if os.path.isfile(args.dna):
        with open(args.dna) as fh:          # context manager: chiusura garantita
            args.dna = fh.read().rstrip()
    return Args(args.dna)
 
def main() -> None:
    args = get_args()
    s = args.dna.upper()
    print(s.count('A'), s.count('C'), s.count('G'), s.count('T'))
 
if __name__ == '__main__':
    main()
