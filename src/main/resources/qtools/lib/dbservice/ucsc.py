"""
Methods for scraping and computing information from the SNPDB
database hosted at UCSC.
"""
from sqlalchemy import MetaData, schema
from sqlalchemy.engine import create_engine
from sqlalchemy.exc import OperationalError
from sqlalchemy.orm import scoped_session, sessionmaker
from sqlalchemy.sql import select, and_, or_

from qtools.lib.bio import reverse_complement, base_regexp_expand, TransformedGenomeSequence
from qtools.lib.datasource import SNPDataSource, MutationTransformer, UnknownMutationError, UnhandledMutationWarning
from qtools.lib.exception import ReturnWithCaveats

import operator


def bins(chromNumber):
    """
    Return the hierarchical bin numbers that a feature at the specified
    chromosome may be stored in.

    Binning source: http://genome.cshlp.org/content/12/6/996.full.pdf+html
    *except* Paper claims 1-based bins, bins appear to be 0-based.
    """
    # I could do bit shifting like the Ruby impl but whatever, this code is easier to read
    kb = 1024
    mb = kb**2

    bin_levels_offsets = ((512*mb, 0),
                          (64*mb, 1),
                          (8*mb, 8+1),
                          (1*mb, 64+8+1),
                          (128*kb, 512+64+8+1))

    if chromNumber > 512*mb:
        raise ValueError, "Number too large for bin: %s" % chromNumber
    elif chromNumber < 1:
        raise ValueError, "Number too small for bin: %s" % chromNumber
    
    member_bins = []
    for bin, offset in bin_levels_offsets:
        divisor, rem = divmod(chromNumber, bin)
        member_bins.append(divisor+offset)
    
    return member_bins

def bin_ranges(chromStart, chromEnd):
    if chromStart > chromEnd:
        # just key off chromStart (likely a SNP deletion)
        chromEnd = chromStart
    
    start_bins = bins(chromStart)
    end_bins = bins(chromEnd)

    range_bins = []
    for start_bin, end_bin in zip(start_bins, end_bins):
        range_bins.extend([i for i in range(start_bin, end_bin+1)])
    
    return sorted(list(set(range_bins)))

class HG19Source(object):
    """
    Establishes a connection to query against the hg19 database on
    UCSC's public mysql server.
    """
    def __init__(self, engine=None, snp_table='snp131', gene_table='knownGene'):
        self._engine = engine
        self._snp_table = None
        self._gene_table = None
        self._snp_db_table = snp_table
        self._gene_db_table = gene_table
        if not self._engine:
            self.engine_url = 'mysql://genomep:password@genome-mysql.cse.ucsc.edu/hg19'
    
    @property
    def engine(self):
        if not self._engine:
            self._engine = create_engine(self.engine_url)
            
        return self._engine
    
    def execute_statement(self, stmt, max_tries=5):
        for i in range(max_tries):
            try:
                result = self.engine.execute(stmt)
                return result
            except Exception, e:
                if e.__class__.__name__.find('OperationalError') != 1:
                    # rebuild engine?
                    self._engine = create_engine(self.engine_url)
                else:
                    raise e
        raise OperationalError, "Could not connect to SNP database after %s tries" % max_tries
    
    @property
    def snp_table(self):
        if self._snp_table is None:
            metadata = MetaData()
            metadata.bind = self.engine
            self._snp_table = schema.Table(self._snp_db_table, metadata, autoload=True)
        
        return self._snp_table

    @property
    def gene_table(self):
        if self._gene_table is None:
            metadata = MetaData()
            metadata.bind = self.engine
            self._gene_table = schema.Table(self._gene_db_table, metadata, autoload=True)

    def snps_by_rsid(self, rsid):
        """
        Returns snp rows for the snp at the specified id, or None
        if none exist.
        """
        table = self.snp_table
        cols = table.c
        s = select([table], cols.name==rsid)

        # executing by the engine closes the connection by default
        result = self.execute_statement(s)
        rows = result.fetchall()
        if(len(rows) == 0):
            return None
        return rows

    def snps_in_range(self, chrom, start, end):
        """
        Returns all the snps that are between the specified
        endpoints.  This maps directly onto the genome table,
        so start is interpreted as 'chromStart'.  In reality,
        the 'chromStart' can be interpreted as the gap before
        the base at position (1-based) chromStart+1.
    
        TODO: write better docs here
        """
        table = self.snp_table
        cols = table.c
        chrom_bins = bin_ranges(start, end)
        s = select([table], and_(cols.chrom=='chr%s' % chrom,
                                 cols.bin.in_(chrom_bins),
                                 or_(cols.chromStart.between(start, end),
                                     cols.chromEnd.between(start, end))))
        result = self.execute_statement(s)
        snps = result.fetchall()
        return snps

    def snps_in_chrom_ranges(self, chrom, ranges):
        table = self.snp_table
        cols = table.c
        range_bins = [bin_ranges(start, end) for start, end in ranges]
        range_stmt = [and_(cols.bin.in_(bin),
                           or_(cols.chromStart.between(start, end),
                               cols.chromEnd.between(start, end))) for bin, (start, end) in zip(range_bins, ranges)]
        s = select([table], and_(cols.chrom=='chr%s' % chrom,
                                 or_(*range_stmt)))
        result = self.execute_statement(s)
        snps = result.fetchall()
        return snps

    def known_gene_info(self, name):
        table = self.gene_table
        cols = table.c
        s = select([table], cols.name.like('%s%%' % name))
        result = self.execute_statement(s)
        genes = result.fetchall()
        if len(genes) > 1: 
            raise ValueError, "Ambiguous gene name: %s" % name
        elif not genes:
            return None
        else:
            return genes[0]
    
class SNP131Transformer(MutationTransformer):
    """
    snp131-specific mutation transformer.
    
    """
    def sequence_variant(self, sequence, mutation, strand='+'):
        """
        Return the possible mutation(s) in the sequence due to
        the sequence.  For now, return the original sequence.
        # TODO: probably not return the original sequence
        """
        # first step: get positive string, standardizing so it's
        # easier for me to think about
        if sequence.strand == '-':
            seq = sequence.reverse_complement()
        else:
            seq = sequence
        
        if mutation['observed'] == 'lengthTooLong':
            #raise UnknownMutationError, "Could not read the variants for %s SNP %s at chr%s:%s-%s" % (mutation['class'], mutation['name'], mutation['chrom'], mutation['chromStart'], mutation['chromEnd'])
            sequences = []
            dup = self.__class__.duplicate(sequence)
            dup2 = self.__class__.duplicate(sequence, name=mutation['name'])

            xform = TransformedGenomeSequence.replace(dup2, mutation['chromStart'], mutation['chromEnd'],
                '?'*(mutation['chromEnd']-mutation['chromStart']+1))
            sequences.append(dup)
            sequences.append(xform)

        else:
            klass = mutation['class'].lower().replace('-','')
            sequences = getattr(self.__class__, '_%s_sequence_variant' % klass, self.__class__._unknown_variant)(seq, mutation)
        
        if strand == '-':
            return [reverse_complement(s) for s in sequences]
        else:
            return sequences
    
    @classmethod
    def _unknown_variant(cls, sequence, mutation):
        raise UnhandledMutationWarning, "Do not know how to process SNP of type %s" % mutation['class']
    
    @classmethod
    def duplicate(cls, sequence, name=None):
        return TransformedGenomeSequence.from_sequence(sequence, name=name)
        
    @classmethod
    def _observed(cls, observed):
        """
        Returns observed bases, excluding deletions.
        
        @param observed The observed column from the snp table row.
                        Assumes format '[-ACTG][/ACTG]*'
        """
        return [base for base in observed.split('/') if base != '-']
    
    @classmethod
    def _observed_complement(cls, observed):
        """
        Returns the reverse complement of observed bases, excluding deletions.
        
        @param observed The observed column from the snp table row.
                        Assumes format '[-ACTG][/ACTG]*'
        """
        return [reverse_complement(base) for base in cls._observed(observed)]
    
    @classmethod
    def _named_sequence_variant(cls, sequence, mutation):
        raise UnhandledMutationWarning, "SNP %s %s present at chr%s:%s-%s" % (mutation['name'], mutation['observed'], mutation['chrom'], mutation['chromStart'], mutation['chromEnd'])
    
    @classmethod
    def _het_sequence_variant(cls, sequence, mutation):
        raise UnhandledMutationWarning, "SNP het %s present at chr%s:%s-%s" % (mutation['name'], mutation['chrom'], mutation['chromStart'], mutation['chromEnd'])
    
    @classmethod
    def _microsatellite_sequence_variant(cls, sequence, mutation):
        raise UnhandledMutationWarning, "Microsatellite %s present at chr%s:%s-%s" % (mutation['name'], mutation['chrom'], mutation['chromStart'], mutation['chromEnd'])
        
    @classmethod
    def _single_sequence_variant(cls, sequence, mutation):
        """
        @param seq positive-stranded sequence
        @param mutation row
        """
        sequences = []
        if mutation['strand'] == '+':
            bases = cls._observed(mutation['observed'])
        else:
            bases = cls._observed_complement(mutation['observed'])
        
        for base in bases:
            newseq = cls.duplicate(sequence, mutation['name'])
            newseq.single(mutation['chromEnd'], base)
            sequences.append(newseq)
        
        return sequences
    
    @classmethod
    def _deletion_sequence_variant(cls, sequence, mutation):
        """
        @param seq positive-strand sequence
        @param mutation deletion row
        """
        sequences = (cls.duplicate(sequence),
                     cls.duplicate(sequence, mutation['name']).delete(mutation['chromStart']+1, mutation['chromEnd']))
                     
        return sequences
    
    @classmethod
    def _insertion_sequence_variant(cls, sequence, mutation):
        """
        @param seq positive-strand sequence
        @param mutation insertion row
        """
        if mutation['strand'] == '+':
            base = cls._observed(mutation['observed'])[0]
        else:
            base = cls._observed_complement(mutation['observed'])[0]
        
        sequences = (cls.duplicate(sequence),
                     cls.duplicate(sequence, mutation['name']).insert(mutation['chromEnd'], base))
        
        return sequences
    
    @classmethod
    def _indel_sequence_variant(cls, sequence, mutation):
        """
        
        """
        offset = mutation['chromStart']+1 - sequence.start
        
        remainder = mutation['chromEnd']+1 - sequence.start
        if mutation['strand'] == '+':
            base = cls._observed(mutation['observed'])[0]
        else:
            base = cls._observed_complement(mutation['observed'])[0]
        
        sequences = (cls.duplicate(sequence),
                     cls.duplicate(sequence, mutation['name']).replace(mutation['chromStart']+1, mutation['chromEnd'], base),
                     cls.duplicate(sequence, mutation['name']).delete(mutation['chromStart']+1, mutation['chromEnd']))
        
        return sequences
    
    @classmethod
    def _mixed_sequence_variant(cls, sequence, mutation):
        """
        """
        if mutation['strand'] == '+':
            bases = cls._observed(mutation['observed'])
        else:
            bases = cls._observed_complement(mutation['observed'])
        
        if mutation['refUCSC'] == '-':
            # there is an insertion
            sequences = [cls.duplicate(sequence)]
            sequences.extend([cls.duplicate(sequence, mutation['name']).insert(mutation['chromEnd'], base) for base in bases])
        else:
            # there is a base pair already
            sequences = []
            if '-' in mutation['observed']:
                sequences.append(cls.duplicate(sequence, mutation['name']).delete(mutation['chromStart']+1, mutation['chromEnd']))
            sequences.extend([cls.duplicate(sequence, mutation['name']).replace(mutation['chromStart']+1, mutation['chromEnd'], base) for base in bases])
        
        return tuple(sequences)
    
    @classmethod
    def _mnp_sequence_variant(cls, sequence, mutation):
        # mixed algorithm should work on mnp, since mnp's seem
        # to be subset of deletion type mixed w/o the deletion possibility
        #
        # (subtlety: the internals of all the variant methods are that
        # they take the prefix and suffix of the mutation and vary the range
        # at the mutation location-- [:chromStart][*][chromEnd:]. The values
        # of * for a mixed mutation are '-', [ATCG]*.  The values of * for
        # a MNP mutation are [ATCG]*.  The original value can still be
        # blank (mixed handles that case as well, since the 'bases' added
        # do not include the empty string)
        #
        # To summarize, the only reason this works is because of the
        # internal implementation of _mixed_sequence_variant; it may need
        # to be split down the line if we run into more edge cases.
        #
        # FOR EXAMPLE: It is already known that if the MNP is on the edge,
        # the entire base allele will be returned.  For MNPs, it may only be
        # necessary to return a subset of the alleles.
        return cls._mixed_sequence_variant(sequence, mutation)
    
    def sequence_variants(self, sequence, mutations=None, combination_width=0, strand='+'):
        """
        For now, issue a warning if SNPs overlap; just return all the
        permutations generating by activating SNPs one at a time.  Will fill in
        overlapping functionality later, as needed (will throw a warning)
        """
        if mutations is None or len(mutations) == 0:
            return [sequence]
        
        mutations = sorted(mutations, key=operator.itemgetter('chromStart'))
        current = mutations[0]
        overlapping = False
        unknown_msgs = []
        for mutation in mutations[1:]:
            # overlapping case-- chrom start guaranteed ascending
            if mutation['chromEnd'] <= current['chromEnd']:
                overlapping = True
                break
            elif mutation['chromStart'] <= current['chromEnd']+combination_width:
                overlapping = True
                break
        
        # just permute the original sequence among all the mutations.
        sequences = []
        for mutation in mutations:
            try:
                sequences.extend(self.sequence_variant(sequence, mutation, strand))
            except UnhandledMutationWarning, e:
                unknown_msgs.append(e.message)
        
        caveats = {}
        if overlapping:
            caveats['snp_overlapping'] = 'Overlapping/nearby SNPs detected; not all possible combinations generated.'
        if unknown_msgs:
            caveats['snp_processing'] = unknown_msgs
        
        if caveats:
            raise ReturnWithCaveats(caveats, sequences)
        else:
            return sequences

