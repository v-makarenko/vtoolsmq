def populate_multiform_context(controller, source):
	"""
	For each set s of variables in source that are lists,
	populate the template context with variable 's_length',
	which is the length of the variable list.
	"""
	c = controller._py_object.tmpl_context
	for k, v in source.items():
		if isinstance(v, list) or isinstance(v, tuple):
			setattr(c, '%s_length' % k, len(v))