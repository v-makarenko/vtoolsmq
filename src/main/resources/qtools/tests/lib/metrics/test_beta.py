from qtools.lib.metrics.db import get_beta_plate_metrics
from qtools.model import Session, PlateType
from qtools.tests.lib.test_metrics import MetricsTest

class TestBetaMetrics(MetricsTest):
	"""
	Test beta-specific stuff.
	"""
	def setUp(self):
		super(TestBetaMetrics, self).setUp()
		# add plate types
		self.cnv_dbplate.plate_type = self.__get_plate_type_by_code('bcnv')
		self.duplex_dbplate.plate_type = self.__get_plate_type_by_code('bdplex')
		self.fpfn_dbplate.plate_type = self.__get_plate_type_by_code('bfpfn')
		self.red_dbplate.plate_type = self.__get_plate_type_by_code('bred')
	
	def __get_plate_type_by_code(self, code):
		return Session.query(PlateType).filter_by(code=code).first()
	
	def test_get_beta_plate_metrics(self):
		cnv_metrics = get_beta_plate_metrics(self.cnv_dbplate, self.cnv_qlplate)
		# assert some stuff
		assert len([wm for wm in cnv_metrics.well_metrics if wm.expected_cnv is not None]) == 21
		assert len([wm for wm in cnv_metrics.well_metrics if wm.expected_cnv == 6]) == 3
		assert len([wm for wm in cnv_metrics.well_metrics if wm.expected_cnv == 2]) == 6
		assert len([wm for wm in cnv_metrics.well_metrics if wm.well_channel_metrics[0].auto_threshold_expected is False]) == 3
		assert len([wm for wm in cnv_metrics.well_metrics if wm.well_channel_metrics[1].auto_threshold_expected is False]) == 3

		# copied verbatim from TestMetricsMethods
		wd = cnv_metrics.well_metric_name_dict
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

		assert len([wm for wm in cnv_metrics.well_metrics if wm.well_channel_metrics[0].threshold == 0]) == 3
		assert len([wm for wm in cnv_metrics.well_metrics if wm.well_channel_metrics[1].threshold == 0]) == 3

		duplex_metrics = get_beta_plate_metrics(self.duplex_dbplate, self.duplex_qlplate)
		assert len([wm for wm in duplex_metrics.well_metrics if wm.well_channel_metrics[0].expected_concentration == 0]) == 4
		assert len([wm for wm in duplex_metrics.well_metrics if wm.well_channel_metrics[1].expected_concentration == 1000]) == 24
		assert len([wm for wm in duplex_metrics.well_metrics if wm.well_channel_metrics[0].auto_threshold_expected is False]) == 4
		assert len([wm for wm in duplex_metrics.well_metrics if wm.well_channel_metrics[1].auto_threshold_expected is False]) == 0

		# copied verbatim from test_compute_conc_metrics
		wd  = duplex_metrics.well_metric_name_dict
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

		fpfn_metrics = get_beta_plate_metrics(self.fpfn_dbplate, self.fpfn_qlplate)
		assert len([wm for wm in fpfn_metrics.well_metrics if wm.well_channel_metrics[1].false_positive_peaks is not None]) == 2
		assert len([wm for wm in fpfn_metrics.well_metrics if wm.well_channel_metrics[1].false_negative_peaks is not None]) == 1
		assert len([wm for wm in fpfn_metrics.well_metrics if wm.well_channel_metrics[0].auto_threshold_expected is False]) == 24
		assert len([wm for wm in fpfn_metrics.well_metrics if wm.well_channel_metrics[1].auto_threshold_expected is False]) == 19

		# copied verbatim from test_compute_false_positives
		wd = fpfn_metrics.well_metric_name_dict
		assert wd['F03'].well_channel_metrics[1].false_positive_peaks == 0
		assert wd['F06'].well_channel_metrics[1].false_positive_peaks == 6
		assert wd['E03'].well_channel_metrics[1].false_negative_peaks == 61

		red_metrics = get_beta_plate_metrics(self.red_dbplate, self.red_qlplate)
		# copied verbatim from test_compute_lod_false_positives
		wd = red_metrics.well_metric_name_dict
		assert len([well for name, well in wd.items() if well.well_channel_metrics[0].false_positive_peaks is None]) == 21
		assert len([well for name, well in wd.items() if well.well_channel_metrics[0].false_positive_peaks is not None]) == 3
		assert len([wm for wm in red_metrics.well_metrics if wm.well_channel_metrics[0].auto_threshold_expected is False]) == 12
		assert len([wm for wm in red_metrics.well_metrics if wm.well_channel_metrics[1].auto_threshold_expected is False]) == 21


		assert wd['E10'].well_channel_metrics[0].false_positive_peaks == 5
		assert wd['E11'].well_channel_metrics[0].false_positive_peaks == 5
		assert wd['E12'].well_channel_metrics[0].false_positive_peaks == 5

		# since RED has both expected conc and false positives, just test expected conc
		assert wd['E07'].well_channel_metrics[0].expected_concentration == 0
		assert wd['E07'].well_channel_metrics[1].expected_concentration == 0
		assert wd['E10'].well_channel_metrics[0].expected_concentration == 0
		assert wd['E10'].well_channel_metrics[1].expected_concentration is None
		assert wd['F08'].well_channel_metrics[0].expected_concentration == 0.1
		assert wd['F08'].well_channel_metrics[1].expected_concentration is None
		assert wd['F12'].well_channel_metrics[0].expected_concentration == 0.5
		assert wd['F12'].well_channel_metrics[1].expected_concentration is None
		assert wd['G09'].well_channel_metrics[0].expected_concentration == 1
		assert wd['G09'].well_channel_metrics[1].expected_concentration is None
		assert wd['G11'].well_channel_metrics[0].expected_concentration == 5
		assert wd['G11'].well_channel_metrics[1].expected_concentration is None
		assert wd['H07'].well_channel_metrics[0].expected_concentration == 10
		assert wd['H07'].well_channel_metrics[1].expected_concentration is None
		assert wd['H10'].well_channel_metrics[0].expected_concentration == 10
		assert wd['H10'].well_channel_metrics[1].expected_concentration is None
