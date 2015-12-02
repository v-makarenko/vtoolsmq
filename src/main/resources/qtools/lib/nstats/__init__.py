import numpy as np
import math

# TODO put in utils, from StackOverflow originally, key=lambda x:x excluded,
# elements sorted
def percentile(N, percent, key=lambda x:x):
    if N is None or len(N) == 0:
        return None
    k = (len(N)-1) * percent
    f = math.floor(k)
    c = math.ceil(k)
    Np = sorted(N, key=key)
    if f == c:
        return key(Np[int(k)])
    d0 = key(Np[int(f)]) * (c-k)
    d1 = key(Np[int(c)]) * (k-f)
    return d0+d1

def moving_average(array, count, hfill=True):
    if hfill:
        extended_array = np.hstack([[array[0]]*(count-1), array, [array[-1]]*(count-1)])
    else:
        extended_array = array
    weightings = np.repeat(1.0, count) / count
    return np.convolve(extended_array, weightings,'same')[count:-(count-1)]

def moving_average_by_interval(array, interval_array, interval_width, count):
    """
    Returns a moving average along the set of intervals.  The count is the number
    of intervals to compute the average over.

    Returns (interval_tick, moving_average) for the interval widths bounded by the
    min/max of the interval_array.
    """
    bins, interval_avgs = zip(*interval_averages(array, interval_array, interval_width))
    moving_interval_avgs = moving_average(interval_avgs, count)
    return zip(bins, moving_interval_avgs)
    

def interval_averages(array, interval_array, interval_width, fill_blanks=True, blank_val=None):
    lowest_interval = min(interval_array)
    highest_interval = max(interval_array)
    low_start, rem = divmod(lowest_interval, interval_width)
    high_start, high_rem = divmod(highest_interval, interval_width)

    if high_rem:
        high_start = high_start+1
    bin_count = (high_start-low_start)+1
    bins = np.linspace(low_start*interval_width, high_start*interval_width, bin_count)
    digitized = np.digitize(interval_array, bins)

    indexable_array = np.array(array)
    interval_avgs = [indexable_array[digitized==i].mean() for i in range(1, len(bins)+1)]
    interval_avgs = []
    for i in range(1, len(bins)+1):
        interval_vals = indexable_array[digitized==i]
        if len(interval_vals) > 0:
            interval_avgs.append(interval_vals.mean())
        else:
            interval_avgs.append(blank_val)

    if fill_blanks:
        for i, val in enumerate(interval_avgs):
            if val is None and i > 0:
                interval_avgs[i] = interval_avgs[i-1]

        # now clean up the reverse
        lowest_filled_index = 0
        for i, val in enumerate(interval_avgs):
            if val is not None:
                lowest_filled_index = i
                break

        if lowest_filled_index > 0:
            interval_avgs[:lowest_filled_index] = [interval_avgs[lowest_filled_index]]*lowest_filled_index

    return zip(bins, interval_avgs)