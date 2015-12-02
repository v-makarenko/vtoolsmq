"""
Methods for computing the tM of an assay.
"""
import subprocess, tempfile

from qtools.components.interfaces import TMCalculator
from qtools.constants.tm import TM_CONFIG_PARAM_PROBE_CONC, TM_CONFIG_PARAM_PRIMER_CONC, TM_CONFIG_PARAM_SALT

# TODO phase out
def tm_probe(config, seq):
	return tm_call(config, seq, '2e-07','0.1')

# TODO phase out
def tm_mgb_probe(config, seq):
	return tm_call(config, seq, '2e-07','0.1', mg='5e-03')
	 
# TODO phase out
def tm_primer(config, seq):
	return tm_call(config, seq, '9e-07','0.1')

# TODO phase out
def tm_pcr_sequence(config, pcr_seq):
	"""
	Add the tm to the PCR sequence.
	"""
	pcr_seq.tm = tm_probe(config, pcr_seq.amplicon.sequence)
	return pcr_seq

# TODO phase out
def tm_assay(config, assay):
    """
    Return tm for assay
    Returns 3-tuple (fwd_primer_tm, rev_primer_tm, probe_tm)
    """
    # 2 vs 3 calls negligible
    return (tm_primer(config, assay.primer_fwd),
            tm_primer(config, assay.primer_rev),
            tm_mgb_probe(config, assay.probe_seq) if (assay.quencher and assay.quencher.upper() == 'MGB') else \
              tm_probe(config, assay.probe_seq))
        
# TODO phase out
def tm_call(config, seq, concentration, salt, mg=None):
	tm_util_path = config['qtools.bin.tm_util']
	tf = tempfile.NamedTemporaryFile()
	tf.write('QTools-tm %s' % seq)
	tf.flush()
	args = [tm_util_path, '-con', concentration, '-salt', salt]
	if mg is not None:
		args.extend(['-mg', mg, '-tmgb'])
	args.extend(['-iraw', tf.name])
	retval = None

	# ASK RK: why does this return an error code (venpipe doesn't)
	try:
		prog_output = subprocess.check_output(args)
	except subprocess.CalledProcessError, e:
		prog_output = e.output
	for line in prog_output.split('\n'):
		if line.startswith('QTools-tm'):
			toks = line.strip().split()
			retval = float(toks[-1])
	tf.close()
	return retval


class CommandLineDriver(TMCalculator):
	def __init__(self, component_manager):
		config = component_manager.pylons_config
		self.params = component_manager.tm_config
		self.tm_util_path = config['qtools.bin.tm_util']
		self.tm_mgb_config = config['qtools.bin.tm_mgb_par']
	
	def tm_probe(self, sequence, concentration=None, mgb=False):
		args = [self.tm_util_path,
		        '-con', str(concentration or self.params[TM_CONFIG_PARAM_PROBE_CONC]),
		        '-salt', str(self.params[TM_CONFIG_PARAM_SALT])]
		if mgb:
			args.extend(['-par', self.tm_mgb_config])
		
		return self.__tm_call(sequence, *args)
	
	def tm_primer(self, sequence, concentration=None, mgb=False):
		args = [self.tm_util_path,
		        '-con', str(concentration or self.params[TM_CONFIG_PARAM_PRIMER_CONC]),
		        '-salt', str(self.params[TM_CONFIG_PARAM_SALT])]
		return self.__tm_call(sequence, *args)
	
	def __tm_call(self, sequence, *args):
		tf = tempfile.NamedTemporaryFile()
		tf.write('QTools-tm %s' % sequence)
		tf.flush()
		process_args = list(args) + ['-iraw', tf.name]
		retval = None

		try:
			prog_output = subprocess.check_output(process_args)
		except subprocess.CalledProcessError, e:
			return None
		
		for line in prog_output.split('\n'):
			if line.startswith('QTools-tm'):
				toks = line.strip().split()
				retval = float(toks[-1])
		tf.close()
		return retval
			

