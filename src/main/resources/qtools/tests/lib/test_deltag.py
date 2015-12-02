from qtools.components.manager import create_manager
from qtools.lib.bio import reverse_complement
from qtools.lib.deltag import *
from qtools.model import Assay
from paste.deploy import loadapp
from paste.script.appinstall import SetupCommand
import pylons.test
import unittest

SetupCommand('setup-app').run([pylons.test.pylonsapp.config['__file__']])

@unittest.skip("tests old logic")
def test_dg_seq():
    wsgiapp = pylons.test.pylonsapp
    seq = 'cggcggatcggcaaaggcgaggctctgtgctcgcggggcggacgcggtctcggcggtggtggcgcgtcgcgccgctgggttttatagggcgccgccgcggccgctcgagccataaaaggcaactttcggaacggcgc' # Beta-Actin 137
    dg = dg_seq(wsgiapp.config, seq)
    assert dg > -5.5 and dg < -5.4 # -5.49

@unittest.skip("tests old logic")
def test_dg_assay():
    wsgiapp = pylons.test.pylonsapp
    fakebeta = Assay(name='Fake Beta',
                     primer_fwd='cggcggatcggcaaaggcgaggctctgtgctcgcggggcggacgcggtctcggcggtggtggcgcgtcgcgccgctgggttttatagggcgccgccgcggccgctcgagccataaaaggcaactttcggaacggcgc',
                     primer_rev='cggcggatcggcaaaggcgaggctctgtgctcgcggggcggacgcggtctcggcggtggtggcgcgtcgcgccgctgggttttatagggcgccgccgcggccgctcgagccataaaaggcaactttcggaacggcgc',
                     probe_seq='atcgcccgatataccgagatt')
    dg_fwd, dg_rev, dg_probe = dg_assay(wsgiapp.config, fakebeta)
    assert dg_fwd > -5.5 and dg_fwd < -5.4
    assert dg_rev > -5.5 and dg_rev < -5.4
    assert dg_probe == 0