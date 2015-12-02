import numpy as np
import operator

from pyqlb.factory import QLNumpyObjectFactory
from pyqlb.nstats.peaks import fam_amplitudes, cluster_1d
from scipy.optimize import curve_fit
#from qtools.lib.ext.gaussfitter import onedgaussfit

def gauss(x, *p):
    A, mu, sigma = p
    return A*np.exp(-(x-mu)**2/(2*sigma**2))

def amp_bins(amps, num_bins=129, max_dynamic_range=32767):
    """
    bins the amplitudes into num_bins number of bins,
    the width of which is (dynamic_range*2/num_bins).
    The double is to ensure that all possible values in
    the dynamic range are captured, even if the mean is
    zero.
    """
    mean = np.mean(amps)
    bins = np.arange(num_bins)*((max_dynamic_range*2.0)/num_bins)
    bins = [b-(max_dynamic_range-mean) for b in bins]
    return bins

# does this exist in numpy?
def bin_centers(bins):
    return [(bins[i]+bins[i+1])/2.0 for i in range(len(bins)-1)]

def fam_variation(well):
    amps = fam_amplitudes(well.peaks)
    mean = np.mean(amps)
    bins = amp_bins(amps, num_bins=129)
    histvals, histpos = np.histogram(amps, bins=bins)
    histposp = bin_centers(histpos)

    #params, model, errors, chisq = onedgaussfit(histpos[1:], histvals,
    #                                            fixed=[True,False,True,False],
    #                                            params=[0, max(histvals), np.mean(amps), histposp[1]-histposp[0]])

    (gamp, gmean, gsigma), covar = curve_fit(gauss, histposp, histvals, p0=[max(histvals), mean, histposp[1]-histposp[0]])
    # c1 from matlab is sqrt(2)*sigma, as (sqrt(2)*sigma)**2 = 2*sigma**2-- lines up with Klint's calc.
    # real sigma is c1/sqrt(2)
    return gsigma/gmean

def peak_count(bins, min_peak_val=0):
    """
    Determine whether a distribution has more than one peak. Really rough.
    TODO: add dip size, figure out flat tops.  Sucks.
    """
    db = [bins[i+1]-bins[i] for i in range(len(bins)-1)]
    dbp = [db[i+1]*db[i] for i in range(len(db)-1)]

    # ignore flat top valleys, known bug but I'm counting on it for a histogram
    minmax_idx = [idx+1 for idx, db2 in enumerate(dbp) if db2 < 0]
    local_maxima = [(idx, bins[idx]) for idx in minmax_idx if db[idx] < 0]
    local_minima = [(idx, bins[idx]) for idx in minmax_idx if db[idx] > 0]
    
    # ignore dipsize for now
    return len([lmax for lmax in local_maxima if lmax[1] >= min_peak_val])
    




def fam_variation_splits(well, threshold=None):
    """
    Returns a 8-tuple: the gaussian parameters (A, mu, sigma) overall,
    then for the first half of the amplitudes, then for the second half;
    the overall mean, mean of the first half and the
    mean of the second half, and the number of peaks on each half.
    """
    from scipy.optimize import curve_fit
    
    if threshold is not None:
        positives, negatives = cluster_1d(well.peaks, 0, threshold)
        peaks = positives
    else:
        peaks = well.peaks

    amps = fam_amplitudes(peaks)
    first_half = amps[:len(amps)/2]
    second_half = amps[len(amps)/2:]

    fbins = amp_bins(first_half, num_bins=257)
    fvals, fpos = np.histogram(first_half, bins=fbins)
    fcenters = bin_centers(fpos)

    sbins = amp_bins(second_half, num_bins=257)
    svals, spos = np.histogram(second_half, bins=sbins)
    scenters = bin_centers(spos)

    abins = amp_bins(amps, num_bins=257)
    avals, apos = np.histogram(amps, bins=abins)
    acenters = bin_centers(apos)

    (gamp1, gmean1, gsigma1), covar = curve_fit(gauss, fcenters, fvals, p0=[max(fvals), np.mean(first_half), fpos[1]-fpos[0]])
    (gamp2, gmean2, gsigma2), covar = curve_fit(gauss, scenters, svals, p0=[max(svals), np.mean(second_half), spos[1]-spos[0]])
    (gamp, gmean, gsigma), covar = curve_fit(gauss, acenters, avals, p0=[max(avals), np.mean(amps), apos[1]-apos[0]])

    return ((gamp, gmean, gsigma),
            (gamp1, gmean1, gsigma1),
            (gamp2, gmean2, gsigma2),
            np.mean(amps),
            np.mean(first_half),
            np.mean(second_half),
            peak_count(fvals, min_peak_val=max(fvals)/3),
            peak_count(svals, min_peak_val=max(svals)/3))