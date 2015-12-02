"""
Extensions to formencode.variabledecode to play a
little nicer with htmlfill.
"""
from formencode import variabledecode

def clean_variable_encode(encoded):
	"""
	For variabledecode.variable_encoded dicts, get rid
	of the empty subdicts.
	"""
	for k, v in encoded.items():
		if v is None:
			encoded.pop(k)
		elif isinstance(v, dict):
			clean_variable_encode(v)
	
	return encoded

def variable_encode_except(formvars, *exclude_vars, **kwargs):
	formvars_copy = dict(formvars)
	formvars_keep = dict()
	for var in exclude_vars:
		if var in formvars_copy:
			formvars_keep[var] = formvars_copy.pop(var)
	
	encoded = variabledecode.variable_encode(formvars_copy, **kwargs)
	encoded.update(formvars_keep)
	return encoded
	