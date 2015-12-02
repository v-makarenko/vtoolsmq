from pyqlb import *
from pyqlb.nstats import cnv as cnv_ratio_numeric

import os, re, glob
from datetime import datetime
from qtools.lib.collection import AttrDict
from qtools.lib.nstats.peaks import polydisperse_peaks, revb_polydisperse_peaks,total_events_amplitude_vals

# these are almost certainly wrong
CURRENT_ALGORITHM_MAJOR_VERSION=0
CURRENT_ALGORITHM_MINOR_VERSION=43


class WellStatisticsUI(AttrDict):
    def __getitem__(self, idx):
        return self.channels[idx]

class WellChannelStatisticsUI(AttrDict):
    pass

# shim from original PyQLB PeakStatistics/PeakChannelStatistics object
def well_statistics(qlwell, override_thresholds=None):
    from pyqlb.nstats import concentration, concentration_interval
    from pyqlb.nstats.peaks import cluster_1d
    from pyqlb.nstats.well import well_observed_positives_negatives, accepted_peaks

    if override_thresholds is None:
        override_thresholds = [None]*len(qlwell.channels)
    wellui = WellStatisticsUI(channels=[])
    for idx, channel in enumerate(qlwell.channels):
        if not override_thresholds[idx]:
            positives, negatives, unclassified = well_observed_positives_negatives(qlwell, idx)
            threshold = channel.statistics.threshold
            conc = channel.statistics.concentration
            conc_interval = (channel.statistics.concentration,
                             channel.statistics.concentration_lower_bound,
                             channel.statistics.concentration_upper_bound)
        else:
            positives, negatives = cluster_1d(accepted_peaks(qlwell), idx, override_thresholds[idx])
            threshold = override_thresholds[idx]
            conc = concentration(len(positives), len(negatives), qlwell.droplet_volume)
            conc_interval = concentration_interval(len(positives), len(negatives), qlwell.droplet_volume)

        channelui = WellChannelStatisticsUI(positives=len(positives),
                                            negatives=len(negatives),
                                            threshold=threshold,
                                            concentration=conc,
                                            concentration_interval=conc_interval)
        wellui.channels.append(channelui)

    return wellui

def stats_for_qlp_well_path(qlp_path, well_name, compute_clusters=False, override_thresholds=None):
    """
    Return statistics about a well, given a path to a QLP file with the well metrics and the name
    of the well to look at in the plate.

    Structure is a bit legacy and can be massaged more.

    :param qlp_path: The path to the QLP file.
    :param well_name: The name of the
    :param compute_clusters: Whether to compute clusters in addition to basic statistics.
    :param override_thresholds: If not None, use the supplied thresholds to determine statistics,
                                such as concentration, clusters, S-value, etc.
    :return: A 2-tuple (statistics, clusters).  (TODO: document this more)
    """
    from pyqlb.factory import QLNumpyObjectFactory
    factory = QLNumpyObjectFactory()
    plate = factory.parse_plate(qlp_path)
    well = plate.analyzed_wells.get(well_name.upper(), None)
    if not well:
        return None
    else:
        return stats_for_qlp_well(well, compute_clusters=compute_clusters, override_thresholds=override_thresholds)

def stats_for_qlp_well(well, compute_clusters=False, override_thresholds=None):
    """
    Return statistics about a QLWell object read from a QLP file.
    The QLWell object should have a populated `peaks` attribute (reading from QLBs won't work)

    For parameter explanations and return values, see :func:`stats_for_qlp_well`.
    """
    from pyqlb.nstats.peaks import cluster_1d, channel_amplitudes
    from pyqlb.nstats.well import accepted_peaks, above_min_amplitude_peaks, well_channel_sp_values, well_cluster_peaks
    from pyqlb.nstats.well import well_observed_positives_negatives, well_s2d_values, getClusters
    from pyqlb.nstats.well import high_flier_droplets, low_flier_droplets, singleRain_droplets, doubleRain_droplets, diagonal_scatter
    from numpy import mean as np_mean, std as np_std

    if not override_thresholds:
        override_thresholds = (None, None)

    statistics = well_statistics(well, override_thresholds=override_thresholds)
    accepted = len(accepted_peaks(well))
    num_above_min = len(above_min_amplitude_peaks(well))

    if num_above_min > 0 and accepted > 0:
        if well.sum_amplitude_bins:
            peaksets, boundaries, amps = revb_polydisperse_peaks(well, 0, threshold=override_thresholds[0])
            poly_peaks = sum([len(p) for p in peaksets])
            statistics[0].revb_polydispersity_pct = 100*float(poly_peaks)/num_above_min
        else:
            peaksets, boundaries, width_gates = polydisperse_peaks(well, 0, threshold=override_thresholds[0])
            poly_peaks = sum([len(p) for p in peaksets])
            statistics[0].revb_polydispersity_pct = 100*float(poly_peaks)/num_above_min
    else:
        statistics[0].revb_polydispersity_pct = 0

    s, p_plus, p, p_minus = well_channel_sp_values(well, 0, override_threshold=override_thresholds[0])
    statistics[0].s_value = s
    statistics[0].p_plus = p_plus
    statistics[0].p_plus_drops = int(p_plus*accepted) if p_plus is not None else None
    statistics[0].p = p
    statistics[0].p_drops = int(p*accepted) if p is not None else None
    statistics[0].p_minus = p_minus
    statistics[0].p_minus_drops = int(p_minus*accepted) if p_minus is not None else None

    if num_above_min > 0 and accepted > 0:
        if well.sum_amplitude_bins:
            peaksets, boundaries, amps = revb_polydisperse_peaks(well, 1, threshold=override_thresholds[1])
            poly_peaks = sum([len(p) for p in peaksets])
            statistics[1].revb_polydispersity_pct = 100*float(poly_peaks)/num_above_min
        else:
            peaksets, boundaries, width_gates = polydisperse_peaks(well, 1, threshold=override_thresholds[1])
            poly_peaks = sum([len(p) for p in peaksets])
            statistics[1].revb_polydispersity_pct = 100*float(poly_peaks)/num_above_min
    else:
        statistics[1].revb_polydispersity_pct = 0

    s, p_plus, p, p_minus = well_channel_sp_values(well, 1, override_threshold=override_thresholds[1])
    statistics[1].s_value = s
    statistics[1].p_plus = p_plus
    statistics[1].p_plus_drops = int(p_plus*accepted) if p_plus is not None else None
    statistics[1].p = p
    statistics[1].p_drops = int(p*accepted) if p is not None else None
    statistics[1].p_minus = p_minus
    statistics[1].p_minus_drops = int(p_minus*accepted) if p_minus is not None else None

    ## compute s2d plots
    s2d_vals = well_s2d_values( well, thresholds=override_thresholds)
    statistics[0].s2d_value = s2d_vals[0] if s2d_vals is not None else None
    statistics[1].s2d_value = s2d_vals[1] if s2d_vals is not None else None

    ## compute extra cluster metrics
    clusters = getClusters( well, override_thresholds )
    dscatter = diagonal_scatter( clusters )
    statistics.diagonal_scatter = dscatter[1] if dscatter is not None else None
    statistics.diagonal_scatter_pct  = dscatter[2] *100 if dscatter is not None else None
    for channel in [0,1]:
        high_fliers = high_flier_droplets( clusters, channel )
        statistics[channel].high_flier_value = high_fliers[1] if high_fliers is not None else None
        statistics[channel].high_flier_pct = high_fliers[2] * 100 if high_fliers is not None else None

        low_fliers  = low_flier_droplets( clusters, channel )
        statistics[channel].low_flier_value  = low_fliers[1] if low_fliers is not None else None
        statistics[channel].low_flier_pct    = low_fliers[2] * 100 if low_fliers is not None else None
        
        singleRain  = singleRain_droplets( clusters, channel )
        statistics[channel].single_rain_value  = singleRain[1] if singleRain is not None else None
        statistics[channel].single_rain_pct  = singleRain[2] * 100 if singleRain is not None else None
        
        doubleRain  = doubleRain_droplets( clusters, channel )
        statistics[channel].double_rain_value = doubleRain[1] if doubleRain is not None else None
        statistics[channel].double_rain_pct = doubleRain[2] * 100 if doubleRain is not None else None


    if compute_clusters:
        clusters = well_cluster_peaks(well, override_thresholds)
    else:
        clusters = {'positive_peaks': {'positive_peaks': [], 'negative_peaks': []},
                    'negative_peaks': {'positive_peaks': [], 'negative_peaks': []}}
 
    # cheap hack
    statistics.alg_version = "%s.%s/%s.%s" % (well.statistics.peak_alg_major_version,
                                              well.statistics.peak_alg_minor_version,
                                              well.statistics.quant_alg_major_version,
                                              well.statistics.quant_alg_minor_version)
    statistics.ref_copy_num = well.ref_copy_num
    statistics[0].decision_tree = well.channels[0].decision_tree_verbose
    statistics[1].decision_tree = well.channels[1].decision_tree_verbose
    # end cheap hack

    # SNR
    for chan in (0,1):
        if override_thresholds[chan]:
            # TODO add this to pyqlb.nstats.well instead
            pos, neg = cluster_1d(accepted_peaks(well), chan, override_thresholds[chan])
        else:
            pos, neg, unknown = well_observed_positives_negatives(well, chan)

        for attr, coll in (('positive_snr', pos),('negative_snr',neg)):
            if len(pos) > 0:
                amps = channel_amplitudes(coll, chan)
                amp_mean = np_mean(amps)
                amp_std = np_std(amps)
                if amp_std > 0:
                    setattr(statistics[chan], attr, amp_mean/amp_std)
                else:
                    setattr(statistics[chan], attr, 10000)
            else:
                setattr(statistics[chan], attr, 0)

    for channel in [0,1]:
        means,stds = total_events_amplitude_vals(well,channel) 
        statistics[channel].total_events_amplitude_mean = means if means is not None else None
        statistics[channel].total_events_amplitude_stdev = stds if stds is not None else None

    return statistics, clusters

def readable(metadata):
    version = metadata['version']
    if metadata['type'] == 'raw':
        return tuple(version.split('.')) >= (1, 0, 0, 28)
    elif metadata['type'] == 'processed':
        return version != '1.00' and tuple(version.split('.')) >= (0, 1, 1, 9)

def file_version(reader):
    # TODO: should go in PyQLB reader instead?
    return reader.metadata['host_software'].split()[-1]

def run_id(reader):
    # TODO: should go in PyQLB reader instead?
    # the host_machine can be overwritten if you save the QLP file
    # on your own laptop-- so use equipment_serial.
    
    # TODO: deploy this
    #if reader.isprocessed():
    #    machine = reader.metadata['equipment_serial']
    #else:
    machine = reader.metadata["host_machine"]
    rundate = reader.metadata['host_datetime']
    return "%s_%s_%s" % (machine,
                         datetime.strptime(rundate, '%Y:%m:%d %H:%M:%S').strftime('%s'),
                         "RAW" if reader.israw() else "PROC")


# this is a bad abstraction-- return field instead
def run_time(reader):
    return datetime.strptime(reader.metadata['host_datetime'], '%Y:%m:%d %H:%M:%S')

def well_name_for_number(motion_well_number):
    row, col = divmod(int(motion_well_number)-1, 12)
    return "%s%02d" % (chr(ord('A')+row), col+1)
