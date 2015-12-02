import numpy as np
import math

from pyqlb.factory import peak_dtype
from pyqlb.nstats.peaks import cluster_1d, cluster_2d, peak_times, fam_widths, rain_pvalues_thresholds
from pyqlb.nstats.peaks import channel_widths, channel_amplitudes, fam_amplitudes, vic_amplitudes, cluster_angle_ccw
from pyqlb.nstats import concentration
from pyqlb.nstats.well import well_static_width_gates, above_min_amplitude_peaks, accepted_peaks as well_accepted_peaks

# for backwards compatibility
def accepted_peaks(well):
    return well_accepted_peaks(well)


def total_events_amplitude_vals(well,ch):
    peaks = well.peaks
    return (np.mean(channel_amplitudes(peaks, ch)), np.std(channel_amplitudes(peaks, ch))) 

# TODO move into PyQLB?
def polydisperse_peaks(well, channel_num, threshold=None, pct_boundary=0.3, exclude_min_amplitude_peaks=True):
    """
    Returns a 3-tuple (4-tuple, 4-tuple, 2-tuple).  The first 4-tuple is:
    
    * positive rain above the width gates.
    * middle rain above the width gates.
    * middle rain below the width gates.
    * negative rain below the width gates.

    The second 4-tuple is:

    * positive rain boundary
    * middle rain upper boundary (can be None)
    * middle rain lower boundary (can be None)
    * negative rain boundary

    The last 2-tuple is:

    * computed min width gate
    * computed max width gate

    Positives & negatives are computed on the specified channel number.
    """
    if not threshold:
        threshold = well.channels[channel_num].statistics.threshold
    if not threshold:
        threshold = None
    
    # filter out min_amplitude_peaks
    if exclude_min_amplitude_peaks:
        peaks = above_min_amplitude_peaks(well)
    else:
        peaks = well.peaks

    p_plus, p, p_minus, pos, middle_high, middle_low, neg = \
            rain_pvalues_thresholds(peaks,
                                    channel_num=channel_num,
                                    threshold=threshold,
                                    pct_boundary=pct_boundary)
    
    min_gate, max_gate = well_static_width_gates(well)

    pos_peaks = np.extract(
        reduce(np.logical_and,
               (channel_widths(peaks, channel_num) > max_gate,
                channel_amplitudes(peaks, channel_num) > pos)),
        peaks)
    
    
    if middle_high and middle_low:
        midhigh_peaks = np.extract(
            reduce(np.logical_and,
                   (channel_widths(peaks, channel_num) > max_gate,
                    reduce(np.logical_and,
                           (channel_amplitudes(peaks, channel_num) < middle_high,
                            channel_amplitudes(peaks, channel_num) > middle_low)))),
            peaks)
        midlow_peaks = np.extract(
            reduce(np.logical_and,
                   (channel_widths(peaks, channel_num) < min_gate,
                    reduce(np.logical_and,
                           (channel_amplitudes(peaks, channel_num) < middle_high,
                            channel_amplitudes(peaks, channel_num) > middle_low)))),
            peaks)
    else:
        midhigh_peaks = np.ndarray([0],dtype=peak_dtype(2))
        midlow_peaks = np.ndarray([0],dtype=peak_dtype(2))
    
    neg_peaks = np.extract(
        reduce(np.logical_and,
               (channel_widths(peaks, channel_num) < min_gate,
                channel_amplitudes(peaks, channel_num) < neg)),
        peaks)
    
    return ((pos_peaks, midhigh_peaks, midlow_peaks, neg_peaks),
            (pos, middle_high, middle_low, neg),
            (min_gate, max_gate))

def revb_polydisperse_peaks(well, channel_num, threshold=None, pct_boundary=0.3, exclude_min_amplitude_peaks=True):
    """
    Computes polydispersity for a well which has amplitude bins defined.

    Returns a 3-tuple (4-tuple, 4-tuple, 2-tuple).  The first 4-tuple is:

    * positive droplets, with widths above the width gate set for that droplet's amplitude bin.
    * middle rain, with widths above the bin width gate.
    * middle rain, with width below the bin width gate.
    * negative rain, with width below the bin width gate.

    The second 4-tuple is:

    * positive rain boundary
    * middle rain upper boundary (can be None)
    * middle rain lower boundary (can be None)
    * negative rain boundary

    The third 2-tuple is:

    * mean FAM amplitude
    * mean VIC amplitude

    This is for being able to draw approximate single-channel polydispersity graphs
    down the line (this does beg the question, is there a better 2D definition of
    polydispersity?)

    Will raise an error if amplitude bins are not defined on the well.
    """
    if not hasattr(well, 'sum_amplitude_bins') or len(well.sum_amplitude_bins) == 0:
        raise ValueError("No amplitude bins for this well.")
    
    if not threshold:
        threshold = well.channels[channel_num].statistics.threshold
    if not threshold:
        threshold = None
    
    if exclude_min_amplitude_peaks:
        peaks = above_min_amplitude_peaks(well)
    else:
        peaks = well.peaks
    
    p_plus, p, p_minus, pos, middle_high, middle_low, neg = \
            rain_pvalues_thresholds(peaks,
                                    channel_num=channel_num,
                                    threshold=threshold,
                                    pct_boundary=pct_boundary)
    
    binned_peaks         = bin_peaks_by_amplitude(peaks, well.sum_amplitude_bins)
    
    pos_peaks     = np.ndarray([0], dtype=peak_dtype(2))
    midhigh_peaks = np.ndarray([0], dtype=peak_dtype(2))
    midlow_peaks  = np.ndarray([0], dtype=peak_dtype(2))
    neg_peaks     = np.ndarray([0], dtype=peak_dtype(2))

    for bin, (min_gate, max_gate, boundary) in zip(binned_peaks, well.sum_amplitude_bins):
        pos_peaks = np.hstack([pos_peaks, np.extract(
            reduce(np.logical_and,
                   (channel_widths(bin, channel_num) > max_gate,
                    channel_amplitudes(bin, channel_num) > pos)),
            bin)])
    
        if middle_high and middle_low:
            midhigh_peaks = np.hstack([midhigh_peaks, np.extract(
                reduce(np.logical_and,
                       (channel_widths(bin, channel_num) > max_gate,
                        reduce(np.logical_and,
                               (channel_amplitudes(bin, channel_num) < middle_high,
                                channel_amplitudes(bin, channel_num) > middle_low)))),
                bin)])
            
            midlow_peaks = np.hstack([midlow_peaks, np.extract(
                reduce(np.logical_and,
                       (channel_widths(bin, channel_num) < min_gate,
                        reduce(np.logical_and,
                               (channel_amplitudes(bin, channel_num) < middle_high,
                                channel_amplitudes(bin, channel_num) > middle_low)))),
                bin)])
        
        neg_peaks = np.hstack([neg_peaks, np.extract(
            reduce(np.logical_and,
                   (channel_widths(bin, channel_num) < min_gate,
                    channel_amplitudes(bin, channel_num) < neg)),
            bin)])
    
    return ((pos_peaks, midhigh_peaks, midlow_peaks, neg_peaks),
            (pos, middle_high, middle_low, neg),
            (np.mean(fam_amplitudes(peaks)), np.mean(vic_amplitudes(peaks))))


def extracluster_peaks(well, channel_num, threshold=None, pct_boundary=0.3, exclude_min_amplitude_peaks=True):
    """
    Return the peaks that are outside the clusters.
    A superset of polydispersity peaks, meant primarily for dye wells,
    where there should be no biological basis for rain.

    Returns a 3-tuple: peaks, rain gates, width gates
    """
    if not threshold:
        threshold = well.channels[channel_num].statistics.threshold
    if not threshold:
        threshold = None
    
    if exclude_min_amplitude_peaks:
        peaks = above_min_amplitude_peaks(well)
    else:
        peaks = well.peaks
    
    # get rain_pvalues
    p_plus, p, p_minus, pos, middle_high, middle_low, neg = \
            rain_pvalues_thresholds(peaks,
                                    channel_num=channel_num,
                                    threshold=threshold,
                                    pct_boundary=pct_boundary)
    
    min_gate, max_gate = well_static_width_gates(well)

    if middle_high and middle_low:
        extracluster_peaks = np.extract(np.logical_not(
            np.logical_or(
                   reduce(np.logical_and,
                          (channel_widths(peaks, channel_num) > min_gate,
                           channel_widths(peaks, channel_num) < max_gate,
                           channel_amplitudes(peaks, channel_num) > middle_high,
                           channel_amplitudes(peaks, channel_num) < pos)),
                   reduce(np.logical_and,
                          (channel_widths(peaks, channel_num) > min_gate,
                           channel_widths(peaks, channel_num) < max_gate,
                           channel_amplitudes(peaks, channel_num) > neg,
                           channel_amplitudes(peaks, channel_num) < middle_low))
            )
        ), peaks)
    else:
        extracluster_peaks = np.extract(np.logical_not(
            reduce(np.logical_and,
                   (channel_widths(peaks, channel_num) > min_gate,
                    channel_widths(peaks, channel_num) < max_gate,
                    channel_amplitudes(peaks, channel_num) > neg,
                    channel_amplitudes(peaks, channel_num) < pos)
            )
        ), peaks)
    
    return (extracluster_peaks,
            (pos, middle_high, middle_low, neg),
            (min_gate, max_gate))


def revb_extracluster_peaks(well, channel_num, threshold=None, pct_boundary=0.3, exclude_min_amplitude_peaks=True):
    """
    Return the peaks that are outside the clusters.
    A superset of polydispersity peaks, meant primarily for dye wells,
    where there should be no biological basis for rain.

    Returns a 3-tuple: peaks, rain gates, width gates
    """
    if not threshold:
        threshold = well.channels[channel_num].statistics.threshold
    if not threshold:
        threshold = None
    
    if exclude_min_amplitude_peaks:
        peaks = above_min_amplitude_peaks(well)
    else:
        peaks = well.peaks
    
    # get rain_pvalues
    p_plus, p, p_minus, pos, middle_high, middle_low, neg = \
            rain_pvalues_thresholds(peaks,
                                    channel_num=channel_num,
                                    threshold=threshold,
                                    pct_boundary=pct_boundary)
    
    binned_peaks = bin_peaks_by_amplitude(peaks, well.sum_amplitude_bins)

    extra_peaks = np.ndarray([0], dtype=peak_dtype(2))
    for bin, (min_gate, max_gate, boundary) in zip(binned_peaks, well.sum_amplitude_bins):
        if middle_high and middle_low:
            extra_peaks = np.hstack([extra_peaks, np.extract(np.logical_not(
                np.logical_or(
                       reduce(np.logical_and,
                              (channel_widths(bin, channel_num) > min_gate,
                               channel_widths(bin, channel_num) < max_gate,
                               channel_amplitudes(bin, channel_num) > middle_high,
                               channel_amplitudes(bin, channel_num) < pos)),
                       reduce(np.logical_and,
                              (channel_widths(bin, channel_num) > min_gate,
                               channel_widths(bin, channel_num) < max_gate,
                               channel_amplitudes(bin, channel_num) > neg,
                               channel_amplitudes(bin, channel_num) < middle_low))
                )
            ), bin)])
        else:
            extra_peaks = np.hstack([extra_peaks, np.extract(np.logical_not(
                reduce(np.logical_and,
                       (channel_widths(bin, channel_num) > min_gate,
                        channel_widths(bin, channel_num) < max_gate,
                        channel_amplitudes(bin, channel_num) > neg,
                        channel_amplitudes(bin, channel_num) < pos)
                )
            ), bin)])
    
    return (extra_peaks,
            (pos, middle_high, middle_low, neg),
            (np.mean(fam_amplitudes(peaks)), np.mean(vic_amplitudes(peaks))))

def revb_extracluster_peaks_by_region(well, channel_num, threshold=None, pct_boundary=0.3, exclude_min_amplitude_peaks=True):
    """
    Return the peaks that are not desired (outside clusters)
    and separate them by region.  The region order is:

    -- positive large peaks
    -- positive rain
    -- positive small peaks
    -- positive wide peaks (directly above positive cluster)
    -- positive narrow peaks (directly below positive cluster)
    -- middle large peaks
    -- middle rain
    -- middle small peaks
    -- negative large peaks
    -- negative rain
    -- negative small peaks
    -- negative wide peaks (directly above positive cluster)
    -- negative narrow peaks (directly below positive cluster)

    Returns this 9-tuple, then rain gates, then mean of FAM and VIC.
    """
    extra_peaks, rain_gates, means = \
        revb_extracluster_peaks(well, channel_num,
                                threshold=threshold,
                                pct_boundary=pct_boundary,
                                exclude_min_amplitude_peaks=exclude_min_amplitude_peaks)

    pos_gate, midhigh_gate, midlow_gate, neg_gate = rain_gates
    binned_peaks = bin_peaks_by_amplitude(extra_peaks, well.sum_amplitude_bins)
    plpeaks = np.ndarray([0], dtype=peak_dtype(2))
    prpeaks = np.ndarray([0], dtype=peak_dtype(2))
    pspeaks = np.ndarray([0], dtype=peak_dtype(2))
    pwpeaks = np.ndarray([0], dtype=peak_dtype(2))
    pnpeaks = np.ndarray([0], dtype=peak_dtype(2))
    mlpeaks = np.ndarray([0], dtype=peak_dtype(2))
    mrpeaks = np.ndarray([0], dtype=peak_dtype(2))
    mspeaks = np.ndarray([0], dtype=peak_dtype(2))
    nlpeaks = np.ndarray([0], dtype=peak_dtype(2))
    nrpeaks = np.ndarray([0], dtype=peak_dtype(2))
    nspeaks = np.ndarray([0], dtype=peak_dtype(2))
    nwpeaks = np.ndarray([0], dtype=peak_dtype(2))
    nnpeaks = np.ndarray([0], dtype=peak_dtype(2))

    for bin, (min_gate, max_gate, boundary) in zip(binned_peaks, well.sum_amplitude_bins):
        plpeaks = np.hstack([plpeaks, np.extract(
            reduce(np.logical_and,
                   (channel_widths(bin, channel_num) > max_gate,
                    channel_amplitudes(bin, channel_num) > pos_gate)
            ), bin)])
        prpeaks = np.hstack([prpeaks, np.extract(
            reduce(np.logical_and,
                   (channel_widths(bin, channel_num) >= min_gate,
                    channel_widths(bin, channel_num) <= max_gate,
                    channel_amplitudes(bin, channel_num) > pos_gate)
            ), bin)])
        pspeaks = np.hstack([pspeaks, np.extract(
            reduce(np.logical_and,
                   (channel_widths(bin, channel_num) < min_gate,
                    channel_amplitudes(bin, channel_num) > pos_gate)
            ), bin)])
        if midhigh_gate and midlow_gate:
            mlpeaks = np.hstack([mlpeaks, np.extract(
            reduce(np.logical_and,
                   (channel_widths(bin, channel_num) > max_gate,
                    channel_amplitudes(bin, channel_num) < midhigh_gate,
                    channel_amplitudes(bin, channel_num) > midlow_gate)
            ), bin)])
            mrpeaks = np.hstack([mrpeaks, np.extract(
                reduce(np.logical_and,
                       (channel_widths(bin, channel_num) >= min_gate,
                        channel_widths(bin, channel_num) <= max_gate,
                        channel_amplitudes(bin, channel_num) < midhigh_gate,
                        channel_amplitudes(bin, channel_num) > midlow_gate)
                ), bin)])
            mspeaks = np.hstack([mspeaks, np.extract(
                reduce(np.logical_and,
                       (channel_widths(bin, channel_num) < min_gate,
                        channel_amplitudes(bin, channel_num) < midhigh_gate,
                        channel_amplitudes(bin, channel_num) > midlow_gate)
                ), bin)])
            # this means there are positives
            pwpeaks = np.hstack([pwpeaks, np.extract(
                reduce(np.logical_and,
                       (channel_widths(bin, channel_num) > max_gate,
                        channel_amplitudes(bin, channel_num) >= midhigh_gate,
                        channel_amplitudes(bin, channel_num) <= pos_gate)
                ), bin)])
            pnpeaks = np.hstack([pnpeaks, np.extract(
                reduce(np.logical_and,
                       (channel_widths(bin, channel_num) < min_gate,
                        channel_amplitudes(bin, channel_num) >= midhigh_gate,
                        channel_amplitudes(bin, channel_num) <= pos_gate)
                ), bin)])
            nwpeaks = np.hstack([nwpeaks, np.extract(
                reduce(np.logical_and,
                       (channel_widths(bin, channel_num) > max_gate,
                        channel_amplitudes(bin, channel_num) >= neg_gate,
                        channel_amplitudes(bin, channel_num) <= midlow_gate)
                ), bin)])
            nnpeaks = np.hstack([nnpeaks, np.extract(
                reduce(np.logical_and,
                       (channel_widths(bin, channel_num) < min_gate,
                        channel_amplitudes(bin, channel_num) >= neg_gate,
                        channel_amplitudes(bin, channel_num) <= midlow_gate)
                ), bin)])
        else:
            nwpeaks = np.hstack([nwpeaks, np.extract(
                reduce(np.logical_and,
                       (channel_widths(bin, channel_num) > max_gate,
                        channel_amplitudes(bin, channel_num) >= neg_gate,
                        channel_amplitudes(bin, channel_num) <= pos_gate)
                ), bin)])
            nnpeaks = np.hstack([nnpeaks, np.extract(
                reduce(np.logical_and,
                       (channel_widths(bin, channel_num) < min_gate,
                        channel_amplitudes(bin, channel_num) >= neg_gate,
                        channel_amplitudes(bin, channel_num) <= pos_gate)
                ), bin)])

        nlpeaks = np.hstack([nlpeaks, np.extract(
            reduce(np.logical_and,
                   (channel_widths(bin, channel_num) > max_gate,
                    channel_amplitudes(bin, channel_num) < neg_gate)
            ), bin)])
        nrpeaks = np.hstack([nrpeaks, np.extract(
            reduce(np.logical_and,
                   (channel_widths(bin, channel_num) >= min_gate,
                    channel_widths(bin, channel_num) <= max_gate,
                    channel_amplitudes(bin, channel_num) < neg_gate)
            ), bin)])
        
        pbpeaks = np.hstack([pspeaks, np.extract(
            reduce(np.logical_and,
                   (channel_widths(bin, channel_num) < min_gate,
                    channel_amplitudes(bin, channel_num) >= midhigh_gate,
                    channel_amplitudes(bin, channel_num) <= pos_gate)
            ), bin)])

    return ((plpeaks, prpeaks, pspeaks,
             pwpeaks, pnpeaks,
             mlpeaks, mrpeaks, mspeaks,
             nlpeaks, nrpeaks, nspeaks,
             nwpeaks, nnpeaks),
            rain_gates,
            means)

def bin_peaks_by_amplitude(peaks, amplitude_bins):
    """
    Given a set of peaks and bins, bin the peaks into the bins by sum channel.
    """
    amplitude_sums = fam_amplitudes(peaks) + vic_amplitudes(peaks)
    amplitude_boundaries = [bin[2] for bin in amplitude_bins]
    MAX_AMPLITUDE        = 32768

    amplitude_regions    = zip(amplitude_boundaries[:-1],amplitude_boundaries[1:]) \
                           + [(amplitude_boundaries[-1], MAX_AMPLITUDE)]
    binned_peaks         = []

    for region in amplitude_regions:
        binned_peaks.append(np.extract(
            reduce(np.logical_and,
                   (amplitude_sums >= region[0],
                    amplitude_sums < region[1])),
            peaks))

    return binned_peaks

def well_fragmentation_probability(well):
    """
    Returns the percentage likelihood per droplet that the molecules in
    the two channels are unlinked (TODO: refine definition)

    Returns the 3-tuple (probability, ci_low, ci_high).  If thresholds are
    not present, then the function will return the 3-tuple (None, None, None)
    """
    from qtools.lib.nstats.frag import prob_of_frag

    fam_threshold = well.channels[0].statistics.threshold
    vic_threshold = well.channels[1].statistics.threshold

    if not (fam_threshold and vic_threshold):
        return (None, None, None)
    
    ok_peaks = accepted_peaks(well)
    fampos_vicpos, fampos_vicneg, famneg_vicpos, famneg_vicneg = \
        cluster_2d(ok_peaks, fam_threshold, vic_threshold)
    
    retarr = prob_of_frag(len(fampos_vicneg), len(fampos_vicpos),
                          len(famneg_vicneg), len(famneg_vicpos),
                          len(ok_peaks))
    if not retarr:
        return (None, None, None)
    else:
        pct_interval, vic_interval, fam_interval, linked_interval = retarr
        return pct_interval


def quartile_concentration_ratio(well, channel_num=0, threshold=None, peaks=None, min_events=4000):
    if peaks is None:
        peaks = accepted_peaks(well)
    
    if len(peaks) < min_events:
        return None
    
    if not threshold:
        threshold = well.channels[channel_num].statistics.threshold
    
    if not threshold:
        return None
    
    quartile_size = len(peaks)/4
    first_quartile = peaks[0:quartile_size]
    last_quartile = peaks[len(peaks)-quartile_size:]

    first_pos, first_neg = cluster_1d(first_quartile, channel_num, threshold)
    fq_conc = concentration(len(first_pos), len(first_neg), droplet_vol=well.droplet_volume) # could be nan
    last_pos, last_neg = cluster_1d(last_quartile, channel_num, threshold)
    lq_conc = concentration(len(last_pos), len(last_neg), droplet_vol=well.droplet_volume) # could be nan

    # if conc is nan or zero, we can't compute a real ratio
    if math.isnan(fq_conc) or math.isnan(lq_conc) or fq_conc == 0 or lq_conc == 0:
        return None
    else:
        return lq_conc/fq_conc


def rain_split(qlwell, channel_num=0, threshold=None, pct_boundary=0.3, split_all_peaks=False):
    """
    Splits between rain and non-rain.  If you want the well's auto threshold to be used,
    use None as a threshold parameter (the default).
    If you do not want a threshold to be calculated, use '0'. (little unclear from the spec)

    Returns tuple (rain, non-rain)
    """
    if threshold is None:
        threshold = qlwell.channels[channel_num].statistics.threshold
    
    ok_peaks = accepted_peaks(qlwell)
    prain, rain, nrain, p_thresh, mh_thresh, ml_thresh, l_thresh = \
        rain_pvalues_thresholds(ok_peaks, channel_num=channel_num, threshold=threshold, pct_boundary=pct_boundary)

    if split_all_peaks:
        peaks = qlwell.peaks
    else:
        peaks = ok_peaks
    # this would be useful as a standalone, but for efficiency's sake will cut out for now        
    rain_condition_arr = [channel_amplitudes(peaks, channel_num) > p_thresh]
    if mh_thresh and ml_thresh:
        rain_condition_arr.append(np.logical_and(channel_amplitudes(peaks, channel_num) > ml_thresh,
                                              channel_amplitudes(peaks, channel_num) < mh_thresh))
    rain_condition_arr.append(channel_amplitudes(peaks, channel_num) < l_thresh)
    rain_condition = reduce(np.logical_or, rain_condition_arr)
    nonrain_condition = np.logical_not(rain_condition)

    rain = np.extract(rain_condition, peaks)
    nonrain = np.extract(nonrain_condition, peaks)
    return rain, nonrain

def gap_rain(qlwell, channel_num=0, threshold=None, pct_boundary=0.3, gap_size=10000):
    """
    Return the rain in the gaps between non-rain droplets.
    """
    rain, nonrain = rain_split(qlwell,
                               channel_num=channel_num,
                               threshold=threshold,
                               pct_boundary=pct_boundary)
    
    # ok, now identify the gaps in the gates.
    times = peak_times(nonrain)
    if nonrain is None or len(nonrain) < 2:
        return np.ndarray([0],dtype=peak_dtype(2))
    
    intervals = np.ediff1d(times, to_begin=0, to_end=0)
    big_intervals = intervals > gap_size

    # find beginning of gaps with extract
    beginnings = np.extract(big_intervals[1:], times)
    ends = np.extract(big_intervals[:-1], times)

    gap_intervals = zip(beginnings, ends)
    gap_intervals.insert(0, (0, times[0]))
    gap_intervals.append((times[-1], times[-1]*100))
    
    # count the rain in the intervals
    gap_drops = np.extract(reduce(np.logical_or, [np.logical_and(peak_times(rain) > b,
                                                                 peak_times(rain) < e) for b, e in gap_intervals]),
                           rain)
    return gap_drops

def gap_air(qlwell, channel_num=0, threshold=None, pct_boundary=0.3, gap_size=10000, gap_buffer=250, max_amp=1000):
    """
    Return the air (gap rain < max_amp) in the gaps between non-rain droplets.

    :param channel_num: The channel on which to detect air droplets.
    :param threshold: The threshold dividing positives and negatives (used to detect 'rain')
    :param pct_boundary: The percentage outside of which a droplet is classified as rain.
    :param gap_size: The minimum size (in samples) of a gap.  Default 0.1s.
    :param gap_buffer: The distance a droplet must be from the main population to be considered an
                       air droplet, in samples.  Default 0.0025s.
    :param max_amp: The maximum color-corrected amplitude of an air droplet.  Default 1000 RFU.
    """
    rain, nonrain = rain_split(qlwell,
                               channel_num=channel_num,
                               threshold=threshold,
                               pct_boundary=pct_boundary,
                               split_all_peaks=True)
    
    low_amp = np.extract(channel_amplitudes(rain, channel_num) < max_amp, rain)

    times = peak_times(nonrain)
    if nonrain is None or len(nonrain) < 2:
        return np.ndarray([0], dtype=peak_dtype(2))
    
    intervals = np.ediff1d(times, to_begin=0, to_end=0)
    big_intervals = intervals > gap_size

    # find beginning of gaps with extract
    beginnings = [b+gap_buffer for b in np.extract(big_intervals[1:], times)]
    ends = [e-gap_buffer for e in np.extract(big_intervals[:-1], times)]

    gap_intervals = zip(beginnings, ends)
    gap_intervals.insert(0, (0, times[0]-gap_buffer))
    gap_intervals.append((times[-1]+gap_buffer, times[-1]*100))
    
    # count the rain in the intervals
    gap_drops = np.extract(reduce(np.logical_or, [np.logical_and(peak_times(low_amp) > b,
                                                                 peak_times(low_amp) < e) for b, e in gap_intervals]),
                           low_amp)
    return gap_drops

def neg_cluster_angle_2d(qlwell, fam_threshold=None, vic_threshold=None):
    if fam_threshold is None:
        fam_threshold = qlwell.channels[0].statistics.threshold
    if vic_threshold is None:
        vic_threshold = qlwell.channels[1].statistics.threshold

    ok_peaks = accepted_peaks(qlwell)

    fampos_vicpos, fampos_vicneg, famneg_vicpos, famneg_vicneg = \
        cluster_2d(ok_peaks, fam_threshold, vic_threshold)

    if len(fampos_vicneg) == 0 or len(famneg_vicpos) == 0 or len(famneg_vicneg) == 0:
        return 0

    return cluster_angle_ccw(famneg_vicneg, famneg_vicpos, fampos_vicneg)

def pos_cluster_angle_2d(qlwell, fam_threshold=None, vic_threshold=None):
    if fam_threshold is None:
        fam_threshold = qlwell.channels[0].statistics.threshold
    if vic_threshold is None:
        vic_threshold = qlwell.channels[1].statistics.threshold

    ok_peaks = accepted_peaks(qlwell)

    fampos_vicpos, fampos_vicneg, famneg_vicpos, famneg_vicneg = \
        cluster_2d(ok_peaks, fam_threshold, vic_threshold)

    if len(fampos_vicneg) == 0 or len(famneg_vicpos) == 0 or len(fampos_vicpos) == 0:
        return 0

    return cluster_angle_ccw(fampos_vicpos, fampos_vicneg, famneg_vicpos)


