import urllib2, urllib, re, cookielib, operator
from poster.streaminghttp import StreamingHTTPHandler
from BeautifulSoup import BeautifulSoup

from qtools.lib.bio import SimpleGenomeSequence, PCRSequence, ExonSpanningSequence
from qtools.lib.datasource import SequenceSource
from qtools.lib.patches import poster_multipart_encode_patch
from qtools.lib.webservice import *

from qtools.model.ucsc import PCRPrimerMatchSequence, PCRGenePrimerMatchSequence

BASE_URL = "http://genome.ucsc.edu/cgi-bin/"
RE_TABLE_URL = "http://genome.ucsc.edu/cgi-bin/hgTables?hgta_table=hgFixed.cutters&hgta_track=snp131&hgta_outputType=primaryTable&hgta_compressType=none&hgta_doTopSubmit=get+output"
REF_DB = GENOME = HG19 = "hg19"
HUMAN = ORGANISM = "Human"
MAMMAL = CLADE = "mammal"
SNP131 = "snp131"
UA = MAC_FIREFOX_UA = "Mozilla/5.0 (Macintosh; U; Intel Mac OS X 10.6; en-US; rv:1.9.2.8) Gecko/20100722 Firefox/3.6.8"

SEQUENCE_POS_RE = re.compile(r'chr(\w+):(\d+)([\+\-])(\d+)')
GENE_POS_RE = re.compile(r'(\w+)\.\d+_+(\w+):(\d+)([\+\-])(\d+)')
HGSID_RE = re.compile(r'hgsid=(\d+)')
HGCT_TABLE_RE = re.compile(r'hgct_table=ct_\w+_(\d+)')
FASTA_SEQ_RE = re.compile(r'range=chr(\w+):(\d+)-(\d+).*strand=([\+\-])')

def get_ucsc_session(fill_hgsid=True, hgsid=None):
    return GenomeBrowserSession(fill_hgsid=fill_hgsid, hgsid=hgsid)

# from http://genome.ucsc.edu/cgi-bin/hgTracks?chromInfoPage
hg19_chromosome_maxes = {
    'chr1'                  : 249250621,
    'chr1_gl000191_random'  :    106433,
    'chr1_gl000192_random'  :    547496,
    'chr2'                  : 243199373,
    'chr3'                  : 198022430,
    'chr4'                  : 191154276,
    'chr4_ctg9_hap1'        :    590426,
    'chr4_gl000193_random'  :    189789,
    'chr4_gl000194_random'  :    191469,
    'chr5'                  : 180915260,
    'chr6'                  : 171115067,
    'chr6_apd_hap1'         :   4622290,
    'chr6_cox_hap2'         :   4795371,
    'chr6_dbb_hap3'         :   4610396,
    'chr6_mann_hap4'        :   4683263,
    'chr6_mcf_hap5'         :   4833398,
    'chr6_qbl_hap6'         :   4611984,
    'chr6_ssto_hap7'        :   4928567,
    'chr7'                  : 159138663,
    'chr7_gl000195_random'  :    182896,
    'chr8'                  : 146364022,
    'chr8_gl000196_random'  :     38914,
    'chr8_gl000197_random'  :     37175,
    'chr9'                  : 141213431,
    'chr9_gl000198_random'  :     90085,
    'chr9_gl000199_random'  :    169874,
    'chr9_gl000200_random'  :    187035,
    'chr9_gl000201_random'  :     36148,
    'chr10'                 : 135534747,
    'chr11'                 : 135006516,
    'chr11_gl000202_random' :     40103,
    'chr12'                 : 133851895,
    'chr13'                 : 115169878,
    'chr14'                 : 107349540,
    'chr15'                 : 102531392,
    'chr16'                 :  90354753,
    'chr17'                 :  81195210,
    'chr17_ctg5_hap1'       :   1680828,
    'chr17_gl000203_random' :     37498,
    'chr17_gl000204_random' :     81310,
    'chr17_gl000205_random' :    174588,
    'chr17_gl000206_random' :     41001,
    'chr18'                 :  78077248,
    'chr18_gl000207_random' :      4262,
    'chr19'                 :  59128983,
    'chr19_gl000208_random' :     92689,
    'chr19_gl000209_random' :    159169,
    'chr20'                 :  63025520,
    'chr21'                 :  48129895,
    'chr21_gl000210_random' :     27682,
    'chr22'                 :  51304566,
    'chrX'                  : 155270560,
    'chrY'                  :  59373566,
    'chrUn_gl000211'        :    166566,
    'chrUn_gl000212'        :    186858,
    'chrUn_gl000213'        :    164239,
    'chrUn_gl000214'        :    137718,
    'chrUn_gl000215'        :    172545,
    'chrUn_gl000216'        :    172294,
    'chrUn_gl000217'        :    172149,
    'chrUn_gl000218'        :    161147,
    'chrUn_gl000219'        :    179198,
    'chrUn_gl000220'        :    161802,
    'chrUn_gl000221'        :    155397,
    'chrUn_gl000222'        :    186861,
    'chrUn_gl000223'        :    180455,
    'chrUn_gl000224'        :    179693,
    'chrUn_gl000225'        :    211173,
    'chrUn_gl000226'        :     15008,
    'chrUn_gl000227'        :    128374,
    'chrUn_gl000228'        :    129120,
    'chrUn_gl000229'        :     19913,
    'chrUn_gl000230'        :     43691,
    'chrUn_gl000231'        :     27386,
    'chrUn_gl000232'        :     40652,
    'chrUn_gl000233'        :     45941,
    'chrUn_gl000234'        :     40531,
    'chrUn_gl000235'        :     34474,
    'chrUn_gl000236'        :     41934,
    'chrUn_gl000237'        :     45867,
    'chrUn_gl000238'        :     39939,
    'chrUn_gl000239'        :     33824,
    'chrUn_gl000240'        :     41933,
    'chrUn_gl000241'        :     42152,
    'chrUn_gl000242'        :     43523,
    'chrUn_gl000243'        :     43341,
    'chrUn_gl000244'        :     39929,
    'chrUn_gl000245'        :     36651,
    'chrUn_gl000246'        :     38154,
    'chrUn_gl000247'        :     36422,
    'chrUn_gl000248'        :     39786,
    'chrUn_gl000249'        :     38502,
    'chrM'                  :     16571
}

CHROMOSOME_MAXES = {HG19: hg19_chromosome_maxes}

class UCSCSequenceSource(SequenceSource):
    """
    Gets sequence information from UCSC.
    """
    def __init__(self, get_hgsid=True, hgsid=None):
        self._session = None
    
    @property
    def session(self):
        if not self._session:
            self._session = get_ucsc_session()
        return self._session
    
    def sequence(self, chromosome, startpos, endpos):
        try:
            return get_sequence_range(chromosome, startpos, endpos, session=self.session)
        # TODO: common handler
        except urllib2.HTTPError:
            # todo: better logging/debug
            print "Got a bad response from the UCSC genome server."
            return None
        except urllib2.URLError:
            # todo: better logging/debug
            print "Could not connect to UCSC genome server."
            return None
    
    def sequences_for_primers(self, primer_fwd, primer_rev, fwd_prefix_length=0, rev_suffix_length=0):
        try:
            amplicons = pcr_match(primer_fwd, primer_rev, session=self.session)
            pcr_sequences = []
            for amplicon in amplicons:
                ch = amplicon.chromosome
                startpos = max(1, amplicon.start - fwd_prefix_length) # do padding here since padding on req doesn't really work
                endpos = amplicon.end+rev_suffix_length # do padding here since padding on req doesn't really work
                region = self.sequence(ch, startpos, endpos)
                
                # from this, make the prefix and suffix ranges but embed the original
                # amplicon, because the amplicon may have additional information.
                actual_fwd_prefix_length = amplicon.start - region.start
                actual_rev_suffix_length = region.end - amplicon.end
                
                # todo: helper function (see sequence_around_loc)
                if actual_fwd_prefix_length > 0:
                    prefix = SimpleGenomeSequence(ch, region.start, amplicon.start-1, region.strand, region.sequence[:actual_fwd_prefix_length])
                else:
                    prefix = None
                
                if actual_rev_suffix_length > 0:
                    suffix = SimpleGenomeSequence(ch, amplicon.end+1, region.end, region.strand, region.sequence[-actual_rev_suffix_length:])
                else:
                    suffix = None
                                
                pcr_sequences.append(PCRSequence(amplicon, prefix, suffix))
            return pcr_sequences
            
        # todo: common error handler

        except urllib2.HTTPError:
            # todo: debug
            print "Got a bad response from the UCSC genome server."
            return None
        except urllib2.URLError:
            # todo: debug
            print "Could not connect to UCSC genome server."
            return None
    
    def sequence_around_loc(self, chromosome, pos, amplicon_width, prefix_length=0, suffix_length=0):
        return self.sequence_around_region(chromosome, pos, pos, amplicon_width, prefix_length, suffix_length)
    
    def sequence_around_region(self, chromosome, startpos, endpos, amplicon_width, prefix_length=0, suffix_length=0):
        base_len = endpos-startpos+1
        if base_len > amplicon_width:
            raise ValueError("region width must be >= amplicon_width")
        
        try:
            # make two calls for now since we want to isolate the amplicon, might just do the one later
            amplicon = self.sequence(chromosome, endpos-(amplicon_width-1), startpos+amplicon_width-1)
            startpos = max(1, amplicon.start - prefix_length)
            endpos = amplicon.end+suffix_length
            region = get_sequence_range(chromosome, startpos, endpos, session=self.session)
            
            actual_prefix_length = amplicon.start - region.start
            actual_suffix_length = region.end - amplicon.end
    
            # todo: helper function (see sequence_around_loc)
            if actual_prefix_length > 0:
                prefix = SimpleGenomeSequence(chromosome, region.start, amplicon.start-1, region.strand, region.sequence[:actual_prefix_length])
            else:
                prefix = None
            
            if actual_suffix_length > 0:
                suffix = SimpleGenomeSequence(chromosome, amplicon.end+1, region.end, region.strand, region.sequence[-actual_suffix_length:])
            else:
                suffix = None
            
            return PCRSequence(amplicon, prefix, suffix)
        
        # todo: common error handler

        except urllib2.HTTPError:
            # todo: debug
            print "Got a bad response from the UCSC genome server."
            return None
        except urllib2.URLError:
            # todo: debug
            print "Could not connect to UCSC genome server."
            return None

    def exon_sequences_for_transcript(self, transcript_id):
        try:
            known_gene_filter_clear(self.session)
            known_gene_filter(transcript_id, self.session)
            response = known_gene_request(self.session)
            db_rows = known_gene_request_process(response)
            exon_seqs = []
            for row in db_rows:
                strand = row['strand']
                chrom = row['chrom'][3:]
                # start is exclusive in db, end inclusive
                # https://lists.soe.ucsc.edu/pipermail/genome/2007-January/012515.html
                # do this such that output reflects what you see in genome browser
                exonStarts = [int(start)+1 for start in row['exonStarts'].split(',') if start != '']
                exonEnds = [int(end) for end in row['exonEnds'].split(',') if end != '']
                subseqs = []
                for start, end in zip(exonStarts, exonEnds):
                    subseqs.append(SimpleGenomeSequence(chrom, start, end, strand))
                exon_seqs.append(ExonSpanningSequence(subseqs))

            return exon_seqs


        except urllib2.HTTPError:
            print "Got a bad response from the UCSC genome server."
            return None
        except urllib2.URLError:
            # todo: debug
            print "Could not retrieve exons from UCSC genome server."
            return None

    def transcript_sequences_for_primers(self, primer_fwd, primer_rev):
        try:
            transcripts = pcr_gene_match(primer_fwd, primer_rev, session=self.session)
            if not transcripts:
                return transcripts
            for transcript in transcripts:
                exon_sequences = self.exon_sequences_for_transcript(transcript.ucsc_id)
                # this is going to return length 1 except for 'uc010nxr', as of 2012/02/27 (JM)
                sequence = exon_sequences[0]
                # return val from pcr_gene_match is 1-index based, internal construct is zero-based
                exon_slices = sequence.exon_slice(transcript.start-1, transcript.end-1)
                exon_slices.sort(key=operator.itemgetter(0))
                transcript.chromosome = sequence.chromosome
                if sequence.strand == transcript.strand:
                    # either a positive transcript for a positive genomic region
                    # or a negative transcript for a negative genomic region,
                    # exon order is positive
                    transcript.genomic_strand = '+'
                    transcript.exon_spans = exon_slices
                else:
                    exon_slices.sort(key=operator.itemgetter(0))
                    transcript.exon_spans = exon_slices[::-1]
                    transcript.genomic_strand = '-'

            return transcripts


        except urllib2.HTTPError:
            # todo: debug
            print "Got a bad response from the UCSC genome server."
            return None
        except urllib2.URLError:
            # todo: debug
            print "Could not connect to UCSC genome server."
            return None




class GenomeBrowserResponseProxy(ResponseProxy):
    def _on_read(self, bytes):
        """
        look for hgsid.  This isn't stored in the cookie.
        """
        hit = re.search(HGSID_RE, bytes)
        if hit:
            self.proxy.hgsid = hit.group(1)
        
        track_hit = re.search(HGCT_TABLE_RE, bytes)
        if track_hit:
            self.proxy.track_id = track_hit.group(1)
    

class GenomeBrowserSession(RequestProxy):
    def __init__(self, fill_hgsid=True, hgsid=None):
        self.jar = cookielib.CookieJar()
        self.opener = urllib2.build_opener(urllib2.HTTPCookieProcessor(self.jar), StreamingHTTPHandler())
        RequestProxy.__init__(self, GenomeBrowserResponseProxy, self.opener)
        
        self._hgsid = hgsid or None
        if self._hgsid is None and fill_hgsid:
            # dummy call to get a hgsid
            response = self.request(make_get_request_url(BASE_URL, 'hgPcr'))
            response.read()
        
        self._trackid = None
    
    @property
    def hguid(self):
        for cookie in self.jar:
            if cookie.name == 'hguid':
                return cookie.value
        return None
    
    def get_hgsid(self):
        return self._hgsid
    
    def set_hgsid(self, id):
        # TODO: right thing?  or should it be set once
        # and then immutable?
        if id is not None:
            self._hgsid = id
    
    def get_track_id(self):
        return self._trackid
    
    def set_track_id(self, id):
        # TODO: right thing?  or should it be set once
        # and only mutable after a delete?
        if id is not None:
            self._trackid = id
    
    hgsid = property(get_hgsid, set_hgsid)
    track_id = property(get_track_id, set_track_id)

def pcr_match(primer_fwd, primer_rev, *args, **request_kwargs):
    """
    Given a forward and reverse primer, return a PCRPrimerMatchSequence
    object which contains the position of the matching sequence(s)
    
    If no sequences match, returns an empty list.
    """
    session = request_kwargs.get('session')
    if not session:
        session = get_ucsc_session()
    
    response = pcr_primer_request(primer_fwd, primer_rev, session, **request_kwargs)
    info_tuples = pcr_primer_response_process(response)
    if not info_tuples:
        return []
    
    return [PCRPrimerMatchSequence(primer_fwd, primer_rev, *tup) for tup in info_tuples]

def pcr_gene_match(primer_fwd, primer_rev, *args, **request_kwargs):
    session = request_kwargs.get('session')
    if not session:
        session = get_ucsc_session()

    response = pcr_gene_primer_request(primer_fwd, primer_rev, request_proxy=session, **request_kwargs)
    info_tuples = pcr_gene_primer_response_process(response)
    if not info_tuples:
        return []

    return [PCRGenePrimerMatchSequence(primer_fwd, primer_rev, *tup) for tup in info_tuples]



def get_sequence_range(chromosome, startpos, endpos, *args, **request_kwargs):
    """
    Given a chromosome, starting position and end position, return a
    SimpleGenomeSequence with the data for that region.
    """
    session = request_kwargs.get('session')
    if not session:
        session = get_ucsc_session()
    
    # establish a custom track to be able to nail down a subsequence--
    # don't care about response
    custom_track_request(chromosome, startpos, endpos, session, **request_kwargs)
    seqdata = table_sequence_request(chromosome, startpos, endpos, session, **request_kwargs)
    return table_sequence_request_process(seqdata)


def parse_sequence_identifier(seq):
    """
    parse_sequence_identifier(string)
    
    Parses the sequence in the format chr[C]:[start](+ or -)[end], returning
    a tuple of chromosome number (or X/Y), start base (int), end base (int),
    and strand (+ or -)
    
    Returns None if the string doesn't match.
    """
    m = SEQUENCE_POS_RE.match(seq)
    if not m:
        return None
    else:
        chrom, start, strand, end = m.groups()
        return (chrom, int(start), int(end), strand)

def parse_gene_identifier(seq):
    m = GENE_POS_RE.match(seq)
    if not m:
        return None
    else:
        ucsc_id, gene, start, relative_strand, end = m.groups()
        return (ucsc_id, gene, int(start), int(end), relative_strand)

def pcr_primer_request(primer_fwd, primer_reverse, request_proxy=None, *args, **kwargs):
    """
    Sends a request to get a FASTA region and sequence based on a primer set.
    
    Returns an HTML page as a response (unless the cookie stuff should be
    handled in some other way)
    
    @param kwargs Use these to directly override request parameters.
                  See 'defaults' below for the list of request params.
    """
    uri = "hgPcr"
    
    # TODO might want to rename the kwargs to things that are more
    # readable, but I'll punt on that for now
    defaults = {'org': HUMAN,
                'wp_target': 'genome',
                'wp_size': 1000,
                'wp_good': 15,
                'wp_perfect': 15,
                'db': HG19,
                'boolshad.wp_flipReverse': 0}
    
    req = make_request_params(defaults, **kwargs)
    req['wp_f'] = primer_fwd
    req['wp_r'] = primer_reverse
    
    if request_proxy is not None:
        response = request_proxy.request(make_get_request_url(BASE_URL, uri, req))
    else:
        response = urllib2.urlopen(make_get_request_url(BASE_URL, uri, req)) # TODO parse cookie
    return response.read()

def pcr_gene_primer_request(primer_fwd, primer_reverse, request_proxy=None, *args, **kwargs):
    return pcr_primer_request(primer_fwd, primer_reverse, request_proxy=request_proxy, wp_target='hg19Kg')

def custom_track_request(chromosome, startpos, endpos, request_proxy=None, *args, **kwargs):
    """
    Needs request_proxy with hgsid or kwargs.hgsid
    
    NOTE: for whatever reason, you need to set the startpos in the submit to the
    startpos computed by the hgPcr tool (and referenced in sequence lookup) minus 1.
    I dunno.  Will write unit test to check if this ever changes.
    """
    if request_proxy:
        if not request_proxy.hgsid:
            raise ValueError, "Cannot make custom track request without hgsid in session"
        else:
            hgsid = request_proxy.hgsid
    else:
        if not kwargs.get('hgsid', None):
            raise ValueError, "Cannot make custom track request without hgsid in kwargs"
        else:
            hgsid = kwargs.get('hgsid')
    
    if 'chr%s' % chromosome not in CHROMOSOME_MAXES[HG19]:
        raise ValueError, "Invalid chromosome: %s" % chromosome
    
    if startpos < 1:
        startpos = 1
    if endpos > CHROMOSOME_MAXES[HG19]['chr%s' % chromosome]:
        endpos = CHROMOSOME_MAXES[HG19]['chr%s' % chromosome]
    
    uri = 'hgCustom'
    defaults = {'hgsid': hgsid,
                'clade': MAMMAL,
                'org': HUMAN,
                'db': HG19,
                'hgct_customText': """track name='%s'
chr%s %s %s""" % (hgsid, chromosome, startpos-1, endpos)}
    req = make_request_params(defaults, **kwargs)
    
    datagen, headers = poster_multipart_encode_patch(req)
    request = urllib2.Request(make_get_request_url(BASE_URL, uri), datagen, headers)
    
    if request_proxy is not None:
        response = request_proxy.request(request)
    else:
        response = urllib2.urlopen(request)
    
    response = response.read()
    
    # hack hack hack
    if "Unrecognized format line" in response or "Error line" in response or "Add Custom Tracks" in response:
        # TODO: parse the error as well?
        raise ValueError, "Invalid custom track specification: chr%s %s %s" % (chromosome, startpos, endpos)
    return response


def table_sequence_request(chromosome, startpos, endpos, request_proxy=None, *args, **kwargs):
    """
    Make table sequence request.  Actually makes two requests; the two requests are
    dependent (at least to generate a sequence), so they are grouped in the same
    method.
    
    Requires a request proxy with hgsid and hgct_table set *or* hgsid and track_id
    kwargs set.
    """
    if request_proxy:
        if not request_proxy.hgsid or not request_proxy.track_id:
            raise ValueError, "Required variables (hgsid, track_id) not set in session"
        else:
            hgsid = request_proxy.hgsid
            track_id = request_proxy.track_id
    elif not kwargs.get('hgsid', None) or not kwargs.get('track_id', None):
        raise ValueError, "Required kwargs (hgsid, track_id) not set"
    else:
        hgsid = kwargs.get('hgsid')
        track_id = kwargs.get('track_id')
    
    if 'chr%s' % chromosome not in CHROMOSOME_MAXES[HG19]:
        raise ValueError, "Invalid chromosome: %s" % chromosome
        
    # zero based request
    if startpos < 0:
        startpos = 0
    
    if endpos > CHROMOSOME_MAXES[HG19]["chr%s" % chromosome]:
        endpos = CHROMOSOME_MAXES[HG19]["chr%s" % chromosome]
    
    uri = "hgTables"
    defaults = {'hgsid': hgsid,
                'boolshad.sendToGalaxy': 0,
                'boolshad.sendToGreat': 0,
                'clade': MAMMAL,
                'db': HG19,
                'hgta_compressType': "none",
                'hgta_doTopSubmit': "get output",
                "hgta_outFileName": "",
                "hgta_outputType": "sequence",
                "hgta_regionType": "range",
                "hgta_table": "ct_%s_%s" % (hgsid, track_id),
                "hgta_track": "ct_%s_%s" % (hgsid, track_id),
                "position": "chr%s:%s-%s" % (chromosome, startpos, endpos)}
    req = make_request_params(defaults, **kwargs)
    
    datagen, headers = poster_multipart_encode_patch(req)
    request = urllib2.Request(make_get_request_url(BASE_URL, uri), datagen, headers)
    
    if request_proxy is not None:
        response = request_proxy.request(request)
    else:
        response = urllib2.urlopen(request)
    
    intermediate = response.read()
    intermediate_tree = BeautifulSoup(intermediate)
    
    # TODO is this more general? (Error case in any UCSC response)
    # if so, put on the request proxy
    if "Error" in intermediate_tree.head.title.text or len(intermediate_tree.findAll(id='warnBox')) > 0:
        raise ValueError, "Could not generate sequence from arguments to hgTables"
    
    defaults2 = {'hgsid': hgsid,
                 'boolshad.hgSeq.maskRepeats': 0,
                 'boolshad.hgSeq.revComp': 0,
                 'hgSeq.casing': "upper",
                 'hgSeq.cdsExon': 1,
                 'hgSeq.padding3': 0, # these don't seem to actually work
                 'hgSeq.padding5': 0, # these don't seem to actually work
                 'hgSeq.repMasking': 'lower',
                 'hgta_doGenomicDna': 'get sequence'}
    req = make_request_params(defaults2, **kwargs)
    
    if request_proxy is not None:
        response = request_proxy.request(make_get_request_url(BASE_URL, uri, req))
    else:
        response = urllib2.urlopen(make_get_request_url(BASE_URL, uri, req))
    
    return response.read()

def table_snp_request(chromosome, startpos, endpos, request_proxy=None, *args, **kwargs):
    """
    Make table SNP (snp131) request.
    
    TODO: this could also be done (and potentially more easily) by connecting
    to UCSC's public MySQL server.  For now, an HTTP request is OK because it's pretty
    simple (and not really stateful)
    
    Requires a request proxy with hgsid set or the hgsid keyword.
    """
    if request_proxy:
        if not request_proxy.hgsid:
            raise ValueError, "Required variable hgsid not set in session"
        else:
            hgsid = request_proxy.hgsid
    elif not kwargs.get('hgsid', None):
        raise ValueError, "Required kwargs hgsid not set"
    else:
        hgsid = kwargs.get('hgsid')
    
    uri = "hgTables"
    defaults = {'hgsid': hgsid,
                'boolshad.sendToGalaxy': 0,
                'boolshad.sendToGreat': 0,
                'clade': MAMMAL,
                'db': HG19,
                'hgta_compressType': 'none',
                'hgta_doTopSubmit': 'get output',
                'hgta_group': 'varRep',
                'hgta_outFileName': '',
                'hgta_outputType': 'primaryTable',
                'hgta_regionType': 'range',
                'hgta_table': SNP131,
                'hgta_track': SNP131,
                'position': 'chr%s:%s-%s' % (chromosome, startpos, endpos)}
    
    req = make_request_params(defaults, **kwargs)
    
    # TODO change to req?
    if request_proxy is not None:
        response = request_proxy.request(make_get_request_url(BASE_URL, uri), urllib.urlencode(defaults))
    else:
        response = urllib2.urlopen(make_get_request_url(BASE_URL, uri), urllib.urlencode(defaults))
    
    return response.read()

def known_gene_filter_clear(request_proxy=None, *args, **kwargs):
    if request_proxy:
        if not request_proxy.hgsid:
            raise ValueError, "Required variable hgsid not set in session"
        else:
            hgsid = request_proxy.hgsid
    elif not kwargs.get('hgsid', None):
        raise ValueError, "Required kwargs hgsid not set"
    else:
        hgsid = kwargs.get('hgsid')

    uri = "hgTables"
    defaults = {'hgsid': hgsid,
                'clade': 'mammal',
                'org': 'Human',
                'db': HG19,
                'hgta_group': 'genes',
                'hgta_track': 'knownGene',
                'hgta_table': 'knownGene',
                'hgta_regionType': 'genome',
                'position': '',
                'hgta_doClearFilter': 'clear',
                'hgta_outputType': 'primaryTable',
                'boolshad.sendToGalaxy': 0,
                'boolshad.sendToGreat': 0,
                'hgta_outFileName': '',
                'hgta_compressType': 'none'}
    req = make_request_params(defaults, **kwargs)
    if request_proxy is not None:
        response = request_proxy.request(make_get_request_url(BASE_URL, uri), urllib.urlencode(req))
    else:
        # this will probably throw an error
        response = urllib2.urlopen(make_get_request_url(BASE_URL, uri), urllib.urlencode(req))

    return response.read()

# TODO may not be necessary
def known_gene_filter_start(request_proxy=None, *args, **kwargs):
    if request_proxy:
        if not request_proxy.hgsid:
            raise ValueError, "Required variable hgsid not set in session"
        else:
            hgsid = request_proxy.hgsid
    elif not kwargs.get('hgsid', None):
        raise ValueError, "Required kwargs hgsid not set"
    else:
        hgsid = kwargs.get('hgsid')

    uri = "hgTables"
    defaults= {'hgsid': hgsid,
               'clade': 'mammal',
               'org': 'Human',
               'db': HG19,
               'hgta_group': 'genes',
               'hgta_track': 'knownGene',
               'hgta_table': 'knownGene',
               'hgta_regionType': 'genome',
               'position': '',
               'hgta_doFilterPage': 'create',
               'hgta_outputType': 'primaryTable',
               'boolshad.sendToGalaxy': 0,
               'boolshad.sendToGreat': 0,
               'hgta_outFileName': '',
               'hgta_compressType': 'none'}
    req = make_request_params(defaults, **kwargs)
    if request_proxy is not None:
        response = request_proxy.request(make_get_request_url(BASE_URL, uri), urllib.urlencode(req))
    else:
        # this will probably throw an error
        response = urllib2.urlopen(make_get_request_url(BASE_URL, uri), urllib.urlencode(req))

    return response.read()

def known_gene_filter(gene, request_proxy=None, *args, **kwargs):
    if request_proxy:
        if not request_proxy.hgsid:
            raise ValueError, "Required variable hgsid not set in session"
        else:
            hgsid = request_proxy.hgsid
    elif not kwargs.get('hgsid', None):
        raise ValueError, "Required kwargs hgsid not set"
    else:
        hgsid = kwargs.get('hgsid')

    uri = "hgTables"
    defaults = {'hgsid': hgsid,
                'hgta_database': HG19,
                'hgta_table': 'knownGene',
                'hgta_fil.v.hg19.knownGene.name.dd': 'does',
                'hgta_fil.v.hg19.knownGene.name.pat': '%s*' % gene,
                'hgta_doFilterSubmit': 'submit',
                }
    req = make_request_params(defaults, **kwargs)
    if request_proxy is not None:
        response = request_proxy.request(make_get_request_url(BASE_URL, uri), urllib.urlencode(req))
    else:
        # this will probably throw an error
        response = urllib2.urlopen(make_get_request_url(BASE_URL, uri), urllib.urlencode(req))

    return response.read()


def known_gene_request(request_proxy=None, *args, **kwargs):
    if request_proxy:
        if not request_proxy.hgsid:
            raise ValueError, "Required variable hgsid not set in session"
        else:
            hgsid = request_proxy.hgsid
    elif not kwargs.get('hgsid', None):
        raise ValueError, "Required kwargs hgsid not set"
    else:
        hgsid = kwargs.get('hgsid')

    uri = "hgTables"
    defaults = {'hgsid': hgsid,
                'clade': 'mammal',
                'org': 'Human',
                'db': HG19,
                'hgta_group': 'genes',
                'hgta_track': 'knownGene',
                'hgta_table': 'knownGene',
                'hgta_regionType': 'genome',
                'position': '',
                'hgta_outputType': 'primaryTable',
                'boolshad.sendToGalaxy': 0,
                'boolshad.sendToGreat': 0,
                'hgta_outFileName': '',
                'hgta_compressType': 'none',
                'hgta_doTopSubmit': 'get output'}

    req = make_request_params(defaults, **kwargs)
    if request_proxy is not None:
        response = request_proxy.request(make_get_request_url(BASE_URL, uri), urllib.urlencode(req))
    else:
        # this will probably throw an error
        response = urllib2.urlopen(make_get_request_url(BASE_URL, uri), urllib.urlencode(req))

    return response.read()

def known_gene_request_process(response):
    lines = response.split('\n')
    rows = []
    if not lines[2].startswith('#'):
        cols = lines[1][1:].split()
        for line in lines[2:]:
            vals = line.split()
            if vals:
                rows.append({col:val for col, val in zip(cols, vals)})
    return rows


def pcr_primer_response_process(response):
    """
    Parse the HTML from the response generated by the PCR primer page.
    
    Return a list of tuples from the response:
    (chromosome, start_base, end_base, strand, match_sequence)
    
    For each tuple, the match sequence will be a combination of lowercase and uppercase, the
    uppercase characters being the parts of the sequence that matches the
    forward and reverse primers.
    """
    tree = BeautifulSoup(response)
    
    pre_nodes = tree.findAll('pre')
    if len(pre_nodes) == 0:
        return None
    
    chrom_links = pre_nodes[0].findAll('a')
    
    seq_list = []
    for link in chrom_links:
        # the sequence location identifier is located in the link inside the pre.
        seq_tuple = parse_sequence_identifier(link.string)
        if not seq_tuple:
            continue
        ch, start, end, strand = seq_tuple
        next = link.nextSibling.string
        
        # hacky bit.  ignore the rest of the line on next, then
        # join the remaining chars to the end of the </pre> tag.
        #
        # Then again, what about scraping isn't hacky?
        seq = ''.join(next.replace('>','').strip().split('\n')[1:])
        seq_list.append((ch, start, end, strand, seq))
    
    return seq_list

def pcr_gene_primer_response_process(response):
    """
    Parse the HTML from the response generated by the PCR primer match page.
    """
    tree = BeautifulSoup(response)

    pre_nodes = tree.findAll('pre')
    if len(pre_nodes) == 0:
        return None

    chrom_links = pre_nodes[0].findAll('a')

    seq_list = []
    for link in chrom_links:
        seq_tuple = parse_gene_identifier(link.string)
        if not seq_tuple:
            continue
        ucsc_id, gene, start, end, strand = seq_tuple
        next = link.nextSibling.string

        # >/'' replaces text up until next link.
        # shared functionality with pcr_primer_response_process;
        # maybe should be abstracted.
        seq = ''.join(next.replace('>','').strip().split('\n')[1:])
        seq_list.append((ucsc_id, gene, start, end, strand, seq))

    return seq_list
        


def table_sequence_request_process(response):
    """
    Assumes the response takes the following form:
    
    FASTA line
    sequence (in blocks of 50)
    
    Will return a SimpleGenomeSequence object.  Since the
    supplied start and end positions may not be the requested ones,
    use the response as the source of truth.
    """
    lines = response.split('\n')
    match = re.search(FASTA_SEQ_RE, lines[0])
    if not match:
        print "no match"
        return None
    
    ch, startpos, endpos, strand = match.groups()
    sequence = ''.join(lines[1:])
    return SimpleGenomeSequence(ch, int(startpos), int(endpos), strand, sequence)


def get_rebase_records():
    rebase_response = urllib2.urlopen(RE_TABLE_URL)
    return [line.split() for line in rebase_response.readlines()[1:]]