#!/usr/bin/env python3

# Read and write XML without modification using ElementTree to enable
# exact comparison.

import sys
import logging
import xml.etree.ElementTree as ET

from argparse import ArgumentParser


def argparser():
    ap = ArgumentParser()
    ap.add_argument(
        'xml',
        nargs='+',
        help='XML file(s)'
    )
    return ap


def main(argv):
    args = argparser().parse_args(argv[1:])

    for fn in args.xml:
        try:
            tree = ET.parse(fn)
            tree.write(
                sys.stdout,
                encoding='unicode',
                xml_declaration=True
            )
            sys.stdout.write('\n')
        except Exception as e:
            logging.error(f'failed processing {fn}: {e}')
            continue


if __name__ == '__main__':
    sys.exit(main(sys.argv))
