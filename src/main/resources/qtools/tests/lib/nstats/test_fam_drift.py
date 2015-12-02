from pyqlb.factory import QLNumpyObjectFactory
from qtools.lib.nstats.fam_drift import fam_variation, fam_variation_splits, peak_count
import os, unittest

def local(path):
    """
    Maybe this exists?
    """
    return "%s/%s" % (os.path.dirname(__file__), path)

@unittest.skip("Needs QLP files")
class TestFamDrift(unittest.TestCase):

	def setUp(self):
		factory = QLNumpyObjectFactory()
		self.plate = factory.parse_plate(local('colorcomp.qlp'))
	
	def test_fam_drift(self):
		fam = self.plate.wells['C01']
		var = fam_variation(fam)
		print var
		assert var > 0.03 and var < 0.04
	
	def test_fam_variation_splits(self):
		fam = self.plate.wells['C01']
		gauss, gauss1, gauss2, mean, mean1, mean2, peaks1, peaks2 = fam_variation_splits(fam)
		print gauss1
		print gauss2
		print mean1
		print mean2
	
	def test_peak_count(self):
		single_peak = [0,0,1,4,5,7,3,2,0]
		multi_peak = [0,0,2,5,3,6,2,1,0]
		# known to fail
		multi_peak_valley = [0,0,0,2,5,3,3,6,2,1,0]
		peak_flat_top = [0,1,4,5,7,7,3,2,0]
		three_peaks = [0,0,0,2,4,5,6,7,5,7,4,3,2,5,2,1]
		assert peak_count(multi_peak) == 2
		assert peak_count(single_peak) == 1
		assert peak_count(multi_peak_valley) == 2
		#assert peak_count(peak_flat_top) == 1
		assert peak_count(three_peaks) == 3
		assert peak_count(three_peaks, min_peak_val=6) == 2
		assert peak_count(three_peaks, min_peak_val=5) == 3
