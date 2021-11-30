#!/usr/bin/env python3

import sys
import re
import logging

from argparse import ArgumentParser

from logger import logger
from loadfreki import BBox, load_freki_document


def argparser():
    ap = ArgumentParser()
    ap.add_argument(
        '--debug',
        default=False,
        action='store_true',
        help='print debug info'
    )
    ap.add_argument(
        'freki',
        nargs='+',
        help='freki file(s) extracted from PDF'
    )
    return ap


def main(argv):
    args = argparser().parse_args(argv[1:])

    if args.debug:
        logger.setLevel(logging.DEBUG)
    else:
        logger.setLevel(logging.INFO)

    for fn in args.freki:
        try:
            document = load_freki_document(fn, args)
        except ValueError:
            continue
        document.revise_blocks()
        print(document.to_freki())


if __name__ == '__main__':
    sys.exit(main(sys.argv))
