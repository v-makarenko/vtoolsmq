"""
Helper methods to display genomic sequences.
"""
from qtools.lib.helpers.html import recursive_class_tag
from qtools.lib.helpers.numeric import *

__all__ = ['amplicon_length_vdisp','primer_tm_vdisp','probe_tm_vdisp',
           'intra_primer_delta_tm_vdisp','primer_probe_delta_tm_vdisp',
           'oligo_dg_vdisp','amplicon_dg_vdisp','gc_content_vdisp']

OK = 'validation_ok'
WARN = 'validation_warn'
UHOH = 'validation_uhoh'
UNKNOWN = 'validation_unknown'


def __merge_class_attrs(klass, **attrs):
	if 'class_' in attrs:
		attrs['class_'] = "%s %s" % (klass, attrs['class_'])
	else:
		attrs['class_'] = klass
	# way to return keyword args?
	return attrs

def amplicon_length_vdisp(length=None, *tags, **attrs):
	if not length:
		klass = UNKNOWN
	elif length < 120:
		klass = OK
	elif length >= 120 and length < 150:
		klass = WARN
	else:
		klass = UHOH
	return recursive_class_tag(tags, str(length) if length else 'Unknown', **__merge_class_attrs(klass, **attrs))

def primer_tm_vdisp(tm=None, *tags, **attrs):
	if not tm:
		klass = UNKNOWN
	elif tm >= 58.95 and tm < 63.05:
		klass = OK
	elif (tm > 55 and tm < 58.95) or tm >= 63.05:
		klass = WARN
	else:
		klass = UHOH

	return recursive_class_tag(tags, sig1(tm) if tm else 'Unknown', **__merge_class_attrs(klass, **attrs))

# TODO add SNP precision
def probe_tm_vdisp(tm=None, *tags, **attrs):
	if attrs.pop('snp', False):
		max_tm = 68.05
	else:
		max_tm = 70.05
	if not tm:
		klass = UNKNOWN
	elif tm >= 64.95 and tm < max_tm:
		klass = OK
	else:
		klass = WARN
	return recursive_class_tag(tags, sig1(tm) if tm else 'Unknown', **__merge_class_attrs(klass, **attrs))

def intra_primer_delta_tm_vdisp(fp_tm=None, rp_tm=None, *tags, **attrs):
	if not fp_tm or not rp_tm:
		klass = UNKNOWN
		diff = None
	else:
		diff = abs(rp_tm-fp_tm)
		if abs(rp_tm-fp_tm) < 2:
			klass = OK
		else:
			klass = WARN
	return recursive_class_tag(tags, sig1(diff) if diff is not None else 'Unknown', **__merge_class_attrs(klass, **attrs))

def primer_probe_delta_tm_vdisp(primer_tm=None, probe_tm=None, *tags, **attrs):
	if not primer_tm or not probe_tm:
		klass = UNKNOWN
		diff = None
	else:
		diff = probe_tm-primer_tm
		if diff > 1:
			klass = OK
		elif diff > 0:
			klass = WARN
		else:
			klass = UHOH

	return recursive_class_tag(tags, sig1(diff) if diff is not None else 'Unknown', **__merge_class_attrs(klass, **attrs))

def oligo_dg_vdisp(dg=None, *tags, **attrs):
	if dg is None:
		klass = UNKNOWN
	elif dg == 0:
		klass = OK
	else:
		klass = WARN
	return recursive_class_tag(tags, sig2(dg) if dg is not None else 'Unknown', **__merge_class_attrs(klass, **attrs))

def amplicon_dg_vdisp(dg=None, *tags, **attrs):
	if dg is None:
		klass = UNKNOWN
	elif dg >= -2:
		klass = OK
	elif dg >= -4 and dg < -2:
		klass = WARN
	else:
		klass = UHOH
	return recursive_class_tag(tags, sig2(dg) if dg is not None else 'Unknown', **__merge_class_attrs(klass, **attrs))

def gc_content_vdisp(gc=None, *tags, **attrs):
	if gc is None:
		klass = UNKNOWN
	if gc >= 40 and gc <= 60:
		klass = OK
	elif (gc >= 35 and gc < 40) or (gc > 60 and gc <= 65):
		klass = WARN
	else:
		klass = UHOH
	return recursive_class_tag(tags, "%s%%" % sig0(gc) if gc is not None else 'Unknown', **__merge_class_attrs(klass, **attrs))

def max_overlap_vdisp(overlap=None, *tags, **attrs):
	"""
	Assumes output comes from max_overlap function (len, (off, off))
	"""
	if overlap is None:
		klass = UNKNOWN
	elif overlap[0] < 6:
		klass = OK
	elif overlap[0] < 8:
		klass = WARN
	else:
		klass = UHOH

	return recursive_class_tag(tags, str(overlap[0]) if overlap is not None else 'Unknown', **__merge_class_attrs(klass, **attrs))