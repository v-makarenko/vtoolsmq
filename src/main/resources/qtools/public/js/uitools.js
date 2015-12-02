(function($) {
    // converts selects to autocomplete dropdowns.
    // requires jQuery, jQuery UI
    // TODO: maybe check for UI?
    $.fn.autoselect = function(options) {
        var auto_id = 'auto_' + $(this).attr('id');
	    var self = this;
	    var val = self.children(":selected").text();
	    var input = $('<input class="autocomplete" id="'+auto_id+'" type="text" value="'+val+'" />')
	    var vals = $.map($(this).children('option'), function(o) {
		    return {'label': $(o).text(),
		            'value': $(o).val()
			       };
	    })
	    $(self).change(function() {
			$(input).val(self.children(":selected").text())
	    })
	    $(input).autocomplete({
		    source: vals,
		    delay: 0,
		    select: function(event, ui) {
			    $(self).val(ui.item.value)
			    return false;
		    },
		    // override to show 
		    focus: function(event, ui) {
			    $(input).val(ui.item.label);
			    return false;
		    }
	    })
	    $(this).after(input)
	    
	    if(options && options['toggleSelect']) {
	        var toggle_select = options['toggleSelectText'] || "Show All"
	        var toggle_input = options['toggleInputText'] || "AutoComplete"
	        var toggle_id = 'toggle_' + $(this).attr('id');
	        var toggle = $('<a href="#" class="autoselect_toggle" id="'+toggle_id+'">'+toggle_select+'</a>')
	        toggle.toggle(function() {
	            $(self).show();
	            $(input).hide();
	            $(this).text(toggle_input)
	            return false;
	        }, function() {
	            $(self).hide();
	            $(input).show();
	            $(this).text(toggle_select)
	            return false;
	        });
	        $(input).after(toggle);
	        
    	    if(options && options['toggleMode'] == "select") {
                toggle.click();
    	    }
    	    else {
    	    	// TODO: this may not be the intended thing in all cases
    	    	toggle.click();
    	    	toggle.click();
    	    }
    	    
    	    if(options && options['attrs']) {
    	        for(var v in options['attrs']) {
    	            $(input).attr(v, options['attrs'][v])
    	        }
    	    }
	    }
	};

	// todo: rewrite this like jQuery UI (first param = method call)
	$.fn.autoselect_get = function() {
		var self = $(this);
		var input = $(this).siblings("input")[0]
		if(self.is(":hidden")) {
			return $(input).val()
		}
		else {
			return self.val();
		}
	};

	$.fn.autoselect_set = function(val) {
		var self = $(this)
		var input = $(this).siblings("input")[0]
		var toggle = $(this).siblings(".autoselect_toggle")[0]
		if(self.is(':visible')) {
			if(self.find('option[value="'+val+'"]').length == 0) {
				$(toggle).click();
				$(input).val(val);
			}
			else {
				$(self).val(val);
				$(input).val(val);
			}
		}
		else {
			if(self.find('option[value="'+val+'"]').length != 0) {
				$(self).val(val);
			}
			$(input).val(val);
		}
	};
	
	// change the submit values such that if the value
	// of the text field isn't in the select, signal
	// the value-- and let the backend deal with it
	// (it can either throw an error on validate, or
	// create a new record)
	//
	// should be bound to a form.
	$.fn.submit_autoselect = function(evt) {
	    // TODO: test if this is a form.
	    var self = $(this);
	    $(this).find('.autocomplete').each(function() {
	        var id = $(this).attr('id')
	        var select = $(this).siblings("select")[0]
	        if($(select).is(':hidden')) {
	            // window focus submission issue
	            var vals = $.map($(select).children('option'), function(o) { return $(o).text() })
	            var text = $(this).val()
                var text_id = $.inArray(text, vals)
                if(text_id == -1) {
	                // switch value submitted
	                var formName = $(select).attr('name')
	                $(select).attr('name', "old_"+formName)
	                $(this).attr('name', formName)
	                
	                var input = this
	                // ugly back button hack
	                $(window).focus(function() {
	                    $(input).attr('name', '');
	                    $(select).attr('name', formName)
	                })
	            }
                else {
                    // ensure things line up
                    $(select)[0].selectedIndex = text_id;
                }
	        }
	    });
	    return true;	
	};
	
	$.fn.autoselect_response = function(json) {
	    var self = $(this);
	    $(this).find('.autocomplete').each(function() {
	        var name = $(this).attr('name')
	        var select = $(this).siblings("select")[0]
	        if($(select).attr('name').indexOf('old_') == 0) {
	            var value = $(this).val()
	            $(this).attr('name', '')
	            $(select).attr('name', name)
	            
	            var vals = $.map($(select).children('option'), function(o) { return $(o).text() })
	            if($.inArray(json[name], vals) == -1) {
	                var inserted = false;
	                var children = $(select).children('option')
	                for(var i=0;i<children.length;i++) {
	                    if($(children[i]).text().toLowerCase() > value.toLowerCase()) {
	                        $('<option selected="selected" value="'+json[name]+'">'+value+'</option>').insertBefore($(children[i]))
	                        inserted = true;
	                        break;
	                    }
	                }
	                if(!inserted) {
	                    $(select).append('<option selected="selected" value="'+json[name]+'">'+value+'</option>')
	                }
	                
	                var vals = $.map($(select).children('option'), function(o) {
            		    return {'label': $(o).text(),
            		            'value': $(o).val()
            			       };
            	    })
            	    $(this).autocomplete('option', 'source', vals);
	            }
	        }
	    })
	}
})(jQuery);