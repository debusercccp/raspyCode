#!/usr/bin/env python3
""" Find locations of N-glycosylation motif """
import argparse
import os
import re
import sys
from typing import List, NamedTuple, Tuple
import requests
from Bio import SeqIO

_MOTIF    = re.compile(r'(?=(N[^P][ST][^P]))')          # N-glicosylation motif
_UNIPROT  = re.compile(r'^[A-Z][0-9][A-Z0-9]{3}[0-9]'  # formato UniProt ID
                       r'([A-Z][0-9][A-Z0-9]{3}[0-9])?$')
_AA_VALID = re.compile(r'^[ACDEFGHIKLMNPQRSTVWYacdefghiklmnpqrstvwy]+$')

class Args(NamedTuple):
    # Ogni elemento: (label, sequenza) oppure (prot_id, None) da fetchare
    inputs:       List[Tuple[str, str]]   # (label, seq) già risolti
    ids:          List[str]               # UniProt ID da fetchare
    download_dir: str

def get_args() -> Args:
    parser = argparse.ArgumentParser(
        description='Find locations of N-glycosylation motif',
        formatter_class=argparse.ArgumentDefaultsHelpFormatter)

    parser.add_argument('input', metavar='INPUT',
                        help='Sequenza AA, UniProt ID, o file di ID')
    
    parser.add_argument('-d', '--download_dir', metavar='DIR',
                        type=str, default='fasta',
                        help='Directory per i download')
    
    args = parser.parse_args()

    direct: List[Tuple[str, str]] = []
    to_fetch: List[str] = []

    if os.path.isfile(args.input):
        # File: ogni riga è un UniProt ID
        with open(args.input) as fh:
            to_fetch = [line.strip() for line in fh if line.strip()]
    elif _AA_VALID.match(args.input) and not _UNIPROT.match(args.input):
        # Sequenza diretta da CLI
        direct = [('INPUT', args.input.upper())]
    else:
        # UniProt ID singolo
        to_fetch = [args.input.strip()]

    return Args(direct, to_fetch, args.download_dir)

def fetch_fasta(ids: List[str], fasta_dir: str) -> List[str]:
    os.makedirs(fasta_dir, exist_ok=True)
    files = []
    for prot_id in ids:
        fasta = os.path.join(fasta_dir, prot_id + '.fasta')
        if not os.path.isfile(fasta):
            url = f'https://www.uniprot.org/uniprot/{prot_id}.fasta'
            response = requests.get(url, timeout=10)
            if response.status_code == 200:
                with open(fasta, 'wt') as fh:
                    fh.write(response.text)
            else:
                print(f'Error fetching "{url}": {response.status_code}',
                      file=sys.stderr)
                continue
        files.append(fasta)
    return files

def find_motif(label: str, seq: str) -> None:
    matches = list(_MOTIF.finditer(seq.upper()))
    if matches:
        print(label)
        print(*[m.start() + 1 for m in matches])

def main() -> None:
    args = get_args()

    # 1. Sequenze dirette da CLI
    for label, seq in args.inputs:
        find_motif(label, seq)

    # 2. UniProt ID  fetch  parse
    for file in fetch_fasta(args.ids, args.download_dir):
        prot_id, _ = os.path.splitext(os.path.basename(file))
        rec = next(SeqIO.parse(file, 'fasta'), None)
        if rec is None:
            continue
        find_motif(prot_id, str(rec.seq))

if __name__ == '__main__':
    main()



