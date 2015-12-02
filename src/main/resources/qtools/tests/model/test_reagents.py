import json
from unittest import TestCase

from pyqlb.objects import QLWell, QLWellChannel

from qtools.model.reagents.templates import *

class TestValidationTestLayout(TestCase):
    def test_from_json(self):
        json_str = json.dumps(VALIDATION_LAYOUT_8N_16P_CTC)
        layout = ValidationTestLayout.from_json(json_str)
        assert isinstance(layout, dict)

    def test_control_positive_names(self):
        layout = ValidationTestLayout(VALIDATION_LAYOUT_8N_16P_CTC)
        assert layout.control_positive_names == ['CAP','CBP']

    def test_control_negative_names(self):
        layout = ValidationTestLayout(VALIDATION_LAYOUT_8N_16P_CTC)
        assert layout.control_negative_names == ['CAN','CBN']

    def test_test_positive_names(self):
        layout = ValidationTestLayout(VALIDATION_LAYOUT_8N_16P_CTC)
        assert layout.test_positive_names == ['TP']

    def test_test_negative_names(self):
        layout = ValidationTestLayout(VALIDATION_LAYOUT_8N_16P_CTC)
        assert layout.test_negative_names == ['TN']

    def test_make_layout_sample_name(self):
        f = ValidationTestLayout.make_layout_sample_name
        assert f('BRAF', test=True, positive=True) == 'Test BRAF'
        assert f('BRAF', test=False, positive=True) == 'Ctrl BRAF'
        assert f('BRAF', test=True, positive=False) == 'Test BRAF NTC'
        assert f('BRAF', test=False, positive=False) == 'Ctrl BRAF NTC'

    def test_get_sample_characteristics(self):
        f = ValidationTestLayout.get_sample_characteristics
        original, test, pos = f('Test BRAF')
        print original
        assert original == 'BRAF'
        assert test
        assert pos

        original, test, pos = f('Test BRAF NTC')
        print original
        assert original == 'BRAF'
        assert test
        assert not pos

        original, test, pos = f('Ctrl BRAF')
        print original
        assert original == 'BRAF'
        assert not test
        assert pos

        original, test, pos = f('Ctrl BRAF NTC')
        print original
        assert original == 'BRAF'
        assert not test
        assert not pos

        original, test, pos = f('BRAF')
        assert original is None
        assert not test
        assert not pos

class TestQLPlateFunctions(TestCase):
    def test_make_qlplate_for_layout(self):
        layout = ValidationTestLayout(VALIDATION_LAYOUT_8N_16P_CTC)
        control_names = ('C1','C2')
        test_names = ('T1',)

        plate = make_qlplate_for_layout(layout, control_names, test_names)
        assert len(plate.analyzed_wells) == 72

        assert plate.analyzed_wells['C02'].sample_name == 'Ctrl C1 NTC'
        assert plate.analyzed_wells['D03'].sample_name == 'Ctrl C1'
        assert plate.analyzed_wells['H04'].sample_name == 'Ctrl C1'
        assert plate.analyzed_wells['A05'].sample_name == 'Test T1 NTC'
        assert plate.analyzed_wells['B06'].sample_name == 'Test T1'
        assert plate.analyzed_wells['E07'].sample_name == 'Test T1'
        assert plate.analyzed_wells['F08'].sample_name == 'Ctrl C2 NTC'
        assert plate.analyzed_wells['G09'].sample_name == 'Ctrl C2'
        assert plate.analyzed_wells['A10'].sample_name == 'Ctrl C2'

        # test sample well is set ok
        b06 = plate.analyzed_wells['B06']
        assert b06.experiment_type == QLWell.EXP_TYPE_ABSOLUTE_QUANTITATION
        assert b06.experiment_name == 'ABS'
        assert b06.channels[0].type == QLWellChannel.TARGET_TYPE_UNKNOWN
        assert b06.channels[1].type == QLWellChannel.TARGET_TYPE_UNKNOWN
