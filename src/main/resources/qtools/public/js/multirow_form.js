(function($) {

    var MultiRowForm = function(container, copyNames) {
        this.container = $(container);
        this.copyNames = copyNames;

        this.initHandlers();
        this.correctNumbering();
        this.correctButtons();
    }

    MultiRowForm.prototype.initHandlers = function() {
        var c = this.container;
        var self = this;
        c.delegate('.add_row', 'click', function() {
            var parent = $(this).parents('tr');
            self.insertRow(parent);
            return false;
        })
        c.delegate('.rm_row', 'click', function() {
            var parent = $(this).parents('tr');
            self.deleteRow(parent);
            return false;
        })

        c.submit(function() {
            self.prepareForSubmit();
            return true;
        })
    }

    MultiRowForm.prototype.correctButtons = function() {
        var c = this.container;
        c.find('.add_row').css('visibility', 'hidden');
        c.find('tr:last-child .add_row').css('visibility', 'visible');
        var len = c.find('tbody tr').length;
        var rm_row = c.find('.rm_row');
        if(len <= 2) {
            rm_row.css('visibility', 'hidden')
        }
        else {
            rm_row.css('visibility', 'visible')
        }
    }

    MultiRowForm.prototype.correctNumbering = function() {
        var c = this.container;
        c.find('tbody tr').each(function(idx, el) {
            if($(el).is('.sample_row')) {
                return true;
            }
            var index = idx-1;
            $(el).removeAttr('id').attr('id', 'row'+index);
            var inputs = $(el).find('input, select');
            inputs.each(function(jdx, el2) {
                var currentName = $(el2).attr('name');
                var prefix = currentName.substring(0, currentName.indexOf('-')+1);
                var suffix = currentName.substring(currentName.indexOf('.'));
                $(el2).attr('name', prefix+index+suffix)
            });
        });
    }

    MultiRowForm.prototype.insertRow = function(row) {
        var sample_row = this.container.find('.sample_row');
        var newRow = sample_row.clone(false).removeClass('sample_row');
        if($(row).is('.sample_row')) {
            var index = 0;
        }
        else {
            var index = parseInt($(row).attr('id').substring(3))+1;
        }
        newRow.attr('id','row'+index)
        for(var i=0;i<this.copyNames.length;i++) {
            var input = newRow.find('input.'+this.copyNames[i]+', select.'+this.copyNames[i]);
            if(!input) {
                continue;
            }
            // TODO allow override of how the sample row is named?
            input.attr('name', input.attr('name').replace('X',index));
        }
        newRow.insertAfter(row);
        this.correctButtons();
        this.container.trigger('multiRowAdded', newRow);
        return newRow;
    }

    MultiRowForm.prototype.deleteRow = function(row) {
        row.remove();
        this.container.trigger('multiRowDeleted', row);
        this.correctNumbering();
        this.correctButtons();
    }

    MultiRowForm.prototype.prepareForSubmit = function() {
        this.container.find('.sample_row').remove();
    }

    $.fn.multiRowForm = function(copyNames) {
        return new MultiRowForm(this, copyNames);
    }

})(jQuery);


