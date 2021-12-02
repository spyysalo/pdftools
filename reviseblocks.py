#!/usr/bin/env python3

# Heuristically revise the freki block organization

import sys
import re
import logging

from collections import Counter
from argparse import ArgumentParser

from common import is_prose_line
from loadfreki import BBox, Block, load_freki_document
from logger import logger


DEFAULT_JOIN_GAP = 0.8
DEFAULT_SPLIT_GAP = 1.0


def argparser():
    ap = ArgumentParser()
    ap.add_argument(
        '--max-join-relative-gap',
        type=float,
        default=None,
        help='maximum gap relative to font size to join lines'
    )
    ap.add_argument(
        '--min-split-relative-gap',
        type=float,
        default=DEFAULT_SPLIT_GAP,
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
    split_count = 0
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
        if revised:
            split_count += 1
        else:
            break
    return split_count


def compatible_blocks(block1, block2):
    # require non-empty
    if len(block1.lines) == 0 or len(block2.lines) == 0:
        return False
    # require consistent font size
    if (block1.min_font_size() != block1.max_font_size() or
        block2.min_font_size() != block2.max_font_size() or
        block1.min_font_size() != block2.min_font_size()):
        return False
    # require consistent left margin
    # TODO: add non-zero tolerance
    if (block1.min_llx() != block1.max_llx() or
        block2.min_llx() != block2.max_llx() or
        block1.min_llx() != block2.max_llx()):
        return False
    return True


def compatible_lines(line1, line2):
    if line1 is None or line2 is None:
        return False
    # require consistent font size
    if (line1.min_font_size() != line1.max_font_size() or
        line2.min_font_size() != line2.max_font_size() or
        line1.min_font_size() != line2.min_font_size()):
        return False
    # require consistent left margin
    if line1.bbox.llx != line2.bbox.llx:
        return False
    return True


def can_join(block1, block2, args):
    if not compatible_blocks(block1, block2):
        return False
    font_size = block1.min_font_size()
    max_distance = font_size * args.max_join_relative_gap
    return (
        block1.bbox.is_above(block2.bbox) and
        block1.bbox.vertical_distance(block2.bbox) <= max_distance
    )


def join_page_blocks(page, args):
    # join blocks heuristically estimated to be compatible
    join_count = 0
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
        if revised:
            join_count += 1
        else:
            break
    return join_count


def is_prose_block(block):
    prose_line_count = sum(is_prose_line(line.text) for line in block.lines)
    return prose_line_count >= len(block.lines)/2    # TODO parameterize


def most_common_prose_line_gap(document, args, roundto=0.1):
    # determine the most common gap size (relative to font size) between
    # two consecutive prose lines.
    gap_count = Counter()
    for page in document.pages:
        prev_line = None
        for block in page.blocks:
            for line in block.lines:
                if (compatible_lines(prev_line, line) and
                    prev_line.bbox.is_above(line.bbox)):
                    distance = prev_line.bbox.vertical_distance(line.bbox)
                    font_size = line.max_font_size()
                    relative_gap = distance/font_size
                    relative_gap = round(relative_gap/roundto)*roundto
                    gap_count[relative_gap] += 1
                prev_line = line

    total_count = sum(gap_count.values())
    if total_count < 10:    # not enough data
        return DEFAULT_JOIN_GAP
    most_common = gap_count.most_common(1)[0][0]
    if most_common < DEFAULT_JOIN_GAP:
        logger.warning(f'using {DEFAULT_JOIN_GAP:.2f} instead of smaller '
                       f'estimated gap {most_common:.2f}')
        return DEFAULT_JOIN_GAP
    else:
        return most_common


def revise_document_blocks(document, args):
    stored_gap = args.max_join_relative_gap
    if args.max_join_relative_gap is None:
        # determine heuristically
        roundto = 0.1
        gap = most_common_prose_line_gap(document, args) + roundto/2
        gap = min(gap, args.min_split_relative_gap-roundto/2)
        args.max_join_relative_gap = gap

    # only perform block rearrangement within pages
    split_count, join_count = 0, 0
    for page in document.pages:
        split_count += split_page_blocks(page, args)
        join_count += join_page_blocks(page, args)

    args.max_join_relative_gap = stored_gap
    return split_count, join_count


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
        split_count, join_count = revise_document_blocks(document, args)
        logger.info(f'split {split_count}, joined {join_count} in {fn}')
        print(document.to_freki())


if __name__ == '__main__':
    sys.exit(main(sys.argv))
