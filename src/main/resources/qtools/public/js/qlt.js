var QLTDialogForm = function(el) {
	this.ui = $(el);
	// TODO transition to classes?

	this.defaults = {};
	var self = this;
	$('.as_is_type, .as_is_value').each(function(i, e) {
		var id = $(this).attr('id');
		self[id] = $(this);
		self.defaults[id] = $(this).val();
	});

	this.fam_target.autoselect({'toggleSelect': true, 'toggleMode': 'select', 'toggleInputText': 'Type', 'toggleSelectText': 'All'});
	this.vic_target.autoselect({'toggleSelect': true, 'toggleMode': 'select', 'toggleInputText': 'Type', 'toggleSelectText': 'All'});
	this.enzyme.autoselect({'toggleSelect': true, 'toggleMode': 'select', 'toggleInputText': 'Type', 'toggleSeelctText': 'All'})

	this.ui.dialog({autoOpen: false,
	          position: 'top',
	          show: 'fade',
	          hide: 'fade',
	          height: 200,
	          title: 'Enter Well Information',
	          width: 940});
	
	self.ui.find('#tabs').tabs();
	self.ui.find( ".tabs-bottom .ui-tabs-nav, .tabs-bottom .ui-tabs-nav > *" )
			.removeClass( "ui-corner-all ui-corner-top" )
			.addClass( "ui-corner-bottom" );


	$(el).find('.as_is_value').focus(function() {
		var id = $(this).attr('id')
		self.defaults[id] = $(this).val()
	});

	$(el).find('#auto_fam_target, #auto_vic_target, #auto_enzyme').live('focus', function() {
		var id = $(this).attr('id').substring(5)
		self.defaults[id] = $(this).val()
	});

	$(el).find('input.as_is_value').blur(function() {
		self.inputTextChanged(this);
	});

	$(el).find('#auto_fam_target, #auto_vic_target, #auto_enzyme').live('blur', function() {
		self.inputTextChanged(this);
	});

	$(el).find('select.as_is_value').change(function() {
		self.selectTextChanged(this);
	});

	$(el).find('select.as_is_type').change(function() {
		var id = $(this).attr('id')
		self.ui.trigger("typeChanged", {'element': id, 'key': $(this).val()});
	});

	$(el).find('#clear_button').click(function() {
		self.clear();
	});

	$(el).find('#update_button').click(function() {
		// todo fix (look for defaults?)
		var regions = ['sample_name', 'fam_target', 'vic_target', 'exp_type_name',
		               'fam_type', 'vic_type']
		for(var i=0;i<regions.length;i++) {
			var widget = self.ui.find('#'+regions[i]);
			if(self.ui.find('#'+regions[i]+'_region').is('.enabled_region')) {
				if($(widget).is('.autoselect')) {
					var val = $(widget).autoselect_get();
				}
				else {
					var val = $(widget).val();
				}
				if(regions[i].lastIndexOf('type') == regions[i].length-4) {
					self.ui.trigger('typeChanged', {'element': regions[i], 'key': val})
				}
				else {
					self.ui.trigger('valueChanged', {'element': regions[i], 'key': val})
				}
			}
		}
		//self.ui.dialog('close')
	});

	$(el).find('.disabled_message a').click(function() {
		var region = $(this).parents('.disabled_region')
		$(region).removeClass('disabled_region').addClass('enabled_region')
		$(region).find('input:visible, select:visible').focus()
		return false;
	})

}

// this could be more functional, little clunky at present
QLTDialogForm.prototype.clear = function() {
	this.sample.val('')
	this.fam_target.val('')
	this.fam_type.val('Not Used')
	this.vic_target.val('')
	this.vic_type.val('Not Used')
	this.exp_type_name.val('')
	this.ui.find('#conditions-tab input, #additives-tab input, #expected-tab input').val('')
	this.ui.find('#auto_fam_target, #auto_vic_target, #auto_enzyme').val('')
	this.ui.trigger("clear");
	this.ui.find('.disabled_region').each(function(i, e) {
		$(e).removeClass('disabled_region').addClass('enabled_region')
	});
}

QLTDialogForm.prototype.inputTextChanged = function(source) {
	var val = $(source).val()
	var id = $(source).attr('id');
	if(id.indexOf('auto') == 0) {
		id = id.substring(5);
	}
	var klass = id;
	this.ui.trigger("valueChanged", {'element': klass, 'val': val, 'key': val});
}

QLTDialogForm.prototype.dataSelected = function(data) {
	for(var d in data) {
		var region = this.ui.find('#'+d+"_region");
		if(data[d].length > 1) {
			$(region).removeClass('enabled_region').addClass('disabled_region');
		}
		else {
			$(region).removeClass('disabled_region').addClass('enabled_region'); 
		}
	}
	$(this.fam_target).autoselect_set(data['fam_target'][0]);
	$(this.vic_target).autoselect_set(data['vic_target'][0]);
	$(this.enzyme).autoselect_set(data['enzyme'][0]);
	for(d in data) {
		if(d != 'fam_target' && d != 'vic_target' && d != 'enzyme' && data[d].length == 1) {
			if(this[d]) {
				this[d].val(data[d][0])
			}
		}
	}

}

QLTDialogForm.prototype.selectTextChanged = function(source) {
	var val = $(source).val()
	var id = $(source).attr('id')
	var name = $(source).find('option[value="'+val+'"]').text();
	this.ui.trigger("valueChanged", {'element': id, 'val': name, 'key': val});
}