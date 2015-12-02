from qtools.lib.bio import *

def test_antiparallel():
    def _t(seq):
        return antiparallel(seq)
    
    assert _t('a') == 'T'
    assert _t('A') == 'T'
    assert _t('CG') == 'CG'
    assert _t('TU') == 'AA'
    assert _t('gcccatutaucgaUGTACTTAC') == 'GTAAGTACATCGATAAATGGGC'
    
    # TODO replace with specific exception assertion
    try:
        _t('s')
        assert False
    except Exception, e:
        assert True


def test_complement():
    def _t(seq):
        return complement(seq)
    
    assert _t('a') == 'T'
    assert _t('A') == 'T'
    assert _t('CG') == 'GC'
    assert _t('TU') == 'AA'
    assert _t('gcccatutaucgaUGTACTTAC') == 'CGGGTAAATAGCTACATGAATG'
    
    # TODO replace with specific exception assertion
    try:
        _t('s')
        assert False
    except Exception, e:
        assert True
        

def test_base_regexp_expand():
    def _t(str, matches, nomatches):
        exp = base_regexp_expand(str)
        for match in matches:
            assert exp.search(match)
        for nomatch in nomatches:
            assert not exp.search(nomatch)
    
    _t('A', ('ACG',), ('GCT',))
    _t('C', ('CGT',), ('AGT',))
    _t('G', ('AGC',), ('ACT',))
    _t('T', ('ATT',), ('ACG',))
    _t('RC', ('GCT', 'ACT'), ('TC', 'CC'))
    _t('YA', ('TAC', 'CAG'), ('GA', 'AA'))
    _t('WT', ('ATG', 'TTG'), ('GT', 'CT'))
    _t('SA', ('CAG', 'GAG'), ('AA', 'TA'))
    _t('KG', ('GGT', 'TGT'), ('AG', 'CG'))
    _t('HC', ('ACG', 'TCG', 'CCG'), ('GC',))
    _t('BA', ('CAT', 'GAT', 'TAT'), ('AA',))
    _t('DT', ('ATG', 'GTG', 'TTG'), ('CT',))
    _t('NC', ('AC', 'CC', 'GC', 'TC'), ('C',))

def test_gc_content():
    def _t(str, val):
        assert gc_content(str) == val
    
    _t('CG', 1)
    _t('CGTA', 0.5)
    _t('CGCG', 1)
    _t('AAAA', 0)
    _t('ATG', 1.0/3.0)
    _t('CG ',1)
    _t('gcta', 0.5)

def test_maximal_binding_seq():
    length, offsets = maximal_binding_seq('TACGGAAAG', 'CTTATAAGG')
    assert length == 3
    assert offsets[0] == offsets[1]

    length, offsets = maximal_binding_seq('TACGGAAAG', reverse_complement('TACGGAAAG'))
    assert length == len('TACGGAAAG')
    assert offsets[0] == offsets[1] == 0

    length, offsets = maximal_binding_seq('TACGGAAGA', 'CTTATAAGG')
    assert length == 3
    assert offsets[0] == 5
    assert offsets[1] == 6

    length, offsets = maximal_binding_seq('TACGGAAAG', 'ACTTATAAG')
    assert length == 3
    assert offsets[0] == 6
    assert offsets[1] == 5

    # first seq
    length, offsets = maximal_binding_seq('TACGGAAAG', 'CTTATAGTA')
    assert length == 3
    assert offsets[0] == 0
    assert offsets[1] == 0