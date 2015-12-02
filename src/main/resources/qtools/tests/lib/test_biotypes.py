from qtools.lib.bio import *
import unittest

def test_simple_genome_sequence():
    seq = SimpleGenomeSequence('X', 49502, 49502, '+', 'C')
    assert seq.chromosome == 'X'
    assert seq.start == 49502
    assert seq.end == 49502
    assert seq.strand == '+'
    assert seq.sequence == 'C'
    
    seq2 = SimpleGenomeSequence(9, 2364850, 2364868, '+', 'AAGCAAATAACTTTATATA')
    seq2n = SimpleGenomeSequence(0, 2364850, 2364868, '-', 'TATATAAAGTTATTTGCTT')
    assert seq2[2364850] == 'A'
    assert seq2n[2364851] == 'T'
    assert seq2[2364850:2364858] == 'AAGCAAATA' # slicing inclusive, for now
    print seq2n[2364850:2364852]
    assert seq2n[2364850:2364852] == 'CTT'
    assert seq2.reverse_complement()[2364850:2364852] == 'CTT'
    assert seq2n.reverse_complement()[2364850:2364852] == 'AAG'
    assert seq2.base(0) == 2364850
    assert seq2n.base(0) == 2364868
    assert seq2.base(16) == 2364866
    assert seq2n.base(16) == 2364852
    try:
        assert seq2[2364849] and False
    except IndexError, e:
        pass
    
    try:
        assert seq2[2364869] and False
    except IndexError, e:
        pass
    
    assert seq2[2364850:2364868:2] == 'AGAAACTAAA'

@unittest.expectedFailure
def test_transformed_genome_sequence():
    """
    A lot of code that tests this module is tests/lib/dbservice/test_ucsc.py.
    TODO: move that code (and make some of the SGS, mutations fixtures)
    """
    seq = SimpleGenomeSequence('22', 2364850, 2364868, '+', 'AAGCAAATAACTTTATATA')
    dxf = TransformedGenomeSequence.from_sequence(seq).delete(2364851, 2364851)
    assert len(dxf) == 17
    # TODO: fix getitem by idx-- kinda wonky.
    # TODO: also fix slicing (at least on delete)
    assert dxf[2364850:2364851] == 'A'
    assert dxf[2364850:2364852] == 'AG'
    assert dxf[2364852:2364853] == 'GC'
    assert dxf[2364851:2364852] == 'G' # FAIL: this should work

def test_sequence_group():
    seq1 = SimpleGenomeSequence('22', 34304505, 34304508, '+', 'TTAC')
    seq2 = SimpleGenomeSequence('22', 34304509, 34304512, '+', 'AGAT')
    seq2n = SimpleGenomeSequence('22', 34304509, 34304512, '+')
    seqN = SimpleGenomeSequence('22', 34304513, 34304516, '-', 'ATCA')
    
    # for now; TODO: overlap detection & merge
    seqO = SimpleGenomeSequence('22', 34304512, 34304515, '+', 'TTGA')
    seqF = SimpleGenomeSequence('22', 34304514, 34304517, '+', 'GATG')
    seqX = SimpleGenomeSequence('X', 34304513, 34304516, '+', 'CCCC')
    
    def _c(*args):
        sg = SequenceGroup(args)
        return sg.contiguous
    
    assert _c(seq1, seq2)
    assert _c(seq2, seqN)
    assert not _c(seq2, seqO)
    assert not _c(seq2, seqF)
    assert not _c(seq2, seqX)
    
    def _m(*args):
        sg = SequenceGroup(args)
        return sg.merged_positive_sequence
    
    def _n(*args):
        sg = SequenceGroup(args)
        return sg.merged_negative_sequence
    
    assert _m(seq1, seq2) == SimpleGenomeSequence('22', 34304505, 34304512, '+', 'TTACAGAT')
    assert _n(seq1, seq2) == SimpleGenomeSequence('22', 34304505, 34304512, '-', 'ATCTGTAA')
    assert _m(seq2, seqN) == SimpleGenomeSequence('22', 34304509, 34304516, '+', 'AGATTGAT')
    assert _n(seq2, seqN) == SimpleGenomeSequence('22', 34304509, 34304516, '-', 'ATCAATCT')
    assert _m(seq2, seqO) is None
    assert _m(seq2, seqF) is None
    assert _m(seq2, seqX) is None
    
    try:
        _m(seq1, seq2n) # returns value error since sequence is partially defined
        assert False
    except ValueError, e:
        assert True

def test_pcr_sequence():
    amplicon = SimpleGenomeSequence('22', 34304509, 34304512, '+', 'AGAT')
    prefix = SimpleGenomeSequence('22', 34304505, 34304508, '+', 'TTAC')
    suffix = SimpleGenomeSequence('22', 34304513, 34304516, '+', 'TGAT')
    
    # try various configurations
    seq = PCRSequence(amplicon, prefix, suffix)
    
    assert seq.contiguous
    assert seq.merged_sequence == SimpleGenomeSequence('22', 34304505, 34304516, '+', 'TTACAGATTGAT')
    
    seqa = PCRSequence(amplicon)
    assert seqa.contiguous
    assert seqa.merged_sequence == amplicon
    
    seqp = PCRSequence(amplicon, prefix)
    assert seqp.contiguous
    assert seqp.merged_sequence == SimpleGenomeSequence('22', 34304505, 34304512, '+', 'TTACAGAT')
    
    seqs = PCRSequence(amplicon, None, suffix)
    assert seqs.contiguous
    assert seqs.merged_sequence == SimpleGenomeSequence('22', 34304509, 34304516, '+', 'AGATTGAT')

def test_exon_spanning_sequence():
    # http://www.ncbi.nlm.nih.gov/nuccore/NM_018189
    # negative strand exon-spanning primers: ACAATATGTTGTGCCCCAAATGTG, AAACAGGTGCAGAGGACCAGAG
    # negative strand intra-exon primers: TCTCAGTTCAGTGCAATCTCCG, AACCTGGCCAACATGGTGA
    # positive strand exon-spanning primers (ge_LAG_2_3): ATCTCAGCCTTCTGCGAAGAG, ACGCTCAGCACCGTGTAG
    # positive strand intra-exon primers: GAGGGACTCAGTGTCCCTCCT, TTGCTCTAAGGCAGAAAATCGTCTT
    # positive strand variable exon primers (ge_LAG_7_8): TGGTGACTGGAGCCTTTGG, TTGCTCTAAGGCAGAAAATCGTCTT
    pass
