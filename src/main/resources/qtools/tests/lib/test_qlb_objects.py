from pyqlb.constants import ROWCOL_ORDER_ROW
from pyqlb.objects import QLWell, QLWellChannel
from qtools.lib.qlb_objects import *
from unittest import TestCase

class TestExperimentMetadataQLPlate(TestCase):
	# no setup necessary
	def test_init(self):
		plate = ExperimentMetadataQLPlate()
		assert plate.file_description is None

		plate = ExperimentMetadataQLPlate(file_description='File Description')
		assert plate.file_description == "File Description"

		plate = ExperimentMetadataQLPlate(file_description='plate_setup_id=13&plate_template_id=7')
		assert plate.file_description == 'plate_setup_id=13&plate_template_id=7'
		assert plate.plate_setup_id == '13'
		assert plate.plate_template_id == '7'
	
	def test_set(self):
		plate1  = ExperimentMetadataQLPlate(file_description='Shit')
		plate1.file_description = None
		assert plate1.file_description is None
		plate1.file_description = 'plate_setup_id=13'
		assert plate1.file_description == 'plate_setup_id=13'
		assert plate1.plate_setup_id == '13'
		plate1.file_description = None
		assert plate1.plate_setup_id is None
		plate1.plate_setup_id = 13
		assert plate1.file_description == 'plate_setup_id=13'
		assert plate1.plate_setup_id == '13'
		plate1.plate_template_id = 7
		assert plate1.file_description == 'plate_setup_id=13&plate_template_id=7'
		assert plate1.plate_template_id == '7'
	
	def test_metadata(self):
		plate = ExperimentMetadataQLPlate(plate_setup_id=13, plate_template_id=7)
		assert plate.file_description == 'plate_setup_id=13&plate_template_id=7'
		assert plate.plate_setup_id == '13'
		assert plate.plate_template_id == '7'


class TestExperimentMetadataQLWell(TestCase):
	# no setup necessary
	def test_init(self):
		well1 = ExperimentMetadataQLWell('A03', num_channels=2)
		assert well1.sample_name is None
		assert well1.name == 'A03'
		assert len(well1.channels) == 2

		well2 = ExperimentMetadataQLWell('A03', num_channels=2, sample_name='MRGPRX1')
		print well2.sample_name, well2.sample
		assert well2.sample_name == 'MRGPRX1'
		assert well2.sample == 'MRGPRX1'

		well3 = ExperimentMetadataQLWell('A03', num_channels=2, sample_name='MRGPRX1;Temp:57')
		assert well3.sample_name == 'MRGPRX1;Temp:57'
		assert well3.temperature == '57'
		assert well3.sample == 'MRGPRX1'

		well4 = ExperimentMetadataQLWell('A03', num_channels=2, temperature=56)
		assert well4.sample_name == 'Temp:56'
		assert well4.temperature == '56'

		well5 = ExperimentMetadataQLWell('A05', num_channels=2, sample='MRGPRX1')
		assert well5.sample_name == 'MRGPRX1'
		assert well5.sample == 'MRGPRX1'

		well6 = ExperimentMetadataQLWell('A06', num_channels=2, sample_name='Temp:57')
		assert well6.sample_name == 'Temp:57'
		assert well6.sample is None
		assert well6.temperature == '57'

		well7 = ExperimentMetadataQLWell('A07', num_channels=2, sample=None, temperature=None)
		assert well7.sample_name is None
		assert well7.sample is None
		assert well7.temperature is None
	
	def test_set(self):
		well1 = ExperimentMetadataQLWell('A03', num_channels=2)
		well1.sample_name = None
		assert well1.sample_name is None
		well1.sample_name = 'MRGPRX1'
		assert well1.sample_name == 'MRGPRX1'
		well1.sample_name = 'MRGPRX1;Temp:45'
		assert well1.sample_name == 'MRGPRX1;Temp:45'
		assert well1.temperature == '45'
		assert well1.sample == 'MRGPRX1'
		well1.sample_name = 'Temp:56'
		assert well1.sample is None
		assert well1.temperature == '56'
	
	def test_metadata(self):
		well1 = ExperimentMetadataQLWell('A04', num_channels=2)
		assert well1.temperature is None
		well1.temperature = 45
		assert well1.temperature == '45'
		assert well1.sample_name == 'Temp:45'
		well1.temperature = None
		assert well1.sample_name is None

		well2 = ExperimentMetadataQLWell('A05', num_channels=2, sample_name='Test')
		assert well2.sample_name == 'Test'
		assert well2.sample == 'Test'
		assert well2.temperature is None
		well2.temperature = 58
		assert well2.sample_name == 'Test;Temp:58'
		well2.temperature = None
		assert well2.sample_name == 'Test'
		well2.sample = None
		assert well2.sample_name is None
		assert well2.sample is None
	
	def test_fields(self):
		well = ExperimentMetadataQLWell('A05', num_channels=2,
		                                sample='MRGPRX1',
		                                temperature=55,
		                                enzyme='AluI',
		                                enzyme_conc='0.5',
		                                additive='DeazaGTP',
		                                additive_conc='2',
		                                expected_cpd='1.5',
		                                expected_cpul='1500')
		assert well.temperature == '55'
		assert well.enzyme == 'AluI'
		assert well.enzyme_conc == '0.5'
		assert well.additive == 'DeazaGTP'
		assert well.additive_conc == '2'
		assert well.expected_cpd == '1.5'
		assert well.expected_cpul == '1500'

		assert well.sample_name == 'MRGPRX1;Cp/d:1.5|Cp/uL:1500|RE:AluI|REConc:0.5|Temp:55|W:DeazaGTP|WConc:2'

		well.expected_cpul = None
		assert well.sample_name == 'MRGPRX1;Cp/d:1.5|RE:AluI|REConc:0.5|Temp:55|W:DeazaGTP|WConc:2'
		assert well.expected_cpul is None

		well.sample_name = 'NA19205;Temp:56|W:Glycerol'
		assert well.expected_cpd is None
		assert well.additive == 'Glycerol'
		assert well.temperature == '56'

class TestWellChannelFunctions(TestCase):
    def test_make_unused_well(self):
        well = make_unused_well('A07')
        assert well.name == 'A07'
        assert well.channels[0].type == QLWellChannel.TARGET_TYPE_NOT_USED
        assert well.channels[1].type == QLWellChannel.TARGET_TYPE_NOT_USED
        assert not well.sample_name
        assert not well.channels[0].target
        assert not well.channels[1].target
        assert not well.experiment_type
        assert not well.experiment_name

    def test_make_fam_abs_singleplex_well(self):
        well = make_fam_abs_singleplex_well('B05','S.a. 1cpd')
        assert well.name == 'B05'
        assert well.sample_name == 'S.a. 1cpd'
        assert well.experiment_type == QLWell.EXP_TYPE_ABSOLUTE_QUANTITATION
        assert well.experiment_name == 'ABS'
        assert well.channels[0].type == QLWellChannel.TARGET_TYPE_UNKNOWN
        assert not well.channels[0].target
        assert well.channels[1].type == QLWellChannel.TARGET_TYPE_NOT_USED
        assert not well.channels[1].target

        well2 = make_fam_abs_singleplex_well('B06', 'S.a. 1cpd', fam_target='Sa822')
        assert well2.channels[0].target == 'Sa822'

    def test_make_vic_abs_singleplex_well(self):
        well = make_vic_abs_singleplex_well('B05','RPP30')
        assert well.name == 'B05'
        assert well.sample_name == 'RPP30'
        assert well.experiment_type == QLWell.EXP_TYPE_ABSOLUTE_QUANTITATION
        assert well.experiment_name == 'ABS'
        assert well.channels[1].type == QLWellChannel.TARGET_TYPE_UNKNOWN
        assert not well.channels[1].target
        assert well.channels[0].type == QLWellChannel.TARGET_TYPE_NOT_USED
        assert not well.channels[0].target

        well2 = make_vic_abs_singleplex_well('B06', 'RPP30', vic_target='QL_RPP30_1')
        assert well2.channels[1].target == 'QL_RPP30_1'

    def test_make_abs_duplex_well(self):
        well = make_abs_duplex_well('C04','NA19442')
        assert well.name == 'C04'
        assert well.sample_name == 'NA19442'
        assert well.experiment_type == QLWell.EXP_TYPE_ABSOLUTE_QUANTITATION
        assert well.experiment_name == 'ABS'
        assert well.channels[0].type == QLWellChannel.TARGET_TYPE_UNKNOWN
        assert not well.channels[0].target
        assert well.channels[1].type == QLWellChannel.TARGET_TYPE_UNKNOWN
        assert not well.channels[1].target

        well2 = make_abs_duplex_well('C04','NA19442',fam_target='MRGPRX1 CNV',vic_target='QL_RPP30_1')
        assert well2.channels[0].target == 'MRGPRX1 CNV'
        assert well2.channels[1].target == 'QL_RPP30_1'

    def test_make_empty_plate(self):
        empty = make_empty_plate()
        assert empty.acquisition_order == ROWCOL_ORDER_ROW
        assert len(empty.wells) == 96
        assert len(empty.analyzed_wells) == 0
