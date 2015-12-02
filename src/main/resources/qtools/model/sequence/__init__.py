from qtools.lib.bio import reverse_complement, gc_content, maximal_binding_seq
from qtools.model import now, AssayCacheMixin
from qtools.model.meta import Base

from sqlalchemy import orm, Integer, Unicode, String, Text, SmallInteger, UnicodeText, DateTime, Float, Boolean
from sqlalchemy.schema import Table, Column, Sequence as SchemaSequence, ForeignKey
from sqlalchemy.dialects.mysql import LONGBLOB
from sqlalchemy.dialects.mysql.base import MSEnum, MSSet

from itertools import product

import re

STRAND_RE = re.compile(r'[\+\-]')

metadata = Base.metadata

sequence_group_project_table = Table('sequence_group_project', metadata,
    Column('id', Integer, SchemaSequence('sequence_group_projects_seq_id', optional=True), primary_key=True),
    Column('sequence_group_id', Integer, ForeignKey('sequence_group.id'), nullable=False),
    Column('project_id', Integer, ForeignKey('project.id'), nullable=False),
    mysql_engine='InnoDB',
    mysql_charset='utf8'
)

sequence_group_tag_sequence_group_table = Table('sequence_group_tag_sequence_group', metadata,
    Column('id', Integer, SchemaSequence('sequence_group_tag_sequence_group_seq_id', optional=True), primary_key=True),
    Column('sequence_group_id', Integer, ForeignKey('sequence_group.id'), nullable=False),
    Column('sequence_group_tag_id', Integer, ForeignKey('sequence_group_tag.id'), nullable=False),
    mysql_engine='InnoDB',
    mysql_charset='utf8'
)

class Sequence(Base):
    __tablename__ = "sequence"
    __table_args__ = {"mysql_engine": 'InnoDB', 'mysql_charset': 'utf8'}

    id = Column(Integer, SchemaSequence('sequence_seq_id', optional=True), primary_key=True)
    sequence = Column(String(200), nullable=False)
    strand = Column(String(1), nullable=False, default='+')
    folding_dg = Column(Float, nullable=True)
    tail_hits_12mer = Column(Integer, nullable=True)
    tail_hits_10mer = Column(Integer, nullable=True)
    component = orm.relation('SequenceGroupComponent', backref='sequence')

    @property
    def percent_gc(self):
        return 100*gc_content(self.sequence)

class SequenceGroup(Base):
    __tablename__ = "sequence_group"
    __table_args__ = {"mysql_engine": 'InnoDB', 'mysql_charset': 'utf8'}

    CHEMISTRY_TYPE_TAQMAN = 1
    CHEMISTRY_TYPE_SYBR   = 2

    TYPE_DESIGNED = 1
    TYPE_LOCATION = 2
    TYPE_SNP      = 3

    ASSAY_TYPE_CNV       = 1
    ASSAY_TYPE_RED       = 2
    ASSAY_TYPE_SNP       = 2
    ASSAY_TYPE_ABS       = 5
    ASSAY_TYPE_GEX       = 6

    STATUS_TYPE_UNTESTED  = 1
    STATUS_TYPE_VALIDATED = 2
    STATUS_TYPE_GOOD      = 3
    STATUS_TYPE_PREFERRED = 4
    STATUS_TYPE_POOR      = 5
    STATUS_TYPE_BORKED    = 11

    id = Column(Integer, SchemaSequence('sequence_group_seq_id', optional=True), primary_key=True)
    name = Column(Unicode(50), nullable=False)
    owner_id = Column(Integer, ForeignKey('person.id'), nullable=True)
    gene = Column(Unicode(50), nullable=True)
    kit_type = Column(Integer, nullable=False, default=0, doc="Experimental type of the assay")
    type = Column(Integer, nullable=True, doc="Structural type of the assay")
    chemistry_type = Column(Integer, nullable=False, default=1, doc="Chemistry Type")
    notes = Column(UnicodeText(), nullable=True)
    reference_source = Column(UnicodeText(), nullable=True)
    status = Column(Integer, nullable=False, default=0)
    snp_rsid = Column(String(50), nullable=True)
    location_chromosome = Column(String(32), nullable=True)
    location_base = Column(Integer, nullable=True)
    active = Column(Boolean, default=True)
    amplicon_length = Column(Integer, nullable=True)
    added = Column(DateTime(), default=now)
    deleted = Column(Boolean, default=False)
    analyzed = Column(Boolean, default=False)
    customer = Column(Boolean, default=False)
    slug = Column(String(40), nullable=True)
    approved_for_release = Column(Boolean, default=False)
    

    # could be an FK, but want to keep the job architecture agnostic of the DB (could be somewhere else...)
    pending_job_id = Column(Integer, nullable=True)
    forward_primers = orm.relation('SequenceGroupComponent', cascade='all, delete-orphan',
                                   primaryjoin="and_(SequenceGroup.id==SequenceGroupComponent.sequence_group_id, SequenceGroupComponent.role == 1)")
    reverse_primers = orm.relation('SequenceGroupComponent', cascade='all, delete-orphan',
                                   primaryjoin="and_(SequenceGroup.id==SequenceGroupComponent.sequence_group_id, SequenceGroupComponent.role == 2)")
    probes = orm.relation('SequenceGroupComponent', cascade='all, delete-orphan',
                                   primaryjoin="and_(SequenceGroup.id==SequenceGroupComponent.sequence_group_id, SequenceGroupComponent.role == 3)")
    projects = orm.relation('Project', secondary=sequence_group_project_table) # TODO: delete?
    tags = orm.relation('SequenceGroupTag', secondary=sequence_group_tag_sequence_group_table)
    amplicons = orm.relation('Amplicon', cascade='all, delete-orphan')
    transcripts = orm.relation('Transcript', cascade='all, delete-orphan')
    owner = orm.relation('Person')
    wells = orm.relation('QLBWellChannel', backref='sequence_group')
    conditions = orm.relation('SequenceGroupCondition', backref='sequence_group')

    @classmethod
    def kit_type_display_options(cls):
        return [(SequenceGroup.TYPE_DESIGNED, 'Known primers/probes'),
                (SequenceGroup.TYPE_LOCATION, 'Location known only'),
                (SequenceGroup.TYPE_SNP, 'SNP known only')]
    
    @property
    def kit_type_display(self):
        return dict(self.__class__.kit_type_display_options()).get(self.kit_type, '')
    
    @classmethod
    def chemistry_type_display_options(cls):
        return [(SequenceGroup.CHEMISTRY_TYPE_TAQMAN, "TaqMan (primers/probe)"),
                (SequenceGroup.CHEMISTRY_TYPE_SYBR, "SYBR (primers only)")]
    
    @property
    def chemistry_type_display(self):
        return dict(self.__class__.chemistry_type_display_options()).get(self.chemistry_type, '')
    
    @classmethod
    def assay_type_display_options(cls):
        return [('',''),
                (SequenceGroup.ASSAY_TYPE_ABS, 'Abs. Quant.'),
                (SequenceGroup.ASSAY_TYPE_CNV, 'CNV'),
                (SequenceGroup.ASSAY_TYPE_RED, 'RED/SNP'),
                (SequenceGroup.ASSAY_TYPE_GEX, 'Gene Exp.')]
    
    @property
    def assay_type_display(self):
        return dict(self.__class__.assay_type_display_options()).get(self.type, '')
    
    @classmethod
    def status_display_options(cls, include_blank=False):
        options = [(SequenceGroup.STATUS_TYPE_UNTESTED, 'Untested'),
                   (SequenceGroup.STATUS_TYPE_VALIDATED, 'Validated'),
                   (SequenceGroup.STATUS_TYPE_GOOD, 'Good'),
                   (SequenceGroup.STATUS_TYPE_PREFERRED, 'Preferred'),
                   (SequenceGroup.STATUS_TYPE_POOR, 'Poor'),
                   (SequenceGroup.STATUS_TYPE_BORKED, 'Does Not Work')]
        if include_blank:
            options = [('','')]+options
        return options
    
    @property
    def status_display(self):
        return dict(self.__class__.status_display_options()).get(self.status, '')

    @property
    def oligo_overlaps(self):
        """
        Warning: may cause additional DB queries.

        Returns overlap characteristics of all primer-probe
        combinations in the sequence.

        An overlap takes the form ((oligo1, oligo2): (maximal overlap, offsets))
        """
        overlaps = []
        combines = [(self.forward_primers, self.reverse_primers),
                    (self.forward_primers, self.probes),
                    (self.reverse_primers, self.probes)]
        # TODO: track probe-probe interaction?
        for oligos1, oligos2 in combines:
            for o1, o2 in product(oligos1 or [], oligos2 or []):
                overlap = self.__class__.maximal_overlap_seq(o1, o2)
                if overlap:
                    overlaps.append(((o1, o2), overlap))
        return overlaps

    @property
    def max_oligo_overlap(self):
        return sorted(self.oligo_overlaps, key=lambda tup: tup[1][0])[-1]

    @classmethod
    def maximal_overlap_seq(cls, component1, component2):
        if component1.sequence and component1.sequence.sequence \
           and component2.sequence and component2.sequence.sequence:
            return maximal_binding_seq(component1.sequence.sequence, component2.sequence.sequence)
        else:
            return None

    @property
    def is_taqman(self):
        return self.chemistry_type == self.__class__.CHEMISTRY_TYPE_TAQMAN

    @property
    def quencher_display(self):
        if self.chemistry_type == self.__class__.CHEMISTRY_TYPE_SYBR:
            return 'Eva'
        elif len(self.probes) == 0:
            return '?'
        elif len(self.probes) > 1:
            return 'Multi'
        else:
            return self.probes[0].quencher



class SequenceGroupComponent(Base):
    __tablename__ = "sequence_group_component"
    __table_args__ = {"mysql_engine": 'InnoDB', 'mysql_charset': 'utf8'}

    FORWARD_PRIMER = 1
    REVERSE_PRIMER = 2
    PROBE = 3

    id = Column(Integer, SchemaSequence('sequence_group_components_seq_id', optional=True), primary_key=True)
    sequence_group_id = Column(Integer, ForeignKey('sequence_group.id'), nullable=False)
    sequence_id = Column(Integer, ForeignKey('sequence.id'), nullable=True)
    role = Column(Integer, nullable=False, default=0) # come up with logic in object
    primary = Column(Boolean, nullable=False, default=True) # primary role in sequence group component
    order = Column(Integer, nullable=False, default=0)
    barcode_label = Column(String(20), nullable=True)
    dye = Column(String(16), nullable=True)
    quencher = Column(String(16), nullable=True)
    snp_allele = Column(String(50), nullable=True)
    note = Column(Unicode(255), nullable=True)
    tm = Column(Float, nullable=True)
    dg = Column(Float, nullable=True)
    sequence_group = orm.relation('SequenceGroup')

    @staticmethod
    def create_label(name, role, order, dye=None, quencher=None):
        if role == SequenceGroupComponent.FORWARD_PRIMER:
            return "%s_FP%d" % (name[:12], order+1)
        elif role == SequenceGroupComponent.REVERSE_PRIMER:
            return "%s_RP%d" % (name[:12], order+1)
        elif role == SequenceGroupComponent.PROBE:
            return "%s_P%s%s%s" % (name[:11], order+1, dye[0] if dye else '', quencher[0] if quencher else '')

class SequenceGroupTag(Base):
    __tablename__ = "sequence_group_tag"
    __table_args__ = {"mysql_engine": 'InnoDB', 'mysql_charset': 'utf8'}
    
    id = Column(Integer, SchemaSequence('sequence_group_tag_seq_id', optional=True), primary_key=True)
    name = Column(String(50), nullable=False, unique=True)
    notes = Column(Text)
    owner_id = Column(Integer, ForeignKey('person.id'), nullable=True)
    creation_date = Column(DateTime, default=now)
    sequence_groups = orm.relation('SequenceGroup', secondary=sequence_group_tag_sequence_group_table)
    owner = orm.relation('Person')


class SequenceGroupCondition(Base):
    __tablename__ = "sequence_group_operating_condition"
    __table_args__ = {"mysql_engine": 'InnoDB', 'mysql_charset': 'utf8'}

    STATUS_TYPE_UNKNOWN = 0
    STATUS_TYPE_GOOD    = 1
    STATUS_TYPE_FAIR    = 2
    STATUS_TYPE_POOR    = 3

    id = Column(Integer, SchemaSequence('sequence_group_condition_seq_id', optional=True), primary_key=True)
    sequence_group_id = Column(Integer, ForeignKey('sequence_group.id'), nullable=False)
    author_id = Column(Integer, ForeignKey('person.id'), nullable=True)
    plate_id = Column(Integer, ForeignKey('plate.id'), nullable=True)
    status = Column(Integer, nullable=False)
    optimal_temp = Column(String(50), nullable=True)
    custom_thermal_protocol = Column(Text, nullable=True)
    mmix_standard_status = Column(Integer, nullable=True)
    mmix_afree_status = Column(Integer, nullable=True)
    mmix_1step_status = Column(Integer, nullable=True)
    mmix_groove_status = Column(Integer, nullable=True)
    restriction_enzymes = Column(String(50), nullable=True)
    notes = Column(Text, nullable=True)
    wells = Column(Text, nullable=True)
    observer = orm.relation('Person')

    @classmethod
    def status_display_options(cls):
        return [(SequenceGroupCondition.STATUS_TYPE_UNKNOWN, 'Unknown'),
                (SequenceGroupCondition.STATUS_TYPE_GOOD, 'Good'),
                (SequenceGroupCondition.STATUS_TYPE_FAIR, 'Fair'),
                (SequenceGroupCondition.STATUS_TYPE_POOR, 'Poor')]
    
    # TODO: classmethod?
    def status_display(self, val):
        return dict(self.__class__.status_display_options()).get(val, '')


class Amplicon(Base):
    __tablename__ = "amplicon"
    __table_args__ = {"mysql_engine": 'InnoDB', 'mysql_charset': 'utf8'}

    id = Column(Integer, SchemaSequence('amplicon_seq_id', optional=True), primary_key=True)
    sequence_group_id = Column(Integer, ForeignKey('sequence_group.id'), nullable=False)
    sequence_fprimer_id = Column(Integer, ForeignKey('sequence.id'), nullable=True)
    sequence_rprimer_id = Column(Integer, ForeignKey('sequence.id'), nullable=True)
    sequence_probe_id = Column(Integer, ForeignKey('sequence.id'), nullable=True)
    primer_strand = Column(String(1), nullable=True)
    probe_pos = Column(Integer, nullable=True)
    probe_strand = Column(String(1), nullable=True) # in case probe not found/SYBR
    cached_sequences = orm.relation('AmpliconSequenceCache', backref='amplicon', cascade='all, delete-orphan')

class Transcript(Base):
    __tablename__ = "transcript"
    __table_args__ = {"mysql_engine": 'InnoDB', 'mysql_charset': 'utf8'}

    id = Column(Integer, SchemaSequence('transcript_seq_id', optional=True), primary_key=True)
    sequence_group_id = Column(Integer, ForeignKey('sequence_group.id'), nullable=False)
    sequence_fprimer_id = Column(Integer, ForeignKey('sequence.id'), nullable=True)
    sequence_rprimer_id = Column(Integer, ForeignKey('sequence.id'), nullable=True)
    sequence_probe_id = Column(Integer, ForeignKey('sequence.id'), nullable=True)

    # strand relative to transcript
    primer_strand = Column(String(1), nullable=True)
    probe_pos = Column(Integer, nullable=True)

    # strand relative to transcript
    probe_strand = Column(String(1), nullable=True)
    # include caching information because other fields don't really make sense without it
    # but make this a two-stage thing (initially nullable)
    folding_dg = Column(Float, nullable=True)
    ucsc_id = Column(String(25), nullable=True)
    gene = Column(String(25), nullable=True)
    # transcript region
    transcript_strand = Column(String(1), nullable=True)
    transcript_start_pos = Column(Integer, nullable=True)
    transcript_end_pos = Column(Integer, nullable=True)
    genomic_strand = Column(String(1), nullable=True)
    chromosome = Column(String(32), nullable=True)
    # for locality within chromosome/compatibility with amplicon_sequence_cache
    start_pos = Column(Integer, nullable=True)
    end_pos = Column(Integer, nullable=True)
    # I don't have a good handle on how many exons this thing could span
    exon_regions = Column(Text, nullable=True)

    # transcript positive strand, not genomic positive strand
    positive_sequence = Column(Text, nullable=True)
    negative_sequence = Column(Text, nullable=True)
    snps = orm.relation('SNPDBCache', backref='transcript', cascade='all, delete-orphan')
    forward_primer = orm.relation('Sequence', primaryjoin="Transcript.sequence_fprimer_id==Sequence.id")
    reverse_primer = orm.relation('Sequence', primaryjoin="Transcript.sequence_rprimer_id==Sequence.id")
    probe = orm.relation('Sequence', primaryjoin="Transcript.sequence_probe_id==Sequence.id")

    @property
    def exon_bounds(self):
        post_colon = self.exon_regions.split(':')[-1]
        bounds = post_colon.split(';')
        return [(int(start), int(end)) for start, end in [STRAND_RE.split(bound) for bound in bounds]]

    @property
    def percent_gc(self):
        return 100*gc_content(self.positive_sequence)


class AmpliconSequenceCache(Base):
    __tablename__ = "amplicon_sequence_cache"
    __table_args__ = {"mysql_engine": 'InnoDB', 'mysql_charset': 'utf8'}

    id = Column(Integer, SchemaSequence('amplicon_sequence_cache_seq_id', optional=True), primary_key=True)
    amplicon_id = Column(Integer, ForeignKey('amplicon.id'), nullable=False)
    genome = Column(String(32), nullable=False, default='hg19')
    chromosome = Column(String(32), nullable=False)
    start_pos = Column(Integer, nullable=False)
    end_pos = Column(Integer, nullable=False)
    seq_padding_pos5 = Column(Integer, nullable=False, default=0)
    seq_padding_pos3 = Column(Integer, nullable=False, default=0)
    positive_sequence = Column(Text)
    negative_sequence = Column(Text)
    folding_dg = Column(Float, nullable=True)
    snps = orm.relation('SNPDBCache', backref='sequence', cascade='all, delete-orphan')

    # copy from HG19AssayCache original impl
    @property
    def positive_amplicon(self):
        return self.cached_seq(0, 0, '+')
    
    @property
    def negative_amplicon(self):
        return self.cached_seq(0, 0, '-')
    
    @property
    def amplicon_length(self):
        return (self.end_pos - self.start_pos) + 1
    
    @property
    def percent_gc(self):
        return 100*gc_content(self.positive_amplicon)
    
    def padding_pos5(self, length, strand='+'):
        return self.cached_seq(length, -self.amplicon_length, strand)
    
    def padding_pos3(self, length, strand='+'):
        return self.cached_seq(-self.amplicon_length, length, strand)
    
    def cached_seq(self, padding_pos5, padding_pos3, strand='+'):
        """
        Returns the cached sequence in the positive strand direction.
        
        @param padding_pos5  The amount of padding (left) in the 5' end
                             on the positive strand
        @param padding_pos3  The amount of padding (right) on the 3' end
                             on the positive strand
        """
        # TODO unit test
        if padding_pos5 > self.seq_padding_pos5:
            padding_pos5 = self.seq_padding_pos5
        
        if padding_pos3 > self.seq_padding_pos3:
            padding_pos3 = self.seq_padding_pos3
        
        start_idx = self.seq_padding_pos5 - padding_pos5
        end_idx = -1*(self.seq_padding_pos3 - padding_pos3) or None # if 0, then None-- pass into idx
        
        if self.negative_sequence:
            seq = reverse_complement(self.negative_sequence)
        else:
            seq = self.positive_sequence
        
        substr = seq[start_idx:end_idx]
        if strand == '+':
            return substr
        else:
            return reverse_complement(substr)
    
    def snps_in_range(self, padding_pos5=0, padding_pos3=0):
        if padding_pos5 > self.seq_padding_pos5:
            padding_pos5 = self.seq_padding_pos5
        if padding_pos3 > self.seq_padding_pos3:
            padding_pos3 = self.seq_padding_pos3
        
        return [snp for snp in self.snps if (snp.chromStart >= self.start_pos-padding_pos5 and snp.chromStart <= self.end_pos+padding_pos3) or \
                                            (snp.chromEnd >= self.start_pos-padding_pos5 and snp.chromEnd <= self.end_pos+padding_pos3)]

class SNPDBCache(Base):
    __tablename__ = "snp_db_cache"
    __table_args__ = {"mysql_engine": 'InnoDB', 'mysql_charset': 'utf8'}

    id = Column(Integer, SchemaSequence('snp_db_cache_id', optional=True), primary_key=True)
    amplicon_sequence_cache_id = Column(Integer, ForeignKey('amplicon_sequence_cache.id'), nullable=False)
    transcript_id = Column(Integer, ForeignKey('transcript.id'), nullable=True)
    snpdb = Column(String(32), nullable=False, default='snp131')
    bin = Column(Integer)
    chrom = Column(String(31))
    chromStart = Column(Integer)
    chromEnd = Column(Integer)
    name = Column(String(15))
    score = Column(SmallInteger)
    strand = Column(MSEnum('+','-'))
    refNCBI = Column(Text)
    refUCSC = Column(Text)
    observed = Column(String(255))
    molType = Column(MSEnum('unknown','genomic','cDNA'))
    class_ = Column(MSEnum('unknown','single','in-del','het','microsatellite','named','mixed','mnp','insertion','deletion'))
    valid = Column(MSSet("'unknown'","'by-cluster'","'by-frequency'","'by-submitter'","'by-2hit-2allele'","'by-hapmap'","'by-1000genomes'"))
    avHet = Column(Float)
    avHetSE = Column(Float)
    func = Column(MSSet("'unknown'","'coding-synon'","'intron'","'coding-synonymy-unknown'","'near-gene-3'","'near-gene-5'","'nonsense'",
                        "'missense'","'frameshift'","'cds-indel'","'untranslated-3'","'untranslated-5'","'splice-3'","'splice-5'"))
    locType = Column(MSEnum('range','exact','between','rangeInsertion','rangeSubstitution','rangeDeletion'))
    weight = Column(Integer)
    exceptions = Column(MSSet("'RefAlleleMismatch'", "'RefAlleleRevComp'", "'DuplicateObserved'", "'MixedObserved'",
                              "'FlankMismatchGenomeLonger'", "'FlankMismatchGenomeEqual'", "'FlankMismatchGenomeShorter'",
                              "'NamedDeletionZeroSpan'", "'NamedInsertionNonzeroSpan'", "'SingleClassLongerSpan'",
                              "'SingleClassZeroSpan'", "'SingleClassTriAllelic'", "'SingleClassQuadAllelic'",
                              "'ObservedWrongFormat'", "'ObservedTooLong'", "'ObservedContainsIupac'",
                              "'ObservedMismatch'", "'MultipleAlignments'", "'NonIntegerChromCount'", "'AlleleFreqSumNot1'"), nullable=True)
    submitterCount = Column(Integer, nullable=True)
    submitters = Column(LONGBLOB, nullable=True)
    alleleFreqCount = Column(Integer, nullable=True)
    alleles = Column(LONGBLOB, nullable=True)
    alleleNs = Column(LONGBLOB, nullable=True)
    alleleFreqs = Column(LONGBLOB, nullable=True)
    bitfields = Column(MSSet("'clinically-assoc'", "'maf-5-some-pop'", "'maf-5-all-pops'", "'has-omim-omia'", "'microattr-tpa'",
                             "'submitted-by-lsdb'", "'genotype-conflict'", "'rs-cluster-nonoverlapping-alleles'", "'observed-mismatch'"), nullable=True)

