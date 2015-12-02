var mean = function() {
	if(arguments.length == 0) {
		return null;
	}

	var sum = 0.0;
	for(var i=0;i<arguments.length;i++) {
		sum += arguments[i];
	}
	return sum/arguments.length;
}

var stddev = function() {
	if(arguments.length == 0) {
		return null;
	}
	var m = mean.apply(null, arguments)
	var dev = 0;
	for(var i=0;i<arguments.length;i++) {
		dev += Math.pow((arguments[i]-m), 2)
	}
	return Math.sqrt(dev*1.0/arguments.length)
}

var cv = function() {
	if(arguments.length == 0) {
		return null;
	}
	return stddev.apply(null, arguments)/mean.apply(null, arguments)
}

var cv_pct = function() {
	if(arguments.length == 0) {
		return null;
	}
	return cv.apply(null, arguments)*100
}

/**
 * Given an input of [num, mean] arrays,
 * compute the total mean.
 */
var combinedIndependentMean = function() {
	if(arguments.length == 0) {
		return null;
	}
	// oh I see the need for CoffeeScript now
	var prodSum = 0;
	var totalSum = 0
	for(var i=0;i<arguments.length;i++) {
		prodSum = prodSum + (arguments[i][0]*arguments[i][1])
		totalSum = totalSum + arguments[i][0]
	}
	return prodSum/totalSum;
}

/**
 * Given an input of [num, mean, stdev] arrays,
 * compute the total standard deviation of the
 * mean statistics in the total num population.
 */
var combinedIndependentStdDev = function() {
	if(arguments.length == 0) {
		return null;
	}
	var mean_pairs = [];
	var compareTermSum = 0;
	var sigmaSum = 0;
	var sizeSum = 0;
	for(var i=0;i<arguments.length;i++) {
		for(var j=0;j<mean_pairs.length;j++) {
			var compareTerm = mean_pairs[j][0]*arguments[i][0]*(Math.pow((mean_pairs[j][1]-arguments[i][1]), 2))
			compareTermSum += compareTerm;
		}
		mean_pairs.push(arguments[i])
		sigmaSum += arguments[i][0]*Math.pow(arguments[i][2], 2);
		sizeSum += arguments[i][0];
	}
	return Math.sqrt((sigmaSum/sizeSum)+(compareTermSum/(Math.pow(sizeSum, 2))))
}