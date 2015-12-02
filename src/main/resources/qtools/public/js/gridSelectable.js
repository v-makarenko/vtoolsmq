(function($) {
	var selectAll = function(el, fil, elements) {
		var filter = fil || el.selectable('option', 'filter');
		var els = elements ? $(elements) : el.find(filter)
		els.each(function() {
			var selectee = $.data(this, 'selectable-item');
			if(!selectee) {
				return;
			}
			selectee.selected = true;
			selectee.$element.addClass('ui-selected');
		});
	}

	var unselectAll = function(el, fil, elements) {
		var filter = fil || el.selectable('option', 'filter');
		var els = elements ? $(elements) : el.find(filter)
		els.each(function() {
			var selectee = $.data(this, 'selectable-item');
			if(!selectee) {
				return;
			}
			selectee.selected = false;
			selectee.$element.removeClass('ui-selected');
		});
	}

	// this is my first attempt at the plugin, so maybe assume convention (cell content)?
	$.fn.gridSelectable = function() {
		var _top = this.find('.grid_top')
		var _left = this.find('.grid_left')
		var _main = this.find('.grid_main')

		$.fn.selectable.apply(_top, arguments);
		$.fn.selectable.apply(_left, arguments);
		$.fn.selectable.apply(_main, arguments);

		// add column/row handlers for selected, unselected
		var self = this;
		_top.bind('selectablestart', function(event, ui) {
			if(!event.metaKey) {
				unselectAll(_main);
				unselectAll(_left);
			}
		});
		_top.bind('selectableselected', function(event, ui) {
			var el = $(ui['selected'])
			var idx = el.closest('th').index()-1 // top corner on row
			if(idx == -1) {
				selectAll(_main);
			}
			else {
				var cols = [];
				var col = _main.find('tr.row').each(function() {
					cols.push($(this).children('td:eq('+idx+')').children('.ui-selectee').get(0));
				});
				selectAll(_main, null, cols);
			}
		});

		_top.bind('selectableunselected', function(event, ui) {
			var el = $(ui['unselected'])
			var idx = el.closest('th').index()-1 // top corner on row
			if(idx == -1) {
				unselectAll(_main);
			}
			else {
				var cols = [];
				var col = _main.find('tr.row').each(function() {
					cols.push($(this).children('td:eq('+idx+')').children('div.ui-selectee').get(0));
				});
				unselectAll(_main, null, cols);
			}
		});

		_top.bind('selectablestop', function(event, ui) {
			self.trigger('gridselectablechanged');
		});

		_left.bind('selectablestart', function(event, ui) {
			if(!event.metaKey) {
				unselectAll(_top);
				unselectAll(_main);
			}
		});

		// add column/row handlers for selected, unselected
		_left.bind('selectableselected', function(event, ui) {
			var el = $(ui['selected'])
			var idx = el.closest('tr').index()
			selectAll(_main, null, _main.children('tbody')
			                            .children('tr.row:eq('+idx+')')
			                            .children('td')
			                            .children('.ui-selectee'));
		});

		_left.bind('selectableunselected', function(event, ui) {
			var el = $(ui['unselected'])
			var idx = el.closest('tr').index()
			unselectAll(_main, null, _main.children('tbody')
			                            .children('tr.row:eq('+idx+')')
			                            .children('td')
			                            .children('.ui-selectee'));
		});

		_left.bind('selectablestop', function(event, ui) {
			self.trigger('gridselectablechanged');
		});

		_main.bind('selectableselected', function(event, ui) {
			if(!event.metaKey) {
				unselectAll(_top);
				unselectAll(_left);
			}
		});

		_main.bind('selectablestop', function(event, ui) {
			self.trigger('gridselectablechanged');
		});

		return {'topBar': _top,
	            'leftBar': _left,
	            'grid': _main};
	}
})(jQuery);