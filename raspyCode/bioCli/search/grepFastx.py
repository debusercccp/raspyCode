#!/usr/bin/env python3
""" Grep through FASTX files """
import argparse
import os
import re
import sys
from typing import List, NamedTuple, TextIO
from Bio import SeqIO

_EXT_TO_FMT = {
    '.fa': 'fasta', '.fna': 'fasta', '.faa': 'fasta', '.fasta': 'fasta',
    '.fq': 'fastq', '.fastq': 'fastq',
}

class Args(NamedTuple):
    pattern:       str
    files:         List[TextIO]
    input_format:  str
    output_format: str
    outfile:       TextIO
    insensitive:   bool

def get_args() -> Args:
    parser = argparse.ArgumentParser(
        description='Grep through FASTX files',
        formatter_class=argparse.ArgumentDefaultsHelpFormatter)

    parser.add_argument('pattern', metavar='PATTERN', type=str,
                        help='Search pattern')

    parser.add_argument('file', metavar='FILE', nargs='+',
                        type=argparse.FileType('rt'), help='Input file(s)')

    parser.add_argument('-f', '--format', metavar='str',
                        choices=['fasta', 'fastq'], default='',
                        help='Input file format')

    parser.add_argument('-O', '--outfmt', metavar='str',
                        choices=['fasta', 'fastq', 'fasta-2line'], default='',
                        help='Output file format')

    parser.add_argument('-o', '--outfile', metavar='FILE',
                        type=argparse.FileType('wt'), default=sys.stdout,
                        help='Output file')

    parser.add_argument('-i', '--insensitive', action='store_true',
                        help='Case-insensitive search')

    args = parser.parse_args()
    return Args(pattern=args.pattern,
                files=args.file,
                input_format=args.format,
                output_format=args.outfmt,
                outfile=args.outfile,
                insensitive=args.insensitive)

def guess_format(filename: str) -> str:
    """ Guess format from file extension — O(1) dict lookup """
    ext = os.path.splitext(filename)[1].lower()
    return _EXT_TO_FMT.get(ext, '')

def main() -> None:
    args = get_args()
    flags = re.IGNORECASE if args.insensitive else 0
    regex = re.compile(args.pattern, flags)

    for fh in args.files:
        input_format = args.input_format or guess_format(fh.name)
        if not input_format:
            sys.exit(f'Please specify file format for "{fh.name}"')
        output_format = args.output_format or input_format

        for rec in SeqIO.parse(fh, input_format):
            # Cerca su id e description; description include già id
            if regex.search(rec.description):
                SeqIO.write(rec, args.outfile, output_format)

# --------------------------------------------------
# Tests
def test_guess_format() -> None:
    assert guess_format('/foo/bar.fa')    == 'fasta'
    assert guess_format('/foo/bar.fna')   == 'fasta'
    assert guess_format('/foo/bar.faa')   == 'fasta'
    assert guess_format('/foo/bar.fasta') == 'fasta'
    assert guess_format('/foo/bar.fq')    == 'fastq'
    assert guess_format('/foo/bar.fastq') == 'fastq'
    assert guess_format('/foo/bar.fx')    == ''

if __name__ == '__main__':
    main()
