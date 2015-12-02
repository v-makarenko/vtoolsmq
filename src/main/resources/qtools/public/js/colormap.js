var LinearSegmentedColormap = function(map) {
	// linear segmented colormap
	// compatible with matplotlib.cm but interpolates (does not precompute lookup table-- yet)
	var segment_sorter = function(a, b) {
		return a[0]-b[0];
	}
	
	this.transferFunc = function(val) { return val; }
	this.outOfBounds = [1.0, 1.0, 1.0]
	this.min = null;
	this.max = null;

	if(arguments.length > 1) {
		$.extend(this, arguments[1])
	}

	this.red = map[0].sort(segment_sorter)
	this.green = map[1].sort(segment_sorter)
	this.blue = map[2].sort(segment_sorter)

	// naive implementation: look up each time

	// todo: out of bounds color (add to options)
	this.getComponent = function(norm, segments, outOfBounds) {
		for(var i=0;i<segments.length;i++) {
			if(norm == segments[i][0]) {
				return segments[i][1];
			}
			else if(norm < segments[i][0]) {
				if(i == 0) {
					break;
				}
				var low = segments[i-1][2];
				var high = segments[i][1];
				var lowAmt = (norm-segments[i-1][0])/(segments[i][0]-segments[i-1][0])
				return (lowAmt*high)+((1-lowAmt)*low)
			}
		}
		return outOfBounds;
	}
}

LinearSegmentedColormap.prototype.rgb = function(val) {
	if(this.min != null) {
		if(val < this.min) {
			val = this.min
		}
	}
	if(this.max != null) {
		if(val > this.max) {
			val = this.max
		}
	}
	return this.rgbNorm(this.transferFunc(val))
}

LinearSegmentedColormap.prototype.rgbNorm = function(norm) {
	// assume normalized value for now
	// get red
	var red = 0;
	var green = 0;
	var blue = 0;

	return [Math.round(this.getComponent(norm, this.red)*255, this.outOfBounds[0]),
	        Math.round(this.getComponent(norm, this.green)*255, this.outOfBounds[1]),
	        Math.round(this.getComponent(norm, this.blue)*255, this.outOfBounds[2])]
}

var StdevSegmentedColormap = function(map, bounds) {
	if(arguments.length > 2) {
		var options = arguments[2];
	}
	else {
		var options = {};
	}
	options.min = -1*bounds;
	options.max = bounds;
	var transferFunc = function(val) {
		var diff = options.max-options.min;
		return (val-options.min)/diff;
	}
	options.transferFunc = transferFunc;
	LinearSegmentedColormap.prototype.constructor.call(this, map, options);
}
StdevSegmentedColormap.prototype = LinearSegmentedColormap.prototype;

StdevSegmentedColormap.prototype.rgbStdev = function(val, mean, stdev) {
	var stdev_diff = (val-mean)/stdev;
	return this.rgb(stdev_diff);
}

LinearSegmentedColormap.jet =
	[[[0.0, 0.25, 0.25],
	  [0.35, 0.25, 0.25],
	  [0.66, 1.0, 1.0],
	  [0.89, 1.0, 1.0],
      [1, 0.75, 0.75]],
     [[0.0, 0.5, 0.5],
      [0.125, 0.5, 0.5],
      [0.375, 1.0, 1.0],
      [0.64, 1.0, 1.0],
      [0.91, 0.25, 0.25],
      [1.0, 0.25, 0.25]],
     [[0.0, 1.0, 1.0],
      [0.11, 1.0, 1.0],
      [0.34, 1.0, 1.0],
      [0.65, 0.25, 0.25],
      [1.0, 0.25, 0.25]]];