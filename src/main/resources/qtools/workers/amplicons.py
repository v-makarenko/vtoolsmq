#!/usr/bin/env python

import logging

from qtools.constants.job import *
from qtools.constants.pcr import *
from qtools.components.manager import get_manager
from qtools.messages import JSONMessage, JSONErrorMessage
from qtools.messages.sequence import *
from qtools.model.meta import Session
from qtools.model.sequence import Sequence, SequenceGroup, SequenceGroupComponent, Amplicon, AmpliconSequenceCache
from qtools.model.sequence.pcr import create_amplicons_from_pcr_sequences, create_db_transcripts_from_pcr_transcripts
from qtools.workers import LogExcRepeatedThread, PasterLikeProcess, PasterDaemonContextProcess

LOGGER_NAME = 'worker.amplicon'
# TODO change to toplevel queue?
def process_assay_job(job_queue, tm_calc, dg_calc):
    logger = logging.getLogger(LOGGER_NAME)

    # mark finished first
    in_progress = job_queue.in_progress(job_type=JOB_ID_PROCESS_ASSAY)
    for job in in_progress:
        job_queue.finish_tree(job, None)
        if job_queue.is_job_done(job):
            logger.info("Job finished [job %s]" % job.id)
            args = job_queue.get_job_input_params(job)
            assay = Session.query(SequenceGroup).get(args.sequence_group_id)
            if assay:
                assay.analyzed = True
                Session.commit()
    
    remaining = job_queue.remaining(job_type=JOB_ID_PROCESS_ASSAY)
    for job in remaining:
        struct = JSONMessage.unserialize(job.input_message)
        sg_id = struct.sequence_group_id
        
        sg = Session.query(SequenceGroup).get(sg_id)
        # TODO: I think the parent function should have cleared out the amplicons,
        # but I need to make that choice
        if not sg:
            logger.error("Unknown sequence group id: %s [job %s]" % (sg_id, job.id))
            job_queue.abort(job, JSONErrorMessage("Unknown sequence group id: %s" % sg_id))
        
        if sg.kit_type == SequenceGroup.TYPE_DESIGNED:
            probe_ids = [p.id for p in sg.probes]
            # TODO: transaction?
            if sg.type == SequenceGroup.ASSAY_TYPE_GEX:
                job_type = JOB_ID_PROCESS_GEX_TAQMAN_TRANSCRIPT
            else:
                job_type = JOB_ID_PROCESS_TAQMAN_AMPLICON

            for fp in sg.forward_primers:
                for rp in sg.reverse_primers:
                    job_queue.add(job_type,
                                  ProcessPrimerAmpliconMessage(sequence_group_id=sg.id,
                                                               forward_primer_id=fp.id,
                                                               reverse_primer_id=rp.id,
                                                               probe_ids=probe_ids),
                                  parent_job=job)
            
            # TM, DG of sequence components right here
            for fp in sg.forward_primers:
                fp.tm = tm_calc.tm_primer(fp.sequence.sequence)
                fp.dg = dg_calc.delta_g(fp.sequence.sequence)
            for rp in sg.reverse_primers:
                rp.tm = tm_calc.tm_primer(rp.sequence.sequence)
                rp.dg = dg_calc.delta_g(rp.sequence.sequence)
            for p in sg.probes:
                if p.quencher and p.quencher.upper() == 'MGB':
                    p.tm = tm_calc.tm_probe(p.sequence.sequence, mgb=True)
                    p.dg = dg_calc.delta_g(p.sequence.sequence)
                else:
                    p.tm = tm_calc.tm_probe(p.sequence.sequence, mgb=False)
                    p.dg = dg_calc.delta_g(p.sequence.sequence)
            Session.commit()


        elif sg.kit_type == SequenceGroup.TYPE_LOCATION:
            job_queue.add(JOB_ID_PROCESS_LOCATION_AMPLICON,
                          ProcessLocationAmpliconMessage(sequence_group_id=sg.id),
                          parent_job=job)
        
        elif sg.kit_type == SequenceGroup.TYPE_SNP:
            job_queue.add(JOB_ID_PROCESS_SNP_RSID,
                          ProcessSNPRSIDMessage(sequence_group_id=sg.id),
                          parent_job=job)
        
        # TODO: need to be in transaction?
        job_queue.progress(job)
    
    # this is the key; otherwise, the SQL connection pool will be sucked up.
    # OH WHY DID I PICK THIS TIME TO WORRY ABOUT THREADING
    Session.close()

def process_amplicon_job(job_queue, sequence_source, dg_calc):
    remaining = job_queue.remaining(job_type=(JOB_ID_PROCESS_TAQMAN_AMPLICON,
                                              JOB_ID_PROCESS_LOCATION_AMPLICON,
                                              JOB_ID_PROCESS_SNP_AMPLICON,
                                              JOB_ID_PROCESS_GEX_TAQMAN_TRANSCRIPT))
    for job in remaining:
        if job.type == JOB_ID_PROCESS_TAQMAN_AMPLICON:
            process_taqman_job(job, job_queue, sequence_source, dg_calc)
        elif job.type == JOB_ID_PROCESS_LOCATION_AMPLICON:
            process_location_job(job, job_queue, sequence_source, dg_calc)
        elif job.type == JOB_ID_PROCESS_SNP_AMPLICON:
            process_snp_job(job, job_queue, sequence_source, dg_calc)
        elif job.type == JOB_ID_PROCESS_GEX_TAQMAN_TRANSCRIPT:
            process_transcript_job(job, job_queue, sequence_source, dg_calc)
    
    Session.close()

def populate_amplicon_dgs(amp, dg_calc):
    """
    Adds folding_dg to the cached sequences for the specified
    amplicon.  Does not commit.
    """
    for cs in amp.cached_sequences:
        cs.folding_dg = dg_calc.delta_g(cs.positive_amplicon)

def populate_transcript_dgs(transcript, dg_calc):
    transcript.folding_dg = dg_calc.delta_g(transcript.positive_sequence)


def process_taqman_job(job, job_queue, sequence_source, dg_calc):
    logger = logging.getLogger(LOGGER_NAME)

    struct            = JSONMessage.unserialize(job.input_message)
    forward_primer_id = struct.forward_primer_id
    reverse_primer_id = struct.reverse_primer_id
    probe_ids         = struct.probe_ids

    sequence_group    = Session.query(SequenceGroup).get(struct.sequence_group_id)
    fp_sequence       = Session.query(SequenceGroupComponent).get(forward_primer_id).sequence
    rp_sequence       = Session.query(SequenceGroupComponent).get(reverse_primer_id).sequence
    probes            = Session.query(SequenceGroupComponent).filter(SequenceGroupComponent.id.in_(probe_ids)).all()
    probe_seqs        = [p.sequence for p in probes]
    
    sequences = sequence_source.sequences_for_primers(fp_sequence.sequence, rp_sequence.sequence,
                                                      fwd_prefix_length=MAX_CACHE_PADDING,
                                                      rev_suffix_length=MAX_CACHE_PADDING)
    
    if sequences is None:
        logger.error("Amplicon TaqMan: Could not get response from server [job %s]" % job.id)
        job_queue.abort(job, JSONErrorMessage('Could not get response from server.'))
        Session.commit()
        return
    
    amplicons = create_amplicons_from_pcr_sequences(sequence_group,
                                                    forward_primer=fp_sequence,
                                                    reverse_primer=rp_sequence,
                                                    probes=probe_seqs,
                                                    pcr_sequences=sequences)
    
    for amp in amplicons:
        populate_amplicon_dgs(amp, dg_calc)
    
    logger.info("Taqman job completed [job %s]" % job.id)
    Session.commit()
    
    # TODO: add finish message
    
    # now add SNPs to cached sequences
    for amp in amplicons:
        for cseq in amp.cached_sequences:
            job_queue.add(JOB_ID_PROCESS_SNPS, ProcessSNPMessage(cached_sequence_id=cseq.id),
                          parent_job=job.parent)
    
    # avoid condition where job completed -- clear child job first
    job_queue.finish(job, None)

def process_transcript_job(job, job_queue, sequence_source, dg_calc):
    logger = logging.getLogger(LOGGER_NAME)

    struct = JSONMessage.unserialize(job.input_message)
    forward_primer_id = struct.forward_primer_id
    reverse_primer_id = struct.reverse_primer_id
    probe_ids = struct.probe_ids

    sequence_group = Session.query(SequenceGroup).get(struct.sequence_group_id)
    fp_sequence    = Session.query(SequenceGroupComponent).get(forward_primer_id).sequence
    rp_sequence    = Session.query(SequenceGroupComponent).get(reverse_primer_id).sequence
    probes         = Session.query(SequenceGroupComponent).filter(SequenceGroupComponent.id.in_(probe_ids)).all()
    probe_seqs     = [p.sequence for p in probes]

    transcripts = sequence_source.transcript_sequences_for_primers(fp_sequence.sequence,
                                                                   rp_sequence.sequence)

    if transcripts is None:
        logger.error("GEX TaqMan: Could not get response from server [job %s]" % job.id)
        job_queue.abort(job, JSONErrorMessage("Could not get response from server."))
        Session.commit()
        return

    db_transcripts = create_db_transcripts_from_pcr_transcripts(sequence_group,
                                                                forward_primer=fp_sequence,
                                                                reverse_primer=rp_sequence,
                                                                probes=probe_seqs,
                                                                pcr_gene_sequences=transcripts)

    sequence_group.transcripts = db_transcripts
    for trans in sequence_group.transcripts:
        populate_transcript_dgs(trans, dg_calc)

    logger.info("GEX TaqMan job completed [job %s]" % job.id)
    Session.commit()

    for trans in db_transcripts:
        job_queue.add(JOB_ID_PROCESS_GEX_SNPS, ProcessGEXSNPMessage(trans.id),
                      parent_job=job.parent)

    job_queue.finish(job, None)


def process_location_job(job, job_queue, sequence_source, dg_calc):
    logger = logging.getLogger(LOGGER_NAME)

    struct         = JSONMessage.unserialize(job.input_message)
    
    sequence_group = Session.query(SequenceGroup).get(struct.sequence_group_id)
    sequence = None
    try:
        sequence = sequence_source.sequence_around_loc(sequence_group.location_chromosome,
                                                        sequence_group.location_base,
                                                        sequence_group.amplicon_length,
                                                        prefix_length=MAX_CACHE_PADDING,
                                                        suffix_length=MAX_CACHE_PADDING)
    except Exception:
        logger.exception("Could not retrieve sequence for assay location [job %s]: " % job.id)
        job_queue.abort(job, JSONErrorMessage('Could not retrieve the sequence for the specified amplicon location.'))
        Session.commit()
        return
    
    if sequence is None:
        logger.error("Amplicon Location: could not get response from server [job %s]: " % job.id)
        job_queue.abort(job, JSONErrorMessage('Could not get response from server.'))
        Session.commit()
        return
    
    amplicons = create_amplicons_from_pcr_sequences(sequence_group,
                                                    pcr_sequences=[sequence])
    
    for amp in amplicons:
        populate_amplicon_dgs(amp, dg_calc)
    
    logger.info("Location job completed [job %s]" % job.id)
    Session.commit()

    for amp in amplicons:
        for cseq in amp.cached_sequences:
            job_queue.add(JOB_ID_PROCESS_SNPS, ProcessSNPMessage(cached_sequence_id=cseq.id),
                          parent_job=job.parent)
    
    job_queue.finish(job, None)


def process_snp_job(job, job_queue, sequence_source, dg_calc):
    logger = logging.getLogger(LOGGER_NAME)

    struct         = JSONMessage.unserialize(job.input_message)
    sequence_group = Session.query(SequenceGroup).get(struct.sequence_group_id)
    chromosome     = struct.chromosome
    snp_start      = struct.start
    snp_end        = struct.end

    sequence = None
    try:
        sequence   = sequence_source.sequence_around_region(chromosome, snp_start, snp_end,
                                                            sequence_group.amplicon_length,
                                                            prefix_length=MAX_CACHE_PADDING,
                                                            suffix_length=MAX_CACHE_PADDING)
    except Exception:
        logger.exception("Could not retrieve sequence around SNP location for [job %s]" % job.id)
        job_queue.abort(job, JSONErrorMessage("Could not retrieve sequence around SNP location."))
        Session.commit()
        return
    
    if sequence is None:
        logger.error("Amplicon SNP: could not get response from server [job %s]" % job.id)
        job_queue.abort(job, JSONErrorMessage('Could not get response from server.'))
        Session.commit()
        return
    
    amplicons      = create_amplicons_from_pcr_sequences(sequence_group,
                                                         pcr_sequences=[sequence])
    
    logger.info("SNP assay job completed [job %s]" % job.id)
    Session.commit()

    for amp in amplicons:
        for cseq in amp.cached_sequences:
            job_queue.add(JOB_ID_PROCESS_SNPS, ProcessSNPMessage(cached_sequence_id=cseq.id),
                          parent_job=job.parent)
    
    job_queue.finish(job, None)
        


class AmpliconWorker(PasterDaemonContextProcess):
    def run(self, config_path, as_daemon=False):
        global process_assay_job, process_amplicon_job

        mgr                  = get_manager(config_path)
        jobqueue             = mgr.jobqueue()
        sequence_source      = mgr.sequence_source()
        tm_calc = mgr.tm_calc(mgr)
        dg_calc = mgr.dg_calc(mgr)

        # does the thread knock it out?
        assay_thread    = LogExcRepeatedThread(10, process_assay_job, LOGGER_NAME, jobqueue, tm_calc, dg_calc)
        sequence_thread = LogExcRepeatedThread(15, process_amplicon_job, LOGGER_NAME, jobqueue, sequence_source, dg_calc)
        if as_daemon:
            assay_thread.daemon = True
            sequence_thread.daemon = True

        assay_thread.start()
        sequence_thread.start()

if __name__ == "__main__":
    worker = PasterLikeProcess('amplicons.pid')
    worker.run(AmpliconWorker)