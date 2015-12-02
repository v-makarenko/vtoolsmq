import logging, StringIO, gc

from pylons import request, response, session, tmpl_context as c, url, config
from pylons.controllers.util import abort

from qtools.lib.beta import *
from qtools.lib.storage import QLStorageSource
from qtools.lib.qlb_factory import get_well
from qtools.lib.base import BaseController
from qtools.model import QLBWell, Session, DropletGenerator

log = logging.getLogger(__name__)

deps_loaded = False
try:
    import numpy as np
    import numpy.fft.fftpack
    from qtools.lib.nstats import fft
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    deps_loaded = True
except ImportError, e:
    pass

FFT_DOWNSAMPLE = 23

class NplotController(BaseController):

    def fft(self, id=None):
        from qtools.lib.mplot import cleanup, render as plt_render
        # make it better?
        if not deps_loaded:
            abort(500)
        
        if not id:
            abort(404)
        
        well = Session.query(QLBWell).get(id)
        if not well:
            abort(404)
        
        file = well.file
        if not file:
            abort(404)
            
        storage = QLStorageSource(config)
        path = storage.qlbwell_path(well)
        wellobj = get_well(path)
        
        fam_samples = wellobj.samples[:,0][::FFT_DOWNSAMPLE].astype('float')
        vic_samples = wellobj.samples[:,1][::FFT_DOWNSAMPLE].astype('float')

        # normalize to 0->1
        fam_samples /= np.max(fam_samples)
        vic_samples /= np.max(vic_samples)

        Sf = np.fft.fft(fam_samples)
        numpy.fft.fftpack._fft_cache = {}
        ff = np.fft.fftfreq(len(Sf), d=FFT_DOWNSAMPLE/wellobj.data_acquisition_params.sample_rate)

        # only consider positive half of frequency domain, normalize by num of samples
        Yf = abs(Sf[0:len(ff)/2])/len(fam_samples)

        # make X-axis in terms of Hz
        Wf = int((len(ff)/2)/max(ff)) # group by 1 Hz

        Sv = np.fft.fft(vic_samples)
        numpy.fft.fftpack._fft_cache = {}
        fv = np.fft.fftfreq(len(Sv), d=FFT_DOWNSAMPLE/wellobj.data_acquisition_params.sample_rate)
        Yv = abs(Sv[0:len(fv)/2])/len(vic_samples)
        Wv = int((len(fv)/2)/max(fv)) # group by 1 Hz

        # find peaks
        fam_peak_indices = fft.find_peak_indices(Yf, Wf*2) # group by 2Hz
        vic_peak_indices = fft.find_peak_indices(Yv, Wv*2) # group by 2Hz

        ftops = ff.take(fam_peak_indices)[0:10]
        vtops = fv.take(vic_peak_indices)[0:10]

        fig = plt.figure()
        fig.set_figwidth(8)
        fig.set_figheight(6)
        plt.subplot(211)

        plt.title('FAM Channel FFT (0-150Hz)')
        plt.plot(ff[0:len(ff)/2], Yf)
        plt.axis([-10, 150, -0.002, 0.04])
        plt.text(70, 0.03, "Top Peaks (2 Hz windows):", weight='bold')
        for i, val in enumerate(ftops):
            plt.text(70 if i < 5 else 90, 0.027-(0.003*(i % 5)), "%.2f" % val, size=10)

        # todo render text func?
        
        
        plt.subplot(212)
        plt.title('VIC Channel FFT (0-150Hz)')
        plt.plot(fv[0:len(fv)/2], Yv)
        plt.axis([-10, 150, -0.002, 0.04])
        plt.text(70, 0.03, "Top Peaks (2 Hz windows):", weight='bold')
        for i, val in enumerate(vtops):
            plt.text(70 if i < 5 else 90, 0.027-(0.003*(i % 5)), "%.2f" % val, size=10)

        # fft leaves cache-- not good for threaded server
        imgdata = self.__render(fig)
        cleanup(fig)
        del fig, wellobj, fam_samples, vic_samples, Sf, ff, Yf, Wf, Sv, fv, Yv, Wv, ftops, vtops
        gc.collect()
        return imgdata

    
    def dg_trend(self, prop, view, dg_id):
        from qtools.lib.mplot import dg_vacuum_time, dg_vacuum_runs, dg_pressure_time, dg_pressure_runs, dg_spike_runs, dg_spike_time
        from qtools.lib.mplot import cleanup, render as plt_render
        if id is None:
            abort(404)
        
        dg = Session.query(DropletGenerator).get(int(dg_id))
        if not dg:
            abort(404)
        
        func_map = dict([(('vacuum', 'time'), dg_vacuum_time),
                         (('vacuum', 'runs'), dg_vacuum_runs),
                         (('pressure', 'time'), dg_pressure_time),
                         (('pressure', 'runs'), dg_pressure_runs),
                         (('spike', 'runs'), dg_spike_runs),
                         (('spike', 'time'), dg_spike_time)])

        good_runs = get_good_dg_runs(int(dg_id))
        fig = func_map[(prop, view)](dg.name, good_runs)
        response.content_type = 'image/png'
        imgdata = plt_render(fig, dpi=72)
        cleanup(fig)
        return imgdata

        
    def __render(self, figure):
        response.content_type = 'image/png'
        imgdata = StringIO.StringIO()
        figure.savefig(imgdata, format='png', dpi=72)
        return imgdata.getvalue()
        
        
        
