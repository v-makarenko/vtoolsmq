"""
Methods and classes for computing metrics for plates and wells.
"""
from qtools.constants.metrics import *

from qtools.lib.nstats.peaks import accepted_peaks, quartile_concentration_ratio
from qtools.lib.nstats.peaks import polydisperse_peaks, revb_polydisperse_peaks, revb_extracluster_peaks
from qtools.lib.nstats.peaks import gap_rain, gap_air, extracluster_peaks, well_fragmentation_probability

import math

import numpy as np
from pyqlb.objects import QLWell, QLWellChannelStatistics
from pyqlb.nstats import cnv_interval, linkage_2d, concentration as calc_conc, cnv as get_cnv
from pyqlb.nstats.peaks import *
from pyqlb.nstats.well import well_static_width_gates, above_min_amplitude_peaks, min_amplitude_peaks, well_channel_automatic_classification
from pyqlb.nstats.well import well_balance_score_2d, narrow_droplet_spacing_count, NARROW_NORMALIZED_DROPLET_SPACING
from pyqlb.nstats.well import well_observed_positives_negatives, well_observed_cnv_interval
from pyqlb.nstats.well import well_s2d_values, getClusters
from pyqlb.nstats.well import high_flier_droplets, low_flier_droplets, singleRain_droplets, doubleRain_droplets, diagonal_scatter
from pyqlb.factory import peak_dtype

__all__ = ['_compute_plate_carryover_metrics',
           '_compute_well_channel_metrics',
           '_compute_well_metrics',
           '_compute_plate_metrics',
           'convert_inf_to_max',
           'convert_nan_to_none',
           'convert_nan_to_zero',
           'ExpectedCNVCalculator',
           'well_sample_name_lookup',
           'compute_metric_foreach_qlwell',
           'compute_metric_foreach_qlwell_channel',
           'ExpectedConcentrationCalculator',
           'well_channel_sample_name_lookup',
           'NTCSaturatedFalsePositiveCalculator',
           'NTCSaturatedFalseNegativeCalculator',
           'AverageComputedThresholdFalsePositiveCalculator',
           'AverageSampleThresholdFalsePositiveCalculator',
           'CNVCalculator',
           'ExpectedThresholdCalculator',
           'CarryoverThresholdCalculator',
           'NullLinkageCalculator',
           'AirDropletsCalculator',
           'StealthAirDropletsCalculator',
           'NOOP_WELL_METRIC_CALCULATOR',
           'NOOP_WELL_CHANNEL_METRIC_CALCULATOR',
           'STEALTH_AIRDROP_CALC',
           'DEFAULT_POLYD_CALC',
           'DEFAULT_EXTRAC_CALC',
           'NEW_DROPLET_CLUSTER_METRICS_CALCULATOR',
           'NEW_DROPLET_CLUSTER_WELL_METRICS_CALCULATOR',
           'DEFAULT_CARRYOVER_CALC',
           'COLORCOMP_CARRYOVER_CALC',
           'PolydispersityCalculator',
           'ExtraclusterCalculator',
           'DyeGapRainMetricCalculator',
           'ColorCompOrthogonalMetric',
           'ColorComp2DRainMetric',
           'NTCPositiveCalculator',
           'DEFAULT_NTC_POSITIVE_CALCULATOR']

def convert_inf_to_max(entity, max_val=1000000):
    """
    For all the attributes on the entity, if the value is infinite,
    convert to the max_val instead before inserting into the database.
    """
    for k, v in entity.__dict__.items():
        if v == float('inf'):
            setattr(entity, k, max_val)

def convert_nan_to_none(entity):
    """
    For all the attributes on the entity, if the value is nan,
    convert the nan to None before inserting into the database.
    """
    for k, v in entity.__dict__.items():
        if type(v) == type(float(3)) and math.isnan(v):
            setattr(entity, k, None)

def convert_nan_to_zero(entity):
    """
    For all the attributes on the entity, if the value is nan,
    convert the nan to zero before inserting into the database.
    """
    for k, v in entity.__dict__.items():
        if type(v) == type(float(3)) and math.isnan(v):
            setattr(entity, k, 0)

def _compute_plate_carryover_metrics(qlplate, plate_metric, override_plate_type_code=None):
    """
    Compute plate carryover metrics.  Use a different standard
    if the supplied plate is a multi-well colorcomp plate.

    :param qlplate: The QLP-derived object to read.
    :param plate_metric: The associated PlateMetric db record.
    :param override_plate_type_code: Which plate type the plate should be.
    :return: plate_metric; this and its child records will be modified.
    """
    code = None
    if not override_plate_type_code:
        plate_type = plate_metric.plate.plate_type
        if plate_type:
            code = plate_type.code
    else:
        code = override_plate_type_code
    
    if code in ('mfgcc', 'bcc'):
        pm = COLORCOMP_CARRYOVER_CALC.compute(qlplate, plate_metric)
    else:
        pm = DEFAULT_CARRYOVER_CALC.compute(qlplate, plate_metric)
    return pm

def _compute_plate_metrics(qlplate, plate_metric):
    """
    Populate the plate_metric record's values with information
    derived from the QLPlate.  Modifies the plate_metric record
    only, not its children.

    :return: plate_metric (modified)
    """
    if qlplate.software_pmt_gains:
        plate_metric.software_pmt_gain_fam = qlplate.software_pmt_gains[0]
        plate_metric.software_pmt_gain_vic = qlplate.software_pmt_gains[1]
    return plate_metric

def _compute_well_channel_metrics(qlwell, well_channel_metric, channel_num):
    """
    Internal method for populating a WellChannelMetric object from statistics
    determined by analyzing the QLWell's channel object.

    This will populate the well_channel_metric object with information such
    as positives and negatives, concentration, polydispersity, and other
    metrics that have separate values for FAM and VIC channels.

    :param qlwell: The QLWell object created by reading a QLP file.
    :param well_channel_metric: The WellChannelMetric object to populate.
    :param channel_num: Which channel to analyze.
    """
    # for convenience
    wcm = well_channel_metric
    stats = qlwell.channels[channel_num].statistics
    wcm.min_quality_gating = stats.min_quality_gate
    wcm.min_quality_gating_conf = stats.min_quality_gate_conf
    wcm.min_width_gate = stats.min_width_gate
    wcm.min_width_gate_conf = stats.min_width_gate_conf
    wcm.max_width_gate = stats.max_width_gate
    wcm.max_width_gate_conf = stats.max_width_gate_conf
    wcm.width_gating_sigma = stats.width_gating_sigma
    # TODO: try to guarantee automatic threshold here?
    wcm.threshold = stats.threshold
    wcm.threshold_conf = stats.threshold_conf
    wcm.auto_threshold_expected = False
    wcm.concentration = stats.concentration
    wcm.conc_lower_bound = stats.concentration_lower_bound
    wcm.conc_upper_bound = stats.concentration_upper_bound
    wcm.conc_calc_mode = stats.concentration_calc_mode
    wcm.clusters_automatic = well_channel_automatic_classification(qlwell, channel_num)

    wcm.decision_tree_flags = qlwell.channels[channel_num].decision_tree_flags

    ap = accepted_peaks(qlwell)
    
    if channel_num == 0:
        ampfunc = fam_amplitudes
    elif channel_num == 1:
        ampfunc = vic_amplitudes
    else:
        raise ValueError, "Incompatible channel number: %s" % channel_num

    wcm.amplitude_mean = np.mean(ampfunc(ap))
    wcm.amplitude_stdev = np.std(ampfunc(ap))

    allpeaks = qlwell.peaks
    wcm.total_events_amplitude_mean  = np.mean(ampfunc(allpeaks))
    wcm.total_events_amplitude_stdev = np.std(ampfunc(allpeaks))

    above_min_peaks = above_min_amplitude_peaks(qlwell)
    quality_gated_peaks = quality_rejected(above_min_peaks, wcm.min_quality_gating, channel_num, include_vertical_streak_flagged=False)
    wcm.quality_gated_peaks = len(quality_gated_peaks)
    width_gated_peaks = width_rejected(above_min_peaks, wcm.min_width_gate, wcm.max_width_gate, channel_num)
    wcm.width_gated_peaks = len(width_gated_peaks)
    # TODO add min amplitude, vertical streak

    wcm.s_value = separation_value(ap, channel_num, wcm.threshold)
    p_plus, p, p_minus = rain_pvalues(ap, channel_num, wcm.threshold)
   
    wcm.rain_p_plus = p_plus
    wcm.rain_p = p
    wcm.rain_p_minus = p_minus

    ## extra cluster events...
    NEW_DROPLET_CLUSTER_METRICS_CALCULATOR.compute(qlwell, qlwell.channels[channel_num], wcm)

#    DEFAULT_TEAVALS.compute(qlwell, qlwell.channels[channel_num], wcm)
    DEFAULT_POLYD_CALC.compute(qlwell, qlwell.channels[channel_num], wcm)
    DEFAULT_EXTRAC_CALC.compute(qlwell, qlwell.channels[channel_num], wcm)
    DEFAULT_NTC_POSITIVE_CALCULATOR.compute(qlwell, qlwell.channels[channel_num], wcm)

    wcm.baseline_mean = qlwell.channels[channel_num].statistics.baseline_mean
    wcm.baseline_stdev = qlwell.channels[channel_num].statistics.baseline_stdev
    wcm.cluster_conf = qlwell.channels[channel_num].statistics.cluster_conf

    positive_peaks, negative_peaks, unclassified_peaks = well_observed_positives_negatives(qlwell, channel_num)
    if len(positive_peaks) > 0 or len(negative_peaks) > 0:
        wcm.positive_peaks = len(positive_peaks)
        wcm.negative_peaks = len(negative_peaks)
        wcm.positive_mean = np.mean(ampfunc(positive_peaks))
        wcm.positive_stdev = np.std(ampfunc(positive_peaks))
        wcm.negative_mean = np.mean(ampfunc(negative_peaks))
        wcm.negative_stdev = np.std(ampfunc(negative_peaks))

        wcm.positive_skew = skew(positive_peaks, channel_num)
        wcm.positive_kurtosis = kurtosis(positive_peaks, channel_num)
        wcm.nonpositive_skew = skew(negative_peaks, channel_num)
        wcm.nonpositive_kurtosis = kurtosis(negative_peaks, channel_num)

        # CLUSTER-TODO: this is not going to be right for clusters.  Consider
        # changing this.
        wcm.concentration_rise_ratio = quartile_concentration_ratio(qlwell, peaks=ap,
                                                                    channel_num=channel_num, threshold=wcm.threshold,
                                                                    min_events=4000)

        del positive_peaks
        del negative_peaks
        del unclassified_peaks
    else:
        wcm.nonpositive_skew = skew(ap, channel_num)
        wcm.nonpositive_kurtosis = kurtosis(ap, channel_num)
    
    del ap
    # daisy chain just in case
    return wcm

def _compute_well_metrics(qlwell, well_metric):
    """
    Populate the well_metric object with statistics derived from
    the QLWell object.  This computes well-specific metrics, which
    are channel-agnostic, such as width, number of accepted peaks,
    and B-score.

    :param qlwell: QLWell record read from QLP.
    :param well_metric: WellMetric object meant to be stored.
    :return: The WellMetric object, though it gets side-effected.
    """
    # assume that width, events are same in both channels; so the width
    # and quality gates should be OK
    accepted_events = accepted_peaks(qlwell)
    wm = well_metric # for convenience
    wm.accepted_event_count = len(accepted_events)
    wm.total_event_count = len(qlwell.peaks)

    # TODO: double check on desired values for these (width of accepted, or overall width?)
    # current hunch is to use the width of all events
    width_peaks = above_min_amplitude_peaks(qlwell)
    wm.width_mean = np.mean(fam_widths(width_peaks))
    wm.width_variance = np.std(fam_widths(width_peaks))
    wm.accepted_width_mean = np.mean(fam_widths(accepted_events))
    wm.accepted_width_stdev = np.std(fam_widths(accepted_events))
    wm.rejected_peaks = qlwell.statistics.rejected_peaks
    wm.min_amplitude_peaks = len(min_amplitude_peaks(qlwell))
    wm.vertical_streak_events = qlwell.statistics.vertical_streak_peaks
    wm.sum_baseline_mean = qlwell.statistics.sum_baseline_mean
    wm.sum_baseline_stdev = qlwell.statistics.sum_baseline_stdev
    wm.short_interval_count = narrow_droplet_spacing_count(qlwell, threshold=NARROW_NORMALIZED_DROPLET_SPACING)
    wm.short_interval_threshold = NARROW_NORMALIZED_DROPLET_SPACING
    wm.balance_score = well_balance_score_2d(qlwell)[0]
    wm.fragmentation_probability = well_fragmentation_probability(qlwell)[0]

    #new droplet metrics -> Diagonal scatter....
    NEW_DROPLET_CLUSTER_WELL_METRICS_CALCULATOR.compute(qlwell, wm)
	
    global DEFAULT_CNV_CALC
    DEFAULT_CNV_CALC.compute(qlwell, wm)
    global DEFAULT_NULL_LINKAGE_CALC
    DEFAULT_NULL_LINKAGE_CALC.compute(qlwell, wm)

    return wm

def compute_metric_foreach_qlwell(qlplate, plate_metric, calculator):
    """
    For each analyzed well in the plate, update the metric through the
    transform in the supplied calculator.
    """
    pm_well_map = plate_metric.well_metric_name_dict
    for name, qlwell in sorted(qlplate.analyzed_wells.items()):
        wm = pm_well_map[name]
        calculator.compute(qlwell, wm)

def compute_metric_foreach_qlwell_channel(qlplate, plate_metric, calculator):
    pm_well_map = plate_metric.well_metric_name_dict
    for name, qlwell in sorted(qlplate.analyzed_wells.items()):
        wm = pm_well_map[name]
        for idx, channel in enumerate(qlwell.channels):
            calculator.compute(qlwell, channel, wm.well_channel_metrics[idx])


class PlateMetricCalculator(object):
    """
    Defines a class that calculates metrics for a group of
    wells based off the properties of the plate.
    """
    def compute(self, qlplate, plate_metric):
        return plate_metric

class ColorCompOrthogonalMetric(PlateMetricCalculator):
    def compute(self, qlplate, plate_metric):
        wells = qlplate.analyzed_wells.values()

        fam_hi = [w for w in wells if w.sample_name in ('FAM HI', 'FAM 350nM')]
        fam_lo = [w for w in wells if w.sample_name in ('FAM LO', 'FAM 40nM')]
        vic_hi = [w for w in wells if w.sample_name in ('VIC HI', 'VIC 350nM')]
        vic_lo = [w for w in wells if w.sample_name in ('VIC LO', 'VIC 70nM')]
        if fam_hi and fam_lo and vic_hi and vic_lo:
            fam_hi_peaks = accepted_peaks(fam_hi[0])
            fam_lo_peaks = accepted_peaks(fam_lo[0])
            vic_hi_peaks = accepted_peaks(vic_hi[0])
            vic_lo_peaks = accepted_peaks(vic_lo[0])

            fam_hi_f = np.mean(fam_amplitudes(fam_hi_peaks))
            fam_hi_v = np.mean(vic_amplitudes(fam_hi_peaks))
            fam_lo_f = np.mean(fam_amplitudes(fam_lo_peaks))
            fam_lo_v = np.mean(vic_amplitudes(fam_lo_peaks))

            vic_hi_f = np.mean(fam_amplitudes(vic_hi_peaks))
            vic_hi_v = np.mean(vic_amplitudes(vic_hi_peaks))
            vic_lo_f = np.mean(fam_amplitudes(vic_lo_peaks))
            vic_lo_v = np.mean(vic_amplitudes(vic_lo_peaks))

            fam_vec = [fam_hi_v-fam_lo_v, fam_hi_f-fam_lo_f]
            vic_vec = [vic_hi_v-vic_lo_v, vic_hi_f-vic_lo_f]
            dot = np.dot(fam_vec, vic_vec)
            norm_diff = abs(90-np.rad2deg(math.acos(dot/(math.hypot(*fam_vec)*math.hypot(*vic_vec)))))
            fam_diff = np.rad2deg(math.atan(fam_vec[0]/fam_vec[1]))
            vic_diff = np.rad2deg(math.atan(vic_vec[1]/vic_vec[0]))

            # maybe there is an easier way to do this, but this is how my brain works
            # y = mx + b forever
            mf = fam_vec[1]/fam_vec[0]
            mv = vic_vec[1]/vic_vec[0]
            bf = fam_hi_f - mf*fam_hi_v
            bv = vic_hi_f - mv*vic_hi_v
            xv = (bv-bf)/(mf-mv)
            xf = mf*xv + bf

            origin_diff = math.sqrt(xv**2+xf**2)
            plate_metric.fam_normal_offset = fam_diff
            plate_metric.vic_normal_offset = vic_diff
            plate_metric.famvic_normal_offset = norm_diff
            plate_metric.famvic_origin_offset = origin_diff
        else:
            plate_metric.fam_normal_offset = None
            plate_metric.vic_normal_offset = None
            plate_metric.famvic_normal_offset = None
            plate_metric.famvic_origin_offset = None
        
        return plate_metric

class ColorComp2DRainMetric(PlateMetricCalculator):
    """
    Computes 2D rain metric (rain_2d_hi, rain_2d_lo)
    """
    def compute(self, qlplate, plate_metric):
        wells = qlplate.analyzed_wells.values()
        fam_hi = [w for w in wells if w.sample_name in ('FAM HI', 'FAM 350nM')]
        fam_lo = [w for w in wells if w.sample_name in ('FAM LO', 'FAM 40nM')]
        vic_hi = [w for w in wells if w.sample_name in ('VIC HI', 'VIC 350nM')]
        vic_lo = [w for w in wells if w.sample_name in ('VIC LO', 'VIC 70nM')]

        if fam_hi and vic_hi:
            fam_hi_peaks = accepted_peaks(fam_hi[0])
            vic_hi_peaks = accepted_peaks(vic_hi[0])

            # get tight rain boundaries (3.25% CV*3) -- below fam_hi, below vic_hi
            nil, nil, nil, nil, nil, nil, fam_low = rain_pvalues_thresholds(fam_hi_peaks, channel_num=0, threshold=None, pct_boundary=.0975)
            nil, nil, nil, nil, nil, nil, vic_low = rain_pvalues_thresholds(vic_hi_peaks, channel_num=1, threshold=None, pct_boundary=.135)

            all_peaks = np.hstack([fam_hi_peaks, vic_hi_peaks])
            # find total % of all peaks
            dontcare, dontcare, dontcare, rain = cluster_2d(all_peaks, fam_low, vic_low)
            plate_metric.hi_cluster_rain = float(len(rain))/len(all_peaks)
        
        if fam_lo and vic_lo:
            fam_lo_peaks = accepted_peaks(fam_lo[0])
            vic_lo_peaks = accepted_peaks(vic_lo[0])

            # get tight rain boundaries (4.5% CV*3) -- below fam_hi, below vic_hi
            nil, nil, nil, nil, nil, nil, fam_low = rain_pvalues_thresholds(fam_lo_peaks, channel_num=0, threshold=None, pct_boundary=.0975)
            nil, nil, nil, nil, nil, nil, vic_low = rain_pvalues_thresholds(vic_lo_peaks, channel_num=1, threshold=None, pct_boundary=.135)

            all_peaks = np.hstack([fam_lo_peaks, vic_lo_peaks])
            # find total % of all peaks
            dontcare, dontcare, dontcare, rain = cluster_2d(all_peaks, fam_low, vic_low)
            plate_metric.lo_cluster_rain = float(len(rain))/len(all_peaks)
        
        return plate_metric

class CarryoverPlateMetric(PlateMetricCalculator):
    def __init__(self, empty_sample_names=None, channel_num=0):
        """
        :param empty_sample_names: The sample names of wells that should not have fluorescence.
        :param channel_num: The channel number to measure carryover on (default 0/FAM)
        """
        if not empty_sample_names:
            empty_sample_names = ('Stealth','Stealth well','stealth')
        
        self.empty_sample_names = empty_sample_names
        self.channel_num = channel_num
    
    def compute(self, qlplate, plate_metrics):
        plate_all_contamination, plate_gated_contamination, plate_carryover, num_wells, well_peak_dict = \
            self.contamination_carryover_peaks(qlplate)
        
        # TODO change this to allow metric computation (or store # carryover wells)
        plate_metrics.carryover_peaks = len(plate_carryover)
        plate_metrics.gated_contamination_peaks = len(plate_gated_contamination)
        plate_metrics.contamination_peaks = len(plate_all_contamination)
        plate_metrics.stealth_wells = num_wells

        for k, v in well_peak_dict.items():
            plate_metrics.well_metric_name_dict[k].carryover_peaks = v
        
        return plate_metrics

    def contamination_carryover_peaks(self, qlplate, exclude_min_amplitude_peaks=True):
        """
        Returns (aggregate contamination peaks, aggregate gated contamination peaks, aggregate carryover peaks,
                 number of carryover wells, well name->#carryover well peaks per well)
        """
        well_pairs = []
        eventful_well = None
        stealth_well = None
        
        # FIXFIX relax when QuantaSoft bug is resolved
        #for well in qlplate.in_run_order:
        wells = sorted(qlplate.analyzed_wells.values(), cmp=QLWell.row_order_comparator)
        for well in sorted(qlplate.analyzed_wells.values(), cmp=QLWell.row_order_comparator):
            if well.original_sample_name not in self.empty_sample_names:
                stealth_well = None
                eventful_well = well
            elif well.original_sample_name in self.empty_sample_names:
                stealth_well = well
                if eventful_well:
                    well_pairs.append((eventful_well, stealth_well))
                    eventful_well = None
                    stealth_well = None
        
        contamination_peaks = np.ndarray([0], dtype=peak_dtype(2))
        gated_contamination_peaks = np.ndarray([0], dtype=peak_dtype(2))
        carryover_peaks = np.ndarray([0], dtype=peak_dtype(2))
        num_wells = 0
        carryover_well_peak_dict = dict()
        for e, s in well_pairs:
            num_wells = num_wells + 1
            stats = e.channels[self.channel_num].statistics
            threshold = stats.threshold
            min_width_gate, max_width_gate = well_static_width_gates(e)

            # TODO: what to do about quality gating?
            # get all contamination first above 750 RFU (assume threshold above 750?)
            if exclude_min_amplitude_peaks:
                peaks = above_min_amplitude_peaks(s)
            else:
                peaks = s.peaks
            
            well_contamination_peaks, too_low = cluster_1d(peaks, self.channel_num, 750)
            well_gated_contamination_peaks = width_gated(well_contamination_peaks,
                                                    min_width_gate=min_width_gate,
                                                    max_width_gate=max_width_gate,
                                                    on_channel_num=self.channel_num,
                                                    ignore_gating_flags=True)

            if threshold:
                well_carryover_peaks, under_threshold = cluster_1d(well_gated_contamination_peaks, self.channel_num, threshold)
            else:
                well_carryover_peaks = np.ndarray([0], dtype=peak_dtype(2))
            
            contamination_peaks = np.hstack([contamination_peaks, well_contamination_peaks])
            gated_contamination_peaks = np.hstack([gated_contamination_peaks, well_gated_contamination_peaks])
            carryover_peaks = np.hstack([carryover_peaks, well_carryover_peaks])
            carryover_well_peak_dict[s.name] = len(well_carryover_peaks)
        
        return contamination_peaks, gated_contamination_peaks, carryover_peaks, num_wells, carryover_well_peak_dict

class ColorCompCarryoverPlateMetric(CarryoverPlateMetric):
    def contamination_carryover_peaks(self, qlplate, exclude_min_amplitude_peaks=True):
        """
        For now, just count FAM HI carryover
        """
        carryover_upper_bound = None
        carryover_lower_bound = None
        min_width_gate = None
        max_width_gate = None

        contamination_peaks = np.ndarray([0], dtype=peak_dtype(2))
        gated_contamination_peaks = np.ndarray([0], dtype=peak_dtype(2))
        carryover_peaks = np.ndarray([0], dtype=peak_dtype(2))
        num_wells = 0
        carryover_well_peak_dict = dict()

        fam_bounds = []
        vic_bounds = []
        # TODO fixfix when QS bug resolved
        #for idx, well in enumerate(qlplate.in_run_order):
        for idx, well in enumerate(sorted(qlplate.analyzed_wells.values(), cmp=QLWell.row_order_comparator)):
            if exclude_min_amplitude_peaks:
                peaks = above_min_amplitude_peaks(well)
            else:
                peaks = well.peaks
            
            if well.original_sample_name not in ('FAM HI', 'FAM 350nM'):
                num_wells = num_wells+1
                for bounds, channel in zip((fam_bounds, vic_bounds),(0,1)):
                    for lower_bound, upper_bound, min_width_gate, max_width_gate in bounds:
                        # TODO: this will double-count contamination if the bounds overlap.  But if the bounds
                        # overlap, you have much bigger problems than carryover.  OK for now.
                        argument_bounds = [(None, None),(None, None)]
                        argument_bounds[channel] = (lower_bound, upper_bound)
                        well_contamination_peaks = filter_amplitude_range(peaks, argument_bounds)
                        well_carryover_peaks = width_gated(well_contamination_peaks,
                                                      min_width_gate=min_width_gate,
                                                      max_width_gate=max_width_gate,
                                                      on_channel_num=channel,
                                                      ignore_gating_flags=True)
                        if well.name not in carryover_well_peak_dict:
                            carryover_well_peak_dict[well.name] = len(well_carryover_peaks)
                        else:
                            carryover_well_peak_dict[well.name] = carryover_well_peak_dict[well.name] + len(well_carryover_peaks)
                        
                        contamination_peaks = np.hstack([contamination_peaks, well_contamination_peaks])
                        carryover_peaks = np.hstack([carryover_peaks, well_carryover_peaks])
            
            if well.original_sample_name in ('FAM HI', 'FAM 350nM', 'FAM LO', 'FAM 40nM', 'VIC HI', 'VIC 350nM'):
                if well.original_sample_name.startswith('VIC'):
                    add_to = vic_bounds
                    amps = vic_amplitudes(peaks)
                else:
                    add_to = fam_bounds
                    amps = fam_amplitudes(peaks)
                
                min_width_gate, max_width_gate = well_static_width_gates(well)

                mean = np.mean(amps)
                std = np.std(amps)
                lower_bound = mean - 3*std
                upper_bound = mean + 3*std

                add_to.append((lower_bound, upper_bound, min_width_gate, max_width_gate))
        
        return contamination_peaks, gated_contamination_peaks, carryover_peaks, num_wells, carryover_well_peak_dict

DEFAULT_CARRYOVER_CALC = CarryoverPlateMetric(empty_sample_names=('Stealth','stealth','Stealth well'),channel_num=0)
COLORCOMP_CARRYOVER_CALC = ColorCompCarryoverPlateMetric()


class NTCSaturatedThresholdCalculator(object):
    """
    Compute the number of false positives using a threshold
    calculated by analyzing saturated and NTC wells.
    """
    def __init__(self,
                 positive_threshold_basis_well_names,
                 negative_threshold_basis_well_names,
                 channel_nums):
        self.positive_well_names = positive_threshold_basis_well_names
        self.negative_well_names = negative_threshold_basis_well_names
        self.channel_nums = channel_nums
    
    def _compute_thresholds(self, positive_well_metrics, negative_well_metrics):
        """
        Default mechanism for computing the threshold of the positives
        and negatives -- 1/4 between the positive and negative means.
        """
        channel_thresholds = {}
        for num in self.channel_nums:
            pos_avg = np.mean([pm.well_channel_metrics[num].amplitude_mean for pm in positive_well_metrics if pm.well_channel_metrics[num].amplitude_mean is not None])
            neg_avg = np.mean([nm.well_channel_metrics[num].amplitude_mean for nm in negative_well_metrics if nm.well_channel_metrics[num].amplitude_mean is not None])
            
            channel_thresholds[num] = (neg_avg*3+pos_avg)/4
        
        return channel_thresholds

class NTCSaturatedFalsePositiveCalculator(PlateMetricCalculator, NTCSaturatedThresholdCalculator):
    """
    Calculates false positive peaks by calculating a threshold
    based on the means of saturated and NTC wells, and then
    computing the peaks over the threshold. 
    """
    def __init__(self, positive_threshold_basis_well_names,
                 negative_threshold_basis_well_names,
                 measurement_well_names,
                 channel_nums):
        NTCSaturatedThresholdCalculator.__init__(self, positive_threshold_basis_well_names,
                                                 negative_threshold_basis_well_names,
                                                 channel_nums)
        self.measurement_well_names = measurement_well_names

    def compute(self, qlplate, plate_metric):
        wmd = plate_metric.well_metric_name_dict
        pwm = [wmd.get(name, None) for name in self.positive_well_names]
        nwm = [wmd.get(name, None) for name in self.negative_well_names]
        pwm = [p for p in pwm if p]
        nwm = [n for n in nwm if n]
        thresholds = self._compute_thresholds(pwm, nwm)

        for name in self.measurement_well_names:
            wm = wmd.get(name, None)
            if not wm:
                continue
            for num in self.channel_nums:
                pos, neg = cluster_1d(accepted_peaks(qlplate.analyzed_wells[name]), num, thresholds[num])
                wm.well_channel_metrics[num].false_positive_peaks = len(pos)
                wm.well_channel_metrics[num].manual_threshold = thresholds[num]
        
        return plate_metric

class NTCSaturatedFalseNegativeCalculator(PlateMetricCalculator, NTCSaturatedThresholdCalculator):
    """
    Calculates false positive peaks by calculating a threshold
    based on the means of saturated and NTC wells, and then
    computing the peaks under the threshold. 
    """
    def __init__(self, positive_threshold_basis_well_names,
                 negative_threshold_basis_well_names,
                 measurement_well_names,
                 channel_nums):
        NTCSaturatedThresholdCalculator.__init__(self, positive_threshold_basis_well_names,
                                                 negative_threshold_basis_well_names,
                                                 channel_nums)
        self.measurement_well_names = measurement_well_names
    
    def compute(self, qlplate, plate_metric):
        wmd = plate_metric.well_metric_name_dict
        pwm = [wmd.get(name, None) for name in self.positive_well_names]
        nwm = [wmd.get(name, None) for name in self.negative_well_names]
        pwm = [p for p in pwm if p]
        nwm = [n for n in nwm if n]
        thresholds = self._compute_thresholds(pwm, nwm)

        for name in self.measurement_well_names:
            wm = wmd.get(name, None)
            if not wm:
                continue
            for num in self.channel_nums:
                pos, neg = cluster_1d(accepted_peaks(qlplate.analyzed_wells[name]), num, thresholds[num])
                wm.well_channel_metrics[num].false_negative_peaks = len(neg)
                wm.well_channel_metrics[num].manual_threshold = thresholds[num]
        
        return plate_metric

class AverageComputedThresholdCalculator(object):
    """
    Compute the estimated limits of detection by taking
    the average computed threshold (auto) for a few wells.
    """
    def __init__(self,
                 threshold_well_names,
                 channel_nums):
        self.threshold_well_names = threshold_well_names
        self.channel_nums = channel_nums
    
    def _compute_thresholds(self, threshold_well_metrics):
        channel_thresholds = {}
        
        for num in self.channel_nums:
            channel_thresholds[num] = np.mean([t.well_channel_metrics[num].threshold for t in threshold_well_metrics if t.well_channel_metrics[num].threshold])
        
        return channel_thresholds

class AverageComputedThresholdFalsePositiveCalculator(PlateMetricCalculator, AverageComputedThresholdCalculator):
    def __init__(self, threshold_well_names,
                 measurement_well_names,
                 channel_nums):
        AverageComputedThresholdCalculator.__init__(self, threshold_well_names, channel_nums)
        self.measurement_well_names = measurement_well_names
    
    def compute(self, qlplate, plate_metric):
        wmd = plate_metric.well_metric_name_dict
        twm = [wmd.get(name, None) for name in self.threshold_well_names]
        twm = [t for t in twm if t]
        thresholds = self._compute_thresholds(twm)
        
        for name in self.measurement_well_names:
            wm = wmd.get(name, None)
            if not wm:
                continue
            for num in self.channel_nums:
                pos, neg = cluster_1d(accepted_peaks(qlplate.analyzed_wells[name]), num, thresholds[num])
                wm.well_channel_metrics[num].false_positive_peaks = len(pos)
                wm.well_channel_metrics[num].manual_threshold = thresholds[num]
        
        return plate_metric

class AverageSampleThresholdFalsePositiveCalculator(AverageComputedThresholdFalsePositiveCalculator):
    """
    compute-time hack to get plate metric for FP by sample name.
    """
    def __init__(self, threshold_sample_names, measurement_sample_names, channel_nums):
        self.threshold_sample_names = threshold_sample_names
        self.measurement_sample_names = measurement_sample_names
        super(AverageSampleThresholdFalsePositiveCalculator, self).__init__([], [], channel_nums)

    def compute(self, qlplate, plate_metric):
        threshold_well_names = []
        measurement_well_names = []
        for well_name, well in qlplate.analyzed_wells.items():
            if well.sample_name in self.threshold_sample_names:
                threshold_well_names.append(well_name)
            if well.sample_name in self.measurement_sample_names:
                measurement_well_names.append(well_name)

        self.threshold_well_names = threshold_well_names
        self.measurement_well_names = measurement_well_names
        return super(AverageSampleThresholdFalsePositiveCalculator, self).compute(qlplate, plate_metric)



class WellMetricCalculator(object):
    """
    Defines a class that calculates metrics based off of well
    properties.
    """
    def compute(self, qlwell, well_metric):
        return well_metric

NOOP_WELL_METRIC_CALCULATOR = WellMetricCalculator()

class CNVCalculator(WellMetricCalculator):
    def __init__(self, target_channel_num, reference_channel_num):
        self.target_channel_num = target_channel_num
        self.reference_channel_num = reference_channel_num
    
    def compute(self, qlwell, well_metric):
        target_channel = qlwell.channels[self.target_channel_num]
        reference_channel = qlwell.channels[self.reference_channel_num]

        cnv, cnv_low, cnv_high = well_observed_cnv_interval(qlwell, self.target_channel_num, self.reference_channel_num)
        inverse_cnv, inverse_cnv_low, inverse_cnv_high = well_observed_cnv_interval(qlwell, self.reference_channel_num, self.target_channel_num)

        well_metric.cnv = cnv
        well_metric.cnv_lower_bound = cnv_low
        well_metric.cnv_upper_bound = cnv_high

        well_metric.inverse_cnv = inverse_cnv
        well_metric.inverse_cnv_lower_bound = inverse_cnv_low
        well_metric.inverse_cnv_upper_bound = inverse_cnv_high
        
        # cnv calc mode is only used for display at the moment, should rename and take out of CNVCalculator.
        if qlwell.clusters_defined:
            well_metric.cnv_calc_mode = QLWellChannelStatistics.CONC_CALC_MODE_CLUSTER
        else:
            well_metric.cnv_calc_mode = QLWellChannelStatistics.CONC_CALC_MODE_THRESHOLD

        if not target_channel.statistics.threshold or not reference_channel.statistics.threshold:
           # cannot compute CNV rise ratio if cannot compute threshold -- pos/neg unknown
           convert_nan_to_none(well_metric)
           return well_metric

        ok_peaks = accepted_peaks(qlwell)
        qsize = len(ok_peaks)/4

        # CLUSTER-TODO: fix
        if(qsize >= 1000):
            fq = ok_peaks[:qsize]
            lq = ok_peaks[(len(ok_peaks)-qsize):]
            fq_target_pos, fq_target_neg = cluster_1d(fq, self.target_channel_num,
                                                      qlwell.channels[self.target_channel_num].statistics.threshold)
            lq_target_pos, lq_target_neg = cluster_1d(lq, self.target_channel_num,
                                                      qlwell.channels[self.target_channel_num].statistics.threshold)
            fq_reference_pos, fq_reference_neg = cluster_1d(fq, self.reference_channel_num,
                                                      qlwell.channels[self.reference_channel_num].statistics.threshold)
            lq_reference_pos, lq_reference_neg = cluster_1d(lq, self.reference_channel_num,
                                                      qlwell.channels[self.reference_channel_num].statistics.threshold)
            
            fq_cnv = get_cnv(len(fq_target_pos), len(fq_target_neg),
                             len(fq_reference_pos), len(fq_reference_neg),
                             reference_copies=qlwell.ref_copy_num)
            lq_cnv = get_cnv(len(lq_target_pos), len(lq_target_neg),
                             len(lq_reference_pos), len(lq_reference_neg),
                             reference_copies=qlwell.ref_copy_num)
            
            if not fq_cnv:
                well_metric.cnv_rise_ratio = None
            else:
                well_metric.cnv_rise_ratio = lq_cnv/fq_cnv


        # TODO: probably best done elsewhere
        convert_nan_to_none(well_metric)
        return well_metric


DEFAULT_CNV_CALC = CNVCalculator(0, 1)

class StealthAirDropletsCalculator(WellMetricCalculator):
    """
    Calculate the number of air droplets in the well by looking at the
    number of droplets above the threshold level of amplitude
    on the specified channel.
    """
    def __init__(self, test_well_names, channel_num=1, threshold=250):
        self.channel_num = channel_num
        self.threshold = threshold
        self.test_well_names = test_well_names
    
    def compute(self, qlwell, well_metric):
        # TODO: assume all peaks in play here
        if qlwell.sample_name not in self.test_well_names:
            return well_metric
        
        air, below_air = cluster_1d(qlwell.peaks, self.channel_num, self.threshold)
        well_metric.air_droplets = len(air)
        well_metric.air_droplets_threshold = self.threshold
        return well_metric

STEALTH_AIRDROP_CALC = StealthAirDropletsCalculator(('Stealth', 'stealth'), 1, 250)

class AirDropletsCalculator(WellMetricCalculator):
    """
    Calculate the number of air droplets in the well by looking at
    droplets that are in the gaps in the main droplet distribution.
    """
    def __init__(self, test_well_names, channel_num=1, air_max_threshold=1000):
        self.channel_num     = channel_num
        self.air_max_threshold   = air_max_threshold
        self.test_well_names = test_well_names
    
    def compute(self, qlwell, well_metric):
        if qlwell.sample_name not in self.test_well_names:
            return well_metric
        
        air_drops = gap_air(qlwell, self.channel_num,
                            max_amp=self.air_max_threshold,
                            threshold=qlwell.channels[self.channel_num].statistics.threshold or None)
        # Rev A: droplets would not be there if below min amplitude
        # Rev B: droplets will have min amplitude flag if they were below 500
        # in the VIC channel
        accepted_times = peak_times(accepted_peaks(qlwell))
        air_times = peak_times(air_drops)
        well_metric.air_droplets = len([t for t in air_times if t in accepted_times])
        well_metric.air_droplets_threshold = qlwell.channels[1].statistics.trigger_min_amplitude

# CLUSTER-TODO: eliminate or fix
class NullLinkageCalculator(WellMetricCalculator):
    def compute(self, qlwell, well_metric):
        # do not compute a metric if neither well has a threshold set
        channels = qlwell.channels
        if not channels or len(channels) != 2:
            return None
        
        for c in channels:
            if c.statistics.threshold == 0 or not c.statistics.threshold:
                return None
        
        # get clusters
        peaks = accepted_peaks(qlwell)
        fampos_vicpos, fampos_vicneg, famneg_vicpos, famneg_vicneg = \
            cluster_2d(peaks, channels[0].statistics.threshold, channels[1].statistics.threshold)
        
        well_metric.null_linkage = linkage_2d(len(fampos_vicpos), len(fampos_vicneg),
                                              len(famneg_vicpos), len(famneg_vicneg))
        return well_metric

DEFAULT_NULL_LINKAGE_CALC = NullLinkageCalculator()

## calculates new well metrics - diagonal scatter is the only one really..
class NewDropletClusterWellMetricsCalculator(WellMetricCalculator):
    def compute(self, qlwell, well_metric):
        clusters = getClusters( qlwell )
        dscatter = diagonal_scatter( clusters )
        if ( dscatter is not None ):
            well_metric.diagonal_scatter = dscatter[1]
            well_metric.diagonal_scatter_pct  = dscatter[2] *100
        else:
            well_metric.diagonal_scatter = None
            well_metric.diagonal_scatter_pct = None       
        return well_metric

NEW_DROPLET_CLUSTER_WELL_METRICS_CALCULATOR = NewDropletClusterWellMetricsCalculator()

class ExpectedCNVCalculator(CNVCalculator):
    def __init__(self, target_channel_num, reference_channel_num, expected_cnv_transform=None):
        if not expected_cnv_transform:
            self.expected_cnv_transform = lambda well: None
        else:
            self.expected_cnv_transform = expected_cnv_transform
        super(ExpectedCNVCalculator, self).__init__(target_channel_num, reference_channel_num)
    
    def compute(self, qlwell, well_metric):
        wm = super(ExpectedCNVCalculator, self).compute(qlwell, well_metric)
        wm.expected_cnv = self.expected_cnv_transform(qlwell)

def well_sample_name_lookup(sample_map, default=None):
    """
    Wraps a key lookup into a function.
    """
    def lookup(qlwell):
        return sample_map.get(qlwell.sample_name, default)
    
    # closure
    return lookup

class WellChannelMetricCalculator(object):
    """
    Defines a class that calculates metrics based off of well channel
    properties.
    """
    def compute(self, qlwell, qlwell_channel, well_channel_metric):
        return well_channel_metric

NOOP_WELL_CHANNEL_METRIC_CALCULATOR = WellChannelMetricCalculator()

class DyeGapRainMetricCalculator(object):
    def compute(self, qlwell, qlwell_channel, well_channel_metric):
        if len(qlwell.peaks) < 1000:
            return well_channel_metric
        
        well_channel_metric.gap_rain_droplets = len(gap_rain(qlwell, channel_num=qlwell_channel.channel_num, threshold=0))
        return well_channel_metric

class NTCPositiveCalculator(WellChannelMetricCalculator):
    def __init__(self, fam_threshold=NTC_FAM_POSITIVE_THRESHOLD, vic_threshold=NTC_VIC_POSITIVE_THRESHOLD):
        super(NTCPositiveCalculator, self).__init__()
        self.fam_threshold = fam_threshold
        self.vic_threshold = vic_threshold

    def compute(self, qlwell, qlwell_channel, well_channel_metric):
        if qlwell.sample_name and 'NTC' in qlwell.sample_name:
            ap = accepted_peaks(qlwell)
            if qlwell_channel.channel_num == 0:
                threshold = self.fam_threshold
            else:
                threshold = self.vic_threshold
            ntc_pos, ntc_neg = cluster_1d(ap, qlwell_channel.channel_num, threshold)
            well_channel_metric.ntc_positives = len(ntc_pos)
        return well_channel_metric

DEFAULT_NTC_POSITIVE_CALCULATOR = NTCPositiveCalculator()

class PolydispersityCalculator(WellChannelMetricCalculator):
    def compute(self, qlwell, qlwell_channel, well_channel_metric):
        # only return for >= 1000 peaks
        if len(qlwell.peaks) < 1000:
            return well_channel_metric
        
        data = polydisperse_peaks(qlwell, qlwell_channel.channel_num,
                               threshold=qlwell_channel.statistics.threshold)
        peaksets, rain_gates, width_gates = data
        
        poly_peaks = sum([len(p) for p in peaksets])
        # have to worry about min amplitude peaks here
        # found in well_metric but we don't have access in superclass
        above_min_amp_peaks = above_min_amplitude_peaks(qlwell)
        if len(above_min_amp_peaks) == 0:
            well_channel_metric.polydispersity = 0
        else:
            well_channel_metric.polydispersity = float(poly_peaks)/len(above_min_amp_peaks)

        if hasattr(qlwell, 'sum_amplitude_bins') and len(qlwell.sum_amplitude_bins) > 0:
            data = revb_polydisperse_peaks(qlwell, qlwell_channel.channel_num,
                                           threshold=qlwell_channel.statistics.threshold)
            peaksets, rain_gates, min_amps = data
            poly_peaks = sum([len(p) for p in peaksets])
            if len(above_min_amp_peaks) == 0:
                well_channel_metric.revb_polydispersity = 0
            else:
                well_channel_metric.revb_polydispersity = float(poly_peaks)/len(above_min_amp_peaks)
        else:
            well_channel_metric.revb_polydispersity = None
        return well_channel_metric

DEFAULT_POLYD_CALC = PolydispersityCalculator()

class ExtraclusterCalculator(WellChannelMetricCalculator):
    def compute(self, qlwell, qlwell_channel, well_channel_metric):
        # only return for >= 1000 peaks
        if len(qlwell.peaks) < 1000:
            return well_channel_metric
        
        data = extracluster_peaks(qlwell, qlwell_channel.channel_num,
                                  threshold=qlwell_channel.statistics.threshold)
        peaks, rain_gates, width_gates = data
        # have to worry about min amplitude peaks here
        # found in well_metric but don't have access to wm in compute()
        above_min_amp_peaks = above_min_amplitude_peaks(qlwell)
        if len(above_min_amp_peaks) == 0:
            well_channel_metric.extracluster = 0
        else:
            well_channel_metric.extracluster = float(len(peaks))/len(above_min_amp_peaks)

        if hasattr(qlwell, 'sum_amplitude_bins') and len(qlwell.sum_amplitude_bins) > 0:
            data = revb_extracluster_peaks(qlwell, qlwell_channel.channel_num,
                                           threshold=qlwell_channel.statistics.threshold)
            peaks, rain_gates, mean_amps = data
            if len(above_min_amp_peaks) == 0:
                well_channel_metric.revb_extracluster = 0
            else:
                well_channel_metric.revb_extracluster = float(len(peaks))/len(above_min_amp_peaks)
        else:
            well_channel_metric.revb_extracluster = None
        return well_channel_metric

DEFAULT_EXTRAC_CALC = ExtraclusterCalculator()

## Back fill new droplet cluster metrics including s2d, single rain, double rain, 
class NewDropletClusterMetricsCalculator(WellChannelMetricCalculator):
    def compute(self, qlwell, qlwell_channel, well_channel_metric):

        channel_num = qlwell_channel.channel_num

        well_channel_metric.s2d_value = well_s2d_values( qlwell )[channel_num]

        clusters = getClusters( qlwell  )

        high_fliers = high_flier_droplets( clusters, channel_num )
        if ( high_fliers is not None ):
            well_channel_metric.high_flier_value   = high_fliers[1]
        else:
            well_channel_metric.high_flier_value   = None

        low_fliers  = low_flier_droplets( clusters, channel_num )
        if ( low_fliers  is not None ):
            well_channel_metric.low_flier_value    = low_fliers[1]
        else:
            well_channel_metric.low_flier_value    = None

        singleRain  = singleRain_droplets( clusters, channel_num )
        if ( singleRain is not None ):
            well_channel_metric.single_rain_value  = singleRain[1]
            well_channel_metric.single_rain_pct    = singleRain[2] * 100
        else:
            well_channel_metric.single_rain_value  = None
            well_channel_metric.single_rain_pct    = None

        doubleRain  = doubleRain_droplets( clusters, channel_num )
        if ( doubleRain is not None ):
            well_channel_metric.double_rain_value  = doubleRain[1]
            well_channel_metric.double_rain_pct    = doubleRain[2] * 100
        else:
            well_channel_metric.double_rain_value  = None
            well_channel_metric.double_rain_pct    = None

        return well_channel_metric

NEW_DROPLET_CLUSTER_METRICS_CALCULATOR = NewDropletClusterMetricsCalculator()


class ExpectedConcentrationCalculator(WellChannelMetricCalculator):
    def __init__(self, expected_conc_transform=None):
        if not expected_conc_transform:
            self.expected_conc_transform = lambda well, channel: None
        else:
            self.expected_conc_transform = expected_conc_transform
    
    def compute(self, qlwell, qlwell_channel, well_channel_metric):
        well_channel_metric.expected_concentration = self.expected_conc_transform(qlwell, qlwell_channel)

# TODO: make static method of ExpectedConcentrationCalculator?
def well_channel_sample_name_lookup(sample_map, default=None):
    """
    Wraps a concentration lookup into a function.

    :param sample_map: map (sample_name => (FAM conc, VIC conc))
    """
    def lookup(qlwell, qlwell_channel):
        """
        Given a well and channel, return the expected value
        of that channel.
        """
        conc = sample_map.get(qlwell.sample_name, None)
        if conc:
            return conc[qlwell_channel.channel_num]
        return default
    
    # closure
    return lookup

class ExpectedThresholdCalculator(WellChannelMetricCalculator):
    def __init__(self, expected_threshold_transform=None):
        if not expected_threshold_transform:
            self.expected_threshold_transform = lambda well, channel: True
        else:
            self.expected_threshold_transform = expected_threshold_transform
    
    def compute(self, qlwell, qlwell_channel, well_channel_metric):
        well_channel_metric.auto_threshold_expected = self.expected_threshold_transform(qlwell, qlwell_channel)

class CarryoverThresholdCalculator(WellChannelMetricCalculator):
    def compute(self, qlwell, qlwell_channel, well_channel_metric):
        if well_channel_metric.channel_num == 1 or qlwell.sample_name in ('stealth', 'Stealth'):
            well_channel_metric.auto_threshold_expected = False
        else:
            well_channel_metric.auto_threshold_expected = True
