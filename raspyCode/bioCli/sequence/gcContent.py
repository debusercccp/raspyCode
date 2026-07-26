#!/usr/bin/env python3

import argparse
import sys
from typing import NamedTuple, TextIO, Optional
from Bio.SeqIO.FastaIO import SimpleFastaParser
 
class Args(NamedTuple):
    file: TextIO
    sequence: Optional[str]
 
def get_args() -> Args:
  
    parser = argparse.ArgumentParser(
        description='Compute GC content',
        formatter_class=argparse.ArgumentDefaultsHelpFormatter)
    
    parser.add_argument('file', metavar='FILE',
                        type=argparse.FileType('rt'), nargs='?', default=sys.stdin)
    parser.add_argument('-s', '--sequence', metavar='SEQ', type=str)
    
    args = parser.parse_args()
    return Args(args.file, args.sequence)
 
def gc_percent(seq: str) -> float:
    n = len(seq)
    if not n:
        return 0.0
    upper = seq.upper()                          # 1 copia, 2 count invece di 4
    return (upper.count('G') + upper.count('C')) * 100.0 / n
 
def main() -> None:
    args = get_args()
 
    if args.sequence:
        print(f'{gc_percent(args.sequence):.6f}')
        return
 
    if args.file.name == '<stdin>' and sys.stdin.isatty():
        sys.exit("Errore: nessun input. Usa './script.py file.fasta' o '-s ACGT'")
 
    max_gc, max_id = 0.0, ''
    for title, seq in SimpleFastaParser(args.file):
        pct = gc_percent(seq)
        if pct > max_gc:
            max_gc = pct
            max_id = title.split(None, 1)[0]
 
    if max_id:
        print(f'{max_id} {max_gc:.6f}')
 
if __name__ == '__main__':
    main()
 
