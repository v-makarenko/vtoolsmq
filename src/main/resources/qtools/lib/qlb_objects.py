"""
Extensions of pyqlb.objects.*, which have additional
attributes derived from the sample/target names in
the QLP file.  Only QTools cares about those values;
they go along for the ride in QuantaSoft.

Allowing a custom user-defined value dictionary in
QLP files, like the construct allowed for QLB files,
would eliminate the need for these custom name
trickery.
"""
from pyqlb.objects import QLPlate, QLWell, QLWellChannel
from pyqlb.constants import ROWCOL_ORDER_COL, ROWCOL_ORDER_ROW

__all__ = ['ExperimentMetadataQLPlate','ExperimentMetadataQLWell',
           'make_abs_duplex_well','make_unused_channel','make_unknown_channel',
           'make_blank_channel','make_fam_abs_singleplex_well',
           'make_reference_channel','make_unused_well','make_vic_abs_singleplex_well',
           'make_empty_plate','singlecolor_label_funcs']

def metadata_property(key):
	def getter(self):
		return self.metadata_dict.get(key, None)
	
	def setter(self, val):
		if val is None:
			self.metadata_dict.pop(key, None)
		else:
			self.metadata_dict[key] = str(val)
		self._dumps_metadata_dict()
	
	return property(getter, setter)

class ExperimentMetadataQLPlate(QLPlate):
	"""
	Class which uses the file comment field to store plate metadata.
	Includes convenience decorated attributes.
	"""
	def __init__(self, *args, **kwargs):
		super(ExperimentMetadataQLPlate, self).__init__(*args, **kwargs)
		self._file_description = kwargs.get('file_description', None)
		self._load_metadata_dict()

		for arg in ('plate_setup_id', 'plate_template_id'):
			if kwargs.get(arg, None):
				setattr(self, arg, kwargs[arg])
	
	def _dumps_metadata_dict(self):
		# different than QLWell in that the file description metadata
		# will be the sum total of the file description (no need to
		# support an additional 'sample' parameter)
		#
		# could use urllib here?
		if self.metadata_dict:
			self._file_description = '&'.join(["%s=%s" % (k, v) for k, v in sorted(self.metadata_dict.items())])
		else:
			self._file_description = None
	
	def _load_metadata_dict(self):
		# could use urllib here?
		self.metadata_dict = {}
		if not self._file_description:
			return
		
		try:
			toks = self._file_description.split('&')
			for part in toks:
				key, val = part.split('=')
				self.metadata_dict[key] = val
		except ValueError, e:
			return
	
	def get_file_description(self):
		return self._file_description
	
	def set_file_description(self, fd):
		self._file_description = fd
		self._load_metadata_dict()
	
	file_description = property(get_file_description, set_file_description)

	plate_setup_id = metadata_property('plate_setup_id')
	plate_template_id = metadata_property('plate_template_id')


class ExperimentMetadataQLWell(QLWell):
	"""
	Class which uses the experiment comment field to store well metadata.
	Includes convenience decorated attributes.
	"""
	def __init__(self, *args, **kwargs):
		super(ExperimentMetadataQLWell, self).__init__(*args, **kwargs)
		self._sample_name = kwargs.get('sample_name', None)
		self._load_metadata_dict()

		# TODO: could metadata_property side-effect class such that
		# this list could be computed automatically?
		for arg in ('sample', 'temperature', 'enzyme', 'enzyme_conc',
		            'additive', 'additive_conc', 'expected_cpd', 'expected_cpul',
                    'dg_cartridge', 'mastermix'):
			if kwargs.get(arg, None):
				setattr(self, arg, kwargs[arg])
	
	def _dumps_metadata_dict(self):
		if self.metadata_dict:
			if(self.metadata_dict.get('sample', None)):
				sample = self.metadata_dict.get('sample')
			else:
				sample = None
			
			trail = '|'.join(["%s:%s" % (k,v) for k, v in sorted(self.metadata_dict.items()) if k is not 'sample'])
			if sample and trail:
				self._sample_name = ';'.join((sample, trail))
			elif sample:
				self._sample_name = sample
			else:
				self._sample_name = trail
		else:
			self._sample_name = None
	
	def _load_metadata_dict(self):
		self.metadata_dict = {}
		if not self._sample_name:
			return
		
		try:
			sample = None
			trail = None
			toks = self._sample_name.split(';')
			if len(toks) == 2:
				sample, trail = toks
			elif len(toks) == 1:
				if ':' in toks[0]:
					sample = None
					trail = toks[0]
				else:
					sample = toks[0]
					trail = None
			
			if sample:
				self.metadata_dict['sample'] = sample
			if trail:
				for part in trail.split('|'):
					key, val = part.split(':')
					self.metadata_dict[key] = val
		except ValueError, e:
			self.metadata_dict = {'sample': self._sample_name}
	
	def get_sample_name(self):
		return self._sample_name
	
	def set_sample_name(self, val):
		self._sample_name = val
		self._load_metadata_dict()
	
	sample_name = property(get_sample_name, set_sample_name)

	sample = metadata_property('sample')
	temperature = metadata_property('Temp')
	enzyme = metadata_property('RE')
	enzyme_conc = metadata_property('REConc')
	additive = metadata_property('W')
	additive_conc = metadata_property('WConc')
	expected_cpd = metadata_property('Cp/d')
	expected_cpul = metadata_property('Cp/uL')

def make_empty_plate(run_order=ROWCOL_ORDER_ROW):
    """
    Make an empty QLPlate, ideal for using as a canvas
    on which to replace wells.

    :param run_order: The run order (by row or by col, see QLPlate
    :return: A QLPlate with 96 empty wells.
    """
    plate = QLPlate(acquisition_order=run_order)
    for row in ('A','B','C','D','E','F','G','H'):
        for col in range(1,13):
            well_name = '%s%s' % (row, str(col).zfill(2))
            plate.wells[well_name] = make_unused_well(well_name)
    return plate

def make_unused_well(well_name):
    well = QLWell(well_name)
    well.channels[0] = make_unused_channel(0)
    well.channels[1] = make_unused_channel(1)
    well.processed = True
    return well

def make_fam_abs_singleplex_well(well_name, sample_name, fam_target=None):
    well = QLWell(well_name,
        sample_name=sample_name,
        experiment_name='ABS',
        experiment_type=QLWell.EXP_TYPE_ABSOLUTE_QUANTITATION)
    well.channels[0] = make_unknown_channel(0, target=fam_target)
    well.channels[1] = make_unused_channel(1)
    well.processed = True
    return well

def make_vic_abs_singleplex_well(well_name, sample_name, vic_target=None):
    well = QLWell(well_name,
        sample_name=sample_name,
        experiment_name='ABS',
        experiment_type=QLWell.EXP_TYPE_ABSOLUTE_QUANTITATION)
    well.channels[0] = make_unused_channel(0)
    well.channels[1] = make_unknown_channel(1, target=vic_target)

    well.processed = True
    return well

def make_abs_duplex_well(well_name, sample_name, fam_target=None, vic_target=None):
    well = QLWell(well_name,
        sample_name=sample_name,
        experiment_name='ABS',
        experiment_type=QLWell.EXP_TYPE_ABSOLUTE_QUANTITATION)
    well.channels[0] = make_unknown_channel(0, target=fam_target)
    well.channels[1] = make_unknown_channel(1, target=vic_target)

    well.processed = True
    return well

def make_unknown_channel(channel_num, target=None):
    channel = QLWellChannel(channel_num=channel_num,
        type=QLWellChannel.TARGET_TYPE_UNKNOWN)
    if target:
        channel.target = target
    return channel

def make_reference_channel(channel_num, target=None):
    channel = QLWellChannel(channel_num=channel_num,
        type=QLWellChannel.TARGET_TYPE_REFERENCE)
    if target:
        channel.target = target
    return channel

def make_unused_channel(channel_num):
    return QLWellChannel(channel_num=channel_num,
        type=QLWellChannel.TARGET_TYPE_NOT_USED)

def make_blank_channel(channel_num):
    return QLWellChannel(channel_num=channel_num,
        type=QLWellChannel.TARGET_TYPE_BLANK)

# TODO: this should move along with QLTWriter
def singlecolor_label_funcs(red, green, blue):
    """
    Returns sensible coloring functions for a
    QLT.  This will color the experiment descriptor
    with white text and the background specified
    by RGB for wells that have an experiment type.

    :param red: 0-255.
    :param green: 0-255.
    :param blue: 0-255.
    :return: (fgcolorfunc, bgcolorfunc), useful for QLTWriter.
    """
    def _fg(well):
        if well.experiment_name:
            # white
            return {'alpha': 255, 'red': 255, 'green': 255, 'blue': 255}
        else:
            return {'alpha': 0, 'red': 0, 'green': 0, 'blue': 0}

    def _bg(well):
        if well.experiment_name:
            # white
            return {'alpha': 255, 'red': red, 'green': green, 'blue': blue}
        else:
            return {'alpha': 0, 'red': 0, 'green': 0, 'blue': 0}

    return (_fg, _bg)
