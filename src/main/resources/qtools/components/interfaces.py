"""
Interfaces for DI-loaded components.  While not
strictly necessary, can be used as a guide, or to
hold common behavior for concrete base classes.
"""
from abc import *

class JobQueue(object):
	__metaclass__ = ABCMeta

	BY_DATE_ASC  = 0
	BY_DATE_DESC = 1

	@abstractmethod
	def add(self, type, message=None, parent_job=None):
		"""
		Adds a new job to the queue with the specified type,
		and message.  Return a job object back which you
		can reference later.

		:param type: The job type.
		:param message: A qtools.messages.Message object.
		:param parent_job: The parent job of this job (if any)
		"""
		pass
	
	@abstractmethod
	def next(self, type=None, sort_order=BY_DATE_ASC, parent_job=None):
		"""
		Returns the message payload of the current job to be done.
		If the job type is specified, only returns a job of the
		specified type.
		"""
		pass
	
	@abstractmethod
	def progress(self, job):
		"""
		Mark a job as in progress.
		"""
		pass
	
	@abstractmethod
	def finish(self, job, message=None):
		"""
		Marks the job as finished.

		:param job: A job object.
		:param message: A qtools.messages.Message object.
		"""
		pass
	
	@abstractmethod
	def finish_tree(self, job, message=None):
		"""
		Check to see if all children are finished or aborted.

		If any of the children are aborted, mark the parent
		job as aborted.

		If all of the children are finished, mark the parent
		job as finished.

		Otherwise, mark the job as still not done.

		Return True if the job is somehow resolved, False if
		there was no status change.
		
		:param job: A job object.
		:param message: A qtools.messages.Message object.
		"""
		pass
	
	@abstractmethod
	def abort(self, job, message=None, error_code=None):
		"""
		Marks the job as aborted.

		:param job: A job object.
		:param message: A qtools.messages.Message object.
		"""
		pass
	
	@abstractmethod
	def all(self, job_type=None, sort_order=BY_DATE_ASC, status=None, parent_job=None):
		"""
		Returns all jobs, or only the jobs of the specified
		type(s), status or parent.
		"""
		pass
	
	@abstractmethod
	def by_uid(self, uid):
		"""
		Get a job by its unique identifier, should one exist.
		"""
		pass
	
	@abstractmethod
	def remaining(self, job_type=None, sort_order=BY_DATE_ASC, parent_job=None):
		"""
		Returns all remaining jobs of the specified type(s) or parent (plural of next())
		"""
		pass
	
	@abstractmethod
	def in_progress(self, job_type=None, sort_order=BY_DATE_ASC, parent_job=None):
		"""
		Returns the jobs currently in progress (most likely parent jobs)
		"""
		pass
	
	@abstractmethod
	def is_job_done(self, job):
		"""
		Returns whether the job is done.
		"""
		pass
	
	@abstractmethod
	def get_job_input_params(self, job):
		"""
		Returns the input params for the job.
		"""
		pass
	
	@abstractmethod
	def get_job_result_params(self, job):
		"""
		Return the result params from the job.
		"""
		pass
	
	@abstractmethod
	def children(self, job):
		"""
		Return the parent job's child jobs.
		"""
		pass


class TMCalculator(object):
	__metaclass__ = ABCMeta

	@abstractmethod
	def tm_probe(sequence, concentration, mgb=False):
		"""
		Return the melt temp of the specified probe sequence.
		"""
		pass
	
	@abstractmethod
	def tm_primer(sequence, concentration):
		"""
		Return the melt temp of the specified primer.
		"""
		pass

class DeltaGCalculator(object):
	__metaclass__ = ABCMeta

	@abstractmethod
	def delta_g(sequence):
		"""
		Return the delta-G value for the sequence.
		"""
		pass