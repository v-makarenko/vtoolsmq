from collections import defaultdict
from qtools.lib.inspect import class_properties
from qtools.model import WellMetric, WellChannelMetric

def replicate_well_records(qlbplate):
	"""
	Given a QLBPlate, return the QLBWell objects that are
	technical replicates based off the sample names and targets
	of the well.  The key is a 2-tuple (sample, targets), and
	the value are the list of wells which have those samples
	and targets.
	"""
	replicate_dict = defaultdict(list)
	for well in qlbplate.wells:
		targets = tuple([c.target for c in well.channels])
		replicate_dict[(well.sample_name, targets)].append(well)

	return replicate_dict

def replicate_well_record_names(qlbplate):
	"""
	Same as replicate_well_records, except only track the
	name of the well.
	"""
	replicate_dict = replicate_well_records(qlbplate)
	return dict([(k,[well.well_name for well in v]) for k, v in replicate_dict.items()])

def rowwise_well_records(qlbplate):
	"""
	Return the subset of wells in the plate by row.
	"""
	rowwise_dict = defaultdict(list)
	for well in qlbplate.wells:
		row = well.well_name[0]
		rowwise_dict[row].append(well)

	return rowwise_dict

def rowwise_well_record_names(qlbplate):
	"""
	Same as rowwise_well_records, except only track the names of the available
	wells per row, not the QLBWell object itself.
	"""
	rowwise_dict = rowwise_well_records(qlbplate)
	return dict([(k,[well.well_name for well in v]) for k, v in rowwise_dict.items()])

def colwise_well_records(qlbplate):
	"""
	Return the subset of wells in the plate by column.
	"""
	colwise_dict = defaultdict(list)
	for well in qlbplate.wells:
		col = well.well_name[1:]
		colwise_dict[col].append(well)

	return colwise_dict

def colwise_well_record_names(qlbplate):
	"""
	Same as colwise_well_records, except only track the names of the available
	wells per row, not the QLBWell object itself.
	"""
	colwise_dict = colwise_well_records(qlbplate)
	return dict([(k,[well.well_name for well in v]) for k, v in colwise_dict.items()])

def samplewise_well_records(qlbplate):
	"""
	Given a QLBPlate, return the QLBWell objects that are
	technical replicates based off the sample name.
	"""
	replicate_dict = defaultdict(list)
	for well in qlbplate.wells:
		replicate_dict[well.sample_name].append(well)

	return replicate_dict

def samplewise_well_record_names(qlbplate):
	"""
	Same as samplewise_well_records, except only track the
	names of the available wells, not the QLBWell object
	itself.
	"""
	samplewise_dict = samplewise_well_records(qlbplate)
	return dict([(k,[well.well_name for well in v]) for k, v in samplewise_dict.items()])

def targetwise_well_records(qlbplate, channel_num):
	"""
	Given a QLBPlate, return the QLBWell objects that are
	technical replicates based off the target name in the
	specified channel.
	"""
	replicate_dict = defaultdict(list)
	for well in qlbplate.wells:
		channel = well.channels[channel_num]
		replicate_dict[(channel.target)].append(well)

	return replicate_dict

def targetwise_well_record_names(qlbplate, channel_num):
	"""
	Same as targetwise_well_records, except only track the names of the available
	wells per row, not the QLBWell object itself.
	"""
	targetwise_dict = targetwise_well_records(qlbplate, channel_num)
	return dict([(k,[well.well_name for well in v]) for k, v in targetwise_dict.items()])

def get_well_metric_col_info(name):
	"""
	Return the column info on the WellMetric object for the
	particular name.

	TODO: put on WellMetric object itself?
	"""
	if name in WellMetric.__mapper__.columns:
		return WellMetric.__mapper__.columns[name]
	elif name in dict(class_properties(WellMetric)):
		return getattr(WellMetric, name).fget
	else:
		return None

def get_well_metric_col_accessor(name, multiply_percent=True):
	"""
	Returns a function that will extract the correct value
	from the well metric given the specified name, based on
	the information on the column (e.g., whether it should
	be expressed as a percent)
	
	It would probably be easier just to have a convention for
	columns that represent a percent to have a _pct suffix.
	"""
	col_info = get_well_metric_col_info(name)
	if col_info is None:
		return lambda wm: None

	if multiply_percent:
		percent_attr = getattr(col_info, 'info', {}).get('percent', False)
		multiplier = 100 if percent_attr else 1
	else:
		multiplier = 1
	return lambda wm: getattr(wm, name, 0)*multiplier

def get_well_channel_metric_col_info(name):
	"""
	Return the column info on the WellChannelMetric object for the
	particular name.

	TODO: put on WellChannelMetric object itself?
	"""
	if name in WellChannelMetric.__mapper__.columns:
		return WellChannelMetric.__mapper__.columns[name]
	elif name in dict(class_properties(WellChannelMetric)):
		return getattr(WellChannelMetric, name).fget
	else:
		return None

def get_well_channel_metric_col_accessor(name, multiply_percent=True):
	"""
	Returns a function that will extract the correct value
	from the well channel metric given the specified name, based on
	the information on the column (e.g., whether it should
	be expressed as a percent)
	
	It would probably be easier just to have a convention for
	columns that represent a percent to have a _pct suffix.
	"""
	col_info = get_well_channel_metric_col_info(name)
	if col_info is None:
		return lambda wcm: None

	if multiply_percent:
		percent_attr = getattr(col_info, 'info', {}).get('percent', False)
		multiplier = 100 if percent_attr else 1
	else:
		multiplier = 1
	return lambda wcm: getattr(wcm, name, 0)*multiplier

