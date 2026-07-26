#!/usr/bin/env python3
import argparse
from typing import NamedTuple
 
class Args(NamedTuple):
    seq: str
    subseq: str
 
def get_args() -> Args:

    parser = argparse.ArgumentParser(
        description='Find subsequences',
        formatter_class=argparse.ArgumentDefaultsHelpFormatter)

    parser.add_argument('seq',    metavar='seq',    help='Sequence')

    parser.add_argument('subseq', metavar='subseq', help='Sub-sequence')

    args = parser.parse_args()

    return Args(args.seq.upper(), args.subseq.upper())
 
def main() -> None:

    args = get_args()
    seq, subseq = args.seq, args.subseq
    last, found = 0, []
    
    while True:
        pos = seq.find(subseq, last)
        if pos == -1:
            break
        found.append(pos + 1)
        last = pos + 1
    print(*found)
 
if __name__ == '__main__':
    main()
 
