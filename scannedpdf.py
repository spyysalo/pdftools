#!/usr/bin/env python3

# Heuristically determines whether a PDF is likely scanned by
# determining the average coverage of page area by images.

import sys
import os
import logging

from typing import Iterable
from argparse import ArgumentParser

from pdfminer.layout import LAParams, LTImage
from pdfminer.high_level import extract_pages


logging.basicConfig()
logger = logging.getLogger(os.path.basename(__file__))


def argparser():
    ap = ArgumentParser()
    ap.add_argument(
        '--min-coverage',
        type=float,
        default=0.9,
        help='minimum average image to page ratio'
    )
    ap.add_argument(
        '--verbose',
        default=False,
        action='store_true',
        help='verbose output'
    )
    ap.add_argument(
        'pdf',
        nargs='+',
        help='pdf file(s)'
    )
    return ap


def find_images(layoutitem, args):
    if isinstance(layoutitem, LTImage):
        yield layoutitem
    if isinstance(layoutitem, Iterable):
        for child in layoutitem:
            yield from find_images(child, args)


def area(bbox):
    if bbox[0] > bbox[2] or bbox[1] > bbox[3]:
        return 0
    else:
        return (bbox[2]-bbox[0])*(bbox[3]-bbox[1])


def intersection(bbox1, bbox2):
    return (
        max(bbox1[0], bbox2[0]),
        max(bbox1[1], bbox2[1]),
        min(bbox1[2], bbox2[2]),
        min(bbox1[3], bbox2[3]),
    )


def pdf_is_scanned(fn, args):
    laparams = LAParams()
    page_coverage = []
    for page in extract_pages(fn, laparams=laparams):
        overlaps = [0]
        for image in find_images(page, args):
            isect = intersection(page.bbox, image.bbox)
            overlaps.append(area(isect)/area(page.bbox))
        # TODO consider intersecting images instead of simple max
        page_coverage.append(max(overlaps))
    avg_coverage = sum(page_coverage)/len(page_coverage)
    logger.info(
        f'{fn}: average coverage {avg_coverage:.1%}, '
        'values {}'.format(','.join(f'{c:.1%}' for c in page_coverage))
    )
    return avg_coverage >= args.min_coverage


def main(argv):
    args = argparser().parse_args(argv[1:])

    if args.verbose:
        logger.setLevel(logging.INFO)

    found_scanned = False
    for fn in args.pdf:
        try:
            is_scanned = pdf_is_scanned(fn, args)
            found_scanned |= is_scanned
            print(f'{is_scanned} {fn}')
        except Exception as e:
            logger.error(f'failed to parse {fn}: {e}')

    # invert for shell
    return 0 if found_scanned else 1


if __name__ == '__main__':
    sys.exit(main(sys.argv))
