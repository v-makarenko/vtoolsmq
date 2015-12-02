import time, daemon, lockfile, os, signal, sys, logging
import logging.config
from threading import Timer, Thread
from abc import *
from optparse import OptionParser

class RepeatedThread(Thread):
	"""
	Second shot at repeater.  Cannot be cancelled.
	"""
	def __init__(self, interval, target, *args, **kwargs):
		super(RepeatedThread, self).__init__()
		self._interval = interval
		self._target = target
		self._args = args
		self._kwargs = kwargs
	
	def run(self):
		while True:
			self._target.__call__(*(self._args), **(self._kwargs))
			time.sleep(self._interval)

class LogExcRepeatedThread(RepeatedThread):
	"""
	RepeatedThread which logs exceptions, instead of stopping.
	"""
	def __init__(self, interval, target, logName, *args, **kwargs):
		super(LogExcRepeatedThread, self).__init__(interval, target, *args, **kwargs)
		self._logger = logging.getLogger(logName)
	
	def run(self):
		while True:
			try:
				self._target.__call__(*(self._args), **(self._kwargs))
			except Exception:
				self._logger.exception('Thread handled unexpected error: ')
			time.sleep(self._interval)

class PasterDaemonContextProcess(object):
	__metaclass__ = ABCMeta

	@abstractmethod
	def run(self, config_path):
		pass


class PasterLikeProcess(object):
	def __init__(self, default_pid_name):
		"""
		Create a paster-like process with the following characteristics:

		* Arguments:
		** --daemon: Run as a daemon.
		** --pid-file: If run as a daemon, specify the pid file.
		** --action: Action to issue to the daemon: start or stop.
		** Last argument: config file that should be used to initialize the paster app.

		Command line arguments are available after running the initialization methods through the
		attributes 'cli_options' and 'cli_args'.  "pid_file_path", "stop", "daemon" and "config_path"
		should also be available.
		"""
		self.default_pid_name = default_pid_name
		parser = OptionParser()
		parser.add_option('--daemon', action='store_true', dest='daemon', default=False)
		parser.add_option('--pid-file', action='store', dest='pid_file', default=None)
		parser.add_option('--action', action='store', dest='action', default='start')
		parser.add_option('--log-file', action='store', dest='log_file', default=None)

		self.cli_options, self.cli_args = parser.parse_args()
		self.daemon        = self.cli_options.daemon
		self.pid_file_path = self.cli_options.pid_file or os.path.join(os.path.dirname(__file__), self.default_pid_name)
		self.action        = self.cli_options.action
		self.config_path   = os.path.abspath(self.cli_args[-1])

	def run(self, run_class):
		if self.daemon:
			self.__runDaemon(run_class)
		else:
			self.__runShell(run_class)
	
	@abstractmethod
	def process_stop(self, *args):
		if hasattr(self, 'logfile'):
			self.logfile.close()
		sys.exit(0)
	
	def __loop(self):
		while(True):
			time.sleep(0.1)
	
	def __runDaemon(self, run_class):
		pidfile = lockfile.FileLock(self.pid_file_path)

		if self.action == 'stop':
			try:
				with open(pidfile.lock_file, 'r') as f:
					pid = int(f.readline())
			except IOError, e:
				print "No pid file exists: %s" % pidfile.lock_file
				sys.exit(0)
			try:
				os.kill(pid, signal.SIGTERM)
			except:
				print "Could not kill process %s" % pid
			sys.exit(0)
		
		elif self.action == 'start':
			if pidfile.is_locked():
				print "Lockfile %s is already locked." % self.pid_file_path
				sys.exit(0)
		
			context = daemon.DaemonContext(
				working_directory=os.path.dirname(self.pid_file_path),
				#umask=0o002,
				pidfile=pidfile
			)
			print context

			if self.cli_options.log_file:
				self.logfile = open(self.cli_options.log_file, 'a')
				context.stdout = self.logfile
				context.stderr = self.logfile

			stop_func  = self.process_stop

			context.signal_map = {
				signal.SIGTERM: stop_func,
				signal.SIGHUP: 'terminate'
			}

			context.config_path = self.config_path
			context.run_class = run_class
			context.loop_func = self.__loop

			# to be safe in thread context, initialize everything
			# inside the daemon context.  This was borne out of
			# a theory that spawning a thread was causing memory
			# errors, which later turned out to be a urllib2 clash
			# with CoreFoundation (Mac OS X only).  Awesome.
			with context:
				logging.config.fileConfig(context.config_path)
				with open(pidfile.lock_file, 'w') as f:
					f.write(str(os.getpid()))
				
				run_context = context.run_class()
				run_context.run(context.config_path, as_daemon=True)
				
				# keep daemon outer loop function running so pid file
				# will have something to hold onto
				context.loop_func()
			
		else:
			print "Unknown action: %s" % self.action
			sys.exit(0)
	
	def __runShell(self, run_class):
		run_class().run(self.config_path, as_daemon=True)
		signal.signal(signal.SIGINT, self.process_stop)
		self.__loop()

