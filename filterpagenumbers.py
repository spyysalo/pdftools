#!/usr/bin/env python3

import sys
import os
import re
import logging

from collections import defaultdict
from string import punctuation
from argparse import ArgumentParser

from loadfreki import load_freki_document


logging.basicConfig()
logger = logging.getLogger(os.path.basename(__file__))


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


class PageNumberCandidate:
    def __init__(self, page_index, number, shape, line):
        self.page_index = page_index
        self.number = number
        self.shape = shape
        self.line = line

    def __lt__(self, other):
        # check both page index and the number so that the LIS
        # algorithm will only produce sequences where both increment
        return self.page_index < other.page_index and self.number < other.number

    def __str__(self):
        return f'PageNumberCandidate({self.page_index}, {self.number}, {self.shape})'

    def __repr__(self):
        return self.__str__()


def longest_increasing_subsequence(seq):
    # O(n log n) implementation following
    # https://en.wikipedia.org/wiki/Longest_increasing_subsequence
    min_idx = [0] * (len(seq)+1)
    pred = [0] * len(seq)
    max_len = 0
    for i in range(0, len(seq)):
        # Binary search for the largest positive j <= max_len such
        # that seq[min_idx[j]] < seq[i]
        lo = 1
        hi = max_len + 1
        while lo < hi:
            mid = lo + int((hi-lo)/2)
            if seq[min_idx[mid]] < seq[i]:
                lo = mid + 1
            else:
                hi = mid

        # lo is 1 greater than the length of the longest prefix of seq[i]
        new_len = lo

        # predecessor of seq[i] is the last index of the subsequence
        # of length new_len-1
        pred[i] = min_idx[new_len-1]
        min_idx[new_len] = i

        if new_len > max_len:
            # found subsequence longer than any found yet
            max_len = new_len

    # reconstruct
    lis = [0] * max_len
    k = min_idx[max_len]
    for i in reversed(range(0, max_len)):
        lis[i] = seq[k]
        k = pred[k]

    return lis


def ispunct(string):
    return string and all(c in punctuation for c in string)


def parse_page_number_line(string):
    """Parse line with page number, return number and line shape string."""
    parts = string.split()    # TODO finer-grained tokenization?

    # require that space-separated parts contain exactly one number
    # and that all other parts (if any) are punctuation.
    numbers = [p for p in parts if p.isdigit()]
    nonnumbers = [p for p in parts if not p.isdigit()]
    if len(numbers) != 1 or not all(ispunct(p) for p in nonnumbers):
        raise ValueError(f'failed to parse page number line: {string}')

    number = int(numbers[0])
    shape = ' '.join(p if not p.isdigit() else '<NUM>' for p in parts)
    return number, shape


def page_number_candidates(document):
    candidates = []
    for block in document.blocks:
        for line in block.lines:
            try:
                number, shape = parse_page_number_line(line.text)
            except ValueError:
                continue    # not a page number line
            page_index = block.page_index
            candidate = PageNumberCandidate(page_index, number, shape, line)
            candidates.append(candidate)
    return candidates


def _subsequences(seq, candidate_map):
    # Recursive implementation for candidate_sequences()
    if not seq:
        yield []
    else:
        first, rest = seq[0], seq[1:]
        for c in candidate_map[first]:
            for s in _subsequences(rest, candidate_map):
                yield [c] + s


def candidate_sequences(sequence, candidates):
    # Map (page_index, number) to candidates
    candidates_by_index_and_number = defaultdict(list)
    for c in candidates:
        candidates_by_index_and_number[(c.page_index, c.number)].append(c)
    # TODO this risks a combinatorial explosion
    return list(_subsequences(sequence, candidates_by_index_and_number))


def find_page_number_lines(document, args):
    candidates = page_number_candidates(document)
    if not candidates:
        return []

    # Group candidates by line shape (e.g. "- <NUM> -") and font into
    # compatibly-formatted sequences
    candidate_groups = defaultdict(list)
    for c in candidates:
        candidate_groups[(c.shape, c.line.fonts[0])].append(c)

    # Find longest incrementing subsequence of numbers and page indices
    # from each group, and pick longest
    group_lis = {
        k: longest_increasing_subsequence(v)
        for k, v in candidate_groups.items()
    }
    lis_key, lis = max(group_lis.items(), key=lambda kv: len(kv[1]))

    # There may be more than one set of candidates that could produce
    # the LIS. Get the (page_index, number) from the LIS and find all
    # candidate sequences that can produce it
    lis_sequence = [(c.page_index, c.number) for c in lis]
    sequences = candidate_sequences(lis_sequence, candidate_groups[lis_key])

    if not sequences:
        logger.error(f'failed to recreate candidate sequence')
        return []
    elif len(sequences) == 1:
        selected_sequence = sequences[0]
    elif len(sequences) > 2:
        logger.warning(f'found {len(sequences)} possible page number sequences')
        selected_sequence = sequences[0]    # TODO pick heuristically

    # TODO add a "repair" step that does approximate matching;
    # e.g. sometimes page number fonts differ
    # TODO check for minimum length
    return [c.line for c in selected_sequence]


def main(argv):
    args = argparser().parse_args(argv[1:])

    if args.debug:
        logger.setLevel(logging.DEBUG)
    else:
        logger.setLevel(logging.INFO)

    for fn in args.freki:
        document = load_freki_document(fn, args)
        lines = find_page_number_lines(document, args)
        logger.debug(f'removing {len(lines)}/{len(document.pages)} from {fn}')
        document.remove_lines(lines)
        print(document)


if __name__ == '__main__':
    sys.exit(main(sys.argv))
