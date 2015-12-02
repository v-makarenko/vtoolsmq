#!/usr/bin/env python

import sys, traceback, logging

from qtools.constants.job import *
from qtools.components.manager import get_manager
from qtools.messages import JSONMessage, JSONErrorMessage
from qtools.messages.sequence import ProcessSNPAmpliconMessage
from qtools.model.meta import Session
from qtools.model.sequence import SNPDBCache, AmpliconSequenceCache, SequenceGroup, Transcript
from qtools.model.sequence.util import snp_objects_from_extdb
from qtools.workers import LogExcRepeatedThread, PasterLikeProcess, PasterDaemonContextProcess

LOGGER_NAME = 'worker.snp'

def process_snp_job(job_queue, snp_source, snp_table):
    logger = logging.getLogger(LOGGER_NAME)

    in_progress = job_queue.in_progress(job_type=JOB_ID_PROCESS_SNP_RSID)
    for job in in_progress:
        job_queue.finish_tree(job, None)
    
    remaining = job_queue.remaining(job_type=(JOB_ID_PROCESS_SNPS, JOB_ID_PROCESS_SNP_RSID, JOB_ID_PROCESS_GEX_SNPS))
    for job in remaining:
        if job.type == JOB_ID_PROCESS_SNPS:
            snps               = []
            struct             = JSONMessage.unserialize(job.input_message)
            cached_sequence_id = struct.cached_sequence_id
            cached_seq         = Session.query(AmpliconSequenceCache).get(cached_sequence_id)
            if not cached_seq:
                logger.error("SNP job: Unknown amplicon sequence id: %s [job %s]" % (cached_sequence_id, job.id))
                job_queue.abort(job, JSONErrorMessage("Unknown amplicon sequence id: %s" % cached_sequence_id))
            
            try:
                snps = snp_source.snps_in_range(cached_seq.chromosome,
                                                cached_seq.start_pos-cached_seq.seq_padding_pos5,
                                                cached_seq.end_pos+cached_seq.seq_padding_pos3)
            except Exception:
                # DB timeout: abort job.
                logger.exception("Error from SNP worker:")
                job_queue.abort(job, JSONErrorMessage("Unable to connect to SNP database."))
                continue
            
            if snps:
                db_snps = snp_objects_from_extdb(snps, snp_table)
                if not cached_seq.snps:
                    cached_seq.snps = []
                for snp in db_snps:
                    cached_seq.snps.append(snp)
            
            logger.info("SNP process job finished [job %s]" % job.id)
            Session.commit()
            job_queue.finish(job, None)
        
        elif job.type == JOB_ID_PROCESS_GEX_SNPS:
            snps = []
            struct = JSONMessage.unserialize(job.input_message)
            transcript_id = struct.transcript_id
            transcript = Session.query(Transcript).get(transcript_id)
            if not transcript:
                logger.error("GEX SNP job: Unknown transcript id: %s [job %s]" % (transcript_id, job.id))
                job_queue.abort(job, JSONErrorMessage("Unknown transcript id %s" % transcript_id))
            try:
                print transcript.exon_regions
                snps = snp_source.snps_in_chrom_ranges(transcript.chromosome,
                                                       transcript.exon_bounds)
            except Exception:
                # DB timeout
                logger.exception("Error from SNP worker:")
                job_queue.abort(job, JSONErrorMessage("Unable to connect to SNP database."))
                continue

            if snps:
                # transcript?
                db_snps = snp_objects_from_extdb(snps, snp_table)
                if not transcript.snps:
                    transcript.snps = []
                for snp in db_snps:
                    transcript.snps.append(snp)

            logger.info("GEX SNP process job finished [job %s]" % job.id)
            Session.commit()
            job_queue.finish(job, None)
        
        elif job.type == JOB_ID_PROCESS_SNP_RSID:
            struct = JSONMessage.unserialize(job.input_message)
            sequence_group_id = struct.sequence_group_id
            sequence_group    = Session.query(SequenceGroup).get(sequence_group_id)
            if not sequence_group:
                logger.error("Process RSID unknown sequence id: %s [job %s]" % (sequence_group_id, job.id))
                job_queue.abort(job, JSONErrorMessage("Unknown sequence id."))
            
            snp_rsid = sequence_group.snp_rsid
            if not snp_rsid:
                logger.error("Process RSID empty RSID: %s [job %s]" % (snp_rsid, job.id))
                job_queue.abort(job, JSONErrorMessage("Empty SNP rsid."))
            
            try:
                snps = snp_source.snps_by_rsid(snp_rsid)
                if not snps:
                    logger.info("Process RSID unknown RSID: %s [job %s]" % (snp_rsid, job.id))
                    job_queue.abort(job, JSONErrorMessage("Unknown SNP rsid."))
                    continue
            except Exception:
                logger.exception("Error from SNP worker:")
                job_queue.abort(job, JSONErrorMessage("Unable to connect to SNP database."))
                continue
            
            locations = []
            for snp in snps:
                chromosome = snp['chrom'][3:]
                if snp['refUCSC'] == '-': # deletion:
                    start = snp['chromStart']
                else:
                    start = snp['chromStart']+1
                end = snp['chromEnd']
                message = ProcessSNPAmpliconMessage(sequence_group_id, chromosome, start, end)
                job_queue.add(JOB_ID_PROCESS_SNP_AMPLICON, message, parent_job=job)
            
            # TODO: need to be in transaction?
            job_queue.progress(job)
    
    Session.close()


class SNPWorker(PasterDaemonContextProcess):
    def run(self, config_path, as_daemon=False):
        global process_snp_job

        snp_table = 'snp131'
        mgr = get_manager(config_path)
        jobqueue = mgr.jobqueue()
        # TODO add as runtime argument
        snp_source = mgr.snp_source(snp_table='snp131')
        snp_thread = LogExcRepeatedThread(10, process_snp_job, LOGGER_NAME, jobqueue, snp_source, snp_table)
        if as_daemon:
            snp_thread.daemon = True
        
        snp_thread.start()

if __name__ == "__main__":
    worker = PasterLikeProcess('snps.pid')
    worker.run(SNPWorker)