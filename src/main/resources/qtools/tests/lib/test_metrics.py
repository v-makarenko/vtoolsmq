from qtools.lib.qlb_factory import get_plate
from qtools.lib.metrics import *
from qtools.lib.metrics.db import *
from qtools.tests import DatabaseTest
import os, unittest
from datetime import datetime
from qtools.model import Session, Plate, QLBPlate, QLBFile, QLBWell, QLBWellChannel
from qtools.model import PlateMetric, WellMetric, WellChannelMetric

def local(path):
    """
    Maybe this exists?
    """
    return "%s/%s" % (os.path.dirname(__file__), path)

@unittest.skip("Needs QLP files")
class MetricsTest(unittest.TestCase):
	"""
	Base metrics test with initialization, setup and teardown methods.
	"""
	def __init__(self, *args, **kwargs):
		super(MetricsTest, self).__init__(*args, **kwargs)
		# even with unittest.skip, need to wrap potentially failing constructor
		# in try/except
		try:
			self.cnv_qlplate = get_plate(local('cnv.qlp'))
			self.duplex_qlplate = get_plate(local('duplex.qlp'))
			self.fpfn_qlplate = get_plate(local('fpfn.qlp'))
			self.red_qlplate = get_plate(local('red.qlp'))
		except IOError, e:
			self.cnv_qlplate = None
			self.duplex_qlplate = None
			self.fpfn_qlplate = None
			self.red_qlplate = None

	def __setup_plate(self, qlplate, path, name):
		dbfile = QLBFile(dirname=os.path.dirname(local(path)),
		                 basename=path,
		                 run_id=name,
		                 type='processed',
		                 read_status=1,
		                 mtime=datetime.now())
		
		# TODO add plate type
		plate = Plate(name=name,
		              run_time=datetime.strptime(qlplate.host_datetime, '%Y:%m:%d %H:%M:%S'))

		# TODO make this a general purpose function -- seems useful
		# (this will go into cron, I believe)
		qplate = QLBPlate(plate=plate,
		                  file=dbfile,
		                  host_datetime=qlplate.host_datetime)
		
		qlwells = sorted(qlplate.analyzed_wells.items())
		for name, well in qlwells:
			dbwell = QLBWell(file_id=-1,
			                 well_name=name,
			                 experiment_name=well.experiment_name,
			                 experiment_type=well.experiment_type,
			                 num_channels=well.num_channels,
			                 host_datetime=well.host_datetime)
			
			for idx, channel in enumerate(well.channels):
				dbchannel = QLBWellChannel(channel_num=idx,
				                           type=channel.type,
				                           target=channel.target)
				dbwell.channels.append(dbchannel)
			
			qplate.wells.append(dbwell)
		
		Session.add(plate)
		return plate, PlateMetric(plate=plate)

	def setUp(self):
		self.cnv_dbplate, self.cnv_plate_metrics = \
			self.__setup_plate(self.cnv_qlplate, 'cnv.qlp', "TestCNV")
		self.duplex_dbplate, self.duplex_plate_metrics = \
			self.__setup_plate(self.duplex_qlplate, 'duplex.qlp', 'TestDuplex')
		self.fpfn_dbplate, self.fpfn_plate_metrics = \
			self.__setup_plate(self.fpfn_qlplate, 'fpfn.qlp', 'TestFPFN')
		self.red_dbplate, self.red_plate_metrics = \
			self.__setup_plate(self.red_qlplate, 'red.qlp', 'TestRED')

	def tearDown(self):
		Session.rollback()
		

class TestMetricsMethods(MetricsTest):
	"""
	Test the qtools.lib.metrics module.
	"""
	def test_plate_verification(self):
		assert len(self.cnv_qlplate.analyzed_wells) == 24
	
	def test_make_empty_metrics_tree(self):
		pm = make_empty_metrics_tree(self.cnv_dbplate, self.cnv_qlplate)
		assert len(pm.well_metrics) == 24
		for wm in pm.well_metrics:
			if len(wm.well_channel_metrics) != 2:
				assert False
			
		# check bindings
		assert pm.plate == self.cnv_dbplate
		wmap = self.cnv_dbplate.qlbplate.well_name_map
		for wm in pm.well_metrics:
			assert wm.well == wmap[wm.well_name]
			for c in wm.well_channel_metrics:
				assert c.well_channel.well == wmap[wm.well_name]

	def test_compute_well_channel_metrics(self):
		pm = make_empty_metrics_tree(self.cnv_dbplate, self.cnv_qlplate)
		a01 = self.cnv_qlplate.analyzed_wells['A01']
		wm01 = pm.well_metric_name_dict['A01']
		wm01f = wm01.well_channel_metrics[0]
		wm01v = wm01.well_channel_metrics[1]
		_compute_well_channel_metrics(a01, wm01f, 0)
		_compute_well_channel_metrics(a01, wm01v, 1)
		
		assert wm01f.min_quality_gating == 0.5
		assert wm01f.positive_peaks == 3213
		assert wm01f.negative_peaks == 12955
		assert wm01f.quality_gated_peaks == 1000
		assert wm01f.width_gated_peaks == 165

		assert wm01v.min_quality_gating == 0.5
		assert wm01v.quality_gated_peaks == 1000
		assert wm01v.width_gated_peaks == 165
		assert wm01v.positive_peaks == 5744
		assert wm01v.negative_peaks == 10424

		# now just make sure stuff is populated
		assert wm01f.min_width_gate == wm01v.min_width_gate
		assert wm01f.min_width_gate is not None

		assert wm01f.max_width_gate == wm01v.max_width_gate
		assert wm01f.max_width_gate is not None

		assert wm01f.threshold > 0
		assert wm01v.threshold > 0

		assert wm01f.concentration > 0
		assert wm01v.concentration > 0

		assert wm01f.conc_lower_bound < wm01f.concentration
		assert wm01v.conc_lower_bound < wm01v.concentration

		assert wm01f.conc_upper_bound > wm01f.concentration
		assert wm01v.conc_upper_bound > wm01v.concentration

		assert wm01f.positive_mean > wm01f.threshold
		assert wm01v.positive_mean > wm01v.threshold

		assert wm01f.negative_mean < wm01f.threshold
		assert wm01v.negative_mean < wm01v.threshold

		assert wm01f.amplitude_mean > 0
		assert wm01v.amplitude_mean > 0
		assert wm01f.amplitude_stdev > 0
		assert wm01v.amplitude_stdev > 0
		assert wm01f.positive_stdev > 0
		assert wm01v.negative_stdev > 0
	
	def test_compute_well_metrics(self):
		pm = make_empty_metrics_tree(self.cnv_dbplate, self.cnv_qlplate)
		a01 = self.cnv_qlplate.analyzed_wells['A01']
		wm01 = pm.well_metric_name_dict['A01']

		_compute_well_metrics(a01, wm01)
		assert wm01.rejected_peaks > 0
		assert wm01.vertical_streak_events == 1000
		assert wm01.width_mean > 11
		assert wm01.width_variance > 0
		assert wm01.accepted_event_count == 16168
		assert wm01.total_event_count == 17333
		assert wm01.well_name == 'A01'
	
	def test_process_plate(self):
		pm = process_plate(self.cnv_dbplate, self.cnv_qlplate)
		assert min([wm.total_event_count for wm in pm.well_metrics]) == 6871
		assert max([wm.total_event_count for wm in pm.well_metrics]) == 17333

		assert max([wm.well_channel_metrics[0].concentration for wm in pm.well_metrics]) > 1092
		assert max([wm.well_channel_metrics[0].concentration for wm in pm.well_metrics]) < 1093

		assert len([wm for wm in pm.well_metrics if wm.well_channel_metrics[0].threshold != 0]) == 21
		assert len([wm for wm in pm.well_metrics if wm.well_channel_metrics[1].threshold != 0]) == 21
	
	def test_compute_well_cnv_metrics(self):
		cnv_lookup_func = well_sample_name_lookup({'NA11994 CN1': 1,
		                                     'NA18507 CN2': 2,
		                                     'NA19108 CN2': 2,
		                                     'NA18502 CN3': 3,
		                                     'NA18916 CN6': 6,
		                                     'NA19221 CN4': 4,
		                                     'NA19205 CN5': 5})
		
		pm = process_plate(self.cnv_dbplate, self.cnv_qlplate)
		cnv_calc = ExpectedCNVCalculator(0, 1, cnv_lookup_func)
		compute_metric_foreach_qlwell(self.cnv_qlplate, pm, cnv_calc)

		wd = pm.well_metric_name_dict
		assert wd['A01'].expected_cnv == 1
		assert wd['A02'].expected_cnv is None
		assert wd['B01'].expected_cnv == 2
		assert wd['B02'].expected_cnv == 2
		assert wd['F02'].expected_cnv == 3
		assert wd['F01'].expected_cnv == 6
		assert wd['E02'].expected_cnv == 4
		assert wd['E03'].expected_cnv == 5

		assert wd['A01'].cnv > 0.9
		assert wd['A01'].cnv < 1.1
		assert wd['A02'].cnv is None
		assert wd['B01'].cnv > 1.8
		assert wd['B01'].cnv < 2.2
		assert wd['B02'].cnv > 1.8
		assert wd['B02'].cnv < 2.2
		assert wd['F02'].cnv > 2.8
		assert wd['F02'].cnv < 3.2
		assert wd['F01'].cnv > 5.7
		assert wd['F01'].cnv < 6.3
		assert wd['E02'].cnv > 3.8
		assert wd['E02'].cnv < 4.2
		assert wd['E03'].cnv > 4.8
		assert wd['E03'].cnv < 5.2
	
	def test_compute_conc_metrics(self):
		conc_lookup_func = well_channel_sample_name_lookup({'NTC': (0,1000),
		                                       'S.a. 0.125': (125, 1000),
		                                       'S.a. 0.25': (250, 1000),
		                                       'S.a. 0.5': (500, 1000),
		                                       'S.a. 1.02': (1020, 1000),
		                                       'S.a. 2.0': (2000, 1000)})
		
		pm = process_plate(self.duplex_dbplate, self.duplex_qlplate)
		conc_calc = ExpectedConcentrationCalculator(conc_lookup_func)
		compute_metric_foreach_qlwell_channel(self.duplex_qlplate, pm, conc_calc)

		wd  = pm.well_metric_name_dict
		assert wd['A01'].well_channel_metrics[0].expected_concentration == 0
		assert wd['A01'].well_channel_metrics[1].expected_concentration == 1000
		assert wd['B02'].well_channel_metrics[0].expected_concentration == 125
		assert wd['B02'].well_channel_metrics[1].expected_concentration == 1000
		assert wd['C03'].well_channel_metrics[0].expected_concentration == 250
		assert wd['C03'].well_channel_metrics[1].expected_concentration == 1000
		assert wd['D04'].well_channel_metrics[0].expected_concentration == 500
		assert wd['D04'].well_channel_metrics[1].expected_concentration == 1000
		assert wd['A05'].well_channel_metrics[0].expected_concentration == 1020
		assert wd['A05'].well_channel_metrics[1].expected_concentration == 1000
		assert wd['B06'].well_channel_metrics[0].expected_concentration == 2000
		assert wd['B06'].well_channel_metrics[1].expected_concentration == 1000

		assert wd['B02'].well_channel_metrics[0].concentration > 118
		assert wd['B02'].well_channel_metrics[0].concentration < 119
		assert wd['B02'].well_channel_metrics[1].concentration > 978
		assert wd['B02'].well_channel_metrics[1].concentration < 979
	
	def test_compute_false_positives(self):
		pm = process_plate(self.fpfn_dbplate, self.fpfn_qlplate)
		fp_calc = NTCSaturatedFalsePositiveCalculator(('A02','A03','B01',
		                                               'A08','A09','B07',
		                                               'E02','E03','F01',
		                                               'E08','E09','F07'),
		                                              ('A01','B03','B06',
		                                               'A07','B09','B12',
		                                               'E01','F03','F06',
		                                               'E07','F09','F12'),
		                                              ('B03','B06',
		                                               'B09','B12',
		                                               'F03','F06',
		                                               'F09','F12'),
		                                               (1,))
		
		fp_calc.compute(self.fpfn_qlplate, pm)

		wd = pm.well_metric_name_dict
		assert len([well for name, well in wd.items() if well.well_channel_metrics[1].false_positive_peaks is None]) == 22
		assert len([well for name, well in wd.items() if well.well_channel_metrics[1].false_positive_peaks is not None]) == 2
		assert len([well for name, well in wd.items() if well.well_channel_metrics[1].manual_threshold is not None]) == 2
		assert wd['F03'].well_channel_metrics[1].false_positive_peaks == 0
		assert wd['F06'].well_channel_metrics[1].false_positive_peaks == 6
		assert wd['F03'].well_channel_metrics[1].manual_threshold == wd['F06'].well_channel_metrics[1].manual_threshold
		assert wd['F03'].well_channel_metrics[1].manual_threshold > 1408
		assert wd['F03'].well_channel_metrics[1].manual_threshold < 1409
	
	def test_compute_false_negatives(self):
		pm = process_plate(self.fpfn_dbplate, self.fpfn_qlplate)
		fn_calc = NTCSaturatedFalseNegativeCalculator(('A02','A03','B01',
		                                               'A08','A09','B07',
		                                               'E02','E03','F01',
		                                               'E08','E09','F07'),
		                                              ('A01','B03','B06',
		                                               'A07','B09','B12',
		                                               'E01','F03','F06',
		                                               'E07','F09','F12'),
		                                              ('A03','A09','E03','E09'),
		                                               (1,))
		
		fn_calc.compute(self.fpfn_qlplate, pm)

		wd = pm.well_metric_name_dict
		assert len([well for name, well in wd.items() if well.well_channel_metrics[1].false_negative_peaks is None]) == 23
		assert len([well for name, well in wd.items() if well.well_channel_metrics[1].false_negative_peaks is not None]) == 1
		assert len([well for name, well in wd.items() if well.well_channel_metrics[1].manual_threshold is not None]) == 1
		assert wd['E03'].well_channel_metrics[1].false_negative_peaks == 61
		print wd['E03'].well_channel_metrics[1].manual_threshold
		assert wd['E03'].well_channel_metrics[1].manual_threshold > 1408
		assert wd['E03'].well_channel_metrics[1].manual_threshold < 1409
	
	def test_compute_lod_false_positives(self):
		pm = process_plate(self.red_dbplate, self.red_qlplate)
		lod_calc = AverageComputedThresholdFalsePositiveCalculator(('H07','H08','H09'),
		                                                           ('E10','E11','E12'),
		                                                           (0,))
		lod_calc.compute(self.red_qlplate, pm)
		wd = pm.well_metric_name_dict
		assert len([well for name, well in wd.items() if well.well_channel_metrics[0].false_positive_peaks is None]) == 21
		assert len([well for name, well in wd.items() if well.well_channel_metrics[0].false_positive_peaks is not None]) == 3
		assert len([well for name, well in wd.items() if well.well_channel_metrics[0].manual_threshold is not None]) == 3
		assert wd['E10'].well_channel_metrics[0].false_positive_peaks == 5
		assert wd['E11'].well_channel_metrics[0].false_positive_peaks == 5
		assert wd['E12'].well_channel_metrics[0].false_positive_peaks == 5
		assert wd['E11'].well_channel_metrics[0].manual_threshold > 1912
		assert wd['E12'].well_channel_metrics[0].manual_threshold < 1913
	
	def test_compute_expected_threshold(self):
		pm = process_plate(self.red_dbplate, self.red_qlplate)
		auto_threshold_lookup_func = ExpectedThresholdCalculator(well_channel_sample_name_lookup({'NTC': (False,False),
		                                                              '0% Mutant, 1cpd WT': (False,False),
		                                                              '0.01cpd Mutant, 0 WT': (True,False)},
		                                                             default=True))
		compute_metric_foreach_qlwell_channel(self.red_qlplate, pm, auto_threshold_lookup_func)

		assert len([well for well in pm.well_metrics if well.well_channel_metrics[0].auto_threshold_expected is True]) == 18
		assert len([well for well in pm.well_metrics if well.well_channel_metrics[1].auto_threshold_expected is True]) == 15
		
	