from qtools.model import *

import re

def test_excise_well_name():
    f = excise_well_name
    
    assert f('A01') == ''
    assert f('a01') == ''
    assert f('a13') == 'a13'
    assert f('i01') == 'i01'
    
    assert f('Gaming PlateA01') == 'Gaming Plate'
    assert f('Super A01Gaming Plate') == 'Super Gaming Plate'