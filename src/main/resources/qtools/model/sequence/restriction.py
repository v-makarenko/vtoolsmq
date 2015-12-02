from qtools.lib.bio import SimpleGenomeSequence
from qtools.lib.dbservice.ucsc import SNP131Transformer
from qtools.lib.exception import ReturnWithCaveats
from qtools.lib.sequence import mutate_sequences, find_in_sequence

def sequence_group_min_cuts_by_enzyme(sequence_group, enzyme):
    """
    Returns the minimum number of cuts in the amplicons defined within
    the specified sequence group.  If 0, it is not guaranteed that the
    specified enzyme will always cut the amplicon defined by the primers.
    """
    min_cuts = 10000000
    if not sequence_group.amplicons:
        return 0
    
    for a in sequence_group.amplicons:
        cuts = amplicon_min_cuts_by_enzyme(a, enzyme)
        if cuts < min_cuts:
            min_cuts = cuts
        if cuts == 0:
            break
    
    return min_cuts

def amplicon_min_cuts_by_enzyme(amplicon, enzyme):
    """
    Check the amplicon and associated records to see whether the enzyme cuts the amplicon.
    Return the minimum number of cuts that the specified enzyme makes on
    the specified amplicon (which may map to multiple genomic sequences)

    More conditions:
    
    * The cut site must be wholly contained within the amplicon (no overhang)
    * All the sequences that match the assay must have a cut site within
      the amplicon.
    
    :param assay: An Amplicon DB object.
    :param enzyme: An Enzyme DB object.
    :return: False if the assay's sequence is not cached; otherwise, whether
             the enzyme is theoretically guaranteed to cut all sequences
             corresponding to the assay.
    """
    pseqs = []
    if not amplicon.cached_sequences:
        return False
    
    max_cuts = 10000000

    for seq in amplicon.cached_sequences:
        amp = SimpleGenomeSequence(seq.chromosome, seq.start_pos, seq.end_pos, '+', seq.positive_amplicon)
        try:
            snps = seq.snps_in_range(padding_pos5=0, padding_pos3=0)
            mutated_sequences = mutate_sequences(SNPDBCacheTransformer(),
                                                 amp,
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

class SNPDBCacheTransformer(object):
    """
    Adapter for SNP131Transformer to use SNPDBCache objects as mutations.
    """
    def __init__(self):
        self.virtual_super = SNP131Transformer()
    
    @classmethod
    def transform_mutation(cls, mutation):
        mdict = mutation.__dict_
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