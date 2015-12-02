from qtools.lib.dbservice.ucsc import HG19Source, SNP131Transformer, bins, bin_ranges
from qtools.lib.sequence import find_in_sequence_map, mutate_sequences, find_multiple_in_sequence_map, find_in_sequences, find_multiple_for_fragments_map
from qtools.lib.exception import ReturnWithCaveats
from qtools.lib.bio import SimpleGenomeSequence

# TODO: better setup/teardown for connection reuse
def test_snps_by_rsid():
    source = HG19Source()
    snps = source.snps_by_rsid('rs77956831')
    assert snps is not None
    assert len(snps) == 1
    snp = snps[0]
    assert snp['chromStart'] == 34034763
    snps = source.snps_by_rsid('rsFAKEID')
    assert snps is None
    
def test_snps_by_rsid_multi():
    source = HG19Source()
    snps = source.snps_by_rsid('rs17850251')
    assert snps is not None
    assert len(snps) == 3

def test_snps_in_range():
    """
    TODO: moar edge cases
    """
    source = HG19Source()
    snps = source.snps_in_range('22', 34304505, 34304954)
    assert snps is not None
    assert len(snps) == 3

def test_snps_in_chrom_ranges():
    source = HG19Source()
    snps = source.snps_in_chrom_ranges('3', [(109046729,109046871),(109047737,109047767)])
    assert len(snps) == 1
    assert snps[0].chrom == 'chr3'
    assert snps[0].name == 'rs16855542'
    assert snps[0].observed == 'C/T'
    assert snps[0].chromEnd == 109046801

    snps = source.snps_in_chrom_ranges('34', [(1,3),(5,6)])
    assert snps == []

    snps = source.snps_in_chrom_ranges('12', [(6887047, 6887087), (6887410, 6887442)])
    assert snps == []

    snps = source.snps_in_chrom_ranges('12', [(6886947, 6887442)])
    assert len(snps) > 1

def test_transform_single():
    # rs61754211
    # TODO: fixture?
    single_snp_pos = {'name': 'rs61754211',
                      'chrom': 3,
                      'chromStart': 50378152,
                      'chromEnd': 50378153,
                      'strand': '+',
                      'refUCSC': 'A',
                      'observed': 'A/T',
                      'class': 'single',
                      'valid': set(['unknown']),
                      'avHet': 0.0,
                      'avHetSE': 0.0}
    
    single_snp_neg = {'name': 'rs4688725',
                      'chrom': 3,
                      'chromStart': 50378175,
                      'chromEnd': 50378176,
                      'strand': '-',
                      'refUCSC': 'T',
                      'observed': 'A/C',
                      'class': 'single',
                      'valid': set(['by-2hit-2allele','by-cluster','by-1000genomes','by-frequency']),
                      'avHet': 0.496219,
                      'avHetSE': 0.043314}
    
    # do not introduce test dependency on genome browser
    sequence = SimpleGenomeSequence(3,50378107,50378202,'-','AGCTGGCACCCGCTGGGCGCGCTGGGAAGGGCCGCACCCGGCTGGAGCGTGCCAACGCGCTGCGCATCGCGCGGGGCACCGCGTGCAACCCCACAC')
    
    xf = SNP131Transformer()
    sequences = xf.sequence_variant(sequence, single_snp_pos)
    
    reads = [seq.sequence for seq in sequences]
    for seq in sequences:
        assert seq.sequence_index(50378153) == 46
    
    # positive amplicon sequence
    assert 'GTGTGGGGTTGCACGCGGTGCCCCGCGCGATGCGCAGCGCGTTGGCACGCTCCAGCCGGGTGCGGCCCTTCCCAGCGCGCCCAGCGGGTGCCAGCT' in reads
    assert 'GTGTGGGGTTGCACGCGGTGCCCCGCGCGATGCGCAGCGCGTTGGCTCGCTCCAGCCGGGTGCGGCCCTTCCCAGCGCGCCCAGCGGGTGCCAGCT' in reads
    #                                                     ^ there
    
    sequences = xf.sequence_variant(sequence, single_snp_neg)
    
    reads = [seq.sequence for seq in sequences]
    
    # negative amplicon sequence (positive strand)
    assert 'GTGTGGGGTTGCACGCGGTGCCCCGCGCGATGCGCAGCGCGTTGGCACGCTCCAGCCGGGTGCGGCCCTTCCCAGCGCGCCCAGCGGGTGCCAGCT' in reads
    assert 'GTGTGGGGTTGCACGCGGTGCCCCGCGCGATGCGCAGCGCGTTGGCACGCTCCAGCCGGGTGCGGCCCTGCCCAGCGCGCCCAGCGGGTGCCAGCT' in reads
    #                                                                            ^ there

def test_transform_deletion():
    deletion_pos = {'name': 'rs67220081',
                    'chrom': 3,
                    'chromStart': 50379012,
                    'chromEnd': 50379013,
                    'strand': '+',
                    'refUCSC': 'A',
                    'observed': '-/A',
                    'class': 'deletion',
                    'valid': set(['unknown']),
                    'avHet': 0.0,
                    'avHetSE': 0.0}
    
    wide_snp_neg = {'name': 'rs13447390',
                    'chrom': 7,
                    'chromStart': 5570100,
                    'chromEnd': 5570122,
                    'strand': '-',
                    'refUCSC': 'GCCGCCTGCGGCCGGGCCGTGA',
                    'observed': '-/TCACGGCCCGGCCGCAGGCGGC',
                    'class': 'deletion',
                    'valid': set(['by-frequency']),
                    'avHet': 0.448342,
                    'avHetSE': 0.152186}
    
    wide_pre_neg = {'name': 'rs71329416',
                    'chrom': 9,
                    'chromStart': 2364857,
                    'chromEnd': 2364862,
                    'strand': '-',
                    'refUCSC': 'AACTT',
                    'observed': '-/AAGTT',
                    'class': 'deletion',
                    'valid': set(['by-cluster']),
                    'avHet': 0.0,
                    'avHetSE': 0.0}
    
    
    sequence = SimpleGenomeSequence(7, 5570076, 5570412, '+', 'GCTCTGCACGGGCGAAGGGGCCGCGGCCGCCTGCGGCCGGGCCGTGAGCCGCCTGCCCCGGTCGGCTGGCCGGGCTTACCTGGCGGCGGGTGTGGACGGGCGGCGGATCGGCAAAGGCGAGGCTCTGTGCTCGCGGGGCGGACGCGGTCTCGGCGGTGGTGGCGCGTCGCGCCGCTGGGTTTTATAGGGCGCCGCCGCGGCCGCTCGAGCCATAAAAGGCAACTTTCGGAACGGCGCACGCTGATTGGCCCCGCGCCGCTCACTCACCGGCTTCGCCGCACAGTGCAGCATTTTTTTACCCCCTCTCCCCTCCTTTTGCGAAAAAAAAAAAGAGCGA')
    sequence_inv = SimpleGenomeSequence(7, 5570076, 5570412, '-', 'TCGCTCTTTTTTTTTTTCGCAAAAGGAGGGGAGAGGGGGTAAAAAAATGCTGCACTGTGCGGCGAAGCCGGTGAGTGAGCGGCGCGGGGCCAATCAGCGTGCGCCGTTCCGAAAGTTGCCTTTTATGGCTCGAGCGGCCGCGGCGGCGCCCTATAAAACCCAGCGGCGCGACGCGCCACCACCGCCGAGACCGCGTCCGCCCCGCGAGCACAGAGCCTCGCCTTTGCCGATCCGCCGCCCGTCCACACCCGCCGCCAGGTAAGCCCGGCCAGCCGACCGGGGCAGGCGGCTCACGGCCCGGCCGCAGGCGGCCGCGGCCCCTTCGCCCGTGCAGAGC')
    
    xf = SNP131Transformer()
    sequences = xf.sequence_variant(sequence, wide_snp_neg)
    reads = [read.sequence for read in sequences]
    found337 = False
    found315 = False
    foundStat = False
    foundShift = False
    for read in reads:
        if len(read) == 337:
            found337 = True
        if len(read) == 315:
            found315 = True
    
    for seq in sequences:
        if seq.sequence_index(5570200) == 124:
            foundStat = True
        if seq.sequence_index(5570200) == 102:
            foundShift = True
    assert foundStat
    assert foundShift
    
    assert 'GCTCTGCACGGGCGAAGGGGCCGCGGCCGCCTGCGGCCGGGCCGTGAGCCGCCTGCCCCGGTCGGCTGGCCGGGCTTACCTGGCGGCGGGTGTGGACGGGCGGCGGATCGGCAAAGGCGAGGCTCTGTGCTCGCGGGGCGGACGCGGTCTCGGCGGTGGTGGCGCGTCGCGCCGCTGGGTTTTATAGGGCGCCGCCGCGGCCGCTCGAGCCATAAAAGGCAACTTTCGGAACGGCGCACGCTGATTGGCCCCGCGCCGCTCACTCACCGGCTTCGCCGCACAGTGCAGCATTTTTTTACCCCCTCTCCCCTCCTTTTGCGAAAAAAAAAAAGAGCGA' in reads
    #                                ^^^^^^^^^^^^^^^^^^^^^^ this gets deleted.
    assert 'GCTCTGCACGGGCGAAGGGGCCGCGGCCGCCTGCCCCGGTCGGCTGGCCGGGCTTACCTGGCGGCGGGTGTGGACGGGCGGCGGATCGGCAAAGGCGAGGCTCTGTGCTCGCGGGGCGGACGCGGTCTCGGCGGTGGTGGCGCGTCGCGCCGCTGGGTTTTATAGGGCGCCGCCGCGGCCGCTCGAGCCATAAAAGGCAACTTTCGGAACGGCGCACGCTGATTGGCCCCGCGCCGCTCACTCACCGGCTTCGCCGCACAGTGCAGCATTTTTTTACCCCCTCTCCCCTCCTTTTGCGAAAAAAAAAAAGAGCGA' in reads
    
    sequences2 = xf.sequence_variant(sequence_inv, wide_snp_neg)
    # assure that happens on negative strand input
    found337 = False
    found315 = False
    reads2 = [read.sequence for read in sequences2]
    for read in reads2:
        if len(read) == 337:
            found337 = True
        if len(read) == 315:
            found315 = True
    
    assert 'GCTCTGCACGGGCGAAGGGGCCGCGGCCGCCTGCGGCCGGGCCGTGAGCCGCCTGCCCCGGTCGGCTGGCCGGGCTTACCTGGCGGCGGGTGTGGACGGGCGGCGGATCGGCAAAGGCGAGGCTCTGTGCTCGCGGGGCGGACGCGGTCTCGGCGGTGGTGGCGCGTCGCGCCGCTGGGTTTTATAGGGCGCCGCCGCGGCCGCTCGAGCCATAAAAGGCAACTTTCGGAACGGCGCACGCTGATTGGCCCCGCGCCGCTCACTCACCGGCTTCGCCGCACAGTGCAGCATTTTTTTACCCCCTCTCCCCTCCTTTTGCGAAAAAAAAAAAGAGCGA' in reads2
    #                                ^^^^^^^^^^^^^^^^^^^^^^ this gets deleted.
    assert 'GCTCTGCACGGGCGAAGGGGCCGCGGCCGCCTGCCCCGGTCGGCTGGCCGGGCTTACCTGGCGGCGGGTGTGGACGGGCGGCGGATCGGCAAAGGCGAGGCTCTGTGCTCGCGGGGCGGACGCGGTCTCGGCGGTGGTGGCGCGTCGCGCCGCTGGGTTTTATAGGGCGCCGCCGCGGCCGCTCGAGCCATAAAAGGCAACTTTCGGAACGGCGCACGCTGATTGGCCCCGCGCCGCTCACTCACCGGCTTCGCCGCACAGTGCAGCATTTTTTTACCCCCTCTCCCCTCCTTTTGCGAAAAAAAAAAAGAGCGA' in reads2
    assert len(sequences) == 2
    assert len(sequences2) == 2
    
    sequence3 = SimpleGenomeSequence(9, 2364860, 2364878, '+', 'CTTTATATAAACTGGAAAC')
    sequences3 = xf.sequence_variant(sequence3, wide_pre_neg)
    assert len(sequences3) == 2
    reads3 = [read.sequence for read in sequences3]
    assert 'CTTTATATAAACTGGAAAC' in reads3
    #       ^^^ here
    assert 'TATATAAACTGGAAAC' in reads3
    
    reverse = sequences3[1].reverse_complement()
    assert reverse.sequence == 'GTTTCCAGTTTATATA'
    assert reverse.sequence_index(2364863) == 15
    assert sequences3[1].sequence_index(2364860) == -1
    assert sequences3[1].sequence_index(1) == -1
    assert sequences3[1].sequence_index(4444000) == -1
    assert sequences3[1].sequence_index(2364863) == 0
    assert sequences3[1].sequence_slice_indices(2364863, 2364866) == (0,3)
    assert reverse.sequence_slice_indices(2364863, 2364866) == (12, 15)
    
    sequence4 = SimpleGenomeSequence(9, 2364841, 2364859, '+', 'GATTTATATAAGCAAATAA')
    sequences4 = xf.sequence_variant(sequence4, wide_pre_neg)
    reads4 = [read.sequence for read in sequences4]
    assert len(sequences4) == 2
    assert 'GATTTATATAAGCAAATAA' in reads4
    assert 'GATTTATATAAGCAAAT' in reads4

def test_transform_insertion():
    insertion_pos = {'name': 'rs71004684',
                    'chrom': 7,
                    'chromStart': 5570406,
                    'chromEnd': 5570406,
                    'strand': '-',
                    'refUCSC': '-',
                    'observed': '-/A',
                    'class': 'insertion',
                    'valid': set(['unknown']),
                    'avHet': 0.0,
                    'avHetSE': 0.0}
    
    sequence = SimpleGenomeSequence(7, 5570076, 5570412, '+', 'GCTCTGCACGGGCGAAGGGGCCGCGGCCGCCTGCGGCCGGGCCGTGAGCCGCCTGCCCCGGTCGGCTGGCCGGGCTTACCTGGCGGCGGGTGTGGACGGGCGGCGGATCGGCAAAGGCGAGGCTCTGTGCTCGCGGGGCGGACGCGGTCTCGGCGGTGGTGGCGCGTCGCGCCGCTGGGTTTTATAGGGCGCCGCCGCGGCCGCTCGAGCCATAAAAGGCAACTTTCGGAACGGCGCACGCTGATTGGCCCCGCGCCGCTCACTCACCGGCTTCGCCGCACAGTGCAGCATTTTTTTACCCCCTCTCCCCTCCTTTTGCGAAAAAAAAAAAGAGCGA')
    sequence_inv = SimpleGenomeSequence(7, 5570076, 5570412, '-', 'TCGCTCTTTTTTTTTTTCGCAAAAGGAGGGGAGAGGGGGTAAAAAAATGCTGCACTGTGCGGCGAAGCCGGTGAGTGAGCGGCGCGGGGCCAATCAGCGTGCGCCGTTCCGAAAGTTGCCTTTTATGGCTCGAGCGGCCGCGGCGGCGCCCTATAAAACCCAGCGGCGCGACGCGCCACCACCGCCGAGACCGCGTCCGCCCCGCGAGCACAGAGCCTCGCCTTTGCCGATCCGCCGCCCGTCCACACCCGCCGCCAGGTAAGCCCGGCCAGCCGACCGGGGCAGGCGGCTCACGGCCCGGCCGCAGGCGGCCGCGGCCCCTTCGCCCGTGCAGAGC')
    
    xf = SNP131Transformer()
    sequences = xf.sequence_variant(sequence, insertion_pos)
    reads = [read.sequence for read in sequences]
    found337 = False
    found338 = False
    for read in reads:
        if len(read) == 337:
            found337 = True
        if len(read) == 338:
            found338 = True
    
    assert found337
    assert found338
    
    assert 'GCTCTGCACGGGCGAAGGGGCCGCGGCCGCCTGCGGCCGGGCCGTGAGCCGCCTGCCCCGGTCGGCTGGCCGGGCTTACCTGGCGGCGGGTGTGGACGGGCGGCGGATCGGCAAAGGCGAGGCTCTGTGCTCGCGGGGCGGACGCGGTCTCGGCGGTGGTGGCGCGTCGCGCCGCTGGGTTTTATAGGGCGCCGCCGCGGCCGCTCGAGCCATAAAAGGCAACTTTCGGAACGGCGCACGCTGATTGGCCCCGCGCCGCTCACTCACCGGCTTCGCCGCACAGTGCAGCATTTTTTTACCCCCTCTCCCCTCCTTTTGCGAAAAAAAAAAAGAGCGA' in reads
    assert 'GCTCTGCACGGGCGAAGGGGCCGCGGCCGCCTGCGGCCGGGCCGTGAGCCGCCTGCCCCGGTCGGCTGGCCGGGCTTACCTGGCGGCGGGTGTGGACGGGCGGCGGATCGGCAAAGGCGAGGCTCTGTGCTCGCGGGGCGGACGCGGTCTCGGCGGTGGTGGCGCGTCGCGCCGCTGGGTTTTATAGGGCGCCGCCGCGGCCGCTCGAGCCATAAAAGGCAACTTTCGGAACGGCGCACGCTGATTGGCCCCGCGCCGCTCACTCACCGGCTTCGCCGCACAGTGCAGCATTTTTTTACCCCCTCTCCCCTCCTTTTGCGAAAAAAAAAAATGAGCGA'in reads
    #                                                                                                                                                                                                                                                                                                                                                  ^ there
    assert sequences[0].sequence_index(5570412) == 336
    assert sequences[0].sequence_index(5570406) == 330
    assert sequences[1].sequence_index(5570406) == 330
    assert sequences[1].sequence_index(5570407) == 332
    assert sequences[1].sequence_index(5570412) == 337

def test_transform_indel():
    indel_neg = {'name': 'rs79578334',
                 'chrom': 9,
                 'chromStart': 21971319,
                 'chromEnd': 21971320,
                    'strand': '-',
                    'refUCSC': 'C',
                    'observed': '-/ATTA',
                    'class': 'in-del',
                    'valid': set(['unknown']),
                    'avHet': 0.0,
                    'avHetSE': 0.0}
    
    wide_indel = {'name': 'rs71491986',
                  'chrom': 9,
                  'chromStart': 2082348,
                  'chromEnd': 2082350,
                  'strand': '+',
                  'refUCSC': 'GT',
                  'observed': '-/GA',
                  'class': 'in-del',
                  'valid': set(['unknown']),
                  'avHet': 0.0,
                  'avHetSE': 0.0}
    
    sequence = SimpleGenomeSequence(9, 21971302, 21971340, '+', 'CACACAAGCCCCAGGTGTCTAATTACCCCTACATTTGCT')
    sequence_inv = SimpleGenomeSequence(9, 21971302, 21971340, '-', 'AGCAAATGTAGGGGTAATTAGACACCTGGGGCTTGTGTG')
    
    xf = SNP131Transformer()
    sequences = xf.sequence_variant(sequence, indel_neg)
    reads = [read.sequence for read in sequences]
    found39 = False
    found38 = False
    found42 = False
    for read in reads:
        if len(read) == 39:
            found39 = True
        if len(read) == 38:
            found38 = True
        if len(read) == 42:
            found42 = True
    
    assert found38
    assert found39
    assert found42
    assert len(sequences) == 3
    
    assert 'CACACAAGCCCCAGGTGTCTAATTACCCCTACATTTGCT' in reads
    assert 'CACACAAGCCCCAGGTGTTAATTACCCCTACATTTGCT' in reads
    #                         ^ here
    assert 'CACACAAGCCCCAGGTGTTAATTAATTACCCCTACATTTGCT' in reads
    #                         ^^^^ here
    
    assert sequences[0].sequence_index(21971321) == 19
    assert sequences[1].sequence_index(21971321) == 22
    assert sequences[2].sequence_index(21971321) == 18
    assert sequences[1].sequence_index(21971319) == 17
    assert sequences[1].sequence_index(21971320) == 18
    assert sequences[2].sequence_index(21971320) == 17
    
    sequences2 = xf.sequence_variant(sequence_inv, indel_neg)
    reads2 = [read.sequence for read in sequences2]
    assert len(sequences2) == 3
    assert 'CACACAAGCCCCAGGTGTCTAATTACCCCTACATTTGCT' in reads2
    assert 'CACACAAGCCCCAGGTGTTAATTACCCCTACATTTGCT' in reads2
    #                         ^ here
    assert 'CACACAAGCCCCAGGTGTTAATTAATTACCCCTACATTTGCT' in reads2
    #                         ^^^^ here
    
    before_seq = SimpleGenomeSequence(9, 2082350, 2082367, '+', 'TGATTTCTTTGATTTTTT')
    sequences3 = xf.sequence_variant(before_seq, wide_indel)
    reads3 = [read.sequence for read in sequences3]
    assert len(reads3) == 3
    assert 'TGATTTCTTTGATTTTTT' in reads3
    assert 'GATTTCTTTGATTTTTT' in reads3
    assert 'GAGATTTCTTTGATTTTTT' in reads3 # GA for T (GA -> GT, but includes seq)
    
    after_seq = SimpleGenomeSequence(9, 2082331, 2082349, '+', 'GTGTGTGTGTGTGTGTGTG')
    sequences4 = xf.sequence_variant(after_seq, wide_indel)
    reads4 = [read.sequence for read in sequences4]
    assert len(sequences4) == 3
    assert 'GTGTGTGTGTGTGTGTGTG' in reads4
    assert 'GTGTGTGTGTGTGTGTGT' in reads4
    assert 'GTGTGTGTGTGTGTGTGTGA' in reads4

def test_transform_mixed():
    mixed_insert = {'name': 'rs3055618',
                    'chrom': 9,
                    'chromStart': 2246255,
                    'chromEnd': 2246255,
                    'strand': '-',
                    'refUCSC': '-',
                    'observed': '-/AC/CA',
                    'class': 'mixed',
                    'valid': set(['unknown']),
                    'avHet': 0.0,
                    'avHetSE': 0.0}
    
    mixed_delete = {'name': 'rs3057852',
                    'chrom': 9,
                    'chromStart': 2082306,
                    'chromEnd': 2082308,
                    'strand': '-',
                    'refUCSC': 'GT',
                    'observed': '-/AC/CA',
                    'class': 'mixed',
                    'valid': set(['unknown']),
                    'avHet': 0.0,
                    'avHetSE': 0.0}
    
    mixed_shebang = {'name': 'rs2376214',
                    'chrom': 9,
                    'chromStart': 2364859,
                    'chromEnd': 2364860,
                    'strand': '-',
                    'refUCSC': 'C',
                    'observed': '-/A/ATAAA/G',
                    'class': 'mixed',
                    'valid': set(['unknown']),
                    'avHet': 0.0,
                    'avHetSE': 0.0}
    
    sequence = SimpleGenomeSequence(9, 2246246, 2246264, '+', 'TATGTAACACTAAGATAAT')
    sequence_inv = SimpleGenomeSequence(9, 2246246, 2246264, '-', 'ATTATCTTAGTGTTACATA')
    
    xf = SNP131Transformer()
    sequences = xf.sequence_variant(sequence, mixed_insert)
    reads = [read.sequence for read in sequences]
    found19 = False
    found21 = False
    for read in reads:
        if len(read) == 19:
            found19 = True
        if len(read) == 21:
            found21 = True
    assert found19
    assert found21
    assert len(reads) == 3
    
    print reads
    assert 'TATGTAACACTAAGATAAT' in reads
    assert 'TATGTAACACTGTAAGATAAT' in reads
    assert 'TATGTAACACGTTAAGATAAT' in reads
    #                 ^^ here
    
    sequence2 = SimpleGenomeSequence(9, 2082298, 2082316, '+', 'AGGGGAAAGGTGTGTGTGT')
    
    sequences2 = xf.sequence_variant(sequence2, mixed_delete)
    reads2 = [read.sequence for read in sequences2]
    found19 = False
    found17 = False
    for read in reads2:
        if len(read) == 19:
            found19 = True
        if len(read) == 17:
            found17 = True
    assert found19
    assert found17
    
    assert 'AGGGGAAAGGTGTGTGTGT' in reads2
    assert 'AGGGGAAAGTGGTGTGTGT' in reads2
    #                ^^ here
    assert 'AGGGGAAAGGTGTGTGT' in reads2
    
    # sequence from hell (look at this space for combinations, lot going on).
    sequence3 = SimpleGenomeSequence(9, 2364850, 2364868, '+', 'AAGCAAATAACTTTATATA')
    sequences3 = xf.sequence_variant(sequence3, mixed_shebang)
    reads3 = [read.sequence for read in sequences3]
    
    assert len(sequences3) == 4
    assert 'AAGCAAATAACTTTATATA' in reads3
    assert 'AAGCAAATAATTTTATATA' in reads3
    #                 ^ there
    assert 'AAGCAAATAATTTATATA' in reads3
    #                 ^ there (del)
    assert 'AAGCAAATAATTTATTTTATATA' in reads3
    #                 ^^^^^ there (insert)
    
    assert sequences3[0].sequence_index(2364850) == 0
    assert sequences3[0].sequence_index(2364861) == 10
    assert sequences3[0].reverse_complement().sequence_index(2364859) == 8
    assert sequences3[1].sequence_index(2364861) == 11
    assert sequences3[0].reverse_complement().sequence_index(2364852) == 15
    assert sequences3[0].reverse_complement().sequence_index(2364867) == 1
    assert sequences3[1].reverse_complement().sequence_index(2364859) == 9
    assert sequences3[2].sequence_index(2364854) == 4
    assert sequences3[2].sequence_index(2364861) == 15
    assert sequences3[2].reverse_complement().sequence_index(2364861) == 7
    assert sequences3[2].reverse_complement().sequence_index(2364860) == 12

def test_transform_mnp():
    mnp_insert = {'name': 'rs35279883',
                    'chrom': 9,
                    'chromStart': 2400227,
                    'chromEnd': 2400227,
                    'strand': '-',
                    'refUCSC': '-',
                    'observed': 'CT/TC',
                    'class': 'mnp',
                    'valid': set(['by-cluster']),
                    'avHet': 0.0,
                    'avHetSE': 0.0}
    
    mnp_multi = {'name': 'rs35279883',
                 'chrom': 9,
                 'chromStart': 2183635,
                 'chromEnd': 2183638,
                 'strand': '+',
                 'refUCSC': 'AAG',
                 'observed': 'AAG/GGA',
                 'class': 'mnp',
                 'valid': set(['unknown']),
                 'avHet': 0.0,
                 'avHetSE': 0.0}
    
    sequence = SimpleGenomeSequence(9, 2400218, 2400236, '+', 'CTCATAAACTGAATTAGAG')
    xf = SNP131Transformer()
    sequences = xf.sequence_variant(sequence, mnp_insert)
    reads = [read.sequence for read in sequences]
    assert len(sequences) == 3
    assert 'CTCATAAACTGAATTAGAG' in reads
    assert 'CTCATAAACTGAGAATTAGAG' in reads
    #                 ^^ here
    assert 'CTCATAAACTAGGAATTAGAG' in reads
    #                 ^^ here
    
    sequence2 = SimpleGenomeSequence(9, 2183627, 2183645, '-', 'TCTATTCCTTTGTTTGATG')
    sequences2 = xf.sequence_variant(sequence2, mnp_multi)
    assert len(sequences2) == 2
    reads2 = [read.sequence for read in sequences2]
    assert 'CATCAAACAAAGGAATAGA' in reads2
    assert 'CATCAAACAGGAGAATAGA' in reads2

def test_sequence_variants_ignore_overlap():
    """
    For now, ignore overlap, but report it.
    
    Do an end-to-end test (include MySQL lookup)
    """
    source = HG19Source()
    sequence = SimpleGenomeSequence(9, 2364849, 2364871, '+', 'TAAGCAAATAACTTTATATAAAC')
    snps = source.snps_in_range(sequence.chromosome, sequence.start, sequence.end)
    assert len(snps) == 4
    xf = SNP131Transformer()
    
    try:
        sequences = xf.sequence_variants(sequence, snps)
        # should throw an exception since we have overlaps
        assert False
    except ReturnWithCaveats, e:
        sequences = e.return_value
    
    reads = [read.sequence for read in sequences]
    assert 'TAAGCAAATAACTTTATATAAAC' in reads
    assert 'TAAGCAAATTACTTTATATAAAC' in reads
    #                ^ there
    assert 'TAAGCAAATTATATAAAC' in reads
    #                ^ missing 5
    assert 'TAAGCAAATAATTTTATATAAAC' in reads
    #                  ^ there
    assert 'TAAGCAAATAATTTATATAAAC' in reads
    #                  ^ missing 1
    assert 'TAAGCAAATAATTTATTTTATATAAAC' in reads
    #                  ^^^^^
    assert 'TAAGCAAATAACTTATATAAAC' in reads
    #                    ^ missing 1
    assert 'TAAGCAAATAACTAACTTTATATAAAC' in reads
    #                    ^^^^^
    assert len(sequences) == 11 # NOTE: some sequence overlap expected.

def test_find_in_sequences():
    source = HG19Source()
    xf = SNP131Transformer()
    sequence = SimpleGenomeSequence(9, 2364849, 2364871, '+', 'TAAGCAAATAACTTTATATAAAC')
    sequence_inv = SimpleGenomeSequence(9, 2364849, 2364871, '-', 'GTTTATATAAAGTTATTTGCTTA')
    snps = source.snps_in_range(sequence.chromosome, sequence.start, sequence.end)
    
    try:
        variants = mutate_sequences(xf, sequence, snps, 6)
    except ReturnWithCaveats, e:
        variants = e.return_value
    
    assert len(snps) == 4
    assert len(variants) == 8
    
    matches = find_in_sequences("AATT", variants)
    
    assert len(matches) == 5
    for match in matches:
        assert len(match[1]) == 1
    
    gotit_count = 0
    for sequence, match in matches:
        if sequence.positive_strand_sequence == 'TAAGCAAATTACTTTATATAAAC':
            assert match == [(6,10,'+')]
            gotit_count += 1
        elif sequence.positive_strand_sequence == 'TAAGCAAATTATATAAAC':
            assert match == [(6,10,'+')]
            gotit_count += 1
        elif sequence.positive_strand_sequence == 'TAAGCAAATAATTTTATATAAAC':
            assert match == [(9,13,'+')]
            gotit_count += 1
        elif sequence.positive_strand_sequence == 'TAAGCAAATAATTTATATAAAC':
            assert match == [(9,13,'+')]
            gotit_count += 1
        elif sequence.positive_strand_sequence == 'TAAGCAAATAATTTATTTTATATAAAC':
            assert match == [(9,13,'+')]
            gotit_count += 1
    
    assert gotit_count == 5
    
    matches = find_in_sequences("AAMKTT", variants)
    
    assert len(matches) == 2
    
    gotit_count = 0
    for sequence, match in matches:
        if sequence.positive_strand_sequence == 'TAAGCAAATAACTTTATATAAAC':
            assert match == [(9,15,'+')]
            gotit_count += 1
        if sequence.positive_strand_sequence == 'TAAGCAAATAACTAACTTTATATAAAC':
            assert match == [(13,19,'+')]
            gotit_count += 1
    
    assert gotit_count == 2
    
    matches_mk = find_in_sequence_map("AAMKTT", variants)
    
    assert len(matches_mk) == 8
    # just some dblcheckin
    idx1 = [idx for idx, seq in enumerate(variants) if seq.positive_strand_sequence == 'TAAGCAAATAACTTTATATAAAC'][0]
    idx2 = [idx for idx, seq in enumerate(variants) if seq.positive_strand_sequence == 'TAAGCAAATAACTAACTTTATATAAAC'][0]
    assert matches_mk[idx1] == [(9,15,'+')]
    assert matches_mk[idx2] == [(13,19,'+')]
    
    matches = find_multiple_in_sequence_map({'j1': 'AATT', 'j2': 'AAMKTT'}, variants)

    assert len(matches) == 8
    assert len([m for m in matches if len(m) == 0]) == 1
    
    # make sure we're omitting the one we want to omit
    idx3 = [idx for idx, seq in enumerate(variants) if seq.positive_strand_sequence == 'TAAGCAAATAACTTATATAAAC'][0]
    assert len(matches[idx3]) == 0
    
    matches = find_multiple_in_sequence_map({'j1': 'AATT', 'j2': 'AAMKTT'}, variants, False)
    assert len(matches) == 8
    assert len([m for m in matches if len(m) == 0]) == 0
    
    fragments = find_multiple_for_fragments_map({'j1': 'AATT', 'j2': 'AAMKTT'}, variants)
    assert len(fragments) == 2
    print fragments['j1']
    assert len(fragments['j1']) == 8
    assert len([l for l in fragments['j1'] if l]) == 5
    assert len(fragments['j2']) == 8
    assert len([l for l in fragments['j2'] if l]) == 2
    assert len(fragments['j2'][idx1]) > 0
    assert len(fragments['j2'][idx2]) > 0
    
    assert fragments['j2'] == matches_mk

def test_bins():
    assert bins(20000) == [0, 1, 9, 73, 585]
    assert bins(140450089) == [0, 3, 25, 206, 1656]
    assert bins(140457041) == [0, 3, 25, 206, 1656]
    try:
        test = bins(0)
        assert False
    except ValueError:
        assert True
    except Exception:
        assert False
    
    try:
        test  = bins(-1)
        assert False
    except ValueError:
        assert True
    except Exception:
        assert False
    
    try:
        test = bins(512*1024*1024+1)
        assert False
    except ValueError:
        assert True
    except Exception:
        assert False
    
    test = bins(512*1024*1024)
    test = bins(1)

def test_bin_ranges():
    assert bin_ranges(140450089, 140450089) == [0, 3, 25, 206, 1656]
    assert bin_ranges(140450089, 140450088) == [0, 3, 25, 206, 1656]
    assert bin_ranges(140450089, 140457041) == [0, 3, 25, 206, 1656]
    assert bin_ranges(140450089, 140637041) == [0, 3, 25, 206, 207, 1656, 1657]
    assert bin_ranges(140450089, 140737041) == [0, 3, 25, 206, 207, 1656, 1657, 1658]
    try:
        test = bin_ranges(-1, 140450089)
        assert False
    except ValueError:
        assert True
    except Exception:
        assert False
