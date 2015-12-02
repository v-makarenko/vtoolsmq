import types

from qtools.messages import JSONMessage
from qtools.model import now
from qtools.model.meta import Session, Base

from qtools.components.interfaces import JobQueue
from qtools.constants.job import *

from sqlalchemy import Integer, Unicode, String, Text, SmallInteger, UnicodeText, DateTime, Float, Boolean
from sqlalchemy.schema import Table, Column, Sequence, ForeignKey
from sqlalchemy import orm

metadata = Base.metadata

class Job(Base):
    __tablename__ = "job"
    __table_args__ = {"mysql_engine": 'InnoDB', 'mysql_charset': 'utf8'}

    id             = Column(Integer, Sequence('job_seq_id', optional=True), primary_key=True)
    parent_job_id  = Column(Integer, ForeignKey('job.id'), nullable=True)
    type           = Column(Integer, nullable=False)
    status         = Column(Integer, nullable=False, default=0)
    input_message  = Column(UnicodeText, nullable=True)
    result_message = Column(UnicodeText, nullable=True)
    date_created   = Column(DateTime, nullable=True, default=now)
    date_updated   = Column(DateTime, nullable=True, default=now)
    children       = orm.relation('Job', backref=orm.backref('parent', remote_side=[id]), cascade='all')

    STATUS_NOT_DONE      = JOB_STATUS_NOT_DONE
    STATUS_IN_PROGRESS   = JOB_STATUS_IN_PROGRESS
    STATUS_DONE          = JOB_STATUS_DONE
    STATUS_UNKNOWN_ERROR = JOB_STATUS_ABORTED

class DBJobQueue(JobQueue):
    """
    DB-based job queue
    """
    def add(self, type, message=None, parent_job=None):
        job = Job(type=type,
                  input_message=message.serialize() if message else None,
                  status=Job.STATUS_NOT_DONE,
                  date_created = now(),
                  date_updated = now())
        if parent_job:
            job.parent_job_id = parent_job.id
        Session.add(job)
        # TODO: commit automatically?
        Session.commit()
        return job
    
    def __construct_query(self, job_type=None, sort_order=None, status=None, parent_job=None):
        job_query = Session.query(Job)
        if job_type is not None:
            # todo: generic isnum/issequence?
            if type(job_type) in (types.IntType, types.LongType):
                job_query = job_query.filter_by(type=job_type)
            elif getattr(job_type, '__iter__', None) != None:
                job_query = job_query.filter(Job.type.in_(job_type))
            else:
                raise ValueError, "Invalid job type: %s" % job_type
        
        if status is not None:
            job_query = job_query.filter_by(status=status)
        
        if parent_job is not None:
            job_query = job_query.filter_by(parent_job_id=parent_job.id)
        
        if sort_order == JobQueue.BY_DATE_ASC:
            job_query = job_query.order_by('date_created asc')
        elif sort_order == JobQueue.BY_DATE_DESC:
            job_query = job_query.order_by('date_created desc')
        
        return job_query
    
    def next(self, type=None, sort_order=JobQueue.BY_DATE_ASC, parent_job=None):
        job_query = self.__construct_query(type=type,
                                           sort_order=sort_order,
                                           status=Job.STATUS_NOT_DONE,
                                           parent_job=parent_job)
        job = job_query.first()
        return job
    
    def progress(self, job):
        job.date_updated = now()
        job.status = Job.STATUS_IN_PROGRESS
        Session.add(job)
        # TODO: commit automatically?
        Session.commit()
    
    def finish(self, job, message=None):
        job.date_updated = now()
        job.status = Job.STATUS_DONE
        job.result_message = message.serialize() if message else None
        Session.add(job)

        # TODO: commit automatically?
        Session.commit()
    
    # rename to finish_in_progress?
    def finish_tree(self, job, message=None):
        if not job.children:
            self.finish(job, message)
            return True
        
        for j in job.children:
            if j.status not in (Job.STATUS_DONE, Job.STATUS_NOT_DONE, Job.STATUS_IN_PROGRESS):
                job.status = j.status
                Session.add(job)
                # TODO: commit automatically?
                Session.commit()
                return True
            elif j.status in (Job.STATUS_NOT_DONE, Job.STATUS_IN_PROGRESS):
                return False
        
        job.status = Job.STATUS_DONE
        job.date_updated = now()
        Session.commit()
        return True
    
    def abort(self, job, message=None, error_code=None):
        if error_code is None:
            error_code = Job.STATUS_UNKNOWN_ERROR
        
        job.date_updated = now()
        job.status = error_code
        job.result_message = message.serialize() if message else None
        Session.add(job)
        # TODO: commit automatically?
        Session.commit()
    
    def all(self, job_type=None, sort_order=JobQueue.BY_DATE_ASC, status=None, parent_job=None):
        job_query = self.__construct_query(job_type=job_type,
                                           sort_order=sort_order,
                                           status=status,
                                           parent_job=parent_job)
        jobs = job_query.all()
        return jobs
    
    def by_uid(self, uid):
        return Session.query(Job).get(uid)
    
    def children(self, job):
        return job.children
    
    def remaining(self, job_type=None, sort_order=JobQueue.BY_DATE_ASC, parent_job=None):
        return self.all(job_type=job_type,
                        sort_order=sort_order,
                        status=Job.STATUS_NOT_DONE,
                        parent_job=parent_job)
    
    def in_progress(self, job_type=None, sort_order=JobQueue.BY_DATE_ASC, parent_job=None):
        return self.all(job_type=job_type,
                        sort_order=sort_order,
                        status=Job.STATUS_IN_PROGRESS,
                        parent_job=parent_job)
    
    def is_job_done(self, job):
        return job.status == Job.STATUS_DONE
    
    def get_job_input_params(self, job):
        return JSONMessage.unserialize(job.input_message)
    
    def get_job_result_params(self, job):
        return JSONMessage.unserialize(job.result_message)
