"""
Methods for computing delta-G of a sequence.
"""
import subprocess, tempfile

from qtools.components.interfaces import DeltaGCalculator
from qtools.constants.deltag import DG_CONFIG_PARAM_SALT, DG_CONFIG_PARAM_TEMP
from qtools.lib.bio import reverse_complement

# TODO phase out
def dg_seq(config, seq):
    return dg_call(config, seq, '0.1','60')

# TODO phase out
def dg_assay(config, assay):
    return (dg_seq(config, assay.primer_fwd),
            dg_seq(config, assay.primer_rev),
            dg_seq(config, assay.probe_seq))

# TODO phase out
def dg_pcr_sequence(config, pcr_seq):
    """
    Add the dg to the PCR sequence.
    """
    pcr_seq.dg = dg_seq(config, pcr_seq.amplicon.sequence)
    return pcr_seq

# TODO phase out
def dg_call(config, seq, salt, temp):
    tm_util_path = config['qtools.bin.venpipe_util']
    vpar_config = config['qtools.bin.venpipe_vpar']
    tf = tempfile.NamedTemporaryFile()
    tf.write('QTools-tm %s' % seq)
    tf.flush()
    args = [tm_util_path, '-vpar', vpar_config, '-salt', salt, '-temp', temp, '-iraw', tf.name]
    retval = None
    try:
        output = subprocess.check_output(args)
    except subprocess.CalledProcessError, e:
        return None
    
    for line in output.split('\n'):
        if line.startswith('QTools-tm'):
            toks = line.strip().split()
            retval = float(toks[-1])
    tf.close()
    return retval

# definition order matters for metaclass stuff
class CommandLineDriver(DeltaGCalculator):
    def __init__(self, component_manager):
        config = component_manager.pylons_config
        self.params = component_manager.dg_config
        self.venpipe_util_path = config['qtools.bin.venpipe_util']
        self.venpipe_vpar_config = config['qtools.bin.venpipe_vpar']
    
    def delta_g(self, sequence, temp=None):
        tf = tempfile.NamedTemporaryFile()
        tf.write('QTools-tm %s' % sequence)
        tf.flush()
        args = [self.venpipe_util_path,
                '-vpar', self.venpipe_vpar_config,
                '-salt', str(self.params[DG_CONFIG_PARAM_SALT]),
                '-temp', str(temp or self.params[DG_CONFIG_PARAM_TEMP]),
                '-iraw', tf.name]
        retval = None

        try:
            output = subprocess.check_output(args)
        except subprocess.CalledProcessError, e:
            return None
        
        for line in output.split('\n'):
            if line.startswith('QTools-tm'):
                toks = line.strip().split()
                retval = float(toks[-1])
        tf.close()
        return retval
