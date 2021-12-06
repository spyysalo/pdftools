#!/usr/bin/env python3

# Heuristically determines whether a PDF is likely scanned by
# determining the average coverage of page area by images.

import sys
import os
import logging

from typing import Iterable
from multiprocessing import Process, Queue
from argparse import ArgumentParser

from pdfminer.layout import LAParams, LTImage
from pdfminer.high_level import extract_pages


logging.basicConfig()
logger = logging.getLogger(os.path.basename(__file__))


def argparser():
    ap = ArgumentParser()
    ap.add_argument(
        '--timeout',
        type=int,
        default=60,
        help='timeout per file in seconds'
    )
    ap.add_argument(
        '--min-coverage',
        type=float,
        default=0.9,
        help='minimum average image to page ratio'
    )
    ap.add_argument(
        '--debug',
        default=False,
        action='store_true',
        help='debug output'
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
    for i, page in enumerate(extract_pages(fn, laparams=laparams)):
        overlaps = [0]
        for image in find_images(page, args):
            isect = intersection(page.bbox, image.bbox)
            overlaps.append(area(isect)/area(page.bbox))
        # TODO consider intersecting images instead of simple max
        logger.debug(f'page {i}: {max(overlaps):.1%}')
        page_coverage.append(max(overlaps))
    avg_coverage = sum(page_coverage)/len(page_coverage)
    logger.info(
        f'{fn}: average coverage {avg_coverage:.1%}, '
        'values {}'.format(','.join(f'{c:.1%}' for c in page_coverage))
    )
    is_scanned = avg_coverage >= args.min_coverage
    return is_scanned


def mp_run(func, queue, args):
    try:
        retval = func(*args)
        queue.put(retval)
    except Exception as e:
        logger.error(f'{func.__name__} failed with exception: {e}')
        queue.put(type(e).__name__)


def run_with_timeout(func, args, timeout):
    queue = Queue()
    process = Process(target=mp_run, args=(func, queue, args))
    process.start()
    process.join(timeout)
    if process.exitcode is not None:
        # completed
        return queue.get()
    else:
        # timeout
        process.terminate()
        return None


def main(argv):
    args = argparser().parse_args(argv[1:])

    if args.debug:
        logger.setLevel(logging.DEBUG)
    elif args.verbose:
        logger.setLevel(logging.INFO)

    found_scanned = False
    for fn in args.pdf:
        logger.debug(f'start {fn}')
        try:
            # run with timeout to avoid hangs
            is_scanned = run_with_timeout(
                pdf_is_scanned,
                (fn, args),
                args.timeout
            )
            if is_scanned is None:
                logger.error(f'timeout for {fn}')
                print(f'timeout {fn}')
            elif not isinstance(is_scanned, bool):
                print(f'ERROR:{is_scanned} {fn}')                
            else:
                found_scanned |= is_scanned
                print(f'{is_scanned} {fn}')
        except Exception as e:
            logger.error(f'failed to parse {fn}: {e}')
        logger.debug(f'end {fn}')

    # invert for shell
    return 0 if found_scanned else 1


if __name__ == '__main__':
    sys.exit(main(sys.argv))
