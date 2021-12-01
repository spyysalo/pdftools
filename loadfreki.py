#!/usr/bin/env python3

import sys
import re
import logging

from copy import copy
from collections import Counter
from argparse import ArgumentParser

from logger import logger


# Regular expressions for parsing Freki format
# (see https://github.com/xigt/freki/blob/master/doc/Format.md).
BLOCK_PREAMBLE_RE = re.compile(r'^doc_id=(\S+) page=(\d+) block_id=(\S+) bbox=(\S+) label=(\S*) (\d+) (\d+)$')

BLOCK_LINE_RE = re.compile(r'line=(\d+) fonts=(.+?) bbox=(\S+?)(?: iscore=(\d+\.\d+))?(\s*):(.*)$')

FONT_RE = re.compile(r'(?:([A-Z]{6})\+)?(.+?)-(\d+\.\d+),?')


class EmptyBBox(Exception):
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
        help='freki file(s) extracted from PDF'
    )
    return ap


class BBox:
    def __init__(self, llx, lly, urx, ury):
        self.llx = llx
        self.lly = lly
        self.urx = urx
        self.ury = ury

    def width(self):
        return self.urx - self.llx

    def height(self):
        return self.ury - self.lly

    def is_above(self, other):
        return self.lly >= other.ury

    def contains(self, other):
        return (self.llx <= other.llx and
                self.lly <= other.lly and
                self.urx >= other.urx and
                self.ury >= other.ury)

    def expand_to_contain(self, other):
        self.llx = min(self.llx, other.llx)
        self.lly = min(self.lly, other.lly)
        self.urx = max(self.urx, other.urx)
        self.ury = max(self.ury, other.ury)

    def vertical_distance(self, other):
        if self.is_above(other):
            return self.lly - other.ury
        elif other.is_above(self):
            return other.lly - self.ury
        else:
            raise ValueError(f'neither above: {self} vs {other}')

    def to_freki(self):
        return f'{self.llx},{self.lly},{self.urx},{self.ury}'

    def __str__(self):
        return f'Bbox({self.llx}, {self.lly}, {self.urx}, {self.ury})'

    def __repr__(self):
        return self.__str__()


class Font:
    def __init__(self, tag, name, size):
        self.tag = tag
        self.name = name
        self.size = size

    def to_freki(self):
        if not self.tag:
            return f'{self.name}-{self.size}'
        else:
            return f'{self.tag}+{self.name}-{self.size}'

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
        self.pages = []
        for page in make_pages(blocks):
            self.add_page(page)

    @property
    def blocks(self):
        for page in self.pages:
            for block in page.blocks:
                yield block

    def add_page(self, page):
        self.pages.append(page)
        page.document = self

    def remove_lines(self, lines):
        removed = 0
        for page in self.pages:
            removed += page.remove_lines(lines)
        if removed != len(lines):
            logging.warning(f'only removed {removed}/{len(lines)}')
        return removed

    def most_common_font_name(self, charset=None):
        """Return the most common font name."""
        return self._most_common_font_attribute(
            lambda f: f.name, 'name', charset
        )

    def most_common_font_size(self, charset=None):
        """Return the most common font size."""
        return self._most_common_font_attribute(
            lambda f: f.size, 'size', charset
        )

    def most_common_font(self, charset=None):
        """Return the name and size of the most common font."""
        return self._most_common_font_attribute(
            lambda f: (f.name, f.size), 'name and size', charset
        )

    def most_common_line_width(self, font_name=None, font_size=None, roundto=1):
        return self._most_common_line_attribute(
            lambda line: line.bbox.width(), 'width',
            font_name=font_name, font_size=font_size, roundto=roundto
        )

    def most_common_bbox_llx(self, font_name=None, font_size=None, roundto=1):
        return self._most_common_line_attribute(
            lambda line: line.bbox.llx, 'bbox llx',
            font_name=font_name, font_size=font_size, roundto=roundto
        )

    def _most_common_font_attribute(self, key, label, charset=None):
        font_char_count = self.char_count_by_font(charset)
        count_by_attrib = Counter()
        for font, count in font_char_count.items():
            count_by_attrib[key(font)] += count
        most_common, count = count_by_attrib.most_common(1)[0]
        total = sum(count_by_attrib.values())
        if count < total/2:    # TODO parameterize
            logger.warning(
                f'most common font {label} {most_common} only used for '
                f'{count/total:.1%} ({count}/{total}) of characters '
                f'in {self.id}'
            )
        return most_common

    def _most_common_line_attribute(self, key, label, font_name=None,
                                    font_size=None, roundto=1):
        count_by_attrib = Counter()
        for block in self.blocks:
            for line in block.lines:
                value = round(key(line)/roundto) * roundto
                if line.has_font(font_name, font_size):
                    count_by_attrib[value] += 1
        most_common, count = count_by_attrib.most_common(1)[0]
        total = sum(count_by_attrib.values())
        if count < total/2:    # TODO parameterize
            logger.warning(
                f'most common line {label} {most_common} only used for '
                f'{count/total:.1%} ({count}/{total}) of lines '
                f'in {self.id}'
            )
        return most_common

    def select_blocks(self, font_name=None, font_size=None, width=None,
                      width_range=0, bbox=None, bbox_range=0):
        selected = []
        for block in self.blocks:
            if not block.has_font(font_name, font_size):
                logger.debug(
                    f'not selecting {block.id}: no font {font_name}-{font_size}'
                )
            elif (width is not None and
                  not block.width_matches(width, width_range)):
                logger.debug(f'not selecting {block.id}: not in {width}')
            elif (bbox is not None and
                  not block.bbox_matches(bbox, bbox_range)):
                logger.debug(f'not selecting {block.id}: not in {bbox}')
            else:
                logger.debug(f'selecting {block.id}')
                selected.append(block)
        return selected

    def char_count_by_font(self, charset=None):
        total = Counter()
        for block in self.blocks:
            total.update(block.char_count_by_font(charset))
        return total

    def to_freki(self):
        return '\n'.join(page.to_freki() for page in self.pages)

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

    def remove_lines(self, lines):
        removed = 0
        for block in self.blocks:
            removed += block.remove_lines(lines)
        return removed

    def to_freki(self):
        return '\n'.join(block.to_freki() for block in self.blocks)

    def __str__(self):
        return '\n'.join(str(block) for block in self.blocks)


class Block:
    def __init__(self, doc_id, page_index, block_id, bbox, label, start_line,
                 end_line, page=None, document=None):
        self.doc_id = doc_id
        self.page_index = page_index
        self.id = block_id
        self.bbox = copy(bbox)
        self.label = label
        self.start_line = start_line
        self.end_line = end_line
        self.page = page
        self.document = document
        self.lines = []

    def max_font_size(self, roundto=0.1):
        value = max(font.size for line in self.lines for font in line.fonts)
        return round(value/roundto) * roundto

    def min_font_size(self, roundto=0.1):
        value = min(font.size for line in self.lines for font in line.fonts)
        return round(value/roundto) * roundto

    def min_llx(self, roundto=1.0):
        value = min(line.bbox.llx for line in self.lines)
        return round(value/roundto) * roundto

    def max_llx(self, roundto=1.0):
        value = max(line.bbox.llx for line in self.lines)
        return round(value/roundto) * roundto

    def has_font(self, font_name, font_size):
        """Return True iff any Line in the Block has any text in the given
        font."""
        return any(line.has_font(font_name, font_size) for line in self.lines)

    def width_matches(self, value, tolerance):
        """Return True iff the width of the Block BBox is within the given
        range of the given value."""
        # TODO this function should be on BBox
        return value-tolerance <= self.bbox.width() <= value+tolerance

    def bbox_matches(self, bbox, tolerance):
        # TODO this function should be on BBox
        if all(v is None for v in (bbox.llx, bbox.lly, bbox.urx, bbox.ury)):
            logger.warning(f'bbox_matches with {bbox}')
        return all((
            (bbox.llx is None or
             (bbox.llx-tolerance <= self.bbox.llx <= bbox.llx+tolerance)),
            (bbox.lly is None or
             (bbox.lly-tolerance <= self.bbox.lly <= bbox.lly+tolerance)),
            (bbox.urx is None or
             (bbox.urx-tolerance <= self.bbox.urx <= bbox.urx+tolerance)),
            (bbox.ury is None or
             (bbox.ury-tolerance <= self.bbox.ury <= bbox.ury+tolerance)),
        ))

    def add_line(self, line):
        self.bbox.expand_to_contain(line.bbox)
        self.lines.append(line)
        line.block = self

    def add_lines(self, lines):
        for line in lines:
            self.add_line(line)

    def remove_lines(self, lines):
        removed = 0
        for l in lines:
            try:
                self.lines.remove(l)
                removed += 1
            except ValueError:
                pass    # not in this block
        if not self.lines:
            return removed    # TODO eliminate emptied block
        if removed:
            # rework bounding box
            self.bbox.llx = min(line.bbox.llx for line in self.lines)
            self.bbox.lly = min(line.bbox.lly for line in self.lines)
            self.bbox.urx = max(line.bbox.urx for line in self.lines)
            self.bbox.ury = max(line.bbox.ury for line in self.lines)
        return removed

    def char_count_by_font(self, charset=None):
        total = Counter()
        for line in self.lines:
            total.update(line.char_count_by_font(charset))
        return total

    def to_freki(self):
        preamble = (
            f'doc_id={self.doc_id} page={self.page_index} '+
            f'block_id={self.id} bbox={self.bbox.to_freki()} ' +
            f'label={self.label} {self.start_line} {self.end_line}'
        )
        return '\n'.join(
            [preamble] +
            [line.to_freki() for line in self.lines] +
            ['']
        )

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
    def __init__(self, line_num, fonts, bbox, iscore, blanks, text, block=None):
        self.line_num = line_num
        self.fonts = fonts
        self.bbox = bbox
        self.iscore = iscore
        self.blanks = blanks    # extra alignment space
        self.text = text
        self.block = block

    def max_font_size(self, roundto=0.1):
        value = max(font.size for font in self.fonts)
        return round(value/roundto) * roundto

    def min_font_size(self, roundto=0.1):
        value = min(font.size for font in self.fonts)
        return round(value/roundto) * roundto

    def char_count_by_font(self, charset=None):
        if charset is None:
            # nonspace by default
            char_count = len(''.join(self.text.split()))
        else:
            char_count = sum(1 for c in self.text if c in charset)
        # if there are multiple fonts, count for each
        return Counter({ font: char_count for font in self.fonts })

    def has_font(self, font_name, font_size):
        """Return True iff the Line has any text in the given font.
        The value None for name or size matches any font."""
        if font_name is None and font_size is None:
            logger.debug('has_font with (None, None)')
        return any(
            (font_name is None or font.name == font_name) and
            (font_size is None or font.size == font_size)
            for font in self.fonts
        )

    def to_freki(self):
        fonts = ','.join([font.to_freki() for font in self.fonts])
        if len(self.block.lines) == 1:
            iscore = ''    # no iscores for singletons
        elif self.iscore is not None:
            iscore = f' iscore={self.iscore:.2f}{self.blanks}'
        else:
            iscore = f'{self.blanks}'
        return (
            f'line={self.line_num} fonts={fonts} ' +
            f'bbox={self.bbox.to_freki()}{iscore}:{self.text}'
        )

    def __str__(self):
        return(f'{self.fonts} {self.bbox}: {self.text}')

    @classmethod
    def from_freki(cls, line):
        m = BLOCK_LINE_RE.match(line)
        if not m:
            raise ValueError(f'failed to parse as Freki block line: {line}')
        line_num, font_string, bbox, iscore, blanks, text = m.groups()
        bbox = parse_bbox(bbox)
        iscore = float(iscore) if iscore else None
        fonts = []
        # TODO check that FONT_RE matches everything except commas
        for tag, name, size in FONT_RE.findall(font_string):
            # for tags, see https://tex.stackexchange.com/a/156438
            fonts.append(Font(tag, name, float(size)))
        return cls(line_num, fonts, bbox, iscore, blanks, text)


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
        raise EmptyBBox    # not sure why these occur
    try:
        coords = bbox.split(',')
        llx, lly, urx, ury = [float(c) for c in coords]
        return BBox(llx, lly, urx, ury)
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
                except EmptyBBox:
                    logger.info(f'empty bbox in {fn}')
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
        try:
            document = load_freki_document(fn, args)
        except ValueError as e:
            logger.error(f'failed to load {fn}: {e}')
            continue
        print(document.to_freki())


if __name__ == '__main__':
    sys.exit(main(sys.argv))
