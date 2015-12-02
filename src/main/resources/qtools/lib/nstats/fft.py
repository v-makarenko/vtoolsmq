import numpy as np

def find_peak_window_indices(data, window_size):
	n = len(data) % window_size
	if n == 0:
		num_arrays = len(data) / window_size
		tail = np.zeros(0)
	else:
		num_arrays = (len(data) / window_size)+1
		tail = np.zeros(window_size-n)
	
	tailed = np.hstack((data, tail))
	windows = np.split(tailed, num_arrays)
	return np.array([(i*window_size)+np.argmax(w) for i, w in enumerate(windows)])

def find_peak_indices(data, window_size):
	peak_indices = find_peak_window_indices(data, window_size)
	peaks = data[peak_indices]
	outer_peak_indices = peak_indices.take(np.argsort(peaks))[::-1]
	return outer_peak_indices

