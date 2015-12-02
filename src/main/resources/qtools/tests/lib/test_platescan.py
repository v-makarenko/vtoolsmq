from qtools.lib.platescan import run_id, duplicate_run_id

def test_run_id():
    path = 'Box 2 Alpha 06/Mikes Test 2_2010-12-20-14-23/Mikes Test 2.qlp'
    assert run_id(path) == 'a06:2010-12-20-14-23/QLP_Mikes Test 2.qlp'
    
    raw_path = 'Box 2 Alpha 06/Mikes Test 2_2010-12-20-24-23/Mikes Test 2_A05_RAW.qlb'
    assert run_id(raw_path) == 'a06:2010-12-20-24-23/A05_Mikes Test 2_A05_RAW.qlb'
    
    path = 'jmr2010_04_24/jmr2010_04_24.qlp'
    assert run_id(path) == '??:QLP_jmr2010_04_24/jmr2010_04_24.qlp'

def test_duplicate_run_id():
    path = 'Box 2 Alpha 06/Mikes Test 2_2010-12-20-14-23/Mikes Test 2.qlp'
    
    assert duplicate_run_id(path).endswith('2010-12-20-14-23/QLP_Mikes Test 2.qlp')
    assert duplicate_run_id(path) != '2010-12-20-14-23/QLP_Mikes Test 2.qlp'
    
    path = 'jmr2010_04_24/jmr2010_04_24.qlp'
    print duplicate_run_id(path)
    assert duplicate_run_id(path).endswith('QLP_jmr2010_04_24/jmr2010_04_24.qlp')
    assert duplicate_run_id(path) != 'jmr2010_04_24/jmr2010_04_24.qlp'