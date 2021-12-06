#!/usr/bin/env python3

# Determine language in freki extracts.

import sys
import logging

import cld3

from collections import Counter
from argparse import ArgumentParser

from common import is_prose_line
from loadfreki import load_freki_document
from logger import logger


# Default values for command-line arguments
DEFAULT_MIN_CHARS = 100
DEFAULT_MIN_PROBABILITY = 0.99


def argparser():
    ap = ArgumentParser()
    ap.add_argument(
        '--min-probability',
        type=float,
        default=DEFAULT_MIN_PROBABILITY,
        help='minimum langid probability to include'
    )
    ap.add_argument(
        '--min-chars',
        type=int,
        default=DEFAULT_MIN_CHARS,
        help='minimum number of characters in blocks to langid'
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


def is_prose_block(block):
    prose_line_count = sum(is_prose_line(line.text) for line in block.lines)
    return prose_line_count >= len(block.lines)/2    # TODO parameterize


def nonspace_char_count(text):
    return len(''.join(c for c in text if not c.isspace()))


def detect_languages(document, args):
    languages = []
    for page in document.pages:
        for block in page.blocks:
            if is_prose_block(block):
                text = block.get_text()
                if nonspace_char_count(text) < args.min_chars:
                    logger.debug(f'ignore due to min_chars: "{text}"')
                    continue
                langid = cld3.get_language(text)
                if not langid.is_reliable:
                    logger.debug(f'ignore due to is_reliable: "{text}"')
                    continue
                if langid.probability < args.min_probability:
                    logger.debug(f'ignore due to min_probability: "{text}"')
                    continue
                languages.append(langid.language)
    return languages


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
        language_count = Counter(detect_languages(document, args))
        if not language_count:
            language_count = Counter(['unknown'])
        most_common = language_count.most_common(1)[0][0]
        languages = ','.join(l[0] for l in language_count.most_common(5))
        print(f'{fn} {most_common} ({languages})')


if __name__ == '__main__':
    sys.exit(main(sys.argv))
