#!/usr/bin/env python
"""
    This worker script is used to reprocess plates in qtools using a different version of Quantasoft on qltester
    
"""

import sys, traceback, logging

from qtools.constants.job import *
from qtools.lib.metrics.db import *
from qtools.components.manager import get_manager
from qtools.messages import JSONMessage, JSONErrorMessage
from qtools.lib.storage import QLPReprocessedFileSource
from qtools.model.meta import Session
from qtools.workers import LogExcRepeatedThread, PasterLikeProcess, PasterDaemonContextProcess
from qtools.model import ReprocessConfig, AnalysisGroup
from qtools.lib.qlb_factory import get_plate

LOGGER_NAME = 'worker.reprocess'

def update_reprocess_analysis_group_data(analysis_group, reprocess_config, config, logger):
    """
        Given an analysis_gropu and repocessor, relaod each into qtools
    """

    update_status = 0

    plates = analysis_group.plates
    # remove old metrics if present
    for plate in plates:
        pm = [pm for pm in plate.metrics if pm.reprocess_config_id == reprocess_config.id]
        # should only be of length 1, but just to be safe
        for p in pm:
            Session.delete(p)

    # TODO: how to make this whole operation transactional
    Session.commit()

    plate_ids = [plate.id for plate in plates]

    data_root = config['qlb.reprocess_root']
    file_source = QLPReprocessedFileSource(data_root, reprocess_config)

    for id in plate_ids:
        dbplate = dbplate_tree(id)
        # TODO: right abstraction?
        plate_path = file_source.full_path(analysis_group, dbplate)

        print "Reading/updating metrics for %s" % plate_path
        qlplate = get_plate(plate_path)
        if not qlplate:
            print "Could not read plate: %s" % plate_path
            continue

        plate_metrics = get_beta_plate_metrics(dbplate, qlplate, reprocess_config)
        Session.add(plate_metrics)
        del qlplate

    Session.commit()

    return update_status


def retreive_and_validate_inputs( job, job_queue, logger): 
    """ 
    retreives and validates analysis group and reprocessor from a job
    """
    struct  = JSONMessage.unserialize(job.input_message)

    ## get IDs
    analysis_group_id     = struct.analysis_group_id
    reprocess_config_id   = struct.reprocess_config_id

    analysis_group        = Session.query(AnalysisGroup).get(analysis_group_id)
    reprocessor           = Session.query(ReprocessConfig).get(reprocess_config_id)

    #check if analysis group exists in DB
    if not analysis_group:
        logger.error("Reprocess job: Analysis group id: %s not found[job %s]" % (analysis_group_id, job.id))
        job_queue.abort(job, JSONErrorMessage("Unknown analysis group id: %s" % analysis_group_id))

    #check if reprocessor exists in DB
    if not reprocessor:
        logger.error("Reprocess job: reprocessor id: %s not found[job %s]" % (reprocess_config_id, job.id))
        job_queue.abort(job, JSONErrorMessage("Unknown reprocessor: %s" % reprocess_config_id))


    return analysis_group, reprocessor


def process_reprocess_job( job_queue, config ):
    logger = logging.getLogger(LOGGER_NAME)

    #mark finished first, 
    #in_progress = job_queue.in_progress(job_type=JOB_ID_PROCESS_REPROCESS)
    in_progress = job_queue.in_progress(job_type=JOB_ID_REPROCESS_QLTESTER)
    for job in in_progress:
        job_queue.finish_tree(job, None)
        if job_queue.is_job_done(job):
            logger.info("Job finished [job %s]" % job.id)
            # We might want to add a flag to the reprocess group/algorthm to prevent multiple starts
            # Below is an example of what to do...
            #args = job_queue.get_job_input_params(job)
            #assay = Session.query(SequenceGroup).get(args.sequence_group_id)
            #if assay:
            #    assay.analyzed = True
            #    Session.commit()

    # now process remaining jobs in que
    remaining = job_queue.remaining(job_type=(JOB_ID_REPROCESS_QLTESTER,JOB_ID_REPROCESS_LOAD_QTOOLS))
    for job in remaining:
        if job.type == JOB_ID_REPROCESS_QLTESTER:

            analysis_group, reprocessor = retreive_and_validate_inputs( job, job_queue, logger )

            ## Try to launch connection
            try:
                import paramiko
                import time

                qltester_host = config['qtools.qltester.host']
                qltester_pw   = config['qtools.qltester.pw']
                qltester_user = config['qtools.qltester.user']

                qltester_cmd = 'python ./run_reprocessor.py ' + str( analysis_group.id ) + ' ' + reprocessor.code
                                       
                client = paramiko.SSHClient()
                client.load_system_host_keys()
                client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
                client.connect(qltester_host, 22, qltester_user, qltester_pw)
                chan = client.get_transport().open_session()
                chan.exec_command( qltester_cmd )

                while ( not chan.exit_status_ready() ):         
                    time.sleep(10)
                
                reprocess_result = chan.recv_exit_status()
                client.close()

            except Exception:
                # DB timeout: abort job.
                logger.exception("Error from Reprocessor worker:")
                job_queue.abort(job, JSONErrorMessage("Unable to connect to qltester."))
                continue
            
            if ( reprocess_result == 0 ):
                ## if sucesful, update db? 
                logger.info("Reprocess process job finished [job %s]" % job.id)
                Session.commit()
    
                ## add step-2 to job que..
                message = JSONMessage(analysis_group_id=analysis_group.id,reprocess_config_id=reprocessor.id)
                job_queue.add(JOB_ID_REPROCESS_LOAD_QTOOLS, message, parent_job=job)           

                #mark progress
                job_queue.progress(job)              
            
            elif( reprocess_result == 1 ):
                #logger is currently processing anouther job try again later....
                logger.info("Reprocessor is busy, process job [job %s] will be attempted again later" % job.id )
            else:
                logger.info("Reprocess process job failed [job %s] qltester exit code %d" % (job.id, reprocess_result) )
                job_queue.abort(job, JSONErrorMessage("Reprocessor failed on qltester: Non-zero result status (%d)" % reprocess_result)) 
        
        elif job.type == JOB_ID_REPROCESS_LOAD_QTOOLS:
            
            analysis_group, reprocessor = retreive_and_validate_inputs( job, job_queue, logger )

            try:
                result = update_reprocess_analysis_group_data(analysis_group, reprocessor, config, logger)

            except Exception:
                logger.exception("Error from Reprocess worker:")
                job_queue.abort(job, JSONErrorMessage("Unable add to qtools"))
                continue
            
            # avoid condition where job completed -- clear child job first
            if ( result == 0 ):
                job_queue.finish(job, None)
            else:
                logger.exception("Error from Reprocess worker [job %s]: Non-zero result status (%d)" % job.id, result )
                job_queue.abort(job, JSONErrorMessage("Unable add to qtools: Non-zero result status (%d)" % result))
                continue

 
    # this is key; otherwise, the SQL connection pool will be sucked up.
    Session.close()


class ReprocessWorker(PasterDaemonContextProcess):
    def run(self, config_path, as_daemon=False):
        global process_reprocess_job

        mgr = get_manager(config_path)
        
        jobqueue = mgr.jobqueue()

        config = mgr.pylons_config

        # TODO add as runtime argument
        reprocess_thread = LogExcRepeatedThread(10, process_reprocess_job, LOGGER_NAME, jobqueue, config )

        if as_daemon:
            reprocess_thread.daemon = True
        
        reprocess_thread.start()

if __name__ == "__main__":
    worker = PasterLikeProcess('reprocess.pid')
    worker.run(ReprocessWorker)
