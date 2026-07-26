#!/usr/bin/env python3
""" Translate RNA to proteins """
import argparse
import os
import sys
from typing import NamedTuple, List
from Bio import SeqIO

# Tabella codoni RNA modulo-level: zero overhead a runtime
_CODON_TABLE = {
    'UUU': 'F', 'UUC': 'F', 'UUA': 'L', 'UUG': 'L',
    'UCU': 'S', 'UCC': 'S', 'UCA': 'S', 'UCG': 'S',
    'UAU': 'Y', 'UAC': 'Y', 'UAA': '*', 'UAG': '*',
    'UGU': 'C', 'UGC': 'C', 'UGA': '*', 'UGG': 'W',
    'CUU': 'L', 'CUC': 'L', 'CUA': 'L', 'CUG': 'L',
    'CCU': 'P', 'CCC': 'P', 'CCA': 'P', 'CCG': 'P',
    'CAU': 'H', 'CAC': 'H', 'CAA': 'Q', 'CAG': 'Q',
    'CGU': 'R', 'CGC': 'R', 'CGA': 'R', 'CGG': 'R',
    'AUU': 'I', 'AUC': 'I', 'AUA': 'I', 'AUG': 'M',
    'ACU': 'T', 'ACC': 'T', 'ACA': 'T', 'ACG': 'T',
    'AAU': 'N', 'AAC': 'N', 'AAA': 'K', 'AAG': 'K',
    'AGU': 'S', 'AGC': 'S', 'AGA': 'R', 'AGG': 'R',
    'GUU': 'V', 'GUC': 'V', 'GUA': 'V', 'GUG': 'V',
    'GCU': 'A', 'GCC': 'A', 'GCA': 'A', 'GCG': 'A',
    'GAU': 'D', 'GAC': 'D', 'GAA': 'E', 'GAG': 'E',
    'GGU': 'G', 'GGC': 'G', 'GGA': 'G', 'GGG': 'G',
}

_DNA_TO_RNA = str.maketrans('Tt', 'Uu')   # supporta DNA in input

class Args(NamedTuple):
    seqs: List[str]   # lista di sequenze già normalizzate

def get_args() -> Args:
    parser = argparse.ArgumentParser(
        description='Translate RNA to proteins',
        formatter_class=argparse.ArgumentDefaultsHelpFormatter)
    parser.add_argument('input', type=str, metavar='INPUT',
                        help='RNA/DNA sequence oppure file FASTA')
    args = parser.parse_args()

    if os.path.isfile(args.input):
        seqs = [str(rec.seq).upper().translate(_DNA_TO_RNA)
                for rec in SeqIO.parse(args.input, 'fasta')]
        if not seqs:
            sys.exit('Errore: nessuna sequenza nel file')
    else:
        seqs = [args.input.upper().translate(_DNA_TO_RNA)]

    return Args(seqs)

def translate(seq: str) -> str:
    """ Traduce RNA → AA fino al primo stop codon.
        Tronca automaticamente a multiplo di 3. """
    n = len(seq) - (len(seq) % 3)
    result = []
    for i in range(0, n, 3):
        aa = _CODON_TABLE.get(seq[i:i+3], '?')
        if aa == '*':
            break
        result.append(aa)
    return ''.join(result)

def main() -> None:
    args = get_args()
    for seq in args.seqs:
        print(translate(seq))

if __name__ == '__main__':
    main()
