from qtools.lib.tm import *
from qtools.model import Assay
from paste.deploy import loadapp
from paste.script.appinstall import SetupCommand
import pylons.test
import unittest

SetupCommand('setup-app').run([pylons.test.pylonsapp.config['__file__']])

@unittest.skip("tests old logic")
def test_tm_probe():
    wsgiapp = pylons.test.pylonsapp
    seq = 'TTCTGACCTGAAGGCTCTGCGCG' # CDC RnaseP
    tm = tm_probe(wsgiapp.config, seq)
    assert tm > 67.6 and tm < 67.7 # 67.62

@unittest.skip("tests old logic")
def test_tm_mgb_probe():
    wsgiapp = pylons.test.pylonsapp
    seq = 'ACCATCTCTAAAATCCT'
    tm = tm_mgb_probe(wsgiapp.config, seq)
    assert tm > 68.4 and tm < 68.5 # 68.48

@unittest.skip("tests old logic")
def test_tm_primer():
    wsgiapp = pylons.test.pylonsapp
    seq = 'CAAAGTAGGAAAACATCATCACAGGA'
    tm= tm_primer(wsgiapp.config, seq)
    assert tm > 61.3 and tm < 61.4 # 61.31

@unittest.skip("tests old logic")
def test_tm_assay():
    cdc = Assay(name='CDC',
                primer_fwd='AGATTTGGACCTGCGAGC',
                primer_rev='GAGCGGCTGTCTCCACAAGT',
                probe_seq='TTCTGACCTGAAGGCTCTGCGCG',
                quencher='BHQ')
    
    mrg = Assay(name='MRGPRX1',
                primer_fwd='TTAAGCTTCATCAGTATCCCCCA',
                primer_rev='CAAAGTAGGAAAACATCATCACAGGA',
                probe_seq='ACCATCTCTAAAATCCT',
                quencher='MGB')
    wsgiapp = pylons.test.pylonsapp
    tm_fwd, tm_rev, tm_probe = tm_assay(wsgiapp.config, cdc)
    assert tm_fwd > 60.9 and tm_fwd < 61
    assert tm_rev > 65.4 and tm_rev < 65.5
    assert tm_probe > 67.6 and tm_probe < 67.7

    tm_fwd, tm_rev, tm_probe = tm_assay(wsgiapp.config, mrg)
    assert tm_fwd > 61.3 and tm_fwd < 61.4
    assert tm_rev > 61.3 and tm_rev < 61.4
    assert tm_probe > 68.4 and tm_probe < 68.5