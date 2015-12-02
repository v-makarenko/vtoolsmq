import unittest, os, math
import numpy as np
from pyqlb.factory import QLNumpyObjectFactory
from pyqlb.nstats.peaks import fam_amplitudes, vic_amplitudes
from qtools.lib.metrics.colorcal import *
from qtools.model import WellChannelMetric, QLBWellChannel

def local(path):
    """
    Maybe this exists?
    """
    return "%s/%s" % (os.path.dirname(__file__), path)

class TestColorCal(unittest.TestCase):
	def __init__(self, *args, **kwargs):
		super(TestColorCal, self).__init__(*args, **kwargs)
		factory = QLNumpyObjectFactory()
		self.vic = factory.parse_plate(local('colorcal_vic.qlp'))
		self.hex = factory.parse_plate(local('colorcal_hex.qlp'))

	@property
	def vic_well(self):
		return self.vic.analyzed_wells['A01']

	@property
	def hex_well(self):
		return self.hex.analyzed_wells['B02']

	def test_single_well_calibration_clusters(self):
		fam_hi, fam_lo, vic_hi, vic_lo = single_well_calibration_clusters(self.vic_well, DYES_FAM_VIC)
		assert len(fam_hi) == 5495
		assert len(fam_lo) == 5201
		assert len(vic_hi) == 5326
		assert len(vic_lo) == 5257

		fam_amp = np.mean(fam_amplitudes(fam_hi))
		assert abs(20000-fam_amp) < 10

		fam_lo_amp = np.mean(fam_amplitudes(fam_lo))
		assert abs(2369-fam_lo_amp) < 10

		vic_amp = np.mean(vic_amplitudes(vic_hi))
		assert abs(10000-vic_amp) < 15

		vic_lo_amp = np.mean(vic_amplitudes(vic_lo))
		assert abs(2025-vic_lo_amp) < 10

		fam_hi, fam_lo, hex_hi, hex_lo = single_well_calibration_clusters(self.hex_well, DYES_FAM_HEX)
		assert len(fam_hi) == 3623
		assert len(fam_lo) == 3456
		assert len(hex_hi) == 3719
		assert len(hex_lo) == 3599

		fam_amp = np.mean(fam_amplitudes(fam_hi))
		assert abs(20000-fam_amp) < 10

		fam_lo_amp = np.mean(fam_amplitudes(fam_lo))
		assert abs(2790-fam_lo_amp) < 10

		hex_amp = np.mean(vic_amplitudes(hex_hi))
		assert abs(10000-hex_amp) < 15

		hex_lo_amp = np.mean(vic_amplitudes(hex_lo))
		assert abs(2010-hex_lo_amp) < 10

	def test_dye_cal(self):
		fam, vic = DYES_FAM_VIC
		assert fam.lo_conc == 40
		assert vic.lo_conc == 70

		fam, hexd = DYES_FAM_HEX
		assert vic.expected_hi_amplitude == 10000
		assert hexd.expected_hi_amplitude == 8100

		assert fam.expected_lo_amplitude == 800000/350.0
		assert hexd.expected_lo_amplitude == (8100*70)/350.0

		assert vic.expected_magnitude_threshold == math.sqrt(2000*10000)

	def test_singlewell_calculator(self):
		calc = SINGLEWELL_CHANNEL_COLORCOMP_CALC

		blue_chan = QLBWellChannel()
		green_chan = QLBWellChannel()
		blue_cm = WellChannelMetric(channel_num=0)
		green_cm = WellChannelMetric(channel_num=1)

		calc.compute(self.vic_well, blue_chan, blue_cm)
		calc.compute(self.vic_well, green_chan, green_cm)

		assert blue_cm.positive_peaks == 5495
		assert blue_cm.negative_peaks == 5201
		assert abs(20000-blue_cm.positive_mean) < 10
		assert abs(350-blue_cm.positive_stdev) < 10
		assert abs(2369-blue_cm.negative_mean) < 10
		assert abs(120-blue_cm.negative_stdev) < 10

		assert green_cm.positive_peaks == 5326
		assert green_cm.negative_peaks == 5257
		assert abs(10000-green_cm.positive_mean) < 15
		assert abs(220-green_cm.positive_stdev) < 10
		assert abs(2025-green_cm.negative_mean) < 10
		assert abs(88-green_cm.negative_stdev) < 5

		calc.compute(self.hex_well, blue_chan, blue_cm)
		calc.compute(self.hex_well, green_chan, green_cm)

		assert blue_cm.positive_peaks == 3623
		assert blue_cm.negative_peaks == 3456
		assert abs(20000-blue_cm.positive_mean) < 10
		assert abs(400-blue_cm.positive_stdev) < 10
		assert abs(2790-blue_cm.negative_mean) < 10
		assert abs(100-blue_cm.negative_stdev) < 10

		assert green_cm.positive_peaks == 3719
		assert green_cm.negative_peaks == 3599
		assert abs(10000-green_cm.positive_mean) < 15
		assert abs(300-green_cm.positive_stdev) < 5
		assert abs(2010-green_cm.negative_mean) < 10
		assert abs(100-green_cm.negative_stdev) < 5
