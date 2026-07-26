#!/usr/bin/env python3

import argparse
import os
import sys
from typing import NamedTuple, List, TextIO, Optional
 
_DNA_TO_RNA = str.maketrans('TtUu', 'UuTt')   # module-level: compilato una volta
 
 
class Args(NamedTuple):
    files: List[TextIO]
    out_dir: str
    sequence: Optional[str]
 
def get_args() -> Args:

    parser = argparse.ArgumentParser(
        description='Transcribe DNA into RNA',
        formatter_class=argparse.ArgumentDefaultsHelpFormatter)
    
    parser.add_argument('file', metavar='FILE',
                        type=argparse.FileType('rt'), nargs='*', default=[])
    parser.add_argument('-s', '--sequence', metavar='SEQ', type=str)
    parser.add_argument('-o', '--out_dir', metavar='DIR', type=str, default='out')
    
    args = parser.parse_args()
    
    if not args.file and not args.sequence:
        parser.error('Fornisci un file o una sequenza con -s')
    return Args(files=args.file, out_dir=args.out_dir, sequence=args.sequence)
 
def main() -> None:
    args = get_args()
 
    if args.sequence:
        print(args.sequence.translate(_DNA_TO_RNA))
        if not args.files:
            return
 
    os.makedirs(args.out_dir, exist_ok=True)
    num_files = num_seqs = 0
 
    for in_fh in args.files:
        num_files += 1
        out_file = os.path.join(args.out_dir, os.path.basename(in_fh.name))
        with open(out_file, 'wt') as out_fh:
            for line in in_fh:
                num_seqs += 1
                out_fh.write(line.translate(_DNA_TO_RNA))   # singolo pass
 
    if num_files:
        print(f'Done, wrote {num_seqs} sequences in {num_files} files to "{args.out_dir}".')
 
if __name__ == '__main__':
    main()
