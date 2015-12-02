from qtools.constants.pcr import MAX_CACHE_PADDING
from qtools.lib.bio import SimpleGenomeSequence, PCRSequence
from qtools.model.sequence import Amplicon, AmpliconSequenceCache, Transcript
from qtools.model.ucsc import PCRGenePrimerMatchSequence

def create_amplicons_from_pcr_sequences(sequence_group,
                                        forward_primer=None,
                                        reverse_primer=None,
                                        probes=None,
                                        pcr_sequences=None):
    db_amplicons = []
    if pcr_sequences:
        db_amplicon = Amplicon(sequence_group_id = sequence_group.id)
        if forward_primer and reverse_primer:
            db_amplicon.sequence_fprimer_id = forward_primer.id
            db_amplicon.sequence_rprimer_id = reverse_primer.id
        
        # TODO: move this into qtools.model.sequence?
        # may be a little dependent on return struct from UCSC
        
        # find first probe seq that hits, and first probe that hits -- make that
        # the probe_pos and probe_id (for now)
        strand_found = False
        probe_found  = False
        for seq in pcr_sequences:
            amplicon = seq.amplicon
            plus = amplicon.positive_strand_sequence
            minus = amplicon.negative_strand_sequence
            
            if forward_primer and reverse_primer:
                if not strand_found:
                    if plus.startswith(forward_primer.sequence):
                        db_amplicon.primer_strand = '+'
                        strand_found              = True
                    elif minus.startswith(reverse_primer.sequence):
                        db_amplicon.primer_strand = '-'
                        strand_found              = True
            
            if probes:
                if not probe_found:
                    for probe in probes:
                        if probe.sequence in plus:
                            db_amplicon.sequence_probe_id = probe.id
                            db_amplicon.probe_pos         = plus.index(probe.sequence)
                            db_amplicon.probe_strand      = '+'
                            probe_found = True
                            break
                        elif probe.sequence in minus:
                            db_amplicon.sequence_probe_id = probe.id
                            db_amplicon.probe_pos         = minus.index(probe.sequence)
                            db_amplicon.probe_strand      = '-'
                            probe_found = True
                            break
            # TODO if not probes, define probe pos as length/2?
            
            cached_seq = AmpliconSequenceCache(start_pos  = amplicon.start,
                                               end_pos    = amplicon.end,
                                               chromosome = amplicon.chromosome,
                                               seq_padding_pos5 = len(seq.left_padding) if seq.left_padding else 0,
                                               seq_padding_pos3 = len(seq.right_padding) if seq.right_padding else 0,
                                               positive_sequence = seq.merged_positive_sequence.sequence,
                                               negative_sequence = seq.merged_negative_sequence.sequence)
            
            # add job for snps on save (after save, right?)
            if not db_amplicon.cached_sequences:
                db_amplicon.cached_sequences = []
            db_amplicon.cached_sequences.append(cached_seq)
        
        # TODO: does this belong inside this statement?
        if not sequence_group.amplicons:
            sequence_group.amplicons = []
        # this may have been a bug... watch for it...
        sequence_group.amplicons.append(db_amplicon)
        
        db_amplicons.append(db_amplicon)
    
    return db_amplicons

def pcr_sequences_for_amplicon(amplicon, padding_pos5=0, padding_pos3=0, include_snps=False):
    """
    Returns the PCRSequence objects representing the specified amplicon.
    If include_snps=True, each object will include an attribute 'snps', which will
    include a list of SNP dictionaries (like the SNPDBCache object, only
    SQLAlchemy-agnostic, and 'class' in place of 'class_')

    :param padding_pos5: The amount of padding to prefix the amplicon.  Max MAX_CACHE_PADDING.
    :param padding_pos3: The amount of padding to suffix the amplicon.  Max MAX_CACHE_PADDING.
    :param include_snps: Whether to include the snps attribute on each amplicon.
    """
    if padding_pos5 < 0 or padding_pos5 > MAX_CACHE_PADDING:
        raise ValueError, "Illegal padding value: %s" % padding_pos5
    
    if padding_pos3 < 0 or padding_pos3 > MAX_CACHE_PADDING:
        raise ValueError, "Illegal padding value: %s" % padding_pos3
    
    pseqs = []
    for seq in amplicon.cached_sequences:
        main     = SimpleGenomeSequence(seq.chromosome, seq.start_pos, seq.end_pos, '+', seq.positive_amplicon)

        # this could be of a different length than requested
        padding_pos5_seq = seq.padding_pos5(padding_pos5, '+')
        padding_pos3_seq = seq.padding_pos3(padding_pos3, '+')

        prefix   = SimpleGenomeSequence(seq.chromosome,
                                        seq.start_pos-len(padding_pos5_seq),
                                        seq.start_pos-1,
                                        '+', padding_pos5_seq)
        suffix   = SimpleGenomeSequence(seq.chromosome,
                                        seq.end_pos+1,
                                        seq.end_pos+len(padding_pos3_seq),
                                        '+', padding_pos3_seq)
        pseq     = PCRSequence(main, prefix, suffix)

        if include_snps:
            snps = seq.snps_in_range(padding_pos5=len(padding_pos5_seq), padding_pos3=len(padding_pos3_seq))
            pseq.snps = [dict([(k, v) for k, v in snp.__dict__.items() if not k.startswith('_')]) for snp in snps]
            for snp in pseq.snps:
                snp['class'] = snp['class_']
        
        pseqs.append(pseq)
    return pseqs

def pcr_sequences_for_group(sequence_group, padding_pos5=0, padding_pos3=0, include_snps=False):
    """
    Returns a list of tuples (amplicon, [sequences]) of PCRSequence objects representing
    each amplicons in the specified sequence group.  If include_snps=True, each
    object will include an attribute 'snps', which will
    include a list of SNP dictionaries (like the SNPDBCache object, only
    SQLAlchemy-agnostic, and 'class' in place of 'class_')

    :param padding_pos5: The amount of padding to prefix the amplicon.  Max MAX_CACHE_PADDING.
    :param padding_pos3: The amount of padding to suffix the amplicon.  Max MAX_CACHE_PADDING.
    :param include_snps: Whether to include the snps attribute on each amplicon.
    """
    amp_tuples = []
    for amp in sequence_group.amplicons:
        pseqs = pcr_sequences_for_amplicon(amp, padding_pos5=padding_pos5,
                                           padding_pos3=padding_pos3, include_snps=include_snps)
        
        amp_tuples.append((amp, pseqs))
    
    return amp_tuples

def pcr_sequences_snps_for_group(sequence_group, padding_pos5=0, padding_pos3=0):
    """
    Returns the PCRSequence objects representing the amplicons in the specified
    sequence group.  Each object will include an attribute 'snps', which will
    include a list of SNP dictionaries (like the SNPDBCache object, only
    SQLAlchemy-agnostic, and 'class' in place of 'class_')

    :param padding_pos5: The amount of padding to prefix the amplicon.  Max MAX_CACHE_PADDING.
    :param padding_pos3: The amount of padding to suffix the amplicon.  Max 3000.
    """
    return pcr_sequences_for_group(sequence_group, padding_pos5=padding_pos5, padding_pos3=padding_pos3, include_snps=True)


def create_db_transcripts_from_pcr_transcripts(sequence_group,
                                               forward_primer,
                                               reverse_primer,
                                               probes=None,
                                               pcr_gene_sequences=None):
    """
    Creates Transcript model objects from the annotated exon sequences returned
    from the UCSC PCR web service proxy.

    :param sequence_group: The SequenceGroup to attach the Transcript to.
    :param forward_primer: The forward primer Sequence to this transcript.
    :param reverse_primer: The reverse primer Sequence to this transcript.
    :param probe: A TaqMan probe for this transcript.
    :param pcr_gene_sequences: The annoated exon sequences to convert.
    """
    db_transcripts = []
    if pcr_gene_sequences:
        # one to one relation between transcript and gene sequence
        for seq in pcr_gene_sequences:
            transcript = Transcript(sequence_group_id=sequence_group.id,
                                    sequence_fprimer_id=forward_primer.id,
                                    sequence_rprimer_id=reverse_primer.id,
                                    ucsc_id=seq.ucsc_id,
                                    gene=seq.gene,
                                    transcript_strand=seq.strand,
                                    transcript_start_pos=seq.start,
                                    transcript_end_pos=seq.end,
                                    chromosome=seq.chromosome,
                                    start_pos=seq.genomic_start,
                                    end_pos=seq.genomic_end,
                                    exon_regions=seq.exon_span_string,
                                    positive_sequence=seq.positive_strand_sequence,
                                    negative_sequence=seq.negative_strand_sequence,
                                    genomic_strand=seq.genomic_strand)
            # TODO exon regions, primer/probe strand

            plus = seq.positive_strand_sequence
            minus = seq.negative_strand_sequence

            # hmm.. this currently assumes perfect matching.
            if plus.startswith(forward_primer.sequence):
                transcript.primer_strand = '+'
            elif minus.startswith(reverse_primer.sequence):
                transcript.primer_strand = '-'

            if probes is not None:
                for probe in probes:
                    if probe.sequence in plus:
                        transcript.sequence_probe_id = probe.id
                        transcript.probe_pos         = plus.index(probe.sequence)
                        transcript.probe_strand      = '+'
                        break
                    elif probe.sequence in minus:
                        transcript.sequence_probe_id = probe.id
                        transcript.probe_pos         = minus.index(probe.sequence)
                        transcript.probe_strand      = '-'
                        break

            db_transcripts.append(transcript)

    return db_transcripts

# TODO: are these necessary, or is the DB object sufficient?
def pcr_gene_sequence_for_transcript(transcript, include_snps=False):
    """
    Returns the PCRGeneSequence objects representing the specified amplicon.
    If include_snps=True, each object will include an attribute 'snps', which will
    include a list of SNP dictionaries (like the SNPDBCache object, only SQLAlchemy-agnostic,
    and 'class' in the place of 'class_')
    """
    pgseq = PCRGenePrimerMatchSequence(transcript.forward_primer.sequence,
                                       transcript.reverse_primer.sequence,
                                       transcript.ucsc_id,
                                       transcript.gene,
                                       transcript.transcript_start_pos,
                                       transcript.transcript_end_pos,
                                       transcript.transcript_strand,
                                       transcript.negative_sequence if transcript.transcript_strand == '-' else transcript.positive_sequence)
    pgseq.exon_spans = transcript.exon_bounds
    pgseq.genomic_strand = transcript.genomic_strand
    pgseq.chromosome = transcript.chromosome
    if include_snps:
        pgseq.snps = [dict([(k, v) for k, v in snp.__dict__.items() if not k.startswith('_')]) for snp in transcript.snps]
        for snp in pgseq.snps:
            snp['class'] = snp['class_']
            del snp['class_']

    return pgseq

def transcript_sequences_for_group(sequence_group, include_snps=False):
    """
    Returns a list of PCRGenePrimerMatchSequence objects representing
    transcripts for the specified sequence group.  If include_snps=True, each
    object will include an attribute 'snps', which will
    include a list of SNP dictionaries (like the SNPDBCache object, only
    SQLAlchemy-agnostic, and 'class' in place of 'class_')

    :param include_snps: Whether to include the snps attribute on each amplicon.
    """
    return [pcr_gene_sequence_for_transcript(t, include_snps=include_snps) for t in sequence_group.transcripts]

def transcript_sequences_snps_for_group(sequence_group):
    """
    Returns the PCRSequence objects representing the amplicons in the specified
    sequence group.  Each object will include an attribute 'snps', which will
    include a list of SNP dictionaries (like the SNPDBCache object, only
    SQLAlchemy-agnostic, and 'class' in place of 'class_')

    :param padding_pos5: The amount of padding to prefix the amplicon.  Max MAX_CACHE_PADDING.
    :param padding_pos3: The amount of padding to suffix the amplicon.  Max 3000.
    """
    return transcript_sequences_for_group(sequence_group, include_snps=True)
