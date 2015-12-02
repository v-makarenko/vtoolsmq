from qtools.lib.dropletgen import *
import os, unittest

def local(path):
    """
    Maybe this exists?
    """
    return "%s/%s" % (os.path.dirname(__file__), path)

@unittest.skip("Needs CSV files")
class TestDGReader(unittest.TestCase):

	def test_ok(self):
		run = read_dg_log(local('ok.csv'))
		assert run.droplet_generator_id == 10
		assert not run.failed
		assert run.datetime.year == 2011
		assert run.vacuum_time == 65.2
		assert run.vacuum_pressure == -1.969
		assert run.spike == .06968
		assert run.failure_reason is None
	
	def test_not_triggered(self):
		run = read_dg_log(local('no_trigger.csv'))
		assert run.droplet_generator_id == 0
		assert not run.failed
		assert run.spike is None
		assert run.vacuum_pressure == -1.965
	
	def test_fail_gasket(self):
		run = read_dg_log(local('fail_gasket.csv'))
		print run.droplet_generator_id
		assert run.droplet_generator_id == 10
		assert run.failed
		assert run.failure_reason == 'Optical Gasket Check'
		assert run.spike is None
		assert run.vacuum_time is None
		assert run.vacuum_pressure is None
	
	def test_fail_spike(self):
		run = read_dg_log(local('fail_spike.csv'))
		assert run.droplet_generator_id == 10
		assert run.failed
		assert run.failure_reason == 'Manifold Pressure Derivative Check,Vacuum'
		assert run.spike == 0.05408
		assert run.vacuum_time == 1.75
	
	def test_run_test(self):
		run = read_dg_log(local('run_test.csv'))
		assert not run
	
	def test_dg_file_re(self):
		assert DG_FILE_RE.match('2011-03-14_04-45-56.csv')
		assert DG_FILE_RE.match('2011-03-14_04-45-56 Fail.csv')
		assert not DG_FILE_RE.match('Test2011-03-14_04-45-56.csv')
	
	def test_numeric_re(self):
		assert NUMERIC_RE.match('9.9668e+000')
		assert NUMERIC_RE.match('9.9520e-001')
	
	def test_run_number(self):
		run = read_dg_log(local('ok.csv'))
		assert run.run_number is None
		run = read_dg_log(local('runno.csv'))
		assert run.run_number == 730
