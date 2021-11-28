#!/usr/bin/env python3

import sys
import os
import re
import logging

from collections import Counter
from argparse import ArgumentParser


logging.basicConfig()
logger = logging.getLogger(os.path.basename(__file__))


# Regular expressions for parsing Freki format
# (see https://github.com/xigt/freki/blob/master/doc/Format.md).
BLOCK_PREAMBLE_RE = re.compile(r'^doc_id=(\S+) page=(\d+) block_id=(\d+-\d+) bbox=(\S+) label=(\S*) (\d+) (\d+)$')

BLOCK_LINE_RE = re.compile(r'line=(\d+) fonts=(.*?) bbox=(\S+?)(?: iscore=(\d+\.\d+))?\s*:(.*)$')

FONT_RE = re.compile(r'(?:([A-Z]{6})\+)?(.+?)-(\d+\.\d+),?')


class EmptyBBOX(Exception):
    pass


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
        help='text file(s) extracted from PDF'
    )
    return ap


class Font:
    def __init__(self, tag, name, size):
        self.tag = tag
        self.name = name
        self.size = size

    def __eq__(self, other):
        # tag ignored intentionally
        return self.name == other.name and self.size == other.size

    def __hash__(self):
        # tag ignored intentionally
        return hash((self.name, self.size))

    def __str__(self):
        # tag omitted intentionally
        return f'Font("{self.name}-{self.size}")'

    def __repr__(self):
        return self.__str__()


class Document:
    def __init__(self, id_, blocks):
        self.id = id_
        self.blocks = []
        for block in blocks:
            self.add_block(block)
        self.pages = []
        for page in make_pages(blocks):
            self.add_page(page)

    def add_page(self, page):
        self.pages.append(page)
        page.document = self

    def add_block(self, block):
        assert block.doc_id == self.id
        self.blocks.append(block)
        block.document = self

    def remove_lines(self, lines):
        removed = 0
        for block in self.blocks:
            removed += block.remove_lines(lines)
        if removed != len(lines):
            logging.warning(f'only removed {removed}/{len(lines)}')
        return removed

    def _most_common_font_attribute(self, key, charset=None):
        font_char_count = self.char_count_by_font(charset)
        count_by_attrib = Counter()
        for font, count in font_char_count.items():
            count_by_attrib[key(font)] += count
        most_common, count = count_by_attrib.most_common(1)[0]
        total = sum(count_by_attrib.values())
        if count < total/2:    # TODO parameterize
            logger.warning(f'font attribute {most_common}" only used for '
                           f'{count/total:.1%} ({count}/{total}) of characters')
        return most_common


    def most_common_font_name(self, charset=None):
        """Return the name of the most common font."""
        return self._most_common_font_attribute(lambda f: f.name, charset)

    def most_common_font_size(self, charset=None):
        """Return the size of the most common font."""
        return self._most_common_font_attribute(lambda f: f.size, charset)

    def char_count_by_font(self, charset=None):
        total = Counter()
        for block in self.blocks:
            total.update(block.char_count_by_font(charset))
        return total

    def __str__(self):
        return '\n'.join(str(block) for block in self.blocks)


class Page:
    def __init__(self, page_index, document=None):
        self.page_index = page_index
        self.document = document
        self.blocks = []

    def add_block(self, block):
        assert block.page_index == self.page_index
        self.blocks.append(block)
        block.page = self

    def __str__(self):
        return '\n'.join(str(block) for block in self.blocks)


class Block:
    def __init__(self, doc_id, page_index, block_id, bbox, label, start_line,
                 end_line, page=None, document=None):
        self.doc_id = doc_id
        self.page_index = page_index
        self.block_id = block_id
        self.bbox = bbox
        self.label = label
        self.start_line = start_line
        self.end_line = end_line
        self.page = page
        self.document = document
        self.lines = []

    def add_line(self, line):
        self.lines.append(line)
        line.block = self

    def remove_lines(self, lines):
        removed = 0
        for l in lines:
            try:
                self.lines.remove(l)
                removed += 1
            except ValueError:
                pass    # not in this block
        return removed

    def char_count_by_font(self, charset=None):
        total = Counter()
        for line in self.lines:
            total.update(line.char_count_by_font(charset))
        return total

    def __str__(self):
        return '\n'.join(line.text for line in self.lines)

    @classmethod
    def from_freki(cls, line):
        m = BLOCK_PREAMBLE_RE.match(line)
        if not m:
            raise ValueError(f'failed to parse as Freki block preamble: {line}')
        doc_id, page, block_id, bbox, label, start_line, end_line = m.groups()
        page_index = int(page)
        bbox = parse_bbox(bbox)
        return cls(
            doc_id, page_index, block_id, bbox, label, start_line, end_line
        )


class Line:
    def __init__(self, line_num, fonts, bbox, iscore, text, block=None):
        self.line_num = line_num
        self.fonts = fonts
        self.bbox = bbox
        self.iscore = iscore
        self.text = text
        self.block = block

    def char_count_by_font(self, charset=None):
        if charset is None:
            # nonspace by default
            char_count = len(''.join(self.text.split()))
        else:
            char_count = sum(1 for c in self.text if c in charset)
        # if there are multiple fonts, count for each
        return Counter({ font: char_count for font in self.fonts })

    def __str__(self):
        return(f'{self.fonts} {self.bbox}: {self.text}')

    @classmethod
    def from_freki(cls, line):
        m = BLOCK_LINE_RE.match(line)
        if not m:
            raise ValueError(f'failed to parse as Freki block line: {line}')
        line_num, font_string, bbox, iscore, text = m.groups()
        bbox = parse_bbox(bbox)
        fonts = []
        # TODO check that RE matches everything except commas
        for tag, name, size in FONT_RE.findall(font_string):
            # for tags, see https://tex.stackexchange.com/a/156438
            fonts.append(Font(tag, name, float(size)))
        return cls(line_num, fonts, bbox, iscore, text)


def make_pages(blocks):
    """Group blocks into pages, return list of Page objects."""
    pages, current_page = [], None
    for block in blocks:
        if current_page is None or block.page_index != current_page.page_index:
            current_page = Page(block.page_index)
            pages.append(current_page)
        current_page.add_block(block)
    return pages


def parse_bbox(bbox):
    """Parse bounding box string, return lower left and upper right x and y."""
    if bbox == 'None,None,None,None':
        raise EmptyBBOX    # not sure why these occur
    try:
        coords = bbox.split(',')
        llx, lly, urx, ury = [float(c) for c in coords]
    except Exception as e:
        raise ValueError(f'failed to parse "{bbox}" as bounding box: {e}')
    return llx, lly, urx, ury


def load_freki_document(fn, args):
    blocks, current_block = [], None
    with open(fn) as f:
        for ln, line in enumerate(f, start=1):
            line = line.rstrip('\n')
            if BLOCK_PREAMBLE_RE.match(line):
                try:
                    current_block = Block.from_freki(line)
                    blocks.append(current_block)
                except EmptyBBOX:
                    logger.warning(f'empty bbox in {fn}')
            elif BLOCK_LINE_RE.match(line):
                current_block.add_line(Line.from_freki(line))
            elif not line:
                current_block = None
            else:
                raise ValueError(f'failed to parse line {ln} in {fn}: {line}')
    if not blocks:
        raise ValueError(f'no blocks found in {fn}')
    doc_ids = list(set([b.doc_id for b in blocks]))
    if len(doc_ids) > 1:
        raise ValueError(f'multiple doc ids in {fn}')
    return Document(doc_ids[0], blocks)


def main(argv):
    args = argparser().parse_args(argv[1:])

    if args.debug:
        logger.setLevel(logging.DEBUG)
    else:
        logger.setLevel(logging.INFO)

    for fn in args.freki:
        document = load_freki_document(fn, args)
        print(document)


if __name__ == '__main__':
    sys.exit(main(sys.argv))
