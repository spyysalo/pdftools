#!/usr/bin/env python3

# Heuristically revise the freki block organization

import sys
import re
import logging

from argparse import ArgumentParser

from common import pairwise
from logger import logger
from loadfreki import BBox, Block, load_freki_document


def argparser():
    ap = ArgumentParser()
    ap.add_argument(
        '--max-join-relative-gap',
        type=float,
        default=0.8,
        help='maximum gap relative to font size to join lines'
    )
    ap.add_argument(
        '--min-split-relative-gap',
        type=float,
        default=1.0,
        help='maximum gap relative to font size to split lines'
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


def can_split(line1, line2, args):
    if not (line1.bbox.is_above(line2.bbox) or line2.bbox.is_above(line1.bbox)):
        return False
    line1_font_size = line1.max_font_size()
    line_font_size = line2.max_font_size()
    font_size = min(line1_font_size, line_font_size)
    min_distance = font_size * args.min_split_relative_gap
    return line1.bbox.vertical_distance(line2.bbox) >= min_distance


def split_page_blocks(page, args):
    while True:
        revised = False
        for block_idx, block in enumerate(page.blocks):
            for i in range(len(block.lines)-1):
                prev, line = block.lines[i], block.lines[i+1]
                if can_split(prev, line, args):
                    new_block = Block(
                        doc_id=block.doc_id,
                        page_index=block.page_index,
                        block_id=f'{block.id}.2',
                        bbox=line.bbox,
                        label=f'{block.label}b',
                        start_line=line.line_num,
                        end_line=block.lines[-1].line_num,
                        page=block.page,
                        document=block.document
                    )
                    block.id = f'{block.id}.1'
                    block.label = f'{block.label}t'
                    block.end_line = prev.line_num
                    split_lines = block.lines[i+1:]
                    block.remove_lines(split_lines)
                    new_block.add_lines(split_lines)
                    page.blocks.insert(block_idx+1, new_block)
                    revised = True
                    break
        if not revised:
            break


def can_join(block1, block2, args):
    # ignore empty blocks
    if len(block1.lines) == 0 or len(block2.lines) == 0:
        return False
    # only consider blocks with a consistent font size
    if (block1.min_font_size() != block1.max_font_size() or
        block2.min_font_size() != block2.max_font_size() or
        block1.min_font_size() != block2.min_font_size()):
        return False
    # only consider blocks with a consistent left margin
    # TODO: add non-zero tolerance
    if (block1.min_llx() != block1.max_llx() or
        block2.min_llx() != block2.max_llx() or
        block1.min_llx() != block2.max_llx()):
        return False
    font_size = block1.min_font_size()
    max_distance = font_size * args.max_join_relative_gap
    return (
        block1.bbox.is_above(block2.bbox) and
        block1.bbox.vertical_distance(block2.bbox) <= max_distance
    )


def join_page_blocks(page, args):
    # join blocks heuristically estimated to be compatible
    while True:
        revised = False
        for i in range(len(page.blocks)-1):
            prev, block = page.blocks[i], page.blocks[i+1]
            if can_join(prev, block, args):
                for line in block.lines:
                    prev.add_line(line)
                page.blocks.remove(block)
                revised = True
                break
        if not revised:
            break


def revise_document_blocks(document, args):
    # only perform block rearrangement within pages
    for page in document.pages:
        split_page_blocks(page, args)
        join_page_blocks(page, args)


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
        revise_document_blocks(document, args)
        print(document.to_freki())


if __name__ == '__main__':
    sys.exit(main(sys.argv))
