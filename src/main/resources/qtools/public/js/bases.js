// TODO: make jQuery plugin instead?
var BaseViewer = function(positive_sequence, negative_sequence, prefix_idx, suffix_idx) {
    this.posWindow = new BaseWindow('posWindow', positive_sequence, prefix_idx, suffix_idx, '+')
    this.negWindow = new BaseWindow('negWindow', negative_sequence, prefix_idx, suffix_idx, '-')
    this.seqLength = positive_sequence.length
    this.sliceWindow = new SliceWindow('sliceWindow', 10, this.seqLength)
    this.active = false
}

BaseViewer.prototype.bindTo = function(el) {
    var self = this;
    this.bound = $(el);
    var bound = this.bound;
    var onBarMove = function(evt) {
        self.onBarMove.call(self, evt)
    }
    this.bound.hover(function(evt) {
        if(!self.active) {
            self.onBarEnter.call(self, evt)
            bound.bind("mousemove", onBarMove)
            self.active = true
        }
    }, function(evt) {
        if(self.active) {
            self.active = false
            bound.unbind("mousemove", onBarMove)
            self.onBarExit.call(self, evt)
        }
    })
    
    $(bound).append(this.posWindow.dom())
    $(bound).append(this.negWindow.dom())
    $(bound).append(this.sliceWindow.dom())
}

BaseViewer.prototype.fixWindows = function(clientX) {
    var ww = this.posWindow.width();
    var bw = $(this.bound).width();
    var off = $(this.bound).offset();
    var posX = clientX-off.left-(ww/2)
    if(posX < 0) {
        posX = 0
    }
    else if(posX+ww > bw) {
        posX = bw-ww
    }
    this.posWindow.moveXTo(posX);
    this.negWindow.moveXTo(posX);
}

BaseViewer.prototype.fixTextWindows = function(clientX) {
    var sw = this.sliceWindow.width();
    var bw = $(this.bound).width();
    var off = $(this.bound).offset();
    var posW = clientX-off.left-(sw/2.0)
    if(posW < 0) {
        posW = 0;
    }
    else if(posW+sw > bw) {
        posW = bw-sw
    }
    this.sliceWindow.moveXTo(posW);
    this.posWindow.moveTextToRatio(posW/bw)
    this.negWindow.moveTextToRatio(posW/bw)
}

BaseViewer.prototype.onBarEnter = function(evt) {
    this.fixWindows(evt.clientX);
    this.posWindow.show();
    this.negWindow.show();
    this.fixTextWindows(evt.clientX);
    this.sliceWindow.show()
}

BaseViewer.prototype.onBarExit = function(evt) {
    this.posWindow.hide();
    this.negWindow.hide();
    this.sliceWindow.hide();
}

BaseViewer.prototype.onBarMove = function(evt) {
    this.fixWindows(evt.clientX)
    this.fixTextWindows(evt.clientX)
}

var BaseWindow = function(id, sequence, prefix_idx, suffix_idx, strand) {
    this.sequence = sequence
    this.prefix_idx = prefix_idx
    this.suffix_idx = suffix_idx
    this.strand = strand
    this.el = this.createElement(id)
    this.textWindow = $(this.el).find('.baseWindow');
}

BaseWindow.prototype.dom = function() {
    return this.el
}

BaseWindow.prototype.show = function() {
    $(this.el).show();
}

BaseWindow.prototype.hide = function() {
    $(this.el).hide();
}

BaseWindow.prototype.moveXTo = function(x) {
    $(this.el).css('left', x+'px');
    return this;
}

BaseWindow.prototype.width = function() {
    return $(this.el).width()
}

BaseWindow.prototype.moveTextToRatio = function(pct) {
    var width = $(this.textWindow).width();
    var left = -1*pct*width;
    // hack for now -- look for window pane?
    if(width+left < 96) {
        left = -1*(width-96)
    }
    $(this.textWindow).css('left',left+'px');
}

BaseWindow.prototype.createElement = function(id) {
    var container = document.createElement('div');
    $(container).addClass("baseWindow").attr('id', id).append(
        '<span class="window_prefix">'+this.sequence.substring(0,this.prefix_idx)+"</span>"
        + '<span class="window_amplicon">'+this.sequence.substring(this.prefix_idx, this.suffix_idx)+"</span>"
        + '<span class="window_suffix">'+this.sequence.substring(this.suffix_idx)+"</span>"
    )
    var pane = document.createElement('div');
    $(pane).addClass("baseWindowPane").append(container);
    
    if(this.strand == '+') {
        $(pane).addClass("baseWindowPositive")
    }
    else {
        $(pane).addClass("baseWindowNegative")
    }
    return pane;
}

var subclass = function(otherobj) {
    function F() {}
    F.prototype = otherobj;
    return new F();
}

var SliceWindow = function(id, windowWidth, seqWidth) {
    this.windowWidth = windowWidth;
    this.seqWidth = seqWidth;
    this.ratio = (100.0*windowWidth)/seqWidth;
    this.el = this.createElement(id)
}

SliceWindow.prototype.createElement = function(id) {
    var slice = document.createElement('div');
    $(slice).addClass("sliceWindow").css('width', this.ratio+'%')
    return slice;
}

// TODO: BaseWindow, SliceWindow can have common superclass
SliceWindow.prototype.dom = function() {
    return this.el
}

SliceWindow.prototype.show = function() {
    $(this.el).show();
}

SliceWindow.prototype.hide = function() {
    $(this.el).hide();
}

SliceWindow.prototype.moveXTo = function(x) {
    $(this.el).css('left', x+'px');
}

SliceWindow.prototype.width = function() {
    return $(this.el).width()
}
