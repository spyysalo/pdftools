from itertools import tee


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
