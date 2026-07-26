#!/usr/bin/env python3
""" Probabilistically subset FASTA/Q files """
import argparse
import gzip
import os
import random
from pathlib import Path
from typing import Iterator, List, NamedTuple, Optional
from Bio import SeqIO

class Args(NamedTuple):
    files:       List[Path]
    file_format: str
    percent:     float
    max_reads:   int
    seed:        Optional[int]
    outdir:      str

# --------------------------------------------------
def get_args() -> Args:
    parser = argparse.ArgumentParser(
        description='Probabilistically subset FASTA/Q files',
        formatter_class=argparse.ArgumentDefaultsHelpFormatter)

    parser.add_argument('file', metavar='FILE', nargs='*', type=str,
                        help='Input FASTA/Q file(s) o directory')

    parser.add_argument('-f', '--format', metavar='format',
                        choices=['fasta', 'fastq'], default='fasta',
                        help='Input file format')

    parser.add_argument('-p', '--percent', metavar='reads',
                        type=float, default=.1,
                        help='Percent of reads (0 < p < 1)')

    parser.add_argument('-m', '--max', metavar='max',
                        type=int, default=0,
                        help='Maximum number of reads (0 = no limit)')

    parser.add_argument('-s', '--seed', metavar='seed',
                        type=int, default=None,
                        help='Random seed value')

    parser.add_argument('-o', '--outdir', metavar='DIR',
                        type=str, default='out',
                        help='Output directory')

    args = parser.parse_args()

    if not 0 < args.percent < 1:
        parser.error(f'--percent "{args.percent}" must be between 0 and 1')

    # Risolve file e directory in una lista flat di Path
    files: List[Path] = []
    for entry in args.file:
        p = Path(entry)
        if p.is_dir():
            files.extend(sorted(p.rglob('*')))   # ricorsivo
        elif p.is_file():
            files.append(p)
        else:
            parser.error(f'"{entry}" non è un file né una directory valida')

    if not files:
        parser.error('Nessun file trovato')

    os.makedirs(args.outdir, exist_ok=True)

    return Args(files=files,
                file_format=args.format,
                percent=args.percent,
                max_reads=args.max,
                seed=args.seed,
                outdir=args.outdir)

# --------------------------------------------------
def open_file(path: Path):
    """ Apre file normali o .gz in modo trasparente """
    return gzip.open(path, 'rt') if path.suffix == '.gz' else open(path, 'rt')

# --------------------------------------------------
def sample_records(path: Path,
                   file_format: str,
                   percent: float,
                   max_reads: int) -> Iterator:
    """ Generator: yielda record campionati probabilisticamente """
    taken = 0
    with open_file(path) as fh:
        for rec in SeqIO.parse(fh, file_format):
            if random.random() <= percent:
                taken += 1
                yield rec
            if max_reads and taken == max_reads:
                break

# --------------------------------------------------
def main() -> None:
    args = get_args()
    random.seed(args.seed)
    total_num = 0

    for i, path in enumerate(args.files, start=1):
        out_file = os.path.join(args.outdir, path.name)
        print(f'{i:3}: {path.name}')
        with open(out_file, 'wt') as out_fh:          # context manager: chiusura garantita
            num_taken = sum(
                SeqIO.write(rec, out_fh, 'fasta')
                for rec in sample_records(
                    path, args.file_format, args.percent, args.max_reads)
            )
        total_num += num_taken

    num_files = len(args.files)
    seqs_s  = '' if total_num == 1 else 's'
    files_s = '' if num_files  == 1 else 's'
    print(f'Wrote {total_num:,} sequence{seqs_s} '
          f'from {num_files:,} file{files_s} '
          f'to directory "{args.outdir}".')

# --------------------------------------------------
if __name__ == '__main__':
    main()
