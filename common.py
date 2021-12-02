import re

from enum import Enum, auto
from itertools import tee
from string import punctuation


# Heuristic constants
MIN_NONSPACE_CHARS = 10
MAX_PUNCT_RATIO = 0.5
MAX_DIGIT_RATIO = 0.5
MAX_UPPER_RATIO = 0.25
MAX_FOREIGN_RATIO = 0.1
MIN_WORDS = 3


# Characters recognized as "regular" lower- and uppercase alphabetic
# characters. This would need to change to support languages with
# characters outside the Basic Latin and Latin-1 Unicode blocks.
CHAR_RANGE = [chr(i) for i in range(0x00, 0xFF)]
LC_CHARS = ''.join(c for c in CHAR_RANGE if c.isalpha() and c.islower())
UC_CHARS = ''.join(c for c in CHAR_RANGE if c.isalpha() and c.isupper())

# Heuristic for "regular" word: sequence of at least three lower-case
# characters delimited by word boundaries.
WORD_RE = re.compile(r'\b['+LC_CHARS+r']{3,}\b')

# Capitalized word: number of upper case characteres optionally
# followed by lower-case characters delimited by word boundaries.
CAP_WORD_RE = re.compile(r'\b['+UC_CHARS+r']+['+LC_CHARS+r']*\b')

# Unicode letter that is not part of the "regular" alphabet
# (https://stackoverflow.com/a/6314634)
FOREIGN_LETTER_RE = re.compile(r'[^\W\d_'+LC_CHARS+UC_CHARS+r']')

# Number-like strings
NUMBER_RE = re.compile(r'[0-9][0-9.,]*')


class LineCategory(Enum):
    BLANK = auto()
    SHORT = auto()
    DIGIT = auto()
    PUNCT = auto()
    UPPER = auto()
    MINWD = auto()
    FORGN = auto()
    CAPWD = auto()
    MIXED = auto()
    PROSE = auto()


def nonspace_count(line):
    return sum(1 for c in line if not c.isspace())


def digit_count(line):
    return sum(1 for c in line if c.isdigit())


def upper_count(line):
    return sum(1 for c in line if c.isupper())


def punct_count(line):
    return sum(1 for c in line if c in punctuation)


def foreign_count(line):
    return len(FOREIGN_LETTER_RE.findall(line))


def num_cap_words(line):
    return len(CAP_WORD_RE.findall(line))


def num_words(line):
    return len(WORD_RE.findall(line))


def is_blank_line(line):
    return line.strip() == ''


def is_short_line(line):
    return nonspace_count(line) <= MIN_NONSPACE_CHARS


def is_digit_line(line):
    return digit_count(line)/nonspace_count(line) > MAX_DIGIT_RATIO


def is_upper_line(line):
    return upper_count(line)/nonspace_count(line) > MAX_UPPER_RATIO


def is_punct_line(line):
    return punct_count(line)/nonspace_count(line) > MAX_PUNCT_RATIO


def is_foreign_line(line):
    return foreign_count(line)/nonspace_count(line) > MAX_FOREIGN_RATIO


def is_cap_word_line(line):
    return num_cap_words(line) > max(MIN_WORDS, 2*num_words(line))


def is_min_word_line(line):
    return num_words(line) < MIN_WORDS


LINE_CATEGORY_FUNCS = [
    (is_blank_line, LineCategory.BLANK),
    (is_short_line, LineCategory.SHORT),
    (is_digit_line, LineCategory.DIGIT),
    (is_upper_line, LineCategory.UPPER),
    (is_punct_line, LineCategory.PUNCT),
    (is_foreign_line, LineCategory.FORGN),
    (is_cap_word_line, LineCategory.CAPWD),
    (is_min_word_line, LineCategory.MINWD),
]


def categorize_line(line):
    for func, category in LINE_CATEGORY_FUNCS:
        if func(line):
            return category
    return LineCategory.PROSE    # prose by default


def is_prose_line(line):
    return categorize_line(line) == LineCategory.PROSE


def pairwise(iterable):
    # Only available since Python 3.10
    # pairwise('ABCDEFG') --> AB BC CD DE EF FG
    a, b = tee(iterable)
    next(b, None)
    return zip(a, b)


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
