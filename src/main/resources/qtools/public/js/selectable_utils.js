var SelectableUtils = {
	bindElementSelected: function(selectable, f, options) {
		var action = 'selectableselected'
		var mode = 'default'
		if(options && options['mode']) {
			mode = options['mode']
		}
		selectable.bind(action+'.'+mode, function(event, ui) {
			var el = ui['selected']
			f.call(el, options)
		});
	},

	unbindElementSelected: function(selectable, options) {
		var action = 'selectableselected'
		var mode = 'default'
		if(options && options['mode']) {
			mode = options['mode']
		}
		selectable.unbind(action+'.'+mode);
	},

	elements: function(selectable) {
		var filter = selectable.selectable('option', 'filter')
		var els = []
		selectable.find(filter).each(function(i, e) {
			var selectee = $.data(e, 'selectable-item');
			if(selectee) {
				els.push(e);
			}
		});
		return els;
	},

	selectedElements: function(selectable) {
		var filter = selectable.selectable('option', 'filter')
		var els = []
		selectable.find(filter).each(function(i, e) {
			var selectee = $.data(e, 'selectable-item');
			if(selectee && selectee.selected) {
				els.push(e);
			}
		});
		return els;
	},

	unselectedElements: function(selectable) {
		var filter = selectable.selectable('option', 'filter')
		var els = []
		selectable.find(filter).each(function(i, e) {
			var selectee = $.data(e, 'selectable-item');
			if(selectee && !selectee.selected) {
				els.push(e);
			}
		});
		return els;
	}
}