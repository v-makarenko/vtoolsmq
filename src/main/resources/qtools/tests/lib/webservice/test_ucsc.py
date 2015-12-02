from qtools.lib.bio import *
from qtools.lib.webservice.ucsc import *

TEST_FWD_PRIMER = 'TAACAGATTGATGATGCATGAAATGGG'
TEST_REV_PRIMER = 'CCCATGAGTGGCTCCTAAAGCAGCTGC'
TEST_FWD_PRIMER_EXACT = 'TTACAGATTGATGATGCATGAAATGGG'
TEST_REV_PRIMER_EXACT = 'CTCATGAGTGGCTCCTAAAGCAGCTGC'
TEST_FWD_PRIMER_ERROR = 'TAACAGATTGATGAaGCATGAAATGAG'
AMBIG_FWD_PRIMER = 'GGGTCCAGAAATACGTCAGT'
AMBIG_REV_PRIMER = 'CATGTTCCCAAGGCTCAG'
TEST_GENE_FWD_PRIMER = 'ACAATATGTTGTGCCCCAAATGTG'
TEST_GENE_REV_PRIMER = 'AAACAGGTGCAGAGGACCAGAG'

TEST_LAG_2_3_FWD_PRIMER = 'ATCTCAGCCTTCTGCGAAGAG'
TEST_LAG_2_3_REV_PRIMER = 'ACGCTCAGCACCGTGTAG'

TEST_INTRA_EXON_FWD_PRIMER = 'GAGGGACTCAGTGTCCCTCCT'
TEST_INTRA_EXON_REV_PRIMER = 'TTGCTCTAAGGCAGAAAATCGTCTT'

TEST_GEX_MULTIAMP_FWD_PRIMER = 'TGGTGACTGGAGCCTTTGG'
TEST_GEX_MULTIAMP_REV_PRIMER = 'TTGCTCTAAGGCAGAAAATCGTCTT'

CHRM_OVERSHOOT_FWD_PRIMER = 'GGTTTCTACTCCAAAGACCACATCA'
CHRM_OVERSHOOT_REV_PRIMER = 'TGTCAGGGAGGTAGCGATGA'

def test_parse_sequence_identifier():
    assert parse_sequence_identifier("crappy_string") is None
    
    # base case
    primer_example = parse_sequence_identifier("chr22:34304505+34304954")
    assert primer_example is not None
    assert primer_example == ('22', 34304505, 34304954, '+')
    
    # X/Y/M case
    assert parse_sequence_identifier("chrY:20502+30504") == ('Y', 20502, 30504, '+')
    
    # - case
    assert parse_sequence_identifier("chr4:25052-18940") == ('4', 25052, 18940, '-')

def test_parse_gene_identifier():
    assert parse_gene_identifier("crappy_string") is None

    # base case
    gene_example = parse_gene_identifier("uc003dxq.4__DPPA4:903+1076")
    assert gene_example is not None
    assert gene_example == ('uc003dxq','DPPA4',903,1076,'+')

def test_genome_browser_session():
    session = get_ucsc_session()
    sequences = pcr_match(TEST_FWD_PRIMER, TEST_REV_PRIMER, session=session)
    assert session.hguid is not None
    assert session.hgsid is not None


def test_pcr_match():
    sequences = pcr_match(TEST_FWD_PRIMER, TEST_REV_PRIMER)
    assert len(sequences) == 1
    
    seq = sequences[0]
    assert seq.chromosome == '22'
    assert seq.start == 34304505
    assert seq.end == 34304954
    assert seq.strand == '+'
    assert seq.sequence == 'TTACAGATTGATGATGCATGAAATGGGGGGTGGCCAGGGGTGGGGGGTGAGACTGCAGAGAAAGGCAGGGCTGGTTCATAACAAGCTTTGTGCGTCCCAATATGACAGCTGAAGTTTTCCAGGGGCTGATGGTGAGCCAGTGAGGGTAAGTACACAGAACATCCTAGAGAAACCCTCATTCCTTAAAGATTAAAAATAAAGACTTGCTGTCTGTAAGGGATTGGATTATCCTATTTGAGAAATTCTGTTATCCAGAATGGCTTACCCCACAATGCTGAAAAGTGTGTACCGTAATCTCAAAGCAAGCTCCTCCTCAGACAGAGAAACACCAGCCGTCACAGGAAGCAAAGAAATTGGCTTCACTTTTAAGGTGAATCCAGAACCCAGATGTCAGAGCTCCAAGCACTTTGCTCTCAGCTCCACGCAGCTGCTTTAGGAGCCACTCATGAG'
    assert not seq.perfect_primer_match
    assert seq.longest_forward_match == 'ACAGATTGATGATGCATGAAATGGG'
    assert seq.longest_forward_match_offset == 2
    assert seq.longest_reverse_match == 'GCAGCTGCTTTAGGAGCCACTCATG'
    assert seq.longest_reverse_match_offset == 2
    assert seq.forward_primer == TEST_FWD_PRIMER
    assert seq.reverse_primer == TEST_REV_PRIMER

def test_pcr_match_exact():
    sequences = pcr_match(TEST_FWD_PRIMER_EXACT, TEST_REV_PRIMER_EXACT)
    assert len(sequences) == 1
    
    seq = sequences[0]
    assert seq.perfect_primer_match
    assert seq.longest_forward_match == TEST_FWD_PRIMER_EXACT
    assert seq.longest_reverse_match == antiparallel(TEST_REV_PRIMER_EXACT)
    assert seq.longest_forward_match_offset == 0
    assert seq.longest_reverse_match_offset == 0

def test_pcr_match_nomatch():
    sequences = pcr_match(TEST_FWD_PRIMER_ERROR, TEST_REV_PRIMER_EXACT)
    assert len(sequences) == 0
    

def test_pcr_primer_request():
    response_html = pcr_primer_request(TEST_FWD_PRIMER, TEST_REV_PRIMER)
    assert len(response_html) > 0
    assert "UCSC In-Silico PCR" in response_html

def test_pcr_gene_match():
    sequences = pcr_gene_match(TEST_GENE_FWD_PRIMER, TEST_GENE_REV_PRIMER)
    assert len(sequences) == 2
    assert sequences[0].start == 903
    assert sequences[1].start == 607
    assert sequences[0].end == 1076
    assert sequences[1].ucsc_id == 'uc011bho'
    assert sequences[0].gene == 'DPPA4'
    assert sequences[0].perfect_primer_match
    assert sequences[1].perfect_primer_match
    assert sequences[0].strand == '+'
    assert sequences[1].sequence == 'ACAATATGTTGTGCCCCAAATGTGTTCACAGGAACAAGGTCTTAATAAAAAGCCTCCAATGGGAATAGAATATCAGGAAAAAGGCCACATCTATGGTAATTAATGGCAGAAAAGCTGGAGAGTTGGATTCTGCGGTGCTGCTGACAGGTGAACTCTGGTCCTCTGCACCTGTTT'

def test_pcr_gene_primer_request():
    response_html = pcr_gene_primer_request(TEST_GENE_FWD_PRIMER, TEST_GENE_REV_PRIMER)
    assert len(response_html) > 0
    assert 'uc003dxq' in response_html

def test_pcr_primer_request_process():
    # TODO: try to get a result that matches multiple primers
    response_html = pcr_primer_request(TEST_FWD_PRIMER, TEST_REV_PRIMER)
    ch, start, end, strand, seq = pcr_primer_response_process(response_html)[0]
    assert ch == '22'
    assert start == 34304505
    assert end == 34304954
    assert strand == '+'
    assert seq == 'TtACAGATTGATGATGCATGAAATGGGgggtggccaggggtggggggtgagactgcagagaaaggcagggctggttcataacaagctttgtgcgtcccaatatgacagctgaagttttccaggggctgatggtgagccagtgagggtaagtacacagaacatcctagagaaaccctcattccttaaagattaaaaataaagacttgctgtctgtaagggattggattatcctatttgagaaattctgttatccagaatggcttaccccacaatgctgaaaagtgtgtaccgtaatctcaaagcaagctcctcctcagacagagaaacaccagccgtcacaggaagcaaagaaattggcttcacttttaaggtgaatccagaacccagatgtcagagctccaagcactttgctctcagctccacGCAGCTGCTTTAGGAGCCACTCATGaG'
    
    response_nomatch = pcr_primer_request(TEST_FWD_PRIMER_ERROR, TEST_REV_PRIMER)
    assert not pcr_primer_response_process(response_nomatch)

def test_pcr_gene_primer_response_process():
    response_html = pcr_gene_primer_request(TEST_GENE_FWD_PRIMER, TEST_GENE_REV_PRIMER)
    seq_list = pcr_gene_primer_response_process(response_html)
    assert len(seq_list) == 2
    ucsc_id, gene, start, end, strand, seq = seq_list[0]
    assert ucsc_id == 'uc003dxq'
    assert gene == 'DPPA4'
    assert start == 903
    assert end == 1076
    assert strand == '+'
    assert seq == 'ACAATATGTTGTGCCCCAAATGTGttcacaggaacaaggtcttaataaaaagcctccaatgggaatagaatatcaggaaaaaggccacatctatggtaattaatggcagaaaagctggagagttggattctgcggtgctgctgacaggtgaaCTCTGGTCCTCTGCACCTGTTT'

    ucsc_id, gene2, start, end, strand, seq2 = seq_list[1]
    assert seq == seq2
    assert gene == gene2
    assert ucsc_id == 'uc011bho'
    assert start == 607
    assert end == 780
    assert strand == '+'

    # modify base
    bunk_primer = TEST_GENE_FWD_PRIMER[0:14] + TEST_GENE_FWD_PRIMER[15:]
    response_html = pcr_gene_primer_request(bunk_primer, TEST_GENE_REV_PRIMER)
    seq_list = pcr_gene_primer_response_process(response_html)
    assert seq_list is None

    # test reverse complement
    response_html = pcr_gene_primer_request(TEST_GENE_REV_PRIMER, TEST_GENE_FWD_PRIMER)
    seq_list = pcr_gene_primer_response_process(response_html)
    assert len(seq_list) == 2
    ucsc_id, gene, start, end, strand, seq = seq_list[0]
    assert ucsc_id == 'uc003dxq'
    assert gene == 'DPPA4'
    assert start == 903
    assert end == 1076
    assert strand == '-'

def test_pcr_primer_request_multiple():
    response_html = pcr_primer_request(AMBIG_FWD_PRIMER, AMBIG_REV_PRIMER)
    tuples = pcr_primer_response_process(response_html)
    assert len(tuples) == 3
    assert tuples[0][4] == 'GGGTCCAGAAATACGTCAGTgacctggagctgagtgcctgaggggtccagaagcttcgaggcccagcgacctcagtgggcccagtggggaggagcaggagcCTGAGCCTTGGGAACATG'

def test_custom_track_request():
    session = get_ucsc_session()
    pcr_match(TEST_FWD_PRIMER, TEST_REV_PRIMER, session=session)
    
    # invalid spec
    try:
        response = custom_track_request('22d', 34304505, 34304954, session)
        assert False
    except ValueError, e:
        assert True
    
    # invalid args
    try:
        response = custom_track_request('22', 34304954, session)
        assert False
    except ValueError, e:
        assert True
    
    response_html = custom_track_request('22', 34304505, 34304954, session)
    assert session.hgsid is not None
    assert session.track_id is not None

    response_html = custom_track_request('M', 10499, 16594, session)
    assert session.hgsid is not None
    assert session.track_id is not None

def test_sequence_fetch():
    session = get_ucsc_session()
    pcr_match(TEST_FWD_PRIMER, TEST_REV_PRIMER, session=session)
    custom_track_request('22', 34304505, 34304954, session)
    response = table_sequence_request('22', 34304505, 34304954, session)
    
    assert session.hgsid is not None
    assert session.track_id is not None
    assert response is not None
    
    assert session.hgsid in response
    assert session.track_id in response
    assert TEST_FWD_PRIMER[2:] in response
    assert reverse_complement(TEST_REV_PRIMER[2:]) in response

    pcr_match(CHRM_OVERSHOOT_FWD_PRIMER, CHRM_OVERSHOOT_REV_PRIMER, session=session)
    custom_track_request('M', 10499, 16594, session) # overshoot on the end
    response = table_sequence_request('M', 10499, 16594, session)
    assert session.hgsid in response
    assert session.track_id in response
    assert CHRM_OVERSHOOT_FWD_PRIMER in response
    assert reverse_complement(CHRM_OVERSHOOT_REV_PRIMER) in response


def test_get_sequence_range():
    # w/o session
    seq = get_sequence_range('22', 34304505, 34304954)
    assert TEST_FWD_PRIMER[2:] in seq.sequence

def test_table_snp_request():
    session = get_ucsc_session()
    snps = table_snp_request('22', 34304505, 34304954, session).strip()
    assert snps is not None
    lines = snps.split('\n')
    lines[0].startswith('#')
    assert len(lines[1:]) == 3

def test_known_gene_request():
    session = get_ucsc_session()
    known_gene_filter_clear(session)
    known_gene_filter('uc003dxq', session)
    genes = known_gene_request(session)
    assert len(genes.strip().split('\n')) == 3

def test_exon_sequences_for_transcript():
    source = UCSCSequenceSource()
    # test negative strand
    exon_sequences = source.exon_sequences_for_transcript('uc003dxq')
    assert len(exon_sequences) == 1
    exon_seq = exon_sequences[0]
    assert exon_seq.start == 109044988
    assert exon_seq.end == 109056419
    assert len(exon_seq) == 2817

    assert exon_seq.base(0) == 109056419
    assert exon_seq.base(2816) == 109044988
    assert exon_seq.base(902) == 109047767
    assert exon_seq.base(1075) == 109046729
    assert exon_seq.strand == '-'
    assert exon_seq.chromosome == '3'

    neg_slice = exon_seq.exon_slice(902, 1075)
    assert neg_slice == [(109047737,109047767),(109046729,109046871)]

    # test positive strand
    exon_sequences = source.exon_sequences_for_transcript('uc001qqu')
    assert len(exon_sequences) == 1
    exon_seq = exon_sequences[0]
    assert exon_seq.base(2286) == 6887324
    assert exon_seq.base(2404) == 6887442
    assert exon_seq.strand == '+'
    assert exon_seq.chromosome == '12'

    pos_slice = exon_seq.exon_slice(2286, 2404)
    assert pos_slice == [(6887324, 6887442)]
    pos_span_slice = exon_seq.exon_slice(800,900)
    assert pos_span_slice == [(6882481,6882505),(6882863,6882938)]




def test_sequences_for_primers():
    source = UCSCSequenceSource()
    sequence_groups = source.sequences_for_primers(TEST_FWD_PRIMER, TEST_REV_PRIMER)
    assert len(sequence_groups) == 1
    seq = sequence_groups[0]
    assert seq.amplicon is not None
    assert seq.left_padding is None
    assert seq.right_padding is None
    amp = seq.amplicon
    assert amp.chromosome == '22'
    assert amp.start == 34304505
    assert amp.end == 34304954
    assert amp.strand == '+'
    assert len(amp.sequence) == 450
    assert amp.sequence.find(TEST_FWD_PRIMER[2:]) == 2
    assert amp.sequence.rfind(reverse_complement(TEST_REV_PRIMER)[:-2]) == 450 - len(TEST_REV_PRIMER)
    
def test_source_sequence():
    source = UCSCSequenceSource()
    assert source.session.hgsid is not None
    sequence = source.sequence('22', 34304505, 34304954)
    assert len(sequence) == 450
    assert sequence.start == 34304505
    assert sequence.end == 34304954
    assert sequence.sequence.find(TEST_FWD_PRIMER[2:]) == 2
    assert sequence.sequence.rfind(reverse_complement(TEST_REV_PRIMER)[:-2]) == 450 - len(TEST_REV_PRIMER)

def test_sequences_for_primers_padded():
    source = UCSCSequenceSource()
    sequence_groups = source.sequences_for_primers(TEST_FWD_PRIMER, TEST_REV_PRIMER, 500, 500)
    assert len(sequence_groups) == 1
    seq = sequence_groups[0]
    assert seq.amplicon is not None
    assert seq.left_padding is not None
    assert seq.right_padding is not None
    assert seq.contiguous
    assert seq.start == 34304005
    assert seq.end == 34305454
    full_seq = seq.merged_sequence
    assert len(full_seq) == 1450
    assert full_seq.sequence.find(TEST_FWD_PRIMER[2:]) == 502
    assert full_seq.sequence.find(reverse_complement(TEST_REV_PRIMER)[:-2]) == 1450 - 500 - len(TEST_REV_PRIMER)

    sequence_groups = source.sequences_for_primers(CHRM_OVERSHOOT_FWD_PRIMER, CHRM_OVERSHOOT_REV_PRIMER, 3000, 3000)
    assert len(sequence_groups) == 1
    seq = sequence_groups[0]
    assert seq.amplicon is not None
    assert seq.left_padding is not None
    assert seq.right_padding is not None
    assert seq.contiguous
    assert seq.start == 10499
    assert seq.end == 16571
    full_seq = seq.merged_sequence
    assert len(full_seq) == 6073
    assert full_seq.sequence.find(CHRM_OVERSHOOT_FWD_PRIMER) == 3000
    # overshoots end by 23 bases
    assert full_seq.sequence.find(reverse_complement(CHRM_OVERSHOOT_REV_PRIMER)) == 6073 - (3000 - 23) - len(CHRM_OVERSHOOT_REV_PRIMER)

def test_sequence_around_loc():
    source = UCSCSequenceSource()
    assert source.session.hgsid is not None
    seq = source.sequence_around_loc('22', 34304730, 225)
    assert seq.left_padding is None
    assert seq.right_padding is None
    assert seq.amplicon.start == 34304506
    assert seq.amplicon.end == 34304954
    full_seq = seq.merged_sequence
    assert len(full_seq) == 449
    assert full_seq.sequence.find(TEST_FWD_PRIMER[2:]) == 1
    assert full_seq.sequence.find(reverse_complement(TEST_REV_PRIMER)[:-2]) == 449 - len(TEST_REV_PRIMER)
    
    seqp = source.sequence_around_loc('22', 34304730, 225, 500, 500)
    assert seqp.left_padding is not None
    assert seqp.right_padding is not None
    assert seqp.left_padding.start == 34304006
    assert seqp.left_padding.end == 34304505
    assert seqp.right_padding.start == 34304955
    assert seqp.right_padding.end == 34305454

    # overshoot test
    seqm = source.sequence_around_loc('M', 14549, 48, 3000, 3000)
    assert seqm.left_padding is not None
    assert seqm.right_padding is not None
    assert seqm.right_padding.end == 16571

def test_sequence_around_region():
    source = UCSCSequenceSource()
    seq = source.sequence_around_region('22', 34304729, 34304730, 226)
    assert seq.left_padding is None
    assert seq.right_padding is None
    assert seq.amplicon.start == 34304505
    assert seq.amplicon.end == 34304954

    seqm = source.sequence_around_region('M', 13549, 13550, 47, 3000, 3000)
    assert seqm.left_padding is not None
    assert seqm.right_padding is not None
    assert seqm.right_padding.start == 13596
    assert seqm.right_padding.end == 16571

    seqe = source.sequence_around_region('M', 1174, 1175, 46, 3000, 3000)
    assert seqe.left_padding is not None
    assert seqe.right_padding is not None
    assert seqe.left_padding.start == 1
    assert seqe.left_padding.end == 1129

def test_transcripts_for_primers():
    source = UCSCSequenceSource()
    
    # negative strand (harder) base case
    transcripts = source.transcript_sequences_for_primers(TEST_GENE_FWD_PRIMER, TEST_GENE_REV_PRIMER)
    assert len(transcripts) == 2
    for t in transcripts:
        assert t.genomic_strand == '-'

    assert transcripts[0].chromosome == transcripts[1].chromosome
    assert transcripts[0].gene == transcripts[1].gene
    # in this case
    assert transcripts[0].exon_spans == transcripts[1].exon_spans

    # more nitty gritty stuff
    assert transcripts[0].ucsc_id == 'uc003dxq'
    assert transcripts[0].start == 903
    assert transcripts[1].end == 780
    assert transcripts[1].sequence == 'ACAATATGTTGTGCCCCAAATGTGTTCACAGGAACAAGGTCTTAATAAAAAGCCTCCAATGGGAATAGAATATCAGGAAAAAGGCCACATCTATGGTAATTAATGGCAGAAAAGCTGGAGAGTTGGATTCTGCGGTGCTGCTGACAGGTGAACTCTGGTCCTCTGCACCTGTTT'
    assert transcripts[1].positive_strand_sequence == transcripts[1].sequence
    assert transcripts[0].negative_strand_sequence == reverse_complement(transcripts[0].sequence)
    assert transcripts[0].sequence == transcripts[1].sequence
    assert transcripts[0].exon_spans == [(109047737,109047767),(109046729,109046871)]
    assert transcripts[1].genomic_start == 109046729
    assert transcripts[1].genomic_end == 109047767
    assert transcripts[0].chromosome == '3'
    assert transcripts[1].exon_span_string == "chr3:109047737-109047767;109046729-109046871"
    assert transcripts[1].ordered_exon_span_string == "chr3:109046729-109046871;109047737-109047767"
    
    # now try the reverse
    transcripts = source.transcript_sequences_for_primers(TEST_GENE_REV_PRIMER, TEST_GENE_FWD_PRIMER)
    assert len(transcripts) == 2
    assert transcripts[0].genomic_strand == '+'
    assert transcripts[0].exon_spans == [(109046729,109046871),(109047737,109047767)]
    assert transcripts[0].negative_strand_sequence == transcripts[0].sequence
    
    # positive inter-exon case
    transcripts = source.transcript_sequences_for_primers(TEST_LAG_2_3_FWD_PRIMER, TEST_LAG_2_3_REV_PRIMER)
    assert len(transcripts) == 3
    assert transcripts[0].genomic_strand == '+'
    assert transcripts[0].exon_spans == [(6882454,6882505),(6882863,6882967)]
    assert transcripts[0].genomic_start == 6882454
    assert transcripts[0].genomic_end == 6882967
    assert transcripts[0].exon_spans == transcripts[1].exon_spans == transcripts[2].exon_spans
    # positive reverse complement case
    transcripts = source.transcript_sequences_for_primers(TEST_LAG_2_3_REV_PRIMER, TEST_LAG_2_3_FWD_PRIMER)
    assert len(transcripts) == 3
    assert transcripts[0].genomic_strand == '-'
    assert transcripts[0].exon_spans == [(6882863,6882967),(6882454,6882505)]

    # positive intra-exon case
    transcripts = source.transcript_sequences_for_primers(TEST_INTRA_EXON_FWD_PRIMER, TEST_INTRA_EXON_REV_PRIMER)
    assert len(transcripts) == 1
    assert transcripts[0].genomic_strand == '+'
    assert transcripts[0].start == 2287
    assert transcripts[0].end == 2405
    assert transcripts[0].exon_spans == [(6887324, 6887442)]
    assert transcripts[0].chromosome == '12'
    
    # multiple amplicon length case
    transcripts = source.transcript_sequences_for_primers(TEST_GEX_MULTIAMP_FWD_PRIMER, TEST_GEX_MULTIAMP_REV_PRIMER)
    assert len(transcripts) == 2
    assert transcripts[0].genomic_strand == '+'
    assert transcripts[0].start == 2010
    assert transcripts[0].end == 2405
    assert transcripts[1].start == 1740
    assert transcripts[1].end == 1813

    assert len(transcripts[0].exon_spans) != len(transcripts[1].exon_spans)
    assert len(transcripts[0].sequence) == 396
    assert len(transcripts[1].sequence) == 74
    assert transcripts[0].exon_spans == [(6887047, 6887442)]
    assert transcripts[1].exon_spans == [(6887047, 6887087), (6887410, 6887442)]
    assert transcripts[0].genomic_start == transcripts[1].genomic_start
    assert transcripts[0].genomic_end == transcripts[1].genomic_end
    assert str(transcripts[0]) == "uc001qqu:2010+2405 (LAG3)"
    assert str(transcripts[1]) == "uc001qqt:1740+1813 (LAG3)"
    assert transcripts[0].exon_span_string == "chr12:6887047+6887442"
    assert transcripts[1].exon_span_string == "chr12:6887047+6887087;6887410+6887442"