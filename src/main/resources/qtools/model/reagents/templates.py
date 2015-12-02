import json
from itertools import chain
from pyqlb.objects import QLPlate
from qtools.lib.qlb_objects import *

__all__ = ['ValidationTestLayout',
           'VALIDATION_LAYOUT_8N_16P_CTC',
           'VALIDATION_LAYOUT_8N_8P_EVEN',
           'VALIDATION_LAYOUT_8N_8P_ODD',
           'VALIDATION_LAYOUT_8N_16P_CTCT',
           'VALIDATION_LAYOUT_8N_16P_CT_LEFT',
           'VALIDATION_LAYOUT_8N_16P_CT_RIGHT',
           'make_qlplate_for_layout']

class ValidationTestLayout(dict):
    """
    A way of identifying control and test negative and positive
    cohorts and wells.
    """
    @classmethod
    def from_json(cls, jsonstr):
        return cls(json.loads(jsonstr))

    @property
    def controls(self):
        return self.get('controls', {})

    @property
    def tests(self):
        return self.get('tests', {})

    @classmethod
    def make_layout_sample_name(cls, sample_name, test=False, positive=False):
        """
        Generates the appropriate sample name for the sample, given its positive/negative
        and control/test standing.

        :param sample_name: The original sample name.
        :param test: Whether the sample is a test well.
        :param positive: Whether the sample is a positive well.
        :return: The sample name that the well should take.
        """
        prefix = test and 'Test' or 'Ctrl'
        if positive:
            return '%s %s' % (prefix, sample_name)
        else:
            return '%s %s NTC' % (prefix, sample_name)

    @classmethod
    def get_sample_characteristics(cls, sample_name):
        """
        Given a sample name, return (original sample name, test, negative)--
        the original sample name, whether or not the well was a test (True)
        or control (False), and whether the well was positive (True) or
        negative (False)

        If the sample name does not adhere to the test/control naming
        convention, return None for sample_name (and False for the other
        values)

        :param sample_name: The sample name on the well.
        :return: (sample name, test, positive)
        """
        if not (sample_name.startswith('Ctrl ') or sample_name.startswith('Test ')):
            return (None, False, False)

        if sample_name.endswith('NTC'):
            positive = False
            remainder = sample_name[:-4]
        else:
            positive = True
            remainder = sample_name
        test = sample_name.startswith('Test')
        return (remainder[5:], test, positive)

    @property
    def control_positive_names(self):
        return [repl['positives']['name'] for repl in self.controls if repl.get('positives',False)]

    @property
    def control_negative_names(self):
        return [repl['negatives']['name'] for repl in self.controls if repl.get('positives',False)]

    @property
    def test_positive_names(self):
        return [repl['positives']['name'] for repl in self.tests if repl.get('positives',False)]

    @property
    def test_negative_names(self):
        return [repl['negatives']['name'] for repl in self.tests if repl.get('positives',False)]

def make_qlplate_for_layout(layout, control_names, test_names):
    """
    Generates a QLPlate layout file from the specified layout.
    The negatives are labeled 'sample_name NTC',
    and the positives are labeled 'sample_name'.

    Right now, this assumes ABS/Absolute Quantitation duplex on
    everything, and does not yet include assays.  If the product
    templates mature and include assays, this will be reflected
    here.

    :param layout: The ValidationTestLayout.
    :param control_names: The names of the controls.  The order
                          of the names will be applied to the
                          control order in the layout.
    :param test_names: The names of the test lots.  The order
                       of the names will be applied to the
                       test order in the layout.
    :return: A QLPlate.
    """
    plate = make_empty_plate()
    # the 3rd arg is a hack to make the zip(*var) work
    for spec_name_pair in ((layout.controls, control_names, [False for c in control_names]),
                           (layout.tests, test_names, [True for t in test_names])):
        for spec, name, test in zip(*spec_name_pair):
            negative_name = ValidationTestLayout.make_layout_sample_name(name, test=test, positive=False)
            negative_wells = spec['negatives']['wells']
            for w in negative_wells:
                well_name = w.upper()
                plate.wells[well_name] = make_abs_duplex_well(well_name, negative_name)
            positive_name = ValidationTestLayout.make_layout_sample_name(name, test=test, positive=True)
            positive_wells = spec['positives']['wells']
            for w in positive_wells:
                well_name = w.upper()
                plate.wells[well_name] = make_abs_duplex_well(well_name, positive_name)

    return plate


# 2-4 control A, 5-7 test, 8-10 control B, 1 col NTC, 2 col pos
VALIDATION_LAYOUT_8N_16P_CTC = {
    'controls': [
        {
            'negatives': {
                'name': 'CAN',
                'wells': ['A02','B02','C02','D02','E02','F02','G02','H02']
            },
            'positives': {
                'name': 'CAP',
                'wells': ['A03','B03','C03','D03','E03','F03','G03','H03',
                          'A04','B04','C04','D04','E04','F04','G04','H04']
            }
        },
        {
            'negatives': {
                'name': 'CBN',
                'wells': ['A08','B08','C08','D08','E08','F08','G08','H08']
            },
            'positives': {
                'name': 'CBP',
                'wells': ['A09','B09','C09','D09','E09','F09','G09','H09',
                          'A10','B10','C10','D10','E10','F10','G10','H10']
            }
        }
    ],
    'tests': [
        {
            'negatives': {
                'name': 'TN',
                'wells': ['A05','B05','C05','D05','E05','F05','G05','H05']
            },
            'positives': {
                'name': 'TP',
                'wells': ['A06','B06','C06','D06','E06','F06','G06','H06',
                          'A07','B07','C07','D07','E07','F07','G07','H07']
            }
        }
    ]
}

# 1-3 control A, 4-6 test A, 7-9 control B, 10-12 test B, 1 col NTC, 2 col pos
VALIDATION_LAYOUT_8N_16P_CTCT = {
    'controls': [
        {
            'negatives': {
                'name': 'CAN',
                'wells': ['A01','B01','C01','D01','E01','F01','G01','H01']
            },
            'positives': {
                'name': 'CAP',
                'wells': ['A02','B02','C02','D02','E02','F02','G02','H02',
                          'A03','B03','C03','D03','E03','F03','G03','H03']
            }
        },
        {
            'negatives': {
                'name': 'CBN',
                'wells': ['A07','B07','C07','D07','E07','F07','G07','H07']
            },
            'positives': {
                'name': 'CBP',
                'wells': ['A08','B08','C08','D08','E08','F08','G08','H08',
                          'A09','B09','C09','D09','E09','F09','G09','H09']
            }
        }
    ],
    'tests': [
        {
            'negatives': {
                'name': 'TAN',
                'wells': ['A04','B04','C04','D04','E04','F04','G04','H04']
            },
            'positives': {
                'name': 'TAP',
                'wells': ['A05','B05','C05','D05','E05','F05','G05','H05',
                          'A06','B06','C06','D06','E06','F06','G06','H06']
            }
        },
        {
            'negatives': {
                'name': 'TBN',
                'wells': ['A10','B10','C10','D10','E10','F10','G10','H10']
            },
            'positives': {
                'name': 'TBP',
                'wells': ['A11','B11','C11','D11','E11','F11','G11','H11',
                          'A12','B12','C12','D12','E12','F12','G12','H12']
            }
        }
    ]
}

# 3,5 control; 7,9 test, 1 col NTC, 1 col pos
VALIDATION_LAYOUT_8N_8P_ODD = {
    'controls': [
        {
            'negatives': {
                'name': 'CN',
                'wells': ['A03','B03','C03','D03','E03','F03','G03','H03']
            },
            'positives': {
                'name': 'CP',
                'wells': ['A05','B05','C05','D05','E05','F05','G05','H05']
            }
        }
    ],
    'tests': [
        {
            'negatives': {
                'name': 'TN',
                'wells': ['A07','B07','C07','D07','E07','F07','G07','H07']
            },
            'positives': {
                'name': 'TP',
                'wells': ['A09','B09','C09','D09','E09','F09','G09','H09']
            }
        }
    ]
}

# 4,6 control; 8,10 test, 1 col NTC, 1 col pos
VALIDATION_LAYOUT_8N_8P_EVEN = {
    'controls': [
        {
            'negatives': {
                'name': 'CN',
                'wells': ['A04','B04','C04','D04','E04','F04','G04','H04']
            },
            'positives': {
                'name': 'CP',
                'wells': ['A06','B06','C06','D06','E06','F06','G06','H06']
            }
        }
    ],
    'tests': [
        {
            'negatives': {
                'name': 'TN',
                'wells': ['A08','B08','C08','D08','E08','F08','G08','H08']
            },
            'positives': {
                'name': 'TP',
                'wells': ['A10','B10','C10','D10','E10','F10','G10','H10']
            }
        }
    ]
}

# 1-3 control A, 4-6 test A, 1 col NTC, 2 col pos
VALIDATION_LAYOUT_8N_16P_CT_LEFT = {
    'controls': [
        {
            'negatives': {
                'name': 'CN',
                'wells': ['A01','B01','C01','D01','E01','F01','G01','H01']
            },
            'positives': {
                'name': 'CP',
                'wells': ['A02','B02','C02','D02','E02','F02','G02','H02',
                          'A03','B03','C03','D03','E03','F03','G03','H03']
            }
        }
    ],
    'tests': [
        {
            'negatives': {
                'name': 'TN',
                'wells': ['A04','B04','C04','D04','E04','F04','G04','H04']
            },
            'positives': {
                'name': 'TP',
                'wells': ['A05','B05','C05','D05','E05','F05','G05','H05',
                          'A06','B06','C06','D06','E06','F06','G06','H06']
            }
        }
    ]
}

# 1-3 control A, 4-6 test A, 1 col NTC, 2 col pos
VALIDATION_LAYOUT_8N_16P_CT_RIGHT = {
    'controls': [
        {
            'negatives': {
                'name': 'CN',
                'wells': ['A07','B07','C07','D07','E07','F07','G07','H07']
            },
            'positives': {
                'name': 'CP',
                'wells': ['A08','B08','C08','D08','E08','F08','G08','H08',
                          'A09','B09','C09','D09','E09','F09','G09','H09']
            }
        }
    ],
    'tests': [
        {
            'negatives': {
                'name': 'TN',
                'wells': ['A10','B10','C10','D10','E10','F10','G10','H10']
            },
            'positives': {
                'name': 'TP',
                'wells': ['A11','B11','C11','D11','E11','F11','G11','H11',
                          'A12','B12','C12','D12','E12','F12','G12','H12']
            }
        }
    ]
}