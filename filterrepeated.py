#!/usr/bin/env python3

# Filter repeated elements (e.g. headers and footers) from freki text.

import sys
import re
import logging

from collections import defaultdict
from argparse import ArgumentParser

from loadfreki import load_freki_document
from logger import logger


def argparser():
    ap = ArgumentParser()
    ap.add_argument(
        '--max-distance-from-margin',
        type=float,
        default=50.0,
        help='maximum repeated element distance from margin'
    )
    ap.add_argument(
        '--min-page-ratio',
        type=float,
        default=1/4,
        help='minimum ratio of pages containing a repeated element'
    )
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


def normalize_text(text):
    text = text.strip()
    text = re.sub(r'\d+', '<NUM>', text)
    text = re.sub(r'\s+', '', text)
    return text


def block_group_key(block, roundto=10):
    text = normalize_text(block.get_text())
    lly = round(block.bbox.lly/roundto)*roundto
    return (text, lly)


def find_repeated_elements(document, args):
    group_blocks = defaultdict(list)
    for page in document.pages:
        if not page.blocks:
            continue
        bbox = page.bbox
        for block in page.blocks:
            min_distance = min(
                block.bbox.distance_from_top(bbox),
                block.bbox.distance_from_bottom(bbox)
            )
            if min_distance <= args.max_distance_from_margin:
                key = block_group_key(block)
                group_blocks[key].append(block)

    repeated_element_lines = []
    for key, blocks in group_blocks.items():
        pages = set(block.page_index for block in blocks)
        if (len(blocks) > 1 and
            len(pages)/len(document.pages) >= args.min_page_ratio):
            for block in blocks:
                repeated_element_lines.extend(block.lines)
    return repeated_element_lines


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
        lines = find_repeated_elements(document, args)
        if lines:
            ratio = len(lines)/len(document.pages)
            logger.info(
                f'removing {len(lines)} repeated element lines from '
                f'{len(document.pages)} pages ({ratio:.1%}) in {fn}'
            )
            document.remove_lines(lines)
        print(document.to_freki())


if __name__ == '__main__':
    sys.exit(main(sys.argv))
