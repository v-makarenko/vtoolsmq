function capitalize(str) {
	return str.charAt(0).toUpperCase() + str.slice(1);
}

var ConsumableUI = function(el, state) {
	this.defaults = {};
	this.consumables = [];
	this.consumableIdx = -1;
	this.orientation = 0; // 0, 1, 2, 3
	this.state = "consumable"
	this.cursor = null;
	this.cursorEnabled = false;

	var default_keys = ['lotName', 'lotDate', 'lotBondingTemp', 'dg', 'dg_run'];

	if(arguments.length > 2) {
		var options = arguments[2];
		for(var k in default_keys) {
			if(options[k]) {
				this.defaults[k] = options[k];
			}
			else {
				this.defaults[k] = ''
			}
		}
	}

	this.initUI(el);
	if(state) {
		this.initState(state);
	}
	else {
		this.initState({});
	}
}

ConsumableUI.prototype.initState = function(state) {
	for(var i=0; i<state.length;i++) {
		this.addConsumable(state[i], false);
	}
	this.refreshStateUI();
	this.refreshUI();
}

ConsumableUI.prototype.initUI = function(el) {
	this.ui = $(el);
	this.plate = $(el).find('.consumable_plate');
	this.cursor = $(el).find('.consumable_cursor');
	var self = this;
	$(self.ui).find('.consumable_hook_state').live('click',
		function() {
			var rel = $(this).attr('rel');
			self.state = rel;
			self.refreshStateUI();
		}
	);
	$(self.ui).find('.consumable_hook_add').live('click',
		function() {
			var rel = $(this).attr('rel');
			self['add'+capitalize(rel)].call(self);
		}
	);
	$(self.ui).find('.consumable_hook_action').live('click',
	    function(evt) {
			var rel = $(this).attr('rel');
			// invoke options?
			self[rel].call(self, this);
		}
	);
	$(self.ui).find('.consumable_chip td').each(function(i, e) {
		$(e).bind('click', function() {
			var rel = parseInt($(this).attr('rel'));
			if(rel >= 1 && rel <= 8) {
				self.togglePipette(rel-1);
			}
			else if(rel == 0) {
				// move to function?
				for(var i=0;i<8;i++) {
					self.unpipette(i);
				}
			}
			else {
				// move to function?
				for(var i=0;i<8;i++) {
					self.pipette(i);
				}
			}
			self.refreshChannelUI();
			self.refreshCursorUI();
		});
	});

	this.refreshChannelUI();
	this.refreshCursorDimensions();
}

ConsumableUI.prototype.refreshUI = function() {
	this.refreshChannelUI();
	this.refreshCursorUI();
	this.refreshPlateUI();
	this.refreshTableUI();
}

ConsumableUI.prototype.rotateRight = function(evt) {
	if(this.orientation == 0) {
		this.orientation = 3;
	}
	else {
		this.orientation--;
	}
	this.refreshCursorUI();
}

ConsumableUI.prototype.rotateLeft = function(evt) {
	if(this.orientation == 3) {
		this.orientation = 0;
	}
	else {
		this.orientation++;
	}
	this.refreshCursorUI();
}

ConsumableUI.prototype.consumableMove = function(evt) {
	var x = evt.pageX;
	var y = evt.pageY;
	var offset = this.plate.offset();
	this.cursor.css({left: (x-offset.left)+'px',
			         top: (y-offset.top)+'px'});
}

ConsumableUI.prototype.consumableClick = function(evt) {
	var x = evt.pageX;
	var y = evt.pageY;
	var offset = this.plate.offset();
	var w = this.cursor.find('td:first').outerWidth();
	var h = this.cursor.find('td:first').outerHeight();
	var col = parseInt(Math.round((x-offset.left) / w));
	var row = parseInt(Math.round((y-offset.top) / h))-1;
	var cc = this.consumables[this.consumableIdx];
	var c = cc.wells;
	var letterA = "A"

	var cw = this.getCursorWidth()
	var co = this.getCursorOffset()
	if(this.orientation % 2 == 1) {
		var rowStr = String.fromCharCode(letterA.charCodeAt(0)+row);
		for(var i=0;i<c.length;i++) {
			var cellCol = this.orientation == 1 ? (col+i-co) : ((col+cw)-(i-co+1))
			if(c[i] == 'pipette') {
				if(cellCol >=1 && cellCol <= 12) {
					if(cellCol < 10) {
						var cellStr = rowStr + '0' + cellCol;
					}
					else {
						var cellStr = rowStr + cellCol
					}
					// TODO: add method to get consumable, channel for well;
					// check to see if there is no override
					c[i] = cellStr;
				}
			}
		}
	}
	else {
		for(var i=co;i<(co+cw);i++) {
			var cellRow = this.orientation == 0 ? (row+i-co) : ((row+cw)-(i-co+1));
			var cellRowStr = String.fromCharCode(letterA.charCodeAt(0)+cellRow);
			if(c[i] == 'pipette') {
				if(cellRow >= 0 && cellRow <= 7) {
					if(col < 10) {
						var cellStr = cellRowStr + '0' + col;
					}
					else {
						var cellStr = cellRowStr + col;
					}
					c[i] = cellStr;
				}
			}
		}
	}
	this.placeConsumable(this.consumableIdx, cc);
}

ConsumableUI.prototype.chipAt = function(idx) {
	return $(this.ui).find('.consumable_chip td[rel='+(idx+1)+']');
}

ConsumableUI.prototype.bindCursor = function() {
	var self = this;
	this.plate.mouseenter(function() {
		$(this).bind('mousemove', function(evt) {
			self.consumableMove.call(self, evt);
		});
		$(this).bind('click', function(evt) {
			self.consumableClick.call(self, evt);
		});
		self.cursor.css('display','block')
	})
	this.plate.mouseleave(function() {
		$(this).unbind('mousemove');
		$(this).unbind('click');
		self.cursor.hide()
	});
	this.cursorEnabled = true;
}

ConsumableUI.prototype.unbindCursor = function() {
	this.plate.unbind('mouseenter');
	this.plate.unbind('mouseleave');
	this.cursorEnabled = false;
}

ConsumableUI.prototype.refreshChannelUI = function() {
	if(this.consumables.length > 0) {
		$('.consumable_chip').css('visibility', 'visible');
		if(!this.cursorEnabled) {
			this.bindCursor();
		}
	}
	else {
		$('.consumable_chip').css('visibility', 'hidden');
		$(this.ui).find('.consumable_chip_number').text('');
		return;
	}
	$(this.ui).find('.consumable_chip_number').text(this.consumableIdx+1);
	var c = this.consumables[this.consumableIdx].wells;
	for(var i=0;i<c.length;i++) {
		if(!c[i]) {
			this.chipAt(i).removeClass('selected placed');
		}
		else if(c[i] == 'pipette') {
			this.chipAt(i).removeClass('placed');
			this.chipAt(i).addClass('selected');
		}
		else {
			this.chipAt(i).removeClass('placed');
			this.chipAt(i).addClass('placed');
		}
	}
}

ConsumableUI.prototype.refreshStateUI = function() {
	var ui = this.ui;
	$('.consumable_palette_panel').hide();
	switch(this.state) {
		case "start":
			$(ui).find('.consumable_palette_start').show()
			break;
		case "enterbag":
			// todo: shortcuts for UI elements?
			$(ui).find('.consumable_palette_bag').show()
			break;
		case "consumable":
			$(ui).find('.consumable_palette_consumable').show();
			break;
		
	}
}

ConsumableUI.prototype.refreshTableUI = function() {
	var rowTable = $(this.ui).find('#consumable_lot_numbers');
	var rows = $(rowTable).find('tr.consumable_info_row');
	var len = this.consumables.length;
	var diff = len-(rows.length-1)
	if(diff > 0) {
		for(var i=diff;i>0;i--) {
			var c = this.consumables[len-i]
			// copy last row, add id
			var last = $(rowTable).find('tr.consumable_info_row:last')
			var next = last.clone()
			next.attr('id', last.attr('id').substring(0,15) + (parseInt(last.attr('id').substring(15))+1))
			next.find('input.consumable_batch').val(c.batch)
			next.find('input.consumable_date').val(c.date).attr('id','').removeClass('hasDatepicker').datepicker();
			next.find('input.consumable_bonding_temp').val(c.temp)
			next.find('input.consumable_dg_run').val(c.dg_run)
			next.find('select.consumable_dg').val(c.dg)
			next.find('td.consumable_info_num').text((len-i)+1)
			$(rowTable).append(next)
		}
	}
	if(diff < 0) {
		for(var i=0;i>diff;i--) {
			$(rowTable).find('tr.consumable_info_row:last').remove()
		}
	}
}

ConsumableUI.prototype.addConsumable = function(c) {
	if(!c) {
		var cc = {'batch': this.defaults['lotName'],
		     'date': this.defaults['lotDate'],
		     'temp': this.defaults['lotBondingTemp'],
		     'wells': [null,null,null,null,null,null,null,null],
		     'dg': this.defaults['dg'],
		     'dg_run': this.defaults['dg_run']
		    };
	}
	// decorate time if old format -- temporary hack
	else if($.isArray(c)) {
		var cc = {'batch': this.defaults['lotName'],
	         'date': this.defaults['lotDate'],
	         'temp': this.defaults['lotBondingTemp'],
	         'wells': c,
	         'dg': this.defaults['dg'],
	         'dg_run': this.defaults['dg_run']
	        }
	}
	else {
		// temporary hack
		if(typeof(c.dg) == 'undefined') {
			c.dg = this.defaults['dg']
			c.dg_run = this.defaults['dg_run']
		}
		var cc = c;
	}
	this.consumables.push(cc);
	this.selectConsumable(this.consumables.length-1)

	if(arguments.length <= 2 || arguments[2] != false) {
		this.refreshUI();
	}
}

ConsumableUI.prototype.placeConsumable = function(idx, c) {
	this.consumables[idx] = c;
	this.refreshUI();
}

ConsumableUI.prototype.selectConsumable = function(idx) {
	this.consumableIdx = idx;
	this.refreshChannelUI();
	this.refreshCursorUI();
}

ConsumableUI.prototype.refreshCursorUI = function() {
	this.refreshCursorDimensions();
	this.refreshCursorContent();
}

ConsumableUI.prototype.refreshPlateUI = function() {
	this.plate.find('#plate_map td[class!="row_name"]').html('&nbsp;').attr('class', '');
	for(var i=0;i<this.consumables.length;i++) {
		var c = this.consumables[i].wells;
		for(var j=0;j<c.length;j++) {
			if(c[j] && c[j] != 'pipette') {
				var c_num = i+1;
				var ch_num = j+1;
				var cell_class = c_num+"_"+ch_num;
				this.plate.find('td[id$="'+c[j]+'"]').addClass('placed c'+cell_class).text((i+1)+'-'+(j+1));
			}
		}
	}
}

ConsumableUI.prototype.getCursorWidth = function() {
	if(this.consumableIdx == -1) {
		return 0;
	}
	var c = this.consumables[this.consumableIdx].wells;

	var first = -1;
	var last = -1;
	var w = 0;
	for(var i=0;i<c.length;i++) {
		if(c[i] == 'pipette' && first == -1) {
			first = i;
		}
		if(c[i] == 'pipette') {
			last = i;
		}
	}
	if(first != -1) {
		if(last == -1) {
			w = c.length - first;
		}
		else {
			w = (last-first)+1;
		}
	}
	return w;
}

ConsumableUI.prototype.getCursorOffset = function() {
	if(this.consumableIdx == -1) {
		return 0;
	}
	var c = this.consumables[this.consumableIdx].wells;

	for(var i=0;i<c.length;i++) {
		if(c[i] == 'pipette') {
			return i;
		}
	}
	return 0;
}

ConsumableUI.prototype.refreshCursorDimensions = function() {
	// TODO: cache all finds?
	var cur = this.cursor;
	cur.find('tr').remove();
	var w = this.getCursorWidth();
	if(this.orientation % 2 == 0) {
		for(var i=0;i<w;i++) {
			cur.append("<tr><td>&nbsp;</td></tr>");
		}
		cur.css('width','auto');
	}
	else {
		var tr = $('<tr></tr>');
		for(var i=0;i<w;i++) {
			tr.append("<td>&nbsp;</td>");
		}
		cur.append(tr);
		cur.css('width',(w*46+2)+'px');
	}
}

ConsumableUI.prototype.refreshCursorContent = function() {
	// TODO: will have to truncate if a subset selected because of left, upper overhang
	// (td display: none)
	var cur = $(this.ui).find('.consumable_cursor');
	var w = this.getCursorWidth();
	var f = this.getCursorOffset();
	if(this.consumableIdx == -1) {
		cur.find('td').html('&nbsp;')
		return;
	}
	var c = this.consumables[this.consumableIdx].wells

	for(var i=0;i<w;i++) {
		var col = this.orientation > 1 ? (w-1)-i : i;
		var td = cur.find('td:eq('+col+')');
		if(c[i+f] == 'pipette') {
			td.text((this.consumableIdx+1)+'-'+(i+f+1));
		}
		else {
			td.html('&nbsp;');
		}
	}
}

ConsumableUI.prototype.fillVertical = function() {
	this.clear()
	var consumables = [['A01','B01','C01','D01','E01','F01','G01','H01'],
	                    ['A02','B02','C02','D02','E02','F02','G02','H02'],
	                    ['A03','B03','C03','D03','E03','F03','G03','H03'],
	                    ['A04','B04','C04','D04','E04','F04','G04','H04'],
	                    ['A05','B05','C05','D05','E05','F05','G05','H05'],
	                    ['A06','B06','C06','D06','E06','F06','G06','H06'],
	                    ['A07','B07','C07','D07','E07','F07','G07','H07'],
	                    ['A08','B08','C08','D08','E08','F08','G08','H08'],
	                    ['A09','B09','C09','D09','E09','F09','G09','H09'],
	                    ['A10','B10','C10','D10','E10','F10','G10','H10'],
	                    ['A11','B11','C11','D11','E11','F11','G11','H11'],
	                    ['A12','B12','C12','D12','E12','F12','G12','H12']];

	for(var i=0;i<consumables.length;i++) {
		this.addConsumable(consumables[i], false);
	}
	this.consumableIdx = 11;
	this.refreshUI();
}

ConsumableUI.prototype.fillHorizontal = function() {
	this.consumables = [['A01','A02','A03','A04','A05','A06','A07','A08'],
	                    ['A09','A10','A11','A12','B01','B02','B03','B04'],
	                    ['B05','B06','B07','B08','B09','B10','B11','B12'],
	                    ['C01','C02','C03','C04','C05','C06','C07','C08'],
	                    ['C09','C10','C11','C12','D01','D02','D03','D04'],
	                    ['D05','D06','D07','D08','D09','D10','D11','D12'],
	                    ['E01','E02','E03','E04','E05','E06','E07','E08'],
	                    ['E09','E10','E11','E12','F01','F02','F03','F04'],
	                    ['F05','F06','F07','F08','F09','F10','F11','F12'],
	                    ['G01','G02','G03','G04','G05','G06','G07','G08'],
	                    ['G09','G10','G11','G12','H01','H02','H03','H04'],
	                    ['H05','H06','H07','H08','H09','H10','H11','H12']];


	this.consumableIdx = 11;
	this.refreshUI();
}

ConsumableUI.prototype.clear = function() {
	this.consumables = []
	this.consumableIdx = -1;
	this.refreshUI();
}

ConsumableUI.prototype.pipette = function(idx) {
	var c = this.consumables[this.consumableIdx].wells
	if(c[idx] == null) {
		c[idx] = 'pipette';
	}
}

ConsumableUI.prototype.unpipette = function(idx) {
	var c = this.consumables[this.consumableIdx].wells
	if(c[idx] == 'pipette') {
		c[idx] = null;
	}
}

ConsumableUI.prototype.togglePipette = function(idx) {
	var c = this.consumables[this.consumableIdx].wells;
	if(!c[idx]) {
		this.pipette(idx);
	}
	else {
		this.unpipette(idx);
	}
}

ConsumableUI.prototype.updateLotData = function() {
	var self = this;
	$('tr.consumable_info_row').each(function(i, row) {
		var id = parseInt($(row).attr('id').substring(15));
		if(id == 0) {
			return true;
		}
		self.consumables[id-1].batch = $(row).find('.consumable_batch').val()
		self.consumables[id-1].date = $(row).find('.consumable_date').val()
		self.consumables[id-1].temp = $(row).find('.consumable_bonding_temp').val()
		self.consumables[id-1].dg = $(row).find('.consumable_dg').val()
		self.consumables[id-1].dg_run = $(row).find('.consumable_dg_run').val()
	})
}

ConsumableUI.prototype.applyConsumableInfoAll = function(src) {
	var row = $(src).parents('tr')
	var batch = row.find('.consumable_batch').val()
	var date = row.find('.consumable_date').val()
	var temp = row.find('.consumable_bonding_temp').val()
	var dg = row.find('.consumable_dg').val()
	$(this.ui).find('.consumable_info_row input.consumable_batch').val(batch)
	$(this.ui).find('.consumable_info_row input.consumable_date').val(date)
	$(this.ui).find('.consumable_info_row input.consumable_bonding_temp').val(temp)
	$(this.ui).find('.consumable_info_row select.consumable_dg').val(dg)
	this.defaults['lotName'] = batch
	this.defaults['lotDate'] = date
	this.defaults['lotBondingTemp'] = temp
	this.defaults['dg'] = dg
}

ConsumableUI.prototype.applyConsumableInfoDown = function(src) {
	var row = $(src).parents('tr')
	var id = parseInt(row.attr('id').substring(15))
	var batch = row.find('.consumable_batch').val()
	var date = row.find('.consumable_date').val()
	var temp = row.find('.consumable_bonding_temp').val()
	var dg = row.find('.consumable_dg').val()
	$(this.ui).find('.consumable_info_row').each(function(i, r) {
		var rid = parseInt($(r).attr('id').substring(15))
		if(rid > id) {
			$(r).find('.consumable_batch').val(batch);
			$(r).find('.consumable_date').val(date);
			$(r).find('.consumable_bonding_temp').val(temp);
			$(r).find('.consumable_dg').val(dg)
		}
	});
}

ConsumableUI.prototype.getData = function() {
	this.updateLotData();
	return this.consumables;
}