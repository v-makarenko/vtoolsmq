from qtools.lib.nstats.peaks import *
import os, unittest
from qtools.lib.qlb_factory import get_plate


def local(path):
    """
    Maybe this exists?
    """
    return "%s/%s" % (os.path.dirname(__file__), path)

try:
	jack = get_plate(local('6543.qlp'))
	carryover = get_plate(local('7174.qlp'))
	biggap = get_plate(local('7587.qlp'))
	events = get_plate(local('8569.qlp'))
	colorcomp = get_plate(local('8977.qlp'))
except IOError, e:
	jack = None
	carryover = None
	biggap = None
	events = None
	colorcomp = None

@unittest.skip("Needs QLP files")
class TestPeaks(unittest.TestCase):
	def setUp(self):
		self.jack = jack
		self.carryover = carryover
		self.events = events
		self.colorcomp = colorcomp
		self.biggap = biggap
	
	def test_quartile_concentration_ratio(self):
		c05 = self.jack.analyzed_wells['C05']
		assert quartile_concentration_ratio(c05, 0) > 1.068
		assert quartile_concentration_ratio(c05, 0) < 1.07
		assert quartile_concentration_ratio(c05, 1) > 1.172
		assert quartile_concentration_ratio(c05, 1) < 1.174

		f06 = self.jack.analyzed_wells['F06']
		assert quartile_concentration_ratio(f06, 0) is None
		assert quartile_concentration_ratio(f06, 1) > 1.014
		assert quartile_concentration_ratio(f06, 1) < 1.016
		assert quartile_concentration_ratio(f06, 1, min_events=20000) is None

		# just testing peaks
		assert quartile_concentration_ratio(f06, 1, peaks=accepted_peaks(c05), threshold=c05.channels[0].statistics.threshold) > 1.068
		assert quartile_concentration_ratio(f06, 0, peaks=accepted_peaks(c05), threshold=c05.channels[0].statistics.threshold) < 1.07
	
	def test_accepted_peaks(self):
		a01 = self.carryover.analyzed_wells['A01']
		apeaks = accepted_peaks(a01)
		assert len(apeaks) == 14279
		a02 = self.carryover.analyzed_wells['A02']
		apeaks = accepted_peaks(a02)
		assert len(apeaks) == 0
	
	def test_rain_split(self):
		# TODO test this
		a05 = self.carryover.analyzed_wells['A05']
		rain, nonrain = rain_split(a05, 0)
		assert len(rain) == 34
		assert len(nonrain) == 9530

		a03 = self.events.analyzed_wells['A03']
		rain, nonrain = rain_split(a03, 0, threshold=0) # go with this one for single chan
		assert len(rain) == 5
		rain, nonrain = rain_split(a03, 0)
		assert len(rain) == 2
	
	def test_gap_rain(self):
		a03 = self.colorcomp.analyzed_wells['B03']
		gap_drops = gap_rain(a03, 1, threshold=0)
		assert len(gap_drops) == 5
		assert len(gap_rain(self.colorcomp.analyzed_wells['B04'], 1, threshold=0)) == 4

		f06 = self.biggap.analyzed_wells['F06']
		gap_drops = gap_rain(f06, 0, threshold=0)
		assert len(gap_drops) == 843


