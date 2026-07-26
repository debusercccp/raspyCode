#!/usr/bin/env python3
""" Annotate BLAST output """
import argparse
import os
import sys
import pandas as pd
from typing import NamedTuple, TextIO

_BLAST_COLS = [
    'qseqid', 'sseqid', 'pident', 'length', 'mismatch',
    'gapopen', 'qstart', 'qend', 'sstart', 'send', 'evalue', 'bitscore'
]
_OUT_COLS = ['pident', 'depth', 'lat_lon']

class Args(NamedTuple):
    hits:        TextIO
    annotations: TextIO
    outfile:     TextIO
    delimiter:   str
    pctid:       float

def get_args() -> Args:

    parser = argparse.ArgumentParser(
        description='Annotate BLAST output',
        formatter_class=argparse.ArgumentDefaultsHelpFormatter)

    parser.add_argument('-b', '--blasthits', metavar='FILE',
                        type=argparse.FileType('rt'), required=True,
                        help='BLAST -outfmt 6 (tab-separated)')
    
    parser.add_argument('-a', '--annotations', metavar='FILE',
                        type=argparse.FileType('rt'), required=True,
                        help='Annotations file (CSV con seq_id)')
    
    parser.add_argument('-o', '--outfile', metavar='FILE',
                        type=argparse.FileType('wt'), default='out.csv',
                        help='Output file')
    
    parser.add_argument('-d', '--delimiter', metavar='DELIM',
                        type=str, default='',
                        help='Output field delimiter (default: da estensione)')
    
    parser.add_argument('-p', '--pctid', metavar='PCTID',
                        type=float, default=0.,
                        help='Minimum percent identity')
    
    args = parser.parse_args()
    
    return Args(hits=args.blasthits,
                annotations=args.annotations,
                outfile=args.outfile,
                delimiter=args.delimiter or guess_delimiter(args.outfile.name),
                pctid=args.pctid)

def guess_delimiter(filename: str) -> str:
    ext = os.path.splitext(filename)[1]
    return ',' if ext == '.csv' else '\t'

def main() -> None:
    args = get_args()

    annots = pd.read_csv(args.annotations, sep=',', index_col='seq_id')

    # BLAST -outfmt 6 è TAB-separated, non CSV
    hits = pd.read_csv(args.hits, sep='\t', header=None,
                       names=_BLAST_COLS, index_col='qseqid')

    # Filtra per pident minima
    filtered = hits[hits['pident'] >= args.pctid]

    # Controlla che le colonne di output esistano nelle annotazioni
    missing = [c for c in _OUT_COLS if c != 'pident' and c not in annots.columns]
    if missing:
        sys.exit(f'Colonne mancanti nelle annotazioni: {", ".join(missing)}')

    joined = filtered.join(annots, how='inner')

    if joined.empty:
        print('Nessun match trovato dopo il join.', file=sys.stderr)
        return

    joined.to_csv(args.outfile, index=True, index_label='qseqid',
                  columns=_OUT_COLS, sep=args.delimiter)

    print(f'Exported {joined.shape[0]:,} to "{args.outfile.name}".')

if __name__ == '__main__':
    main()
