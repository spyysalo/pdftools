#!/usr/bin/env python3

# Heuristically extracts body text from freki.

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
        except ValueError as e:
            logger.error(f'failed to load {fn}: {e}')
            continue
        body_font_name, body_font_size = document.most_common_font()
        logger.debug(f'body font: {body_font_name}-{body_font_size}"')
        body_line_width = document.most_common_line_width(
            font_name=body_font_name,
            font_size=body_font_size,
            roundto=50
        )
        logger.debug(f'body line width: {body_line_width}')
        body_bbox_llx = document.most_common_bbox_llx(
            font_name=body_font_name,
            font_size=body_font_size,
            roundto=10
        )
        bbox = BBox(body_bbox_llx, None, None, None)
        logger.debug(f'body text bbox: {bbox}')
        selected = document.select_blocks(
            font_name=body_font_name,
            font_size=body_font_size,
            width=body_line_width,
            width_range=50,
            bbox=bbox,
            bbox_range=10
        )
        for block in selected:
            for line in block.lines:
                print(line.text)
            print()


if __name__ == '__main__':
    sys.exit(main(sys.argv))
