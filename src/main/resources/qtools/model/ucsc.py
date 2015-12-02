import re, operator

# might be able to be more restrictive (ATCGU) but playin it safe
UPPER_RE = re.compile(r'[A-Z]+')

from qtools.lib.bio import SimpleGenomeSequence

class PCRPrimerMatchSequence(SimpleGenomeSequence):
    """
    TODO: abstract PCRPrimerMatchSequence and UCSC-specific
    "good enough" max lengths?
    """
    
    def __init__(self, forward_primer, reverse_primer, chromosome, start, end, strand, full_sequence):
        self._fp = forward_primer
        self._rp = reverse_primer
        
        # The full_sequence match has uppercase and lowercase characters.  Uppercase characters
        # correspond to the areas that matched the primer (and reverse primer complement).
        
        # find the longest capital subsequences in the area full_sequence[0:len(fwd_primer)], and [:-(len(reverse_primer))]
        max_fwd_offset = 0
        max_fwd_match = ''
        max_rev_offset = 0
        max_rev_match = ''
        for match in re.finditer(UPPER_RE, full_sequence[:len(forward_primer)]):
            if len(match.group(0)) > len(max_fwd_match):
                max_fwd_offset = match.start()
                max_fwd_match = match.group(0)
        
        for match in re.finditer(UPPER_RE, full_sequence[-len(reverse_primer):]):
            if len(match.group(0)) > len(max_rev_match):
                max_rev_offset = len(reverse_primer)-match.end()
                max_rev_match = match.group(0)
        
        self._perfect = len(max_fwd_match) == len(forward_primer) and len(max_rev_match) == len(reverse_primer)
        self._fwd_offset = max_fwd_offset
        self._fwd_match = max_fwd_match
        self._rev_offset = max_rev_offset
        self._rev_match = max_rev_match
        
        super(PCRPrimerMatchSequence, self).__init__(chromosome, start, end, strand, full_sequence.upper())
    
    @property
    def forward_primer(self):
        return self._fp
    
    @property
    def reverse_primer(self):
        return self._rp
    
    @property
    def perfect_primer_match(self):
        """
        Returns whether there was a perfect primer match in both directions.
        """
        return self._perfect
    
    @property
    def longest_forward_match(self):
        return self._fwd_match
    
    @property
    def longest_forward_match_offset(self):
        return self._fwd_offset
    
    @property
    def longest_reverse_match(self):
        # TODO: return as reverse complement?
        return self._rev_match
    
    @property
    def longest_reverse_match_offset(self):
        return self._rev_offset

def make_exon_span_string(spans, strand):
    return ";".join(["%s%s%s" % (start, strand, end) for start, end in spans])

class PCRGenePrimerMatchSequence(PCRPrimerMatchSequence):
    def __init__(self, forward_primer, reverse_primer, ucsc_id, gene, start, end, strand, full_sequence):
        super(PCRGenePrimerMatchSequence, self).__init__(forward_primer, reverse_primer, ucsc_id, start, end, strand, full_sequence)
        self.ucsc_id = ucsc_id
        self.gene = gene
        self._exon_spans = []
        self.genomic_strand = '+'
        self._ch = None

    def _get_chromosome(self):
        return self._ch

    def _set_chromosome(self, chrom):
        self._ch = chrom

    chromosome = property(_get_chromosome, _set_chromosome)

    def _get_exon_spans(self):
        return self._exon_spans

    def _set_exon_spans(self, spans):
        self._exon_spans = list(spans)

    exon_spans = property(_get_exon_spans, _set_exon_spans)

    @property
    def genomic_start(self):
        if self._exon_spans:
            return min([tup[0] for tup in self._exon_spans])
        else:
            return None

    @property
    def genomic_end(self):
        if self._exon_spans:
            return max([tup[1] for tup in self._exon_spans])
        else:
            return None

    @property
    def ordered_exon_spans(self):
        if not self._exon_spans:
            return []
        else:
            return sorted(self._exon_spans, key=operator.itemgetter(0))

    @property
    def exon_span_string(self):
        return "chr%s:%s" % (self.chromosome, make_exon_span_string(self._exon_spans, self.genomic_strand))

    @property
    def ordered_exon_span_string(self):
        return "chr%s:%s" % (self.chromosome, make_exon_span_string(self.ordered_exon_spans, self.genomic_strand))

    def __str__(self):
        return "%s:%s%s%s (%s)" % (self.ucsc_id, self.start, self.strand, self.end, self.gene)

    def __unicode__(self):
        return unicode(str(self))

    @property
    def positive_genomic_strand_sequence(self):
        if self.genomic_strand == self.strand:
            return self.positive_strand_sequence
        else:
            return self.negative_strand_sequence

    @property
    def negative_genomic_strand_sequence(self):
        if self.genomic_strand != self.strand:
            return self.positive_strand_sequence
        else:
            return self.negative_strand_sequence

    @property
    def fasta(self):
        raise NotImplementedError