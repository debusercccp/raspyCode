#!/usr/bin/env python3
""" Open Reading Frames """
import argparse
import re
from typing import List, NamedTuple, TextIO
from Bio import SeqIO

_COMP_RNA  = str.maketrans('ACGUacgu', 'UGCAugca')
_ORF_REGEX = re.compile(r'(?=(M[^*]*)\*)')  
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

class Args(NamedTuple):
    file: TextIO

def get_args() -> Args:

    parser = argparse.ArgumentParser(
        description='Open Reading Frames',
        formatter_class=argparse.ArgumentDefaultsHelpFormatter)

    parser.add_argument('file', metavar='FILE',
                        type=argparse.FileType('rt'), help='Input FASTA file')

    args = parser.parse_args()
    return Args(args.file)

def reverse_complement(seq: str) -> str:
    """ Reverse complement di una sequenza RNA — singolo pass C-level """
    return seq.translate(_COMP_RNA)[::-1]

def translate(seq: str) -> str:
    """ Traduce RNA → AA, termina con '*' su stop codon """
    n = len(seq) - (len(seq) % 3)   # tronca a multiplo di 3 inline
    return ''.join(_CODON_TABLE.get(seq[i:i+3], '?') for i in range(0, n, 3))

def find_orfs(aa: str) -> List[str]:
    """ Trova tutti gli ORF (anche sovrapposti) con singolo pass regex """
    return _ORF_REGEX.findall(aa)

def main() -> None:
    args = get_args()
    for rec in SeqIO.parse(args.file, 'fasta'):
        rna = str(rec.seq).upper().replace('T', 'U')   # case-insensitive
        orfs: set = set()
        for seq in [rna, reverse_complement(rna)]:
            for i in range(3):                          # 3 frame di lettura
                prot = translate(seq[i:])
                for orf in find_orfs(prot):
                    orfs.add(orf)
        print('\n'.join(sorted(orfs)))

# --------------------------------------------------
# Tests
def test_translate() -> None:
    assert translate('AUGUAA') == 'M*'
    assert translate('UUUUUC') == 'FF'
    assert translate('AUG') == 'M'

def test_reverse_complement() -> None:
    assert reverse_complement('AUGC') == 'GCAU'
    assert reverse_complement('UUUU') == 'AAAA'

def test_find_orfs() -> None:
    assert find_orfs('') == []
    assert find_orfs('M') == []
    assert find_orfs('*') == []
    assert find_orfs('M*') == ['M']
    assert find_orfs('MAMAPR*') == ['MAMAPR', 'MAPR']
    assert find_orfs('MAMAPR*M') == ['MAMAPR', 'MAPR']
    assert find_orfs('MAMAPR*MP*') == ['MAMAPR', 'MAPR', 'MP']

if __name__ == '__main__':
    main()
