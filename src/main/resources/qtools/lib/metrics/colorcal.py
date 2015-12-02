"""
Color Calibration Classes & Functions
"""

import cmath, math
import numpy as np

from pyqlb.nstats.peaks import fam_amplitudes, vic_amplitudes, color_uncorrected_peaks, fam_widths
from pyqlb.nstats.well import accepted_peaks
from qtools.lib.metrics import WellChannelMetricCalculator, WellMetricCalculator

__all__ = ['single_well_calibration_clusters',
           'DyeCalibrationProperties',
           'DYES_FAM_VIC',
           'DYES_FAM_HEX',
           'DYES_EVA',
           'SINGLEWELL_CHANNEL_COLORCOMP_CALC',
           'SINGLEWELL_COLORCOMP_CALC']

class DyeCalibrationProperties(object):
    def __init__(self, lo_conc, hi_conc, expected_hi_amplitude, scaled_hi_amplitude):
        self.lo_conc               = float(lo_conc)
        self.hi_conc               = float(hi_conc)
        self.expected_hi_amplitude = float(expected_hi_amplitude)
        self.scaled_hi_amplitude   = float(scaled_hi_amplitude)

    @property
    def expected_lo_amplitude(self):
        return (self.lo_conc/self.hi_conc)*self.expected_hi_amplitude

    @property
    def expected_magnitude_threshold(self):
        return math.sqrt(self.expected_lo_amplitude*self.expected_hi_amplitude)


DYE_PROPS_FAM = DyeCalibrationProperties(40, 350, 20000, 20000)
DYE_PROPS_VIC = DyeCalibrationProperties(70, 350, 10000, 10000)
DYE_PROPS_HEX = DyeCalibrationProperties(70, 350, 8100, 10000)

DYES_FAM_VIC = (DYE_PROPS_FAM, DYE_PROPS_VIC)
DYES_FAM_HEX = (DYE_PROPS_FAM, DYE_PROPS_HEX)
DYES_EVA = ()

THETA_THRESHOLD = math.pi / 4

def single_well_calibration_clusters(qlwell, dye_cal_props):
    """
    Returns the clusters for the specified color calibration well.

    Returns them in ch0-HI, ch0-LO, ch1-HI, ch1-LO order.

    :param qlwell: The well to analyze
    :param dye_cal_props: A list of dye properties representing the calibration
                          properties on the dyes for each channel.  (Should be a 2-tuple.)
    """
    ok_peaks = accepted_peaks(qlwell)
    
    if ( len( ok_peaks ) < 1 ):
        #pass back a 4-tuple of empty peaks
        return ( ok_peaks,ok_peaks,ok_peaks,ok_peaks)

    peaks = color_uncorrected_peaks(accepted_peaks(qlwell), qlwell.color_compensation_matrix)

    # FAM is y, VIC is x.
    polars = np.array([cmath.polar(complex(f, v)) for f, v in zip(vic_amplitudes(peaks), fam_amplitudes(peaks))])

    blue_hi = np.extract(reduce(np.logical_and,
                                (polars[...,1] >= THETA_THRESHOLD,
                                 polars[...,0] >= dye_cal_props[0].expected_magnitude_threshold)),
                         ok_peaks)
    blue_lo = np.extract(reduce(np.logical_and,
                                (polars[...,1] >= THETA_THRESHOLD,
                                 polars[...,0] < dye_cal_props[0].expected_magnitude_threshold)),
                         ok_peaks)

    green_hi = np.extract(reduce(np.logical_and,
                                 (polars[...,1] < THETA_THRESHOLD,
                                  polars[...,0] >= dye_cal_props[1].expected_magnitude_threshold)),
                          ok_peaks)

    green_lo = np.extract(reduce(np.logical_and,
                                 (polars[...,1] < THETA_THRESHOLD,
                                  polars[...,0] < dye_cal_props[1].expected_magnitude_threshold)),
                          ok_peaks)
    
    return blue_hi, blue_lo, green_hi, green_lo

DYES_FAM_VIC_LABEL = 'FAM/VIC'
DYES_FAM_HEX_LABEL = 'FAM/HEX'
DYES_EVA_LABEL = 'EVAGREEN'

class SingleWellChannelColorCompCalculator(WellChannelMetricCalculator):
    def compute(self, qlwell, qlwell_channel, well_channel_metric, dyeset=None):
        if dyeset:
            blue_hi, blue_lo, green_hi, green_lo = single_well_calibration_clusters(qlwell, dyeset)
        elif qlwell.sample_name == DYES_FAM_VIC_LABEL:
            blue_hi, blue_lo, green_hi, green_lo = single_well_calibration_clusters(qlwell, DYES_FAM_VIC)
        elif qlwell.sample_name == DYES_FAM_HEX_LABEL:
            blue_hi, blue_lo, green_hi, green_lo = single_well_calibration_clusters(qlwell, DYES_FAM_HEX)
        else:
            # do not know how to compute, return wcm
            return well_channel_metric
        if well_channel_metric.channel_num == 0:
            hi_amplitudes = fam_amplitudes(blue_hi)
            lo_amplitudes = fam_amplitudes(blue_lo)
            well_channel_metric.positive_peaks = len(blue_hi)
            well_channel_metric.positive_mean = np.mean(hi_amplitudes)
            well_channel_metric.positive_stdev = np.std(hi_amplitudes)
            well_channel_metric.negative_peaks = len(blue_lo)
            well_channel_metric.negative_mean = np.mean(lo_amplitudes)
            well_channel_metric.negative_stdev = np.std(lo_amplitudes)
            
            well_channel_metric.width_mean_hi = np.mean( fam_widths(  blue_hi ) )

        elif well_channel_metric.channel_num == 1:
            hi_amplitudes = vic_amplitudes(green_hi)
            lo_amplitudes = vic_amplitudes(green_lo)
            well_channel_metric.positive_peaks = len(green_hi)
            well_channel_metric.positive_mean = np.mean(hi_amplitudes)
            well_channel_metric.positive_stdev = np.std(hi_amplitudes)
            well_channel_metric.negative_peaks = len(green_lo)
            well_channel_metric.negative_mean = np.mean(lo_amplitudes)
            well_channel_metric.negative_stdev = np.std(lo_amplitudes)

            well_channel_metric.width_mean_hi = np.mean( fam_widths(  green_hi ))

        return well_channel_metric

SINGLEWELL_CHANNEL_COLORCOMP_CALC = SingleWellChannelColorCompCalculator()

class SingleWellColorCompCalculator(WellMetricCalculator):
     def compute(self, qlwell, well_metric):
        if len(well_metric.well_channel_metrics) < 2:
            return None
        elif (  well_metric.well_channel_metrics[0].width_mean_hi is None \
           or well_metric.well_channel_metrics[1].width_mean_hi is None ):
            return None

        delta_widths = well_metric.well_channel_metrics[0].width_mean_hi \
                     - well_metric.well_channel_metrics[1].width_mean_hi
        well_metric._delta_widths = delta_widths
        
        return well_metric

SINGLEWELL_COLORCOMP_CALC = SingleWellColorCompCalculator()

