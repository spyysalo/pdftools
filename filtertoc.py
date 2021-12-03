#!/usr/bin/env python3

import sys
import os
import re
import logging

from collections import defaultdict
from argparse import ArgumentParser

from common import is_prose_line, longest_increasing_subsequence
from loadfreki import load_freki_document


logging.basicConfig()
logger = logging.getLogger(os.path.basename(__file__))


# Regular expression for potential TOC lines: lines ending with digits
# that have a minimum number of consequtive alphabetic characters.
TOC_LINE_RE = re.compile(r'^([\W0-9]*[^\W0-9]{3}.*?\b)(?:\d+-)?(\d+)\s*$')

# Regular expression for rejecting coincidental TOC line matches
REJECT_TOC_LINE_START_RE = re.compile(r'.*\w[.,:;-]$')

# Words indicating first section in TOC (TODO: add more; other languages)
FIRST_SECTION_WORDS = {
    'introduction', 'johdanto', 'inledning',
    'abstract', 'tiivistelmä',
    'foreword', 'alkusanat',
    'preface', 'esipuhe', 'johdanto',
}


def argparser():
    ap = ArgumentParser()
    ap.add_argument(
        '--relative-toc-location',
        type=float,
        default=1/3,
        help='how far into the document to look into for TOC'
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


class TocLineCandidate:
    def __init__(self, page_index, number, line):
        self.page_index = page_index
        self.number = number
        self.line = line

    def __lt__(self, other):
        # allow equality for both page index and number so that the LIS
        # algorithm will two sections on the same page
        return (self.page_index <= other.page_index and
                self.number <= other.number)

    def __str__(self):
        return f'TocLineCandidate({self.page_index}, {self.number})'

    def __repr__(self):
        return self.__str__()


def parse_toc_line(string):
    m = TOC_LINE_RE.match(string)
    if not m:
        raise ValueError(f'failed to parse TOC line: {string}')
    start, number = m.groups()
    m = REJECT_TOC_LINE_START_RE.match(start)
    if m:
        logger.debug(f'reject "{start}{number}"')
        raise ValueError(f'failed to parse TOC line: {string}')
    number = int(number)
    return number


def toc_candidates(document, args):
    last_toc_page = int(len(document.pages) * args.relative_toc_location)
    candidates = []
    for page in document.pages[:last_toc_page]:
        for block in page.blocks:
            for line in block.lines:
                try:
                    number = parse_toc_line(line.text)
                except ValueError:
                    continue    # not a TOC line
                page_index = block.page_index
                candidate = TocLineCandidate(page_index, number, line)
                candidates.append(candidate)
    return candidates


def lines_between(document, first, last):
    lines, first_seen = [], False
    for page in document.pages:
        for block in page.blocks:
            for line in block.lines:
                if line == first:
                    first_seen = True
                if first_seen:
                    lines.append(line)
                if line == last:
                    if not first_seen:
                        raise ValueError(f'failed to find {first}')
                    return lines
    raise ValueError(f'failed to find {last}')


def trim_candidates(document, candidates, args):
    # trim implausible candidates from a TOC sequence
    def possible_toc_sequence(seq):
        if len(seq) < 2:
            return False
        page_count = len(document.pages)
        page_span = seq[-1].number - seq[0].number
        # potential page number span can't overextend the number of
        # actual pages
        if page_span > page_count:
            return False
        return True

    while not possible_toc_sequence(candidates):
        if len(candidates) < 2:
            return []    # trimmed to nothing
        # TODO determine which end to trim with
        candidates = candidates[:-1]
    return candidates


def includes_toc_start(candidates):
    # attempts to determine if the candidates include the TOC start
    if not candidates:
        return False
    elif candidates[0].number == 1:
        return True    # assume page 1 is first in TOC

    first_line_text = candidates[0].line.text.strip().lower()
    if first_line_text.startswith('1'):
        return True
    elif any(first_line_text.startswith(d) for d in '23456789'):
        return False
    elif any(w in first_line_text for w in FIRST_SECTION_WORDS):
        return True

    logger.debug(f'unsure if TOC start: {first_line_text}')
    return False


def find_toc_lines(document, args):
    candidates = toc_candidates(document, args)

    # group by page
    candidates_by_page = defaultdict(list)
    for c in candidates:
        candidates_by_page[c.page_index].append(c)

    if not candidates:
        return []    # nothing found

    lis_by_page_range = {}
    def best_candidates_for_page_range(start_page, end_page=None):
        if end_page is None:
            end_page = start_page
        key = (start_page, end_page)
        if key not in lis_by_page_range:
            range_candidates = sum([
                candidates_by_page[i]
                for i in range(start_page, end_page+1)
            ], [])
            lis = longest_increasing_subsequence(range_candidates)
            lis = trim_candidates(document, lis, args)
            lis_by_page_range[key] = lis
        return lis_by_page_range[key]

    # start from page with longest LIS
    lis_by_page = {
        i: best_candidates_for_page_range(i)
        for i in candidates_by_page.keys()
    }
    toc_page = max(lis_by_page, key=lambda i: len(lis_by_page[i]))

    if len(lis_by_page[toc_page]) < 2:
        return []    # no plausible sequences

    # expand to include candidates on surrounding pages while this
    # increases the length of the LIS
    start_page = end_page = toc_page
    best_seq = lis_by_page[toc_page]

    first_page = document.pages[0].page_index
    while start_page > first_page:
        if includes_toc_start(best_seq):
            break    # already covers the full TOC
        extended = best_candidates_for_page_range(start_page-1, end_page)
        if len(extended) < len(best_seq) + 2:
            break    # insufficient extension
        else:
            start_page -= 1
            best_seq = extended

    last_page = document.pages[-1].page_index
    while end_page < last_page:
        extended = best_candidates_for_page_range(start_page, end_page+1)
        if len(extended) < len(best_seq) + 2:
            break    # insufficient extension
        else:
            end_page += 1
            best_seq = extended

    # pick lines between the first and last
    toc_lines = [c.line for c in best_seq]
    toc_range_lines = lines_between(document, toc_lines[0], toc_lines[-1])

    # check how many of the lines in the span are TOC lines
    line_ratio = len(toc_lines)/len(toc_range_lines)
    if line_ratio < 0.2:
        logger.info(f'rejecting low TOC line/TOC span ratio {line_ratio:.1%}')
        return []
    elif line_ratio < 0.5:
        logger.warning(f'low TOC line/TOC span ratio {line_ratio:.1%} '
                       f'({len(toc_lines)}/{len(toc_range_lines)}) '
                       f'in {document.id}')

    return toc_range_lines


def prose_lines(lines):
    return [line for line in lines if is_prose_line(line.text)]


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
        lines = find_toc_lines(document, args)

        # sanity check: if the heuristic returns more than a threshold
        # proprortion of (apparent) prose lines, reject the candidate
        if lines and len(prose_lines(lines))/len(lines) > 0.8:
            logger.warning('rejecting prose block in {fn}')
        else:
            logger.debug(f'removing {len(lines)} lines from {fn}')
            document.remove_lines(lines)
        print(document.to_freki())


if __name__ == '__main__':
    sys.exit(main(sys.argv))
