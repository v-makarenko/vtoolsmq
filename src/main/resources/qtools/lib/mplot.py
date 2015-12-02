"""
Methods that make matplotlib graphs.  Includes the functions that
generate 1D and 2D thumbnails, galaxy plots, and everything else
that is a graphic (except for trends, which are JavaScript).
"""
import StringIO, copy, math, operator

from qtools.constants.plot import *

# right here there may be a problem.  As plt is a module-level variable, it is
# not thread-safe, and I've seen cases where thumbnails look weird because
# something else was being drawn at the same time.  This will likely require
# a fair amount of rewriting (or an initialization step before each draw
# method) to fix.
try:
    import numpy as np
    np.seterr(all='ignore')
    from scipy import stats
    from scipy import linalg
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    deps_loaded = True
except ImportError, e:
    pass

cdict = { 'blue' : ((0.0,1.0,1.0),
                       (0.01,0.0,0.0),
                       (0.02,0.0,0.0),
                    (0.746,0.0,0.0),
                    (1.0,1.0,1.0)),
          'green' : ((0.0,1.0,1.0),
                     (0.01,0.0,0.0),
                     (0.02,0.0,0.0),
                     (0.3650789,0.0,0.0),
                     (0.746,1.0,1.0),
                     (1.0,1.0,1.0)),
          'red'   : ((0.0,1.0,1.0),
                     (0.01, 0.0, 0.0),
                     (0.02,0.0,0.0),
                     (0.365,1.0,1.0),
                     (1.0,1.0,1.0))}

def get_cmap(H):
    max_bin = np.max(H)
    return matplotlib.colors.LinearSegmentedColormap('req',cdict,max_bin+1)

def get_plate_cmap(H):
    max_bin = np.max(H)
    smallest = 1.0/(max_bin+1)

    plate_cdict = { 'blue' : [(0.0,1.0,1.0),
                       (0.003,0.1,0.1),
                       (0.01,0.0,0.0),
                       (0.02,0.0,0.0),
                    (0.746,0.0,0.0),
                    (1.0,1.0,1.0)],
          'green' : [(0.0,1.0,1.0),
                     (0.003,0.1,0.1),
                     (0.01,0.0,0.0),
                     (0.02,0.0,0.0),
                     (0.3650789,0.0,0.0),
                     (0.746,1.0,1.0),
                     (1.0,1.0,1.0)],
          'red'   : [(0.0,1.0,1.0),
                     (0.003,0.1,0.1),
                     (0.01, 0.0, 0.0),
                     (0.02,0.0,0.0),
                     (0.365,1.0,1.0),
                     (1.0,1.0,1.0)]}
    
    if smallest*0.9 > 0 and smallest*0.9 < 0.003:
        plate_cdict['blue'].insert(1,(smallest*0.9,0.5,0.5))
        plate_cdict['green'].insert(1,(smallest*0.9,0.5,0.5))
        plate_cdict['red'].insert(1,(smallest*0.9,0.5,0.5))
    if smallest*2.1 > 0 and smallest*2.1 < 0.003:
        plate_cdict['blue'].insert(2,(smallest*2.1,0.2,0.2))
        plate_cdict['green'].insert(2,(smallest*2.1,0.2,0.2))
        plate_cdict['red'].insert(2,(smallest*2.1,0.2,0.2))


    return matplotlib.colors.LinearSegmentedColormap('plate',plate_cdict,max_bin+1)


def __sum_galaxy(ax, peaks, width=560, height=420,
                 min_droplet_width=5, max_droplet_width=20,
                 min_amplitude=100, max_amplitude=64000):
    """
    Base plot for polydispersity.  Add width overlays downstream.
    """
    from pyqlb.nstats.peaks import channel_amplitudes, channel_widths
    
    xs = np.add(channel_amplitudes(peaks, 0), channel_amplitudes(peaks, 1))
    ys = channel_widths(peaks, 0)

    min_amp_log = np.log10(min_amplitude)
    max_amp_log = np.log10(max_amplitude)

    def amplitude_xform(a):
        #return a
        return (width/float(max_amp_log-min_amp_log))*(np.log10(a)-min_amp_log)
    
    def width_xform(w):
        #return w
        return (height/float(max_droplet_width-min_droplet_width))*(w-min_droplet_width)

    if xs is not None and ys is not None:
        H, xedges, yedges = np.histogram2d(ys, np.log10(xs), bins=[height, width], range=[[min_droplet_width, max_droplet_width],[min_amp_log, max_amp_log]])
        ax.imshow(H, origin='lower', cmap=get_plate_cmap(H), interpolation='nearest')
    
    ax.set_xlabel('Sum Amplitude (log scale)')
    ax.axis([min_amp_log, max_amp_log,5,20])
    ax.set_xticks([0,60,139,200,260,339,399,459,539,560])
    ax.set_xticklabels([100,200,500,1000,2000,5000,10000,20000,50000,64000])
    ax.set_yticks([0,84,168,252,336,420])
    ax.set_yticklabels([5,8,11,14,17,20])
    return ax


def galaxy(title, peaks, threshold, min_width_gate, max_width_gate, channel=0,
           quality_gate=None):
    if not deps_loaded:
        return None
    
    fig = plt.figure()
    from pyqlb.nstats.peaks import fam_widths, fam_amplitudes, width_gated, vic_widths, vic_amplitudes, cluster_1d, quality_gated
    if quality_gate is not None:
        peaks = quality_gated(peaks, min_quality_gate=quality_gate)
    
    xs = vic_amplitudes(peaks) if channel == 1 else fam_amplitudes(peaks)
    ys = vic_widths(peaks) if channel == 1 else fam_widths(peaks)
    plt.axis([100,32000,5,20])
    plt.semilogx(xs, ys, marker='.', linewidth=0, markersize=2, color='#333333', alpha=0.33)
    plt.axhline(y=min_width_gate, ls='dashed', color='#0000ff')
    plt.axhline(y=max_width_gate, ls='dashed', color='#0000ff')
    plt.axvline(x=threshold, ls='dashed', color='#ff0000')
    plt.title(title)
    plt.xlabel('%s Amplitude (log scale)' % ('VIC' if channel == 1 else 'FAM'))
    plt.ylabel('Droplet Width (samples)')
    plt.tick_params(width=1, length=8)
    setsize(fig, False)
    return fig

def __graph_polydisperse(ax, peaks, channel, threshold,
                         pos_rain_gate, midhigh_rain_gate, midlow_rain_gate, neg_rain_gate,
                         pos_peaks, midhigh_peaks, midlow_peaks, neg_peaks,
                         width=560, height=420,
                         min_droplet_width=5, max_droplet_width=20,
                         min_amplitude=100, max_amplitude=32000,
                         min_amplitude_excluded=True,
                         highlight_poly=True,
                         draw_count_summary=False):
    """
    Base plot for polydispersity.  Add width overlays downstream.
    """
    from pyqlb.nstats.peaks import channel_amplitudes, channel_widths
    
    xs = channel_amplitudes(peaks, channel)
    ys = channel_widths(peaks, channel)

    min_amp_log = np.log10(min_amplitude)
    max_amp_log = np.log10(max_amplitude)

    def amplitude_xform(a):
        #return a
        return (width/float(max_amp_log-min_amp_log))*(np.log10(a)-min_amp_log)
    
    def width_xform(w):
        #return w
        return (height/float(max_droplet_width-min_droplet_width))*(w-min_droplet_width)

    if xs is not None and ys is not None:
        H, xedges, yedges = np.histogram2d(ys, np.log10(xs), bins=[height, width], range=[[min_droplet_width, max_droplet_width],[min_amp_log, max_amp_log]])
        ax.imshow(H, origin='lower', cmap=get_plate_cmap(H), interpolation='nearest')
    
    num_poly_peaks = 0
    for peakset in (pos_peaks, midhigh_peaks, midlow_peaks, neg_peaks):
        num_poly_peaks = num_poly_peaks + len(peakset)
    
    if highlight_poly:
        for peakset in (pos_peaks, midhigh_peaks, midlow_peaks, neg_peaks):
            amps = [amplitude_xform(a) for a in channel_amplitudes(peakset, channel)]
            widths = [width_xform(w) for w in channel_widths(peakset, channel)]
            ax.plot(amps, widths, marker='o', markersize=3, markeredgewidth=1, linewidth=0, color='#009900', zorder=2)
    

    ax.set_xlabel('%s Amplitude (log scale)' % ('VIC' if channel == 1 else 'FAM'))


    ax.axis([min_amp_log, max_amp_log,5,20])

    prain = (width/(max_amp_log-min_amp_log))*(np.log10(pos_rain_gate)-min_amp_log)
    ax.axvline(x=prain, color='#0099ff', linestyle='dashed')
    if midhigh_rain_gate:
        mhrain = (width/(max_amp_log-min_amp_log))*(np.log10(midhigh_rain_gate)-min_amp_log)
        ax.axvline(x=mhrain, color='#0099ff', linestyle='dashed')
    if midlow_rain_gate:
        mlrain = (width/(max_amp_log-min_amp_log))*(np.log10(midlow_rain_gate)-min_amp_log)
        ax.axvline(x=mlrain, color='#0099ff', linestyle='dashed')
    nrain = (width/(max_amp_log-min_amp_log))*(np.log10(neg_rain_gate)-min_amp_log)
    ax.axvline(x=nrain, color='#0099ff', linestyle='dashed')
    thresh = (width/(max_amp_log-min_amp_log))*(np.log10(threshold)-min_amp_log)
    ax.axvline(x=thresh, color='#990099')

    if draw_count_summary:
        if len(peaks) > 0:
            ax.text(5, height-15, 'Total polydispersity: %.02f%% (%d/%d)' % \
                (float(num_poly_peaks*100)/len(peaks), num_poly_peaks, len(peaks)))
            ax.text(5, height-30, 'Positive large: %d' % len(pos_peaks))
            ax.text(5, height-45, 'Middle large: %d' % len(midhigh_peaks))
            ax.text(5, height-60, 'Middle small: %d' % len(midlow_peaks))
            ax.text(5, height-75, 'Negative small: %d' % len(neg_peaks))
    
    if min_amplitude_excluded:
        ax.text(width-300, 5, 'NOTE: Min amplitude peaks excluded')

    # TODO standardize galaxy
    ax.set_xticks([0,67,156,223,291,379,446,560])
    ax.set_xticklabels([100,200,500,1000,2000,5000,10000,32000])
    ax.set_yticks([0,84,168,252,336,420])
    ax.set_yticklabels([5,8,11,14,17,20])

def __graph_galaxy_width_bins(ax, sum_amplitude_bins=None,
                              width=560, height=420,
                              min_droplet_width=5, max_droplet_width=20,
                              min_amplitude=1000, max_amplitude=32000,
                              other_channel_mean=None):
    min_amp_log = np.log10(min_amplitude)
    max_amp_log = np.log10(max_amplitude)

    def amplitude_xform(a):
        #return a
        return (width/float(max_amp_log-min_amp_log))*(np.log10(a)-min_amp_log)
    
    def width_xform(w):
        #return w
        return (height/float(max_droplet_width-min_droplet_width))*(w-min_droplet_width)

    if sum_amplitude_bins and other_channel_mean:
        binxs = []
        low_binys = []
        high_binys = []

        # TODO: generic?
        amplitude_boundaries= [bin[2] for bin in sum_amplitude_bins]

        # TODO check top end of boundary as well
        amplitude_regions = zip(amplitude_boundaries[:-1], amplitude_boundaries[1:]) \
                            + [(amplitude_boundaries[-1], max_amplitude)]

        for (start, end), (minw, maxw, boundary) in zip(amplitude_regions, sum_amplitude_bins):
            binxs.append(amplitude_xform(max(min_amplitude, start-other_channel_mean)))
            binxs.append(amplitude_xform(max(min_amplitude, end-other_channel_mean)))
            for i in range(2):
                low_binys.append(width_xform(minw))
                high_binys.append(width_xform(maxw))
        
        ax.plot(binxs, low_binys, linestyle='dashed', color='#0000ff')
        ax.plot(binxs, high_binys, linestyle='dashed', color='#0000ff')
        ax.text(width-300, 20, 'Width bins estimated using other channel\'s mean')
    
def galaxy_polydisperse(title, peaks, channel, threshold, min_width_gate, max_width_gate,
                        pos_rain_gate, midhigh_rain_gate, midlow_rain_gate, neg_rain_gate,
                        pos_peaks, midhigh_peaks, midlow_peaks, neg_peaks,
                        width=560, height=420,
                        min_droplet_width=5, max_droplet_width=20,
                        min_amplitude=100, max_amplitude=32000,
                        min_amplitude_excluded=True):
    if not deps_loaded:
        return None
    
    fig = plt.figure()
    ax = fig.add_subplot(111, title=title)
    __graph_polydisperse(ax, peaks, channel, threshold,
                         pos_rain_gate, midhigh_rain_gate, midlow_rain_gate, neg_rain_gate,
                         pos_peaks, midhigh_peaks, midlow_peaks, neg_peaks,
                         width=width, height=height,
                         min_droplet_width=min_droplet_width, max_droplet_width=max_droplet_width,
                         min_amplitude=min_amplitude, max_amplitude=max_amplitude,
                         min_amplitude_excluded=min_amplitude_excluded)
    
    minw = (height/float(max_droplet_width-min_droplet_width))*(min_width_gate-min_droplet_width)
    ax.axhline(minw, linestyle='dashed', color='#0000ff')
    maxw = (height/float(max_droplet_width-min_droplet_width))*(max_width_gate-min_droplet_width)
    ax.axhline(maxw, linestyle='dashed', color='#0000ff')

    setsize(fig, False)
    return fig

def galaxy_polydisperse_revb(title, peaks, channel, threshold,
                        pos_rain_gate, midhigh_rain_gate, midlow_rain_gate, neg_rain_gate,
                        pos_peaks, midhigh_peaks, midlow_peaks, neg_peaks,
                        width=560, height=420,
                        min_droplet_width=5, max_droplet_width=20,
                        min_amplitude=100, max_amplitude=32000,
                        min_amplitude_excluded=True,
                        sum_amplitude_bins=None, other_channel_mean=None):
    if not deps_loaded:
        return None
    
    fig = plt.figure()
    ax = fig.add_subplot(111, title=title)
    __graph_polydisperse(ax, peaks, channel, threshold,
                         pos_rain_gate, midhigh_rain_gate, midlow_rain_gate, neg_rain_gate,
                         pos_peaks, midhigh_peaks, midlow_peaks, neg_peaks,
                         width=width, height=height,
                         min_droplet_width=min_droplet_width, max_droplet_width=max_droplet_width,
                         min_amplitude=min_amplitude, max_amplitude=max_amplitude,
                         min_amplitude_excluded=min_amplitude_excluded)
    
    __graph_galaxy_width_bins(ax, sum_amplitude_bins,
                              width=width, height=height,
                              min_droplet_width=min_droplet_width, max_droplet_width=max_droplet_width,
                              min_amplitude=min_amplitude, max_amplitude=max_amplitude,
                              other_channel_mean=other_channel_mean)
    
    setsize(fig, False)
    return fig

def graph_extracluster_by_region(title, peaks, channel, threshold,
                                 extra_peaks_by_region,
                                 rain_gates,
                                 width=560, height=420,
                                 min_droplet_width=5, max_droplet_width=20,
                                 min_amplitude=100, max_amplitude=32000,
                                 min_amplitude_excluded=True,
                                 sum_amplitude_bins=None, other_channel_mean=None):
    if not deps_loaded:
        return None
    
    fig = plt.figure()
    ax = fig.add_subplot(111, title=title)
    __graph_polydisperse(ax, peaks, channel, threshold,
                         rain_gates[0], rain_gates[1], rain_gates[2], rain_gates[3],
                         extra_peaks_by_region[0], extra_peaks_by_region[3],
                         extra_peaks_by_region[5], extra_peaks_by_region[8],
                         width=width, height=height,
                         min_droplet_width=min_droplet_width, max_droplet_width=max_droplet_width,
                         min_amplitude=min_amplitude, max_amplitude=max_amplitude,
                         min_amplitude_excluded=min_amplitude_excluded,
                         highlight_poly=False,
                         draw_count_summary=False)
    
    __graph_galaxy_width_bins(ax, sum_amplitude_bins,
                              width=width, height=height,
                              min_droplet_width=min_droplet_width, max_droplet_width=max_droplet_width,
                              min_amplitude=min_amplitude, max_amplitude=max_amplitude,
                              other_channel_mean=other_channel_mean)

    extra_peaks_len = sum([len(p) for p in extra_peaks_by_region])
    ax.text(5, height-15, 'Total extracluster: %.02f%% (%d/%d)' % \
                (float(extra_peaks_len)*100/len(peaks), extra_peaks_len, len(peaks)))

    offset = 15
    for idx, (text, show) in enumerate([('Pos. Large (NE)', True),
                                        ('Pos. Rain (E)', True),
                                        ('Pos. Small (SE)', False),
                                        ('Pos. Wide (NP)', True),
                                        ('Pos. Narrow (SP)', False),
                                        ('Mid. Large (N)', True),
                                        ('Mid. Rain', True),
                                        ('Mid. Small (S)', True),
                                        ('Neg. Large (NW)', False),
                                        ('Neg. Rain (W)', True),
                                        ('Neg. Rain (SW)', True),
                                        ('Neg. Wide (NN)', True),
                                        ('Neg. Narrow (NS)', False)]):
        if not show:
            continue
        offset = offset+15
        region_peaks = extra_peaks_by_region[idx]
        ax.text(5, height-offset, '%s: %.02f%% (%d)' % \
                    (text, float(len(region_peaks))*100/len(peaks), len(region_peaks)))
    setsize(fig, False)
    return fig



def galaxy_sum_width_bins(title, well,
                          width=560, height=420,
                          min_droplet_width=5, max_droplet_width=20,
                          min_amplitude=100, max_amplitude=64000,
                          min_amplitude_excluded=True):
    if not deps_loaded:
        return None
    
    from pyqlb.nstats.well import above_min_amplitude_peaks, well_static_width_gates

    if min_amplitude_excluded:
        peaks = above_min_amplitude_peaks(well)
    else:
        peaks = well.peaks
    
    fig = plt.figure()
    ax = fig.add_subplot(111, title=title)

    __sum_galaxy(ax, peaks, width=width, height=height,
                 min_droplet_width=min_droplet_width, max_droplet_width=max_droplet_width,
                 min_amplitude=min_amplitude, max_amplitude=max_amplitude)
    
    min_amp_log = np.log10(min_amplitude)
    max_amp_log = np.log10(max_amplitude)

    def amplitude_xform(a):
        #return a
        return (width/float(max_amp_log-min_amp_log))*(np.log10(a)-min_amp_log)
    
    def width_xform(w):
        #return w
        return (height/float(max_droplet_width-min_droplet_width))*(w-min_droplet_width)

    if well.sum_amplitude_bins:
        sum_amplitude_bins = well.sum_amplitude_bins
        binxs = []
        low_binys = []
        high_binys = []

        # TODO: generic?
        amplitude_boundaries= [bin[2] for bin in sum_amplitude_bins]

        # TODO check top end of boundary as well
        amplitude_regions = zip(amplitude_boundaries[:-1], amplitude_boundaries[1:]) \
                            + [(amplitude_boundaries[-1], max_amplitude)]

        for (start, end), (minw, maxw, boundary) in zip(amplitude_regions, sum_amplitude_bins):
            binxs.append(amplitude_xform(max(min_amplitude, start)))
            binxs.append(amplitude_xform(max(min_amplitude, end)))
            for i in range(2):
                low_binys.append(width_xform(minw))
                high_binys.append(width_xform(maxw))
        
        ax.plot(binxs, low_binys, linestyle='dashed', color='#0000ff')
        ax.plot(binxs, high_binys, linestyle='dashed', color='#0000ff')
    else:
        ming, maxg = well_static_width_gates(well)
        minw = width_xform(ming)
        maxw = width_xform(maxg)

        ax.axhline(minw, linestyle='dashed', color='#0000ff')
        ax.axhline(maxw, linestyle='dashed', color='#0000ff')
    
    setsize(fig, False)
    return fig


def galaxy_extracluster(title, peaks, channel, threshold, min_width_gate, max_width_gate,
                        pos_rain_gate, midhigh_rain_gate, midlow_rain_gate, neg_rain_gate,
                        extra_peaks,
                        width=560, height=420,
                        min_droplet_width=5, max_droplet_width=20,
                        min_amplitude=100, max_amplitude=32000,
                        min_amplitude_excluded=True):
    if not deps_loaded:
        return None
    
    # TODO abstract this
    def amplitude_xform(a):
        #return a
        return (width/float(max_amp_log-min_amp_log))*(np.log10(a)-min_amp_log)
    
    def width_xform(w):
        #return w
        return (height/float(max_droplet_width-min_droplet_width))*(w-min_droplet_width)
    
    fig = plt.figure()
    from pyqlb.nstats.peaks import channel_amplitudes, channel_widths
    xs = channel_amplitudes(peaks, channel)
    ys = channel_widths(peaks, channel)

    max_width = 20
    min_width = 5
    min_amp_log = np.log10(min_amplitude)
    max_amp_log = np.log10(max_amplitude)

    if xs is not None and ys is not None:
        H, xedges, yedges = np.histogram2d(ys, np.log10(xs), bins=[height, width], range=[[min_droplet_width, max_droplet_width],[min_amp_log, max_amp_log]])
        plt.imshow(H, origin='lower', cmap=get_plate_cmap(H), interpolation='nearest')
    
    amps = [amplitude_xform(a) for a in channel_amplitudes(extra_peaks, channel)]
    widths = [width_xform(w) for w in channel_widths(extra_peaks, channel)]
    plt.plot(amps, widths, marker='o', markersize=3, markeredgewidth=1, linewidth=0, color='#009900', zorder=2)
    
    plt.title(title)
    plt.xlabel('%s Amplitude (log scale)' % ('VIC' if channel == 1 else 'FAM'))

    plt.axis([min_amp_log, max_amp_log,5,20])

    prain = (width/(max_amp_log-min_amp_log))*(np.log10(pos_rain_gate)-min_amp_log)
    plt.axvline(x=prain, color='#0099ff', linestyle='dashed')
    if midhigh_rain_gate:
        mhrain = (width/(max_amp_log-min_amp_log))*(np.log10(midhigh_rain_gate)-min_amp_log)
        plt.axvline(x=mhrain, color='#0099ff', linestyle='dashed')
    if midlow_rain_gate:
        mlrain = (width/(max_amp_log-min_amp_log))*(np.log10(midlow_rain_gate)-min_amp_log)
        plt.axvline(x=mlrain, color='#0099ff', linestyle='dashed')
    nrain = (width/(max_amp_log-min_amp_log))*(np.log10(neg_rain_gate)-min_amp_log)
    plt.axvline(x=nrain, color='#0099ff', linestyle='dashed')
    thresh = (width/(max_amp_log-min_amp_log))*(np.log10(threshold)-min_amp_log)
    plt.axvline(x=thresh, color='#990099')

    minw = (height/float(max_droplet_width-min_droplet_width))*(min_width_gate-min_droplet_width)
    plt.axhline(minw, linestyle='dashed', color='#0000ff')
    maxw = (height/float(max_droplet_width-min_droplet_width))*(max_width_gate-min_droplet_width)
    plt.axhline(maxw, linestyle='dashed', color='#0000ff')

    if len(peaks) > 0:
        plt.text(5, height-15, 'Total extracluster peaks: %.02f%% (%d/%d)' % \
            (float(len(extra_peaks)*100)/len(peaks), len(extra_peaks), len(peaks)))
    
    if min_amplitude_excluded:
        plt.text(width-250, 5, 'NOTE: Min amplitude peaks excluded')


    # TODO standardize galaxy
    plt.xticks([0,67,156,223,291,379,446,560],[100,200,500,1000,2000,5000,10000,32000])
    plt.yticks([0,84,168,252,336,420],[5,8,11,14,17,20])
    
    setsize(fig, False)
    return fig

    

def multi_galaxy(title, wells, channel=0,
                 width=560, height=420,
                 min_droplet_width=5, max_droplet_width=20,
                 min_amplitude=100, max_amplitude=32000,
                 draw_threshold=False, draw_width_gates=False,
                 custom_thresholds=None,
                 quality_gate=False,
                 draw_min_amplitude_peaks=True):
    if not deps_loaded:
        return None
    
    fig = plt.figure()
    from pyqlb.constants import FLT_MIN, FLT_MAX
    from pyqlb.nstats.peaks import fam_widths, fam_amplitudes, width_gated, vic_widths, vic_amplitudes, cluster_1d, quality_gated
    from pyqlb.nstats.well import well_static_width_gates, above_min_amplitude_peaks
    xs = None
    ys = None
    for well in wells:
        if draw_min_amplitude_peaks:
            peaks = well.peaks
        else:
            peaks = above_min_amplitude_peaks(well)
        
        if quality_gate:
            peaks = quality_gated(peaks, min_quality_gate=well.channels[0].statistics.min_quality_gate)
        if xs is None:
            xs = vic_amplitudes(peaks) if channel == 1 else fam_amplitudes(peaks)
            ys = vic_widths(peaks) if channel == 1 else fam_widths(peaks)
        else:
            xs = np.hstack((xs, vic_amplitudes(peaks) if channel == 1 else fam_amplitudes(peaks)))
            ys = np.hstack((ys, vic_widths(peaks) if channel == 1 else fam_widths(peaks)))
    
    max_width = 20
    min_width = 5
    min_amp_log = np.log10(min_amplitude)
    max_amp_log = np.log10(max_amplitude)
    if xs is not None and ys is not None and len(xs) > 0 and len(ys) > 0:
        H, xedges, yedges = np.histogram2d(ys, np.log10(xs), bins=[height,width], range=[[min_droplet_width,max_droplet_width],[min_amp_log,max_amp_log]])
        plt.imshow(H, origin='lower', cmap=get_plate_cmap(H), interpolation='nearest')
    
    plt.title(title)
    plt.xlabel('%s Amplitude (log scale)' % ('VIC' if channel == 1 else 'FAM'))

    if draw_threshold:
        if custom_thresholds:
            thresholds = custom_thresholds
        else:
            thresholds = [w.channels[channel].statistics.threshold for w in wells if w.channels[channel].statistics.threshold]
        if thresholds:
            avg_thresh = np.mean(thresholds)
            min_thresh = min(thresholds)
            max_thresh = max(thresholds)
            histx = (width/(max_amp_log-min_amp_log))*(np.log10(avg_thresh)-min_amp_log)
            histl = (width/(max_amp_log-min_amp_log))*(np.log10(min_thresh)-min_amp_log)
            histh = (width/(max_amp_log-min_amp_log))*(np.log10(max_thresh)-min_amp_log)
            plt.axvline(x=histx, color='#0000ff', linestyle='dashed')
            plt.axvline(x=histl, color='#0099ff', linestyle='dashed', alpha=0.5)
            plt.axvline(x=histh, color='#0099ff', linestyle='dashed', alpha=0.5)
            plt.text(histx+5, 5, "Average threshold: %.01f" % avg_thresh, color='#0000ff')
    
    if draw_width_gates:
        width_gates = [well_static_width_gates(w) for w in wells]
        min_width_gates = [ming for ming, maxg in width_gates if ming and ming != FLT_MIN]
        max_width_gates = [maxg for ming, maxg in width_gates if maxg and maxg != FLT_MAX]
        if min_width_gates and max_width_gates:
            avg_min = np.mean(min_width_gates)
            min_min = min(min_width_gates)
            avg_max = np.mean(max_width_gates)
            max_max = max(max_width_gates)
            histl = (height/float(max_droplet_width-min_droplet_width))*(avg_min-min_droplet_width)
            histh = (height/float(max_droplet_width-min_droplet_width))*(avg_max-min_droplet_width)
            histll = (height/float(max_droplet_width-min_droplet_width))*(min_min-min_droplet_width)
            histhh = (height/float(max_droplet_width-min_droplet_width))*(max_max-min_droplet_width)
            if avg_min > min_droplet_width and avg_min < max_droplet_width:
                plt.axhline(y=histl, color='#009900', linestyle='dashed')
            if avg_max > min_droplet_width and avg_max < max_droplet_width:
                plt.axhline(y=histh, color='#009900', linestyle='dashed')
            if min_min > min_droplet_width and min_min < max_droplet_width:
                plt.axhline(y=histll, color='#00ff00', linestyle='dashed', alpha=0.5)
            if max_max > min_droplet_width and max_max < max_droplet_width:
                plt.axhline(y=histhh, color='#00ff00', linestyle='dashed', alpha=0.5)
            plt.text(350, histl-18, "Average gates: %.02f-%.02f" % (avg_min, avg_max), color='#009900')

    # should be a better way to do this
    plt.xticks([0,67,156,223,291,379,446,560],[100,200,500,1000,2000,5000,10000,32000])
    plt.yticks([0,84,168,252,336,420],[5,8,11,14,17,20])

    #width_lines = [2*i for i in range(min_width/2, (max_width/2)+1)]
    #width_lines = [(height/float(max_width-min_width))*(w-min_width) for w in width_lines if w >= min_width and w <= max_width]
    #for w in width_lines:
    #    plt.axhline(y=w, color='#cccccc', alpha=0.5, zorder=2)

    plt.ylabel('Droplet Width (samples)')
    setsize(fig, False)
    return fig

def galaxy_carryover(title, wells,
                     all_contamination_peaks,
                     gated_contamination_peaks,
                     carryover_peaks,
                     channel=0,
                     width=560, height=420, min_droplet_width=5, max_droplet_width=20,
                     min_amplitude=100, max_amplitude=32000,
                     draw_threshold=False, draw_width_gates=False,
                     quality_gate=False,
                     draw_min_amplitude_peaks=False):
    underlay = multi_galaxy(title, wells, channel=channel,
                            width=width, height=height,
                            min_droplet_width=min_droplet_width, max_droplet_width=max_droplet_width,
                            min_amplitude=min_amplitude, max_amplitude=max_amplitude,
                            draw_threshold=draw_threshold, draw_width_gates=draw_width_gates,
                            custom_thresholds=False,
                            quality_gate=quality_gate,
                            draw_min_amplitude_peaks=draw_min_amplitude_peaks)
    
    # do histogram overlay
    def width_xform(w):
        #return w
        return min(height, (height/float(max_droplet_width-min_droplet_width))*(w-min_droplet_width))
    
    max_amp_log = np.log10(max_amplitude)
    min_amp_log = np.log10(min_amplitude)

    def amplitude_xform(a):
        #return a
        return (width/float(max_amp_log-min_amp_log))*(np.log10(a)-min_amp_log)

    from pyqlb.nstats.peaks import channel_amplitudes, fam_widths
    amplitudes = [amplitude_xform(a) for a in channel_amplitudes(all_contamination_peaks, channel)]
    # fam_widths by default -- could add channel_widths to PyQLB if necessary
    widths = [width_xform(w) for w in fam_widths(all_contamination_peaks)]
    plt.plot(amplitudes, widths, marker='x', markersize=5, markeredgewidth=2, linewidth=0, color='#99ccff', zorder=2)
    
    gated_amplitudes = [amplitude_xform(a) for a in channel_amplitudes(gated_contamination_peaks, channel)]
    # fam_widths by default -- could add channel_widths to PyQLB if necessary
    gated_widths = [width_xform(w) for w in fam_widths(gated_contamination_peaks)]
    plt.plot(gated_amplitudes, gated_widths, marker='x', markersize=5, markeredgewidth=2, linewidth=0, color='#0000ff', zorder=3)
    
    carryover_amplitudes = [amplitude_xform(a) for a in channel_amplitudes(carryover_peaks, channel)]
    # fam_widths by default -- could add channel_widths to PyQLB if necessary
    carryover_widths = [width_xform(w) for w in fam_widths(carryover_peaks)]
    plt.plot(carryover_amplitudes, carryover_widths, marker='x', markersize=5, markeredgewidth=2, linewidth=0, color='#ff00ff', zorder=4)
    
    plt.text(5, 5, 'Total Contamination: %s' % len(all_contamination_peaks), color='#99ccff')
    plt.text(5, 20, 'Gated Contamination: %s' % len(gated_contamination_peaks), color='#0000ff')
    plt.text(5, 35, 'Carryover Peaks: %s' % len(carryover_peaks), color='#ff00ff')

    return underlay

def carryover_hist(title, wells,
                   all_contamination_peaks,
                   gated_contamination_peaks,
                   carryover_peaks,
                   width=560,
                   height=420):
    from qtools.lib.nstats.peaks import peak_times

    fig = plt.figure()
    ax = fig.add_subplot(111)

    all_times = peak_times(all_contamination_peaks)
    gated_times = peak_times(gated_contamination_peaks)
    carryover_times = peak_times(carryover_peaks)

    n, bins, patches = plt.hist(all_times, 50, range=(0,2500000), color='#99ccff', zorder=1)
    n, bins, patches = plt.hist(gated_times, 50, range=(0,2500000), color='#0000ff', zorder=2)
    n, bins, patches = plt.hist(carryover_times, 50, range=(0,2500000), color='#ff00ff', zorder=3)

    plt.title(title)
    plt.xlabel('Time intervals (.5 seconds)')
    return fig

TEMPORAL_MAX = 2250000 # 100000 Hz x 22.5 sec
AMPLITUDE_MAX = 32767
def temporal(title, peaks, threshold, min_width_gate, max_width_gate, channel=0):
    if not deps_loaded:
        return None
    
    fig = plt.figure()
    from pyqlb.nstats.peaks import peak_times, fam_widths, fam_amplitudes, width_gated, vic_quality, vic_widths, vic_amplitudes, cluster_1d
    # TODO add this to pyqlb
    xs = peak_times(peaks)
    max_x = max(TEMPORAL_MAX, (max(xs)+200000 if len(xs) > 0 else 0))
    ys = vic_widths(peaks) if channel == 1 else fam_widths(peaks)
    plt.plot(xs, ys, marker='.', linewidth=0, markersize=2, color='#333333', alpha=0.33)
    # adaptive width gate/vertical streak hack
    peak_qualities = zip(peak_times(peaks), vic_quality(peaks), ys)
    vertical_streaks = [(t, q, y) for t, q, y in peak_qualities if q > 0.449 and q < 0.451]
    adaptive_width_gated = [(t, q, y) for t, q, y in peak_qualities if q > 0.399 and q < 0.401]
    xs = [a[0] for a in adaptive_width_gated]
    ys = [a[2] for a in adaptive_width_gated]
    plt.axis([0,max_x,5,20])
    plt.plot(xs, ys, marker='.', linewidth=0, markersize=2, color='#ff0000', zorder=2, alpha=0.5)

    xs = [a[0] for a in vertical_streaks]
    ys = [a[2] for a in vertical_streaks]
    plt.plot(xs, ys, marker='.', linewidth=0, markersize=2, color='#009900', zorder=2, alpha=0.5)

    plt.axhline(y=min_width_gate, ls='dashed', color='#0000ff')
    plt.axhline(y=max_width_gate, ls='dashed', color='#0000ff')
    plt.title(title)
    plt.xlabel('Sample #')
    plt.ylabel('Droplet Width (samples)')
    setsize(fig, False)
    return fig

def _main_slug_overlay(ax, peak_times):
    # figure out idxs of peaks
    pct5  = peak_times[len(peak_times)*5/100]
    pct95 = peak_times[len(peak_times)*95/100]

    ax.axvline(x=pct5, color='#0000ff')
    ax.axvline(x=pct95, color='#0000ff')

def _amptime(ax, peaks, threshold, channel=0):
    from pyqlb.nstats.peaks import channel_amplitudes, peak_times
    
    xs = peak_times(peaks)
    max_x = max(TEMPORAL_MAX, (max(xs)+200000 if len(xs) > 0 else 0))
    ys = channel_amplitudes(peaks, channel)
    ax.plot(xs, ys, marker='.', linewidth=0, markersize=2, color='#333333', alpha=0.33)
    ax.set_xlim(0, max_x)
    
    ax.axhline(y=threshold, ls='dashed', color='#0000ff')
    ax.set_xlabel('Sample #')
    ax.set_ylabel('Amplitude')

def amptime(title, peaks, threshold, channel=0):
    if not deps_loaded:
        return None
    
    fig = plt.figure()
    ax = fig.add_subplot(111, title=title)
    _amptime(ax, peaks, threshold, channel=channel)
    setsize(fig, False)
    return fig

def airtime(title, peaks, air_peaks, threshold, channel=0):
    if not deps_loaded:
        return None
    
    fig = plt.figure()
    ax = fig.add_subplot(111, title=title)
    _amptime(ax, peaks, threshold, channel=channel)
    
    from pyqlb.nstats.peaks import channel_amplitudes, peak_times
    xs = peak_times(air_peaks)
    ys = channel_amplitudes(air_peaks, channel)
    ax.plot(xs, ys, marker='o', linewidth=0, markersize=2, markeredgewidth=0, color='#ff0000')
    setsize(fig, False)
    return fig

def ampevent(title, peaks, thresholds, min_width_gate, max_width_gate, channel=0, show_gated=False, show_opposite_pos=False):
    if not deps_loaded:
        return None
    
    fig = plt.figure()
    from pyqlb.nstats.peaks import fam_widths, fam_amplitudes, width_gated, vic_widths, vic_amplitudes, filter_width_range, quality_gated
    from qtools.lib.nstats.peaks import accepted_peaks
    # TODO add this to pyqlb
    if not show_gated:
        peaks = width_gated(peaks, min_width_gate, max_width_gate)
        peaks = quality_gated(peaks, 0.5) 
    
    xs = np.arange(len(peaks))
    ys = vic_amplitudes(peaks) if channel == 1 else fam_amplitudes(peaks)
    plt.plot(xs, ys, marker='.', linewidth=0, markersize=2, color='#333333', alpha=0.33)
    opos = []
    if show_opposite_pos:
        if channel == 1:
            opos = [(ys[i] if (y >= thresholds[0] and ys[i] >= thresholds[1]) else -1000) for i, y in enumerate(fam_amplitudes(peaks))]
        else:
            opos = [(ys[i] if (y >= thresholds[1] and ys[i] >= thresholds[0]) else -1000) for i, y in enumerate(vic_amplitudes(peaks))]

        plt.plot(xs, opos, linewidth=0, marker='.', markersize=4, color='#009900', zorder=2, alpha=1)
        plt.text(10, 10, "FAM/VIC positives: %s" % len([y for y in opos if y > 0]))
    
    plt.axhline(y=thresholds[channel], ls='dashed', color='#0000ff')
    plt.axis([0,max(xs)+500,0,max(ys)+1000]) 
    plt.title(title)
    plt.xlabel('Event #')
    plt.ylabel('Amplitude')
    setsize(fig, False)
    fig.set_figwidth(12)
    fig.set_figheight(9)
    return fig

_spectral_data = {'red': [(0.0, 1.0, 1.0), (0.05, 0.4667, 0.4667),
                          (0.10, 0.5333, 0.5333), (0.15, 0.0, 0.0),
                          (0.20, 0.0, 0.0), (0.25, 0.0, 0.0),
                          (0.30, 0.0, 0.0), (0.35, 0.0, 0.0),
                          (0.40, 0.0, 0.0), (0.45, 0.0, 0.0),
                          (0.50, 0.0, 0.0), (0.55, 0.0, 0.0),
                          (0.60, 0.0, 0.0), (0.65, 0.7333, 0.7333),
                          (0.70, 0.9333, 0.9333), (0.75, 1.0, 1.0),
                          (0.80, 1.0, 1.0), (0.85, 1.0, 1.0),
                          (0.90, 0.8667, 0.8667), (0.95, 0.80, 0.80),
                          (1.0, 0.80, 0.80)],
                  'green': [(0.0, 1.0, 1.0), (0.05, 0.0, 0.0),
                            (0.10, 0.0, 0.0), (0.15, 0.0, 0.0),
                            (0.20, 0.0, 0.0), (0.25, 0.4667, 0.4667),
                            (0.30, 0.6000, 0.6000), (0.35, 0.6667, 0.6667),
                            (0.40, 0.6667, 0.6667), (0.45, 0.6000, 0.6000),
                            (0.50, 0.7333, 0.7333), (0.55, 0.8667, 0.8667),
                            (0.60, 1.0, 1.0), (0.65, 1.0, 1.0),
                            (0.70, 0.9333, 0.9333), (0.75, 0.8000, 0.8000),
                            (0.80, 0.6000, 0.6000), (0.85, 0.0, 0.0),
                            (0.90, 0.0, 0.0), (0.95, 0.0, 0.0),
                            (1.0, 0.50, 0.50)],
                  'blue': [(0.0, 1.0, 1.0), (0.05, 0.5333, 0.5333),
                           (0.10, 0.6000, 0.6000), (0.15, 0.6667, 0.6667),
                           (0.20, 0.8667, 0.8667), (0.25, 0.8667, 0.8667),
                           (0.30, 0.8667, 0.8667), (0.35, 0.6667, 0.6667),
                           (0.40, 0.5333, 0.5333), (0.45, 0.0, 0.0),
                           (0.5, 0.0, 0.0), (0.55, 0.0, 0.0),
                           (0.60, 0.0, 0.0), (0.65, 0.0, 0.0),
                           (0.70, 0.0, 0.0), (0.75, 0.0, 0.0),
                           (0.80, 0.0, 0.0), (0.85, 0.0, 0.0),
                           (0.90, 0.0, 0.0), (0.95, 0.0, 0.0),
                           (1.0, 0.50, 0.50)]}

_jet_data = {'red':   [(0., 1, 1), (0.35, 0.5, 0.5), (0.66, 1, 1), (0.89,1, 1),
                       (1, 1, 1)],
             'green': [(0., 1, 1), (0.125,0.25, 0.25), (0.375,1, 1), (0.64,1, 1),
                       (0.91,0,0), (1, 0, 0)],
             'blue':  [(0., 1, 1), (0.11, 1, 1), (0.34, 1, 1), (0.65,0, 0),
                       (1, 0.75, 0.75)]}

def spectral(bins):
    return matplotlib.colors.LinearSegmentedColormap('spec%s' % (bins+1), _spectral_data, bins+1)

def jet(bins, hmax, background=None):
    #raise Exception, (bins, hmax)
    lowres = max(bins, hmax)
    hjet = copy.deepcopy(_jet_data)
    if background:
        hjet['red'][0] = (0, background[0], background[0])
        hjet['green'][0] = (0, background[1], background[1])
        hjet['blue'][0] = (0, background[2], background[2])
    
    if 0.99/lowres < hjet['red'][1][0]:
        hjet['red'].insert(1, (0.99/lowres, 0.6, 0.6))
    if 1.99/lowres < hjet['red'][2][0]:
        hjet['red'].insert(2, (1.99/lowres, 0.3, 0.3))
    if 2.99/lowres < hjet['red'][3][0]:
        hjet['red'].insert(3, (2.99/lowres, 0, 0))
    
    if 0.99/lowres < hjet['green'][1][0]:
        hjet['green'].insert(1, (0.99/lowres, 0.6, 0.6))
    if 1.99/lowres < hjet['green'][2][0]:
        hjet['green'].insert(2, (1.99/lowres, 0.3, 0.3))
    if 2.99/lowres < hjet['green'][3][0]:
        hjet['green'].insert(3, (2.99/lowres, 0, 0))
    

    if 0.99/lowres < hjet['blue'][1][0]:
        hjet['blue'].insert(1, (0.99/lowres, 0.6, 0.6))
    if 1.99/lowres < hjet['blue'][2][0]:
        hjet['blue'].insert(2, (1.99/lowres, 0.3, 0.3))
    if 2.99/lowres < hjet['blue'][3][0]:
        hjet['blue'].insert(3, (2.99/lowres, 1, 1))
    
    return matplotlib.colors.LinearSegmentedColormap('jet%s-%s' % (bins, hmax), hjet, bins+1)

def plot_fam_peaks(peaks,
                   width=60, height=60,
                   threshold=None,
                   threshold_color='red',
                   max_amplitude=24000,
                   background_rgb=AUTO_THRESHOLD_FAM_BGCOLOR):
    binwidth = int(len(peaks)/float(24000) * width)+1
    binheight = height
    fig = plt.figure(1, figsize=(float(binwidth)/72,
                                 (float(binheight))/72),
                                 dpi=72,
                                 frameon=False,
                                 subplotpars=matplotlib.figure.SubplotParams(left=0,right=1,bottom=0,top=1,wspace=0,hspace=0))
    
    from pyqlb.nstats.peaks import fam_amplitudes
    ax = fig.add_axes([0,0,1,1], frameon=False)
    ax.set_axis_off()
    _plot_binned_amplitudes(ax, fam_amplitudes(peaks), binwidth, binheight,
                            threshold, threshold_color, max_amplitude,
                            background_rgb=background_rgb)
    return fig

def plot_vic_peaks(peaks,
                   width=60, height=60,
                   threshold=None,
                   threshold_color='red',
                   max_amplitude=24000,
                   background_rgb=AUTO_THRESHOLD_VIC_BGCOLOR):
    binwidth = int(len(peaks)/float(24000) * width)+1
    binheight = height
    fig = plt.figure(1, figsize=(float(binwidth)/72,
                                 (float(binheight))/72),
                                 dpi=72,
                                 frameon=False,
                                 subplotpars=matplotlib.figure.SubplotParams(left=0,right=1,bottom=0,top=1,wspace=0,hspace=0))
    
    from pyqlb.nstats.peaks import vic_amplitudes
    ax = fig.add_axes([0,0,1,1], frameon=False)
    ax.set_axis_off()
    _plot_binned_amplitudes(ax, vic_amplitudes(peaks), binwidth, binheight,
                            threshold, threshold_color, max_amplitude,
                            background_rgb=background_rgb)
    return fig
    

def plot_fam_vic_peaks(peaks,
                       width=300, height=300,
                       thresholds=None,
                       threshold_colors=None,
                       max_amplitudes=None,
                       background_rgbs=None):
    binwidth = int(len(peaks)/float(24000) * width)+1
    binheight = height/2
    fig = plt.figure(1, figsize=(float(binwidth)/72,
                                 (float(binheight)*2)/72),
                                 dpi=72,
                                 frameon=False,
                                 subplotpars=matplotlib.figure.SubplotParams(left=0,right=1,bottom=0,top=1,wspace=0,hspace=0))
    
    from pyqlb.nstats.peaks import fam_amplitudes, vic_amplitudes
    if not max_amplitudes:
        max_amplitudes = (24000,12000)
    if not threshold_colors:
        threshold_colors = ('red','red')
    if not thresholds:
        thresholds = (0,0)
    if not background_rgbs:
        background_rgbs = (AUTO_THRESHOLD_FAM_BGCOLOR,AUTO_THRESHOLD_VIC_BGCOLOR)
    else:
        if background_rgbs[0] is None:
            background_rgbs[0] = AUTO_THRESHOLD_FAM_BGCOLOR
        if background_rgbs[1] is None:
            background_rgbs[1] = AUTO_THRESHOLD_VIC_BGCOLOR
    
    ax = fig.add_axes([0,0.5,1,0.5], frameon=False)
    ax.set_axis_off()
    _plot_binned_amplitudes(ax, fam_amplitudes(peaks), binwidth, binheight,
                            thresholds[0], threshold_colors[0], max_amplitudes[0],
                            background_rgb=background_rgbs[0])

    ax = fig.add_axes([0,0,1,0.5], frameon=False)
    ax.set_axis_off()
    _plot_binned_amplitudes(ax, vic_amplitudes(peaks), binwidth, binheight,
                            thresholds[1], threshold_colors[1], max_amplitudes[1],
                            background_rgb=background_rgbs[1])

    return fig

def _plot_binned_amplitudes(ax, amplitudes, binwidth, binheight,
                            threshold=None, threshold_color='red', max_amplitude=None,
                            background_rgb=(1,1,1)):
    xs = range(len(amplitudes))
    ys = amplitudes

    if len(ys) == 0:
        return

    # set expected vmax, 
    H, xedges, yedges = np.histogram2d(ys, xs, bins=[binheight,binwidth], range=[[0,max_amplitude],[0,len(amplitudes)]])
    vmax = min(256, float(1000000)/(binheight*binwidth))

    ax.imshow(H, origin='lower', cmap=jet(vmax, np.max(H), background_rgb), vmax=vmax, interpolation='nearest')
    #ax.hexbin(xs, ys, gridsize=75, cmap=spectral(256), vmax=48, extent=[0,len(peaks),0,max_amplitudes[0]])
    if threshold and threshold != 0:
        ax.axhline(y=threshold/(float(max_amplitude)/binheight), color=threshold_color, linestyle='solid')


# maybe decouple graph plotter from figure plotter to show side-by-side
def plot_conc_rolling_window(qlwell, channel_num,
                             width=600, height=400, threshold_color='red',
                             rolling_color='green',
                             title='',
                             max_amplitude=24000, background_rgb=(1,1,1)):
    """
    incoming peaks should probably be accepted peaks
    """
    # compute rolling conc per last 1000 events by 10
    # there's probably an itertools for that
    from pyqlb.nstats import concentration
    from pyqlb.nstats.peaks import cluster_1d, channel_amplitudes
    from qtools.lib.nstats.peaks import accepted_peaks, quartile_concentration_ratio

    fig = plt.figure()
    ax = fig.add_subplot(111)

    peaks = accepted_peaks(qlwell)
    amplitudes = channel_amplitudes(peaks, channel_num)

    binwidth = width
    binheight = height
    threshold = qlwell.channels[channel_num].statistics.threshold
    if not threshold:
        # TODO add text on return?
        return fig
    
    well_conc = qlwell.channels[channel_num].statistics.concentration

    _plot_binned_amplitudes(ax, amplitudes, binwidth, binheight,
                            threshold=threshold, max_amplitude=max_amplitude)
    
    plt.text(10, (threshold/max_amplitude)*binheight+5, 'Threshold: %d' % threshold, color=threshold_color)
    
    wbinsize = float(len(peaks))/binwidth
    startx = int(math.ceil(1000/wbinsize))
    xs = range(startx, binwidth)
    ys = []
    for x in xs:
        point = int(wbinsize*x)
        pos, neg = cluster_1d(peaks[point-1000:point], channel_num, threshold)

        # make computed concentration for entire well the centerline
        ys.append(binheight * (concentration(len(pos), len(neg), droplet_vol=qlwell.droplet_volume)/2000))
    
    # compute conc, pos, neg for quartiles
    quartile_size = len(peaks)/4

    for q in range(3):
        quartile = peaks[q*quartile_size:(q+1)*quartile_size]
        pos, neg = cluster_1d(quartile, channel_num, threshold)
        conc = concentration(len(pos), len(neg), droplet_vol=qlwell.droplet_volume)
        if math.isnan(conc):
            conc = 10000 # arbitrary
        if q == 0:
            fq_conc = conc
        plt.text((binwidth/4)*q+10, binheight-20, "Conc: %d" % conc)
        plt.text((binwidth/4)*q+10, binheight-35, "Pos: %d" % len(pos))
        plt.text((binwidth/4)*q+10, binheight-50, "Neg: %d" % len(neg))
        plt.axvline(binwidth/4*(q+1), color='#999999', alpha=0.5, linestyle='dashed')
    
    quartile = peaks[3*quartile_size:]
    pos, neg = cluster_1d(quartile, channel_num, threshold)
    lq_conc = concentration(len(pos), len(neg), droplet_vol=qlwell.droplet_volume)
    plt.text((binwidth/4)*3+10, binheight-20, "Conc: %d" % lq_conc)
    plt.text((binwidth/4)*3+10, binheight-35, "Pos: %d" % len(pos))
    plt.text((binwidth/4)*3+10, binheight-50, "Neg: %d" % len(neg))
    
    plt.plot([x-(startx/2.0) for x in xs], ys, linewidth=2, color=rolling_color)
    plt.axhline(binheight*(well_conc/2000), linewidth=1, color=rolling_color)
    plt.text(10, (binheight*(well_conc/2000))+5, "Conc: %d" % well_conc, color=rolling_color)

    # determin conc ratio as a string, or N/A if not defined
    if ( fq_conc ):
        conc_ratio = "%.03f" % (lq_conc/fq_conc );
    else:
        conc_ratio = 'N/A'

    plt.text(binwidth-90, (binheight*(well_conc/2000))-15, "Ratio: %s" % conc_ratio, color=rolling_color)
    for q in range(4):
        plt.text
    plt.title(title)
    plt.ylabel('Amplitude')
    ax.axis([0, binwidth, 0, binheight])
    ax2 = plt.twinx() # but it draws a y-axis!  weird, mpl.
    ax2.set_yticks([0,500,1000,1500,2000])
    plt.yticks(color=rolling_color)
    plt.ylabel('Concentration Ratio', rotation=270, color=rolling_color)

    plt.text(5, 30, 'Total Events: %d; Overall concentration: %d; 4Q/1Q Ratio: %s' % (len(peaks), well_conc, conc_ratio))
    setsize(fig, False)
    return fig


def plot_bscore_rolling_window(qlwell,
                               width=600, height=400,
                               rolling_color='green',
                               title=''):
    from pyqlb.nstats import balance_score_2d
    from pyqlb.nstats.peaks import cluster_2d, normalized_droplet_spacing, peak_times
    from pyqlb.nstats.well import accepted_peaks
    
    fig = plt.figure()
    plt.title(title)
    ax = fig.add_subplot(111)

    peaks = accepted_peaks(qlwell)

    # ensure 2000 on each end, iterate by 100
    if len(peaks) < 4000 or not qlwell.channels[0].statistics.threshold or not qlwell.channels[1].statistics.threshold:
        return fig
    
    bscores = []
    ptimes = peak_times(peaks)
    for i in range(2000, len(peaks)-2000, 200):
        n11, n10, n01, n00 = cluster_2d(peaks[i-2000:2000+i],
                                        fam_threshold=qlwell.channels[0].statistics.threshold,
                                        vic_threshold=qlwell.channels[1].statistics.threshold)
        bscores.append((ptimes[i], balance_score_2d(len(n00),len(n01),len(n10),len(n11))[0]))
    
    xs = [b[0] for b in bscores]
    ys = [b[1] for b in bscores]
    plt.plot(xs, ys, linewidth=2, color=rolling_color)

    nds = normalized_droplet_spacing(qlwell.peaks)
    avg_spaces = []
    maxy = max(ys)
    for i in range(2000, len(nds)-2000, 200):
        spaces = nds[i-2000:2000+i]
        short = [s for s in spaces if s < 2.75]
        pct = maxy*float(len(short))/len(spaces)
        avg_spaces.append((ptimes[i+1], pct))

    xs = [s[0] for s in avg_spaces]
    ys = [s[1] for s in avg_spaces]
    plt.plot(xs, ys, linewidth=2, color='#ff0000')

    setsize(fig, False)
    return fig

        


def plot_conc_bias(plate_metric, channel_num=0, width=600, height=400, title=''):
    """
    Simple plot of bias v concentration for a given plate (metric).
    Draws text.
    """
    fig = plt.figure()
    ax = fig.add_subplot(111)
    ax.axis([0.75, 1.5, 500, 1500])

    total = len(plate_metric.well_metrics)
    from matplotlib.cm import spectral as cm
    for idx, w in enumerate(sorted(plate_metric.well_metrics, key=operator.attrgetter('well_name'))):
        if w.well_channel_metrics[channel_num].concentration and\
           w.well_channel_metrics[channel_num].concentration_rise_ratio:
            plt.text(w.well_channel_metrics[channel_num].concentration_rise_ratio,
                     w.well_channel_metrics[channel_num].concentration,
                     w.well_name, color=cm(idx*1.0/total), size=9)
    
    plt.xlabel('4Q/1Q Concentration Ratio')
    plt.ylabel('Concentration')
    plt.title(title)
    
    setsize(fig, False)
    return fig


def plot_widths(peaks,
                width=300, height=300,
                min_width_gate=0, max_width_gate=100,
                max_width=20,
                gate_color='red',
                background_rgbs=None):
    binwidth = int(len(peaks)/float(24000) * width)+1
    binheight = height/2
    fig = plt.figure(1, figsize=(float(binwidth)/72,
                                 (float(binheight)*2)/72),
                                 dpi=72,
                                 frameon=False,
                                 subplotpars=matplotlib.figure.SubplotParams(left=0,right=1,bottom=0,top=1,wspace=0,hspace=0))
    from pyqlb.nstats.peaks import fam_widths, vic_widths
    # keep legacy pattern
    ax = fig.add_axes([0,0.5,1,0.5], frameon=False)
    ax.set_axis_off()
    if not background_rgbs:
        background_rgbs = (AUTO_THRESHOLD_FAM_BGCOLOR,AUTO_THRESHOLD_VIC_BGCOLOR)
    else:
        if background_rgbs[0] is None:
            background_rgbs[0] = AUTO_THRESHOLD_FAM_BGCOLOR
        if background_rgbs[1] is None:
            background_rgbs[1] = AUTO_THRESHOLD_VIC_BGCOLOR

    _plot_channel_widths(ax, fam_widths(peaks), binwidth, binheight,
                         min_width_gate, max_width_gate, max_width, gate_color,
                         background_rgbs[0])
    
    ax = fig.add_axes([0,0,1,0.5], frameon=False)
    ax.set_axis_off()
    _plot_channel_widths(ax, vic_widths(peaks), binwidth, binheight,
                         min_width_gate, max_width_gate, max_width, gate_color,
                         background_rgbs[1])
    return fig

def _plot_channel_widths(ax, widths, binwidth, binheight,
                         min_width_gate, max_width_gate, max_width,
                         gate_color, background_rgb):
    xs = range(len(widths))
    ys = widths

    if len(ys) == 0:
        return
    
    H, xedges, yedges = np.histogram2d(ys, xs, bins=[binheight,binwidth], range=[[0,max_width],[0, len(widths)]])
    vmax = min(256, float(1000000)/(binheight*binwidth))

    ax.imshow(H, origin='lower', cmap=jet(vmax, np.max(H), background_rgb), vmax=vmax, interpolation='nearest')
    if min_width_gate and min_width_gate != 0 and min_width_gate < max_width:
        ax.axhline(y=min_width_gate/(float(max_width)/binheight), color=gate_color, linestyle='solid')
    if max_width_gate and max_width_gate != 0 and max_width_gate < max_width:
        ax.axhline(y=max_width_gate/(float(max_width)/binheight), color=gate_color, linestyle='solid')

def plot_threshold_2d(peaks,
                      width=300, height=300,
                      thresholds=None,
                      boundaries=None,
                      threshold_color='red'):
    binwidth = width
    binheight = height
    fig = plt.figure(1, figsize=(float(binwidth)/72,
                                float(binheight)/72),
                                dpi=72,
                                frameon=False,
                                subplotpars=matplotlib.figure.SubplotParams(left=0,right=1,bottom=0,top=1,wspace=0,hspace=0))
    
    from pyqlb.nstats.peaks import fam_amplitudes, vic_amplitudes
    ax = fig.add_axes([0,0,1,1], frameon=False)
    ax.set_axis_off()

    xs = vic_amplitudes(peaks)
    ys = fam_amplitudes(peaks)

    if len(ys) == 0:
        return
    
    H, xedges, yedges = np.histogram2d(ys, xs, bins=[binheight, binwidth],
                                       range=[[boundaries[1], boundaries[3]],
                                              [boundaries[0], boundaries[2]]])
    vmax = min(256, float(1000000)/(binheight*binwidth))

    ax.imshow(H, origin='lower', cmap=jet(vmax, np.max(H), (0.95, 0.95, 0.95)), vmax=vmax, interpolation='nearest')
    fam_threshold, vic_threshold = thresholds

    space_width = boundaries[2]-boundaries[0]
    space_height = boundaries[3]-boundaries[1]
    if fam_threshold and fam_threshold != 0:
        ax.axhline(y=(fam_threshold-boundaries[1])/(float(space_height)/binheight), color=threshold_color, linestyle='solid')
    if vic_threshold and vic_threshold != 0:
        ax.axvline(x=(vic_threshold-boundaries[0])/(float(space_width)/binwidth), color=threshold_color, linestyle='solid')
    
    ax.axhline(y=(0-boundaries[1])/(float(space_height)/binheight), color='black', linestyle='solid')
    ax.axvline(x=(0-boundaries[0])/(float(space_width)/binwidth), color='black', linestyle='solid')
    return fig

def plot_cluster_2d(peaks,
                    width=300, height=300,
                    thresholds=None,
                    boundaries=None,
                    threshold_color='red',
                    use_manual_clusters=False,
                    show_scale_inline=False,
                    antialiased=False,
                    show_thresholds=True,
                    show_axes=True,
                    unclassified_alpha=1,
                    highlight_thresholds=False):
    binwidth = width
    binheight = height
    fig = plt.figure(1, figsize=(float(binwidth)/72,
                                 float(binheight)/72),
                                 dpi=72,
                                 frameon=False,
                                 subplotpars=matplotlib.figure.SubplotParams(left=0,right=1,bottom=0,top=1,wspace=0,hspace=0))
    from pyqlb.nstats.peaks import cluster_2d_auto, cluster_2d_user, vic_amplitudes, fam_amplitudes
    ax = fig.add_axes([0,0,1,1], frameon=False)
    ax.set_autoscale_on(False)
    ax.set_xbound(boundaries[0], boundaries[2])
    ax.set_ybound(boundaries[1], boundaries[3])
    ax.set_axis_off()

    xs = vic_amplitudes(peaks)
    ys = fam_amplitudes(peaks)

    if use_manual_clusters:
        clusters = cluster_2d_auto(peaks)
    else:
        clusters = cluster_2d_user(peaks)
    
    fpvp, fpvn, fnvp, fnvn, unclassified, undefined = clusters
    if antialiased and width > 150 and height > 150:
        size = 2
    else:
        size = 1
    
    if len(unclassified) > 0:
        ax.scatter(vic_amplitudes(unclassified), fam_amplitudes(unclassified), antialiased=antialiased, s=size, c='#990000', edgecolors='None', alpha=unclassified_alpha)
    if len(undefined) > 0:
        ax.scatter(vic_amplitudes(undefined), fam_amplitudes(undefined), antialiased=antialiased, s=size, c='#aaaaaa', edgecolors='None')
    if len(fpvp) > 0:
        ax.scatter(vic_amplitudes(fpvp), fam_amplitudes(fpvp), antialiased=antialiased, s=size, c='#ff9900', edgecolors='None')
    if len(fpvn) > 0:
        ax.scatter(vic_amplitudes(fpvn), fam_amplitudes(fpvn), antialiased=antialiased, s=size, c='#0000ff', edgecolors='None')
    if len(fnvn) > 0:
        ax.scatter(vic_amplitudes(fnvn), fam_amplitudes(fnvn), antialiased=antialiased, s=size, c='#990099', edgecolors='None')
    if len(fnvp) > 0:
        ax.scatter(vic_amplitudes(fnvp), fam_amplitudes(fnvp), antialiased=antialiased, s=size, c='#00cc00', edgecolors='None')
    
    if show_axes:
        ax.axhline(y=0, color='black', linestyle='solid')
        ax.axvline(x=0, color='black', linestyle='solid')

    if show_thresholds:
        fam_threshold, vic_threshold = thresholds
        if fam_threshold:
            ax.axhline(y=fam_threshold, color=threshold_color, linestyle='solid', alpha=1 if highlight_thresholds else 0.3)
        if vic_threshold:
            ax.axvline(x=vic_threshold, color=threshold_color, linestyle='solid', alpha=1 if highlight_thresholds else 0.3)

    return fig


def plot_cluster_outliers(title, peaks):
    from pyqlb.nstats.peaks import fam_amplitudes, vic_amplitudes
    from matplotlib.patches import Ellipse

    fig = plt.figure()
    ax = fig.add_subplot(111,aspect='equal')
    
    pxs = vic_amplitudes(peaks)
    pys = fam_amplitudes(peaks)
    X   = np.c_[pxs,pys]
    ns,nf = X.shape
    loc = np.mean(X,0)
    dstd = np.std(X,0)
    if dstd[1] > 0:
	cvfam = dstd[1]/loc[1]
    Z   = (X - loc)/dstd
    zcov = np.cov(Z.T,bias=1)
    icov = np.linalg.pinv(zcov)
    dist = np.sum(np.dot(Z,icov) * Z, 1)

    term = np.median(dist)/stats.chi2(2).isf(0.5)
    ccov =zcov/term
    dist = dist/term
    
    mask = dist < stats.chi2(2).isf(0.025)
    rloc = Z[mask].mean(0)
    rcov = np.cov(Z[mask].T,bias=1)
    ircov = np.linalg.pinv(rcov)
    Zc = Z - rloc
    dist = np.sum(np.dot(Zc,ircov) * Zc, 1)

    dist3 = dist ** 0.33 # M-dist is cube root for robust case
    dth = 2.5# min sigma for outliers
    d = (dist3*(dist3 > dth)) 
    nzd = d.nonzero()
    no = len(d[nzd])
    pynzd = Z[:,1]>0
    nynzd = Z[:,1]<0
    pth99 = stats.scoreatpercentile(d[pynzd],99.9)
    nth99 = stats.scoreatpercentile(d[nynzd],99.9)
    th99  = pth99 + nth99 # average?

    ax.plot(Z[:,0],Z[:,1], linewidth=0, marker='.', markersize=1, color='gray')
    ax.plot(Z[nzd,0],Z[nzd,1], linewidth=0, marker='.', markersize=4, color='red')
    # Why is the total number of peaks reported here is lower than actual?
    plt.text(3,-12, '  # total : %5d' % (ns))
    plt.text(3,-14, ' Outliers : %.2f%%' % (np.round(100*1.0*no/ns,2)))
    plt.text(3,-16, '    M-dist : %.1f ' % np.round(th99,1))
    plt.text(3,-18, '    Metric : %.1f ' % np.round(th99*100*1.0*no/ns,1))
    plt.text(3,-20, '          CV : %.1f ' % np.round(cvfam*100.0,1))
    ax.boxplot([Z[:,1]],1,'b.',1,positions=[21])
    ax.boxplot([Z[:,0]],0,'b.',0,positions=[-21])
    matplotlib.pyplot.setp(ax,xticks=[],yticks=[])
    matplotlib.pyplot.setp(ax,xticks=[-20,-15,-10,-5,0,5,10,15,20],yticks=[-20,-15,-10,-5,0,5,10,15,20])
    plt.title(title)
    plt.xlabel('VIC amplitude')
    plt.ylabel('FAM amplitude')
    ax.set_xlim(-22,22)
    ax.set_ylim(-22,22)

    return fig

def plot_cluster_widthbins(title, peaks, amplitude_bins, min_width_gate, max_width_gate,
                           fam_threshold=None, vic_threshold=None):
    from pyqlb.nstats.peaks import fam_amplitudes, vic_amplitudes, width_rejected
    from pyqlb.nstats.peaks import width_gated, cluster_2d
    from pyqlb.nstats import balance_score_2d
    
    fig = plt.figure()
    plt.title(title)
    plt.xlabel('VIC amplitude')
    plt.ylabel('FAM amplitude')
    for i in range(len(amplitude_bins)):
        xs = [0, amplitude_bins[i][2]]
        ys = [amplitude_bins[i][2], 0]
        plt.text(0, amplitude_bins[i][2], '%.02f' % amplitude_bins[i][0])
        plt.text(amplitude_bins[i][2], 0, '%.02f' % amplitude_bins[i][1])
        plt.plot(xs, ys, linewidth=1, color='#ff6600', zorder=1)
    
    pxs = vic_amplitudes(peaks)
    pys = fam_amplitudes(peaks)
    plt.plot(pxs, pys, linewidth=0, marker='.', markersize=1, color='#999999', zorder=2)
    rejects = width_rejected(peaks, min_width_gate=min_width_gate, max_width_gate=max_width_gate)
    xs = vic_amplitudes(rejects)
    ys = fam_amplitudes(rejects)
    plt.plot(xs, ys, linewidth=0, markersize=2, markeredgewidth=1, marker='.', color='#ff0000', zorder=3)

    if fam_threshold and vic_threshold:
        plt.axhline(y=fam_threshold, color='#0000ff', zorder=1)
        plt.axvline(x=vic_threshold, color='#0000ff', zorder=1)
        g11, g10, g01, g00 = cluster_2d(width_gated(peaks, min_width_gate=min_width_gate, max_width_gate=max_width_gate),
                                        fam_threshold=fam_threshold, vic_threshold=vic_threshold)
        r11, r10, r01, r00 = cluster_2d(rejects, fam_threshold=fam_threshold, vic_threshold=vic_threshold)

        if len(r11)+len(g11) > 0:
            p11 = float(len(r11))/(len(r11)+len(g11))
        else:
            p11 = 0
        
        if len(r10)+len(g10) > 0:
            p10 = float(len(r10))/(len(r10)+len(g10))
        else:
            p10 = 0
        
        if len(r01)+len(g01) > 0:
            p01 = float(len(r01))/(len(r01)+len(g01))
        else:
            p01 = 0
        
        if len(r00)+len(g00) > 0:
            p00 = float(len(r00))/(len(r00)+len(g00))
        else:
            p00 = 0

        if amplitude_bins and len(amplitude_bins) > 1:
            xtop = max([a[2] for a in amplitude_bins])
            ytop = xtop
        else:
            xtop = max(pxs)
            ytop = max(pys)

        plt.text(xtop*0.6, ytop*0.9, "-/- %% width rejected: %.01f" % (100*p00))
        plt.text(xtop*0.6, ytop*0.85, "-/+ %% width rejected: %.01f" % (100*p01))
        plt.text(xtop*0.6, ytop*0.8, "+/- %% width rejected: %.01f" % (100*p10))
        plt.text(xtop*0.6, ytop*0.75, "+/+ %% width rejected: %.01f" % (100*p11))

        t11, t10, t01, t00 = cluster_2d(peaks, fam_threshold=fam_threshold, vic_threshold=vic_threshold)
        total_bscore = balance_score_2d(len(t00), len(t01), len(t10), len(t11))
        gated_bscore = balance_score_2d(len(g00), len(g01), len(g10), len(g11))
        
        if ( total_bscore[0] is not None):
            plt.text(xtop*0.6, ytop*0.65, "All peak B-score: %.02f" % total_bscore[0])
        else:
            plt.text(xtop*0.6, ytop*0.65, "All peak B-score is undefined")
    
        if (  gated_bscore[0] is not None):
            plt.text(xtop*0.6, ytop*0.6, "Gated B-score: %.02f" % gated_bscore[0])
        else:
            plt.text(xtop*0.6, ytop*0.6, "Gated B-score is undefined")

    return fig

def plot_cluster_orthogonality(title, fam_hi_peaks, fam_lo_peaks, vic_hi_peaks, vic_lo_peaks,
                               width=600, height=450, max_fam_amplitude=32000, max_vic_amplitude=16000):
    """
    This probably has more math than a plotting function should but it's a good place
    to test and start things
    """
    from pyqlb.nstats.peaks import fam_amplitudes, vic_amplitudes

    fig = plt.figure()
    plt.title(title)
    all_peaks = np.hstack([fam_hi_peaks, fam_lo_peaks, vic_hi_peaks, vic_lo_peaks])
    xs = vic_amplitudes(all_peaks)
    ys = fam_amplitudes(all_peaks)
    H, xedges, yedges = np.histogram2d(ys, xs, bins=[height,width], range=[[-4000,max_fam_amplitude],[-2000,max_vic_amplitude]])
    vmax = min(256, float(10000000)/(height*width))

    cmap = jet(vmax, np.max(H))
    cmap.set_under(alpha=0.0)
    # make zeros transparent
    H[H==0]=-1
    ax = plt.gca()
    ax.patch.set_alpha(0.0)

    plt.imshow(H, origin='lower', cmap=cmap, vmin=0, vmax=vmax, zorder=2)
    plt.axvline(x=(2000*width)/(max_vic_amplitude+2000), color='#cccccc')
    plt.axhline(y=(4000*height)/(max_fam_amplitude+4000), color='#cccccc')
    plt.xticks([0,67,100,200,300,400,500,600],[-2000,0,1000,4000,7000,10000,13000,16000])
    plt.yticks([0,50,90,180,270,360,450],[-4000,0,3200,10400,17600,24800,32000])

    fam_hi_f = np.mean(fam_amplitudes(fam_hi_peaks))
    fam_hi_v = np.mean(vic_amplitudes(fam_hi_peaks))
    fam_lo_f = np.mean(fam_amplitudes(fam_lo_peaks))
    fam_lo_v = np.mean(vic_amplitudes(fam_lo_peaks))
    vic_hi_f = np.mean(fam_amplitudes(vic_hi_peaks))
    vic_hi_v = np.mean(vic_amplitudes(vic_hi_peaks))
    vic_lo_f = np.mean(fam_amplitudes(vic_lo_peaks))
    vic_lo_v = np.mean(vic_amplitudes(vic_lo_peaks))

    def xform(fam, vic):
        return (height*((fam+4000.0)/(max_fam_amplitude+4000)), width*((vic+2000.0)/(max_vic_amplitude+2000)))
    
    fh = xform(fam_hi_f, fam_hi_v)
    fl = xform(fam_lo_f, fam_lo_v)
    vh = xform(vic_hi_f, vic_hi_v)
    vl = xform(vic_lo_f, vic_lo_v)

    plt.plot([fl[1],fh[1]],[fl[0],fh[0]], zorder=3)
    plt.plot([vl[1],vh[1]],[vl[0],vh[0]], zorder=3)
    
    fam_vec = [fam_hi_v-fam_lo_v, fam_hi_f-fam_lo_f]
    vic_vec = [vic_hi_v-vic_lo_v, vic_hi_f-vic_lo_f]
    dot = np.dot(fam_vec, vic_vec)
    norm_diff = abs(90-np.rad2deg(math.acos(dot/(math.hypot(*fam_vec)*math.hypot(*vic_vec)))))
    fam_diff = np.rad2deg(math.atan(fam_vec[0]/fam_vec[1]))
    vic_diff = np.rad2deg(math.atan(vic_vec[1]/vic_vec[0]))

    # maybe there is an easier way to do this, but this is how my brain works
    # y = mx + b forever
    mf = fam_vec[1]/fam_vec[0]
    mv = vic_vec[1]/vic_vec[0]

    bf = fam_hi_f - mf*fam_hi_v
    bv = vic_hi_f - mv*vic_hi_v

    xv = (bv-bf)/(mf-mv)
    xf = mf*xv + bf

    plt.text(width-300, height-50, 'FAM off normal: %.01fdeg' % fam_diff)
    plt.text(width-300, height-70, 'VIC off normal: %.01fdeg' % vic_diff)
    plt.text(width-300, height-90, 'FAM/VIC isect off normal: %.01fdeg' % norm_diff)
    plt.text(width-300, height-110, 'FAM/VIC isect off origin: %.01f' % math.sqrt(xv**2+xf**2))

    return fig

def plot_2d_rain(title, fam_peaks, vic_peaks,
                 width=600, height=450, max_fam_amplitude=32000, max_vic_amplitude=16000,
                 fam_rain_threshold=.0975, vic_rain_threshold=.135):
    """
    This also probably has more math than a plotting function should but it's a good place
    to test and start things
    """
    from pyqlb.nstats.peaks import fam_amplitudes, vic_amplitudes, rain_pvalues_thresholds, cluster_2d

    fig = plt.figure()
    plt.title(title)
    all_peaks = np.hstack([fam_peaks, vic_peaks])

    # TODO: generic 2d plotting function?
    xs = vic_amplitudes(all_peaks)
    ys = fam_amplitudes(all_peaks)
    H, xedges, yedges = np.histogram2d(ys, xs, bins=[height,width], range=[[-4000,max_fam_amplitude],[-2000,max_vic_amplitude]])
    vmax = min(256, float(10000000)/(height*width))

    cmap = jet(vmax, np.max(H))
    cmap.set_under(alpha=0.0)
    # make zeros transparent
    H[H==0]=-1
    ax = plt.gca()
    ax.patch.set_alpha(0.0)

    plt.imshow(H, origin='lower', cmap=cmap, vmin=0, vmax=vmax, zorder=2)
    plt.axvline(x=(2000*width)/(max_vic_amplitude+2000), color='#cccccc')
    plt.axhline(y=(4000*height)/(max_fam_amplitude+4000), color='#cccccc')
    plt.xticks([0,67,100,200,300,400,500,600],[-2000,0,1000,4000,7000,10000,13000,16000])
    plt.yticks([0,50,90,180,270,360,450],[-4000,0,3200,10400,17600,24800,32000])

    # this part can go in a calculation
    nil, nil, nil, nil, nil, nil, fam_low = rain_pvalues_thresholds(fam_peaks, channel_num=0, threshold=None, pct_boundary=fam_rain_threshold)
    nil, nil, nil, nil, nil, nil, vic_low = rain_pvalues_thresholds(vic_peaks, channel_num=1, threshold=None, pct_boundary=vic_rain_threshold)

    # find total % of all peaks
    dontcare, dontcare, dontcare, rain = cluster_2d(all_peaks, fam_low, vic_low)


    def xform(fam, vic):
        return (height*((fam+4000.0)/(max_fam_amplitude+4000)), width*((vic+2000.0)/(max_vic_amplitude+2000)))
    
    fam_rain, nil = xform(fam_low, 0)
    nil, vic_rain = xform(0, vic_low)

    plt.axhline(y=fam_rain)
    plt.axvline(x=vic_rain)
    
    plt.text(10, 10, '-/- rain peaks: %s (%.02f%%)' % (len(rain), 100*float(len(rain))/len(all_peaks)))
    

    return fig



# TODO adapt for PyQLB 0.9
def plot_gated_types(qlwell,
                     width=300, height=300,
                     vertical_streak_color='green',
                     quality_color='blue',
                     width_color='red',
                     min_amplitude_color='yellow',
                     max_amplitudes=None):
    # TODO: combine into common plotter
    cm = matplotlib
    peaks = qlwell.peaks
    binwidth = int(len(peaks)/float(24000) * width)+1
    binheight = height/2
    fig = plt.figure(1, figsize=(float(binwidth)/72,
                                 (float(binheight)*2)/72),
                                 dpi=72,
                                 frameon=False,
                                 subplotpars=matplotlib.figure.SubplotParams(left=0,right=1,bottom=0,top=1,wspace=0,hspace=0))
    ax = fig.add_axes([0,0.5,1,0.5], frameon=False)
    ax.set_axis_off()
    ax.axis([0,len(peaks),0,max_amplitudes[0]])
    from pyqlb.nstats.peaks import fam_amplitudes, vic_amplitudes
    from pyqlb.nstats.peaks import width_rejected, quality_rejected
    from pyqlb.nstats.well import vertical_streak_peaks, min_amplitude_peaks 
    if not max_amplitudes:
        max_amplitudes = (24000,24000)
    
    fs = fam_amplitudes(peaks)
    vs = vic_amplitudes(peaks)
    xs = range(len(fs))

    vss = vertical_streak_peaks(qlwell)
    mas = min_amplitude_peaks(qlwell)
    wrs = width_rejected(peaks, min_width_gate=qlwell.channels[0].statistics.min_width_gate,
                         max_width_gate=qlwell.channels[0].statistics.max_width_gate)
    qrs = quality_rejected(peaks, min_quality_gate=qlwell.channels[0].statistics.min_quality_gate,
                           include_vertical_streak_flagged=False)
    
    # invert peaks
    tdict = dict()
    for i, p in enumerate(peaks):
        tdict[p['time']] = i
    
    vis = [tdict[v['time']] for v in vss]
    mis = [tdict[m['time']] for m in mas]
    wis = [tdict[w['time']] for w in wrs]
    qis = [tdict[q['time']] for q in qrs] 
    

    ax.plot(xs, fs, linewidth=0, marker='.', markersize=1, color='#999999', zorder=2, alpha=1)
    ax.plot(qis, fs[qis], linewidth=0, marker='.', markersize=1, color=quality_color, zorder=2, alpha=1)
    ax.plot(wis, fs[wis], linewidth=0, marker='.', markersize=1, color=width_color, zorder=3, alpha=1, antialiased=False)
    ax.plot(mis, fs[mis], linewidth=0, marker='.', markersize=1, color=min_amplitude_color, zorder=4, alpha=1, antialiased=False)
    ax.plot(vis, fs[vis], linewidth=0, marker='.', markersize=1, color=vertical_streak_color, zorder=5, alpha=1)

    ax = fig.add_axes([0,0,1,0.5], frameon=False)
    ax.set_axis_off()
    ax.axis([0,len(peaks),0,max_amplitudes[1]])

    xs = range(len(peaks))

    ax.plot(xs, vs, linewidth=0, marker='.', markersize=1, color='#999999', zorder=2, alpha=1)
    ax.plot(qis, vs[qis], linewidth=0, marker='.', markersize=1, color=quality_color, zorder=2, alpha=1)
    ax.plot(vis, vs[vis], linewidth=0, marker='.', markersize=1, color=vertical_streak_color, zorder=3, alpha=1)
    ax.plot(wis, vs[wis], linewidth=0, marker='.', markersize=1, color=width_color, zorder=4, alpha=1)
    ax.plot(mis, vs[mis], linewidth=0, marker='.', markersize=1, color=min_amplitude_color, zorder=5, alpha=1, antialiased=False)

    return fig

def plot_amp_hist(peaks,
                  title='Histogram',
                  channel_num = 0,
                  threshold=None):
    
    from pyqlb.nstats.peaks import cluster_1d, skew, kurtosis, channel_amplitudes
    fig = plt.figure()
    ax = fig.add_subplot(111)

    amps = channel_amplitudes(peaks, channel_num)
    n, bins, patches = plt.hist(amps, 300, color='blue' if channel_num == 0 else 'green', linewidth=0)
    
    if threshold:
        plt.axvline(x=threshold, color='red')
    
    plt.title('%s - %s' % (title, 'VIC' if channel_num == 1 else 'FAM'))
    plt.xlabel('Amplitude')
    ax.axis([plt.xlim()[0], plt.xlim()[1], plt.ylim()[0], plt.ylim()[1]*1.2])

    if threshold:
        positive_peaks, negative_peaks = cluster_1d(peaks, channel_num, threshold)
        pos_skew = skew(positive_peaks, channel_num)
        pos_kur = kurtosis(positive_peaks, channel_num)
        neg_skew = skew(negative_peaks, channel_num)
        neg_kur = kurtosis(negative_peaks, channel_num)
        
        plt.text(0.05, 0.95,
                 'Negatives\nSkew: %.03f\nKurtosis: %.03f' % (neg_skew, neg_kur),
                 transform = ax.transAxes,
                 verticalalignment='top')
        
        plt.text(0.95, 0.95,
                 'Positives\nSkew: %.03f\nKurtosis: %.03f' % (pos_skew, pos_kur),
                 transform = ax.transAxes,
                 verticalalignment='top',
                 horizontalalignment='right')
    else:
        pskew = skew(peaks, channel_num)
        kur = kurtosis(peaks, channel_num)

        plt.text(0.05, 0.95,
                 'Skew: %.03f\nKurtosis: %.03f' % (pskew, kur),
                 transform = ax.transAxes,
                 verticalalignment='top')


    return fig
    
def nds(title, peaks, threshold):
    from pyqlb.nstats.peaks import normalized_droplet_spacing
    fig = plt.figure()
    ax = fig.add_subplot(111)

    iei = normalized_droplet_spacing(peaks)

    under = len(np.extract(iei < threshold, iei))
    over = len(np.extract(iei >= threshold, iei))

    n, bins, patches = plt.hist(iei, 60, range=(0,15), color='blue', linewidth=1)

    plt.axvline(x=threshold, color='red')

    plt.title(title)
    plt.xlabel('Interval bins (0.25)')
    plt.text(0.05, 0.97, 'Under %.02f: %s' % (threshold, under), transform = ax.transAxes, verticalalignment='top')
    plt.text(0.95, 0.97, 'Over %.02f: %s' % (threshold, over), transform = ax.transAxes, verticalalignment='top', horizontalalignment='right')
    plt.text(0.95, 0.25, '%% Under Threshold: %.01f' % (float(under)*100/len(iei)), transform = ax.transAxes, verticalalignment='top', horizontalalignment='right')
    #ax.axis([plt.xlim()[0],10,plt.ylim()[0], plt.ylim()[1]*1.2])
    return fig

def air_hist(title, amps, cutoff=500, num_accepted=None):
    fig = plt.figure()
    ax = fig.add_subplot(111)

    n, bins, patches = plt.hist(amps, 50, range=(0, 1000), color='blue', linewidth=1)
    ax.axis([plt.xlim()[0],plt.xlim()[1],plt.ylim()[0], plt.ylim()[1]*1.3])

    plt.axvline(x=cutoff, color='red')
    plt.title(title)
    plt.xlabel("Uncorrected VIC Amplitudes")
    plt.ylabel('# Air droplets')
    plt.xticks([0,100,200,300,400,500,600,700,800,900,1000])
    plt.text(25, max(n)*1.2, 'Mean: %.02f' % np.mean(amps))
    plt.text(25, max(n)*1.15, 'Stdev: %.02f' % np.std(amps))
    if num_accepted is not None:
        plt.text(25, max(n)*1.05, '# Accepted air droplets: %d' % num_accepted)

    above_cutoff = [a for a in amps if a > cutoff]
    if len(amps) > 0:
        plt.text(25, max(n)*1.1, '# Above %s threshold: %s (%.02f%%)' % \
                    (cutoff, len(above_cutoff), 100.0*len(above_cutoff)/len(amps)))
        plt.text(25, max(n)*1.25, 'Total: %s' % len(amps))
    return fig
    

def movavgplot(ax, title, tuples, series_args=None, **chart_args):
    from matplotlib.mlab import movavg
    if not series_args:
        series_args = dict()

    xs = [t[0] for t in tuples]
    ys = [float(t[1]) for t in tuples]

    ax.plot(xs, ys, linewidth=0, marker='x', **series_args)
    plt.title(title)

    # patternize?
    if len(ys) > 61:
        mo = movavg(ys, chart_args.get('window', 30))
        ax.plot(xs[(len(xs)-len(mo)):], mo, linewidth=1, color='#ff0000')
    ax.text(0.05, 0.05, 'Mean: %.02f; Stddev: %.04f' % (np.mean(ys), np.std(ys)),
            transform = ax.transAxes)

def runseries(fig, title, tuples, series_args=None, **chart_args):
    ax = fig.add_subplot(111)

    # FIXFIX this is a memory hit (iter instead of tuples?)
    runseq = [(idx, val) for idx, val in enumerate([tup[1] for tup in tuples])]
    movavgplot(ax, title, runseq, series_args, **chart_args)
    plt.xlabel(chart_args.get('xlabel', 'Run #'))
    plt.ylabel(chart_args.get('ylabel', ''))

def timeseries(fig, title, tuples, series_args=None, **chart_args):
    """
    Simple timeseries with moving average.
    """
    ax = fig.add_subplot(111)
    movavgplot(ax, title, tuples, series_args, **chart_args)
    plt.xlabel(chart_args.get('xlabel', 'Date/Time'))
    plt.ylabel(chart_args.get('ylabel', ''))
    ax.xaxis.set_major_locator(matplotlib.dates.DayLocator())
    ax.xaxis.set_major_formatter(matplotlib.dates.DateFormatter('%m/%d'))
    

def dg_vacuum_runs(subtitle, dg_runs, thumbnail=False):
    title = 'Run Time - %s' % subtitle
    tuples = [(dg.datetime, dg.vacuum_time) for dg in dg_runs]
    fig = plt.figure()
    setsize(fig, thumbnail)
    runseries(fig, title, tuples, ylabel="Run time (sec)")
    return fig

def dg_vacuum_time(subtitle, dg_runs, thumbnail=False):
    title = 'Run Time - %s' % subtitle
    tuples = [(dg.datetime, dg.vacuum_time) for dg in dg_runs]
    fig = plt.figure()
    setsize(fig, thumbnail)
    timeseries(fig, title, tuples, ylabel="Run time (sec)")
    return fig

def dg_pressure_runs(subtitle, dg_runs, thumbnail=False):
    title = 'Vacuum Pressure - %s' % subtitle
    tuples = [(dg.datetime, dg.vacuum_pressure) for dg in dg_runs]
    fig = plt.figure()
    setsize(fig, thumbnail)
    runseries(fig, title, tuples, ylabel="Vacuum pressure (PSI)")
    plt.ylim(-3.4,-3.6)
    return fig

def dg_pressure_time(subtitle, dg_runs, thumbnail=False):
    title = 'Vacuum Pressure - %s' % subtitle
    tuples = [(dg.datetime, dg.vacuum_pressure) for dg in dg_runs]
    fig = plt.figure()
    setsize(fig, thumbnail)
    timeseries(fig, title, tuples, ylabel="Vacuum pressure (PSI)")
    plt.ylim(-3.4,-3.6)
    return fig

def dg_spike_runs(subtitle, dg_runs, thumbnail=False):
    title = 'Pressure Spike - %s' % subtitle
    tuples = [(dg.datetime, dg.spike) for dg in dg_runs]
    fig = plt.figure()
    setsize(fig, thumbnail)
    runseries(fig, title, tuples, ylabel="Pressure Spike Derivative (PSI/s)")
    return fig

def dg_spike_time(subtitle, dg_runs, thumbnail=False):
    title = 'Pressure Spike - %s' % subtitle
    tuples = [(dg.datetime, dg.spike) for dg in dg_runs]
    fig = plt.figure()
    setsize(fig, thumbnail)
    timeseries(fig, title, tuples, ylabel="Pressure Spike Derivative (PSI/s)")
    return fig

def svilen(title, raw_data, ranges, widths):
    fig = plt.figure()
    plt.title(title)
    if len(ranges) == 0:
        setsize(fig)
        return fig
    rows, extra = divmod(len(ranges), 4)
    fig.set_figwidth(10)

    if extra > 0:
        rows = rows + 1
    fig.set_figheight(2*rows)
    
    for i, (begin, end) in enumerate(ranges):
        samples = raw_data[begin:end+1]
        row, col = divmod(i, 4)
        ax = plt.subplot(rows, min(len(ranges), 4), i+1)
        ys = ranges
        ax.set_xlabel("%.02f" % widths[i])
        ax.set_xticks([])
        ax.set_yticks([0,np.max([s[0] for s in samples]), np.max([s[1] for s in samples])])
        ax.plot(range(begin, end+1), [s[0] for s in samples], color='blue')
        ax.plot(range(begin, end+1), [s[1] for s in samples], color='red')
    return fig



def empty_fig(thumbnail=False):
    fig = plt.figure()
    setsize(fig, thumbnail)
    return fig

def cleanup(figure):
    try:
        # note: this cleanup is pretty time-consuming, though
        # not doing this tends to max out memory and cause
        # swapping.  If there is a smart way to figure out how
        # to do this... but available memory is not a guarantee.
        plt.gcf()
        plt.clf()
        plt.cla()
        plt.close()
    except Exception, e:
        pass
    del figure
    
def render(figure, dpi=72, **args):
    imgdata = StringIO.StringIO()
    figure.savefig(imgdata, format='png', dpi=dpi, **args)
    return imgdata.getvalue()

def setsize(fig, thumbnail=False):
    if thumbnail:
        fig.set_figwidth(3.2)
        fig.set_figheight(2.4)
    else:
        fig.set_figwidth(10)
        fig.set_figheight(7.5)
