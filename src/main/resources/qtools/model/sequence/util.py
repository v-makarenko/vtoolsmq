"""
qtools.model.sequence.util

Functions for creating trees or manipulating groups of sequence models.
"""
from qtools.model import Session
from qtools.model.sequence import SequenceGroup, Amplicon, SNPDBCache

def sequence_group_unlink_sequences(sequence_group):
    """
    If a sequence group changes, destroy all the original
    sequences, all amplicons, and associated SNPs.

    Does not commit.
    """
    for a in sequence_group.amplicons:
        for cs in a.cached_sequences:
            for snp in cs.snps:
                Session.delete(snp)
            cs.snps = []
            Session.delete(cs)
        a.cached_sequences = []
        Session.delete(a)
    sequence_group.amplicons = []

    for t in sequence_group.transcripts:
        for snp in t.snps:
            Session.delete(snp)
        t.snps = []
        Session.delete(t)
    sequence_group.transcripts = []

    for fp in sequence_group.forward_primers:
        if fp.sequence:
            Session.delete(fp.sequence)
        Session.delete(fp)
    sequence_group.forward_primers = []

    for rp in sequence_group.reverse_primers:
        if rp.sequence:
            Session.delete(rp.sequence)
        Session.delete(rp)
    sequence_group.reverse_primers = []

    for p in sequence_group.probes:
        if p.sequence:
            Session.delete(p.sequence)
        Session.delete(p)
    sequence_group.probes = []

def snp_objects_from_extdb(snps, snp_table):
    db_snps = []
    for snp in snps:
        db_snps.append(SNPDBCache(snpdb=snp_table,
                                  bin=snp['bin'],
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
    
    return db_snps

def active_sequence_group_query():
    return Session.query(SequenceGroup).filter(SequenceGroup.deleted != True)

def sequence_group_with_amplicon_query():
    """
    Return the backbone of the query that will only return
    sequence groups with known amplicons.
    """
    # TODO: keyword to insure inner join (future-proof)?
    return active_sequence_group_query().join(Amplicon)