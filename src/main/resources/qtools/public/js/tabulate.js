var Tabulate = function(table, options) {
	this.table = $(table);
	this.rowOffset = 0;
	this.colOffset = 0;
	this.fixedDigits = 2;

	if(options) {
		if(options['rowOffset']) {
			this.rowOffset = options['rowOffset']
		}

		if(options['colOffset']) {
			this.colOffset = options['colOffset']
		}

		if(options['fixedDigits']) {
			this.fixedDigits = options['fixedDigits']
		}
	}

	this.funcMap = {'mean': mean,
                    'stdev': cv_pct};

	var self = this;
	this.table.find('input').change(function() {
		var col = $(this).closest('td').index()
		var row = $(this).closest('tr').index()
		var toks = $(this).attr('name').split('.')
		var attr = toks[toks.length-1]
		self.updateRowAggregate(row, attr)
		self.updateColAggregate(col, attr)
		self.updateTotalAggregate(attr)
	})
};

Tabulate.prototype.recalcAll = function(rows, cols, attrs) {
	for(var a=0;a<attrs.length;a++) {
		for(var r=this.rowOffset;r<rows+this.rowOffset;r++) {
			this.updateRowAggregate(r, attrs[a])
		}
		for(var c=this.colOffset;c<cols+this.colOffset;c++) {
			this.updateColAggregate(c, attrs[a])
		}
		this.updateTotalAggregate(attrs[a])
	}
}

// TODO maybe make the selector less rigid
Tabulate.prototype.updateRowAggregate = function(row, stat) {
	var self = this;
	var collect = []
	$(this.table).find('tbody tr:eq('+(row-self.rowOffset)+')').find('input.'+stat).each(
		function(idx) {
			var v = parseFloat($(this).val());
			if(!isNaN(v)) {
				collect.push(v)
			}
		}
	);

	if(collect.length > 0) {
		$(this.table).find('tbody tr:eq('+(row-self.rowOffset)+')').find('.row_aggregate_'+stat).each(
			function(i, e) {
				$(this).html(self.funcMap[$(this).attr('rel')].apply(null, collect).toFixed(self.fixedDigits))
			}
		);
	}
}

// TODO figure out how to make the selectors less rigid
Tabulate.prototype.updateColAggregate = function(col, stat) {
	var self = this;
	var collect = []
	$(this.table).find('tbody tr').each(
		function(idx) {
			var c = $(this).find('td:eq('+(col-self.colOffset)+') input.'+stat)
			if(c.length == 0) {
				return;
			}
			var v = parseFloat($(c).val());
			if(!isNaN(v)) {
				collect.push(v)
			}
		}
	);

	if(collect.length > 0) {
		$(this.table).find('tbody tr:last td:eq('+(col-self.colOffset)+') .col_aggregate_'+stat).each(
			function(i, e) {
				$(this).html(self.funcMap[$(this).attr('rel')].apply(null, collect).toFixed(self.fixedDigits));
			}
		);
	}
}

Tabulate.prototype.updateTotalAggregate = function(stat) {
	var self = this;
	var collect = []
	$(this.table).find('input.'+stat).each(
		function(idx) {
			var v = parseFloat($(this).val());
			if(!isNaN(v)) {
				collect.push(v)
			}
		}
	);

	if(collect.length > 0) {
		$(this.table).find('.total_aggregate_'+stat).each(
			function(i, e) {
				$(this).html(self.funcMap[$(this).attr('rel')].apply(null, collect).toFixed(self.fixedDigits));
			}
		);
	}
}