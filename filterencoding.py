#!/usr/bin/env python3

# Filter for encoding errors.

import sys
import os
import logging

from argparse import ArgumentParser

from loadfreki import load_freki_document
from logger import logger


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


def find_encoding_errors(document, args):
    # very crude first implementation: remove all lines from any block
    # that has an Unicode replacement character "�'" (U+FFFD).
    to_remove, total_chars = [], 0
    for page in document.pages:
        block_chars, found_error = 0, False
        for block in page.blocks:
            for line in block.lines:
                if '�' in line.text:
                    found_error = True
                total_chars += len(line.text)
        if found_error:
            to_remove.extend(block.lines)

    removed_chars = sum(len(line.text) for line in to_remove)
    removed_ratio = removed_chars / total_chars
    if to_remove:
        logger.warning(f'removing {removed_ratio:.1%} of text '
                       f'({removed_chars}/{total_chars} characters) '
                       f'from {document.id}')
    return to_remove


def main(argv):
    args = argparser().parse_args(argv[1:])

    if args.debug:
        logger.setLevel(logging.DEBUG)
    else:
        logger.setLevel(logging.INFO)

    for fn in args.freki:
        try:
            document = load_freki_document(fn, args)
        except ValueError as e:
            logger.error(f'failed to load {fn}: {e}')
            continue
        lines = find_encoding_errors(document, args)
        document.remove_lines(lines)
        print(document.to_freki())


if __name__ == '__main__':
    sys.exit(main(sys.argv))
