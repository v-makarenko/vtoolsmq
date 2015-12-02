"""
SHOULD BE DEPRECATED (on chopping block for deletion)
"""

from qtools.lib.bio import SimpleGenomeSequence, PCRSequence
# right to be in qtools.lib?
from qtools.model import Session, Assay, HG19AssayCache, SNP131AssayCache
from qtools.lib.dbservice.ucsc import SNP131Transformer
from qtools.lib.exception import ReturnWithCaveats
from qtools.lib.sequence import mutate_sequences, find_in_sequence
from qtools.lib.deltag import dg_seq
from qtools.lib.tm import tm_probe

# TODO unit test.
def sequences_snps_for_assay(config, assay, seq_source, snp_source, left_padding=0, right_padding=0, cache=True):
    sequences = []
    if not assay:
        return sequences
    
    if assay.cached_sequences:
        all_cached = True
        for seq in assay.cached_sequences:
            if not seq.cached(left_padding, right_padding):
                all_cached = False
                break
        if all_cached:
            for seq in assay.cached_sequences:
                amplicon = SimpleGenomeSequence(seq.chromosome, seq.start_pos, seq.end_pos, '+', seq.positive_amplicon)
                prefix = SimpleGenomeSequence(seq.chromosome, seq.start_pos-left_padding, seq.start_pos-1,
                                              '+', seq.padding_pos5(left_padding, '+'))
                suffix = SimpleGenomeSequence(seq.chromosome, seq.end_pos+1, seq.end_pos+right_padding, '+',
                                              seq.padding_pos3(right_padding, '+'))
                pseq = PCRSequence(amplicon, prefix, suffix)
                # TODO unify SNP object
                
                pseq.snps = [dict([(k, v) for k, v in snp.__dict__.items() if not k.startswith('_')]) for snp in seq.snps]
                for snp in pseq.snps:
                    snp['class'] = snp['class_']
                
                sequences.append(pseq)
        
            return sequences
                
    
    if assay.assay_type == Assay.TYPE_PRIMER:
        sequences = seq_source.sequences_for_primers(assay.primer_fwd, assay.primer_rev,
                                                     left_padding, right_padding)
    elif assay.assay_type == Assay.TYPE_LOCATION:
        sequence = seq_source.sequence_around_loc(assay.chromosome, assay.probe_pos, assay.amplicon_width,
                                                  left_padding, right_padding)
        sequences.append(sequence)
    elif assay.assay_type == Assay.TYPE_SNP:
        snps = snp_source.snps_by_rsid(assay.snp_rsid)
        # TODO: make SNP object so that access style is same as assay
        for snp in snps:
            if snp['refUCSC'] == '-': # deletion:
                sequences.append(seq_source.sequence_around_region(snp['chrom'][3:], snp['chromEnd'], snp['chromEnd'], assay.amplicon_width,
                                                               left_padding, right_padding))
            else:
                sequences.append(seq_source.sequence_around_region(snp['chrom'][3:], snp['chromStart']+1, snp['chromEnd'], assay.amplicon_width,
                                                               left_padding, right_padding))
    
    for seq in sequences:
        seq.snps = snp_source.snps_in_range(seq.chromosome, seq.start, seq.end)
    
    if cache:
        # TODO: library method? -- given PCR object, SNP dict?  or unify display objects
        # to and from their DB representation?
        assay.cached_sequences = []
        for seq in sequences:
            cached_seq = HG19AssayCache(chromosome = seq.chromosome,
                                        start_pos = seq.amplicon.start,
                                        end_pos = seq.amplicon.end,
                                        seq_padding_pos5 = left_padding,
                                        seq_padding_pos3 = right_padding,
                                        positive_sequence = seq.merged_positive_sequence.sequence)
            

            cached_seq.amplicon_dg = dg_seq(config, cached_seq.positive_amplicon)
            cached_seq.amplicon_tm = tm_probe(config, cached_seq.positive_amplicon)
            for snp in seq.snps:
                cached_seq.snps.append(SNP131AssayCache(bin=snp['bin'],
                                                        chrom=snp['chrom'],
                                                        chromStart=snp['chromStart'],
                                                        chromEnd=snp['chromEnd'],
                                                        name=snp['name'],
                                                        score=snp['score'],
                                                        strand=snp['strand'],
                                                        refNCBI=snp['refNCBI'],
                                                        refUCSC=snp['refUCSC'],
                                                        observed=snp['observed'],
                                                        molType=snp['molType'],
                                                        class_=snp['class'],
                                                        valid=snp['valid'],
                                                        avHet=snp['avHet'],
                                                        avHetSE=snp['avHetSE'],
                                                        func=snp['func'],
                                                        locType=snp['locType'],
                                                        weight=snp['weight']))
            assay.cached_sequences.append(cached_seq)
        
        Session.commit()
    
    return sequences

def set_amplicon_snps(sequences):
    """
    TODO: more consistent data model for sequences and snps, it's
    all jumbled between PCRSequence, SimpleGenomeSequence and
    snp dict (analysis) and HG19AssayCache, SNP131AssayCache,
    Assay (storage).  Need one DB format and one analysis
    format.
    
    In: PCRSequences with snps
    Out: sequences get amplicon_snps attribute, comprising o
    """
    for seq in sequences:
        amplicon_snps = []
        for snp in seq.snps:
            if (snp['chromStart'] >= seq.amplicon.start and snp['chromStart'] <= seq.amplicon.end) or \
               (snp['chromEnd'] >= seq.amplicon.start and snp['chromEnd'] <= seq.amplicon.end):
               amplicon_snps.append(snp)
        
        seq.amplicon_snps = amplicon_snps

def cached_assay_cut_by_enzyme(assay, enzyme):
    """
    Check the cached information to see whether the enzyme cuts the amplicon.
    If the sequence and SNP information is not cached, return False.
    Otherwise, return whether or not the enzyme cuts the assay's amplicon.

    More conditions:
    
    * The cut site must be wholly contained within the amplicon (no overhang)
    * All the sequences that match the assay must have a cut site within
      the amplicon.
    
    :param assay: An Assay DB object.
    :param enzyme: An Enzyme DB object.
    :return: False if the assay's sequence is not cached; otherwise, whether
             the enzyme is theoretically guaranteed to cut all sequences
             corresponding to the assay.
    """
    if not assay.cached_sequences:
        return False
    
    cuts_all = False
    max_cuts = 10000000
    for seq in assay.cached_sequences:
        amplicon = SimpleGenomeSequence(seq.chromosome, seq.start_pos, seq.end_pos, '+', seq.positive_amplicon)
        try:
            snps = [snp for snp in seq.snps if snp.chromEnd >= seq.start_pos and snp.chromStart <= seq.end_pos]
            mutated_sequences = mutate_sequences(CachedSNP131Transformer(),
                                                 amplicon,
                                                 snps,
                                                 len(enzyme.cutseq))
        except ReturnWithCaveats, e:
            mutated_sequences = e.return_value
        # could not read for some other reason
        except Exception, e:
            return 0
        
        for mseq in mutated_sequences:
            cutsites = find_in_sequence(enzyme.cutseq, mseq)
            if not cutsites:
                return 0
            
            within = [(start >= 0, end <= len(mseq.sequence)) for (start, end, strand) in cutsites]
            all_within = [all(w) for w in within]
            if not any(all_within):
                # ensure that the entire cut site is within the amplicon (offset from both
                # positive and negative strand is greater than zero)
                #
                # if there is no cutsite within the bounds of the amplicon, no cutsite for this
                # SNP (or original) sequence
                return 0
            
            cuts = len([a for a in all_within if a])
            if cuts < max_cuts:
                max_cuts = cuts
    
    return max_cuts

class CachedSNP131Transformer(object):
    """
    Adapter for SNP131Transformer to use SNP131AssayCache objects as mutations.
    """
    def __init__(self):
        self.virtual_super = SNP131Transformer()
    
    @classmethod
    def transform_mutation(cls, mutation):
        mdict = mutation.__dict__
        mdict['class'] = mdict['class_']
        return mdict
    
    def sequence_variant(self, sequence, mutation, strand='+'):
        transformed_mutation = self.__class__.transform_mutation(mutation)
        return self.virtual_super.sequence_variant(sequence, transformed_mutation, strand=strand)
    
    # this is a hack, because sequence_variant is going to be busted.
    def sequence_variants(self, sequence, mutations=None, combination_width=0, strand='+'):
        if mutations is None:
            transformed_mutations = None
        else:
            transformed_mutations = [self.__class__.transform_mutation(mut) for mut in mutations]
        
        return self.virtual_super.sequence_variants(sequence, transformed_mutations, combination_width=combination_width, strand=strand)