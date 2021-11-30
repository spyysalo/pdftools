from itertools import tee


def pairwise(iterable):
    # Only available since Python 3.10
    # pairwise('ABCDEFG') --> AB BC CD DE EF FG
    a, b = tee(iterable)
    next(b, None)
    return zip(a, b)
