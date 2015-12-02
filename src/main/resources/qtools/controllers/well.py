import logging, StringIO, csv as csv_pkg

from pylons import request, response, session, tmpl_context as c, config
from pylons.controllers.util import abort, forward
from pylons.decorators import validate, jsonify
from pylons.decorators.rest import restrict

from pyqlb.nstats import cnv as get_cnv
from pyqlb.nstats.well import well_channel_automatic_classification
from pyqlb.objects import QLWellChannelStatistics, QLWell

from paste.fileapp import FileApp

from qtools.constants.plot import *
from qtools.lib.base import BaseController, render
from qtools.lib.decorators import block_contractor_internal_wells, help_at
from qtools.lib.qlb import stats_for_qlp_well
from qtools.lib.storage import *
from qtools.lib import helpers as h
from qtools.lib.validators import IntKeyValidator
from qtools.model import Session, QLBWell, QLBPlate, WellTag, QLBWellTag, Person
from qtools.model import WellMetric, PlateMetric, AnalysisGroup, ReprocessConfig, analysis_group_reprocess_table as agr
import qtools.lib.fields as fl

from sqlalchemy import and_, select
from sqlalchemy.orm import joinedload_all

import formencode

log = logging.getLogger(__name__)

class ThresholdForm(formencode.Schema):
    allow_extra_fields = True
    filter_extra_fields = True
    
    fam_threshold = formencode.validators.Number(not_empty=False, if_missing=None)
    vic_threshold = formencode.validators.Number(not_empty=False, if_missing=None)
    max_fam_amplitude = formencode.validators.Number(not_empty=False, if_missing=24000)
    max_vic_amplitude = formencode.validators.Number(not_empty=False, if_missing=12000)
    analysis_group_id = formencode.validators.Number(not_empty=False, if_missing=None)
    reprocess_config_id = formencode.validators.Number(not_empty=False, if_missing=None)


class WellTagForm(formencode.Schema):
    allow_extra_fields = True
    filter_extra_fields = True
    
    well_id = IntKeyValidator(QLBWell, 'id', not_empty=True)
    tag_id = IntKeyValidator(WellTag, 'id', not_empty=True)
    tagger_id = IntKeyValidator(Person, 'id', not_empty=False, if_missing=None)

class WellController(BaseController):

    def __setup_db_context(self, well_id):
        c.well = Session.query(QLBWell).filter_by(id=well_id)\
                         .options(joinedload_all(QLBWell.channels, innerjoin=True),
                                  joinedload_all(QLBWell.plate, QLBPlate.plate)).first()
        if not c.well:
            abort(404)
        
        c.reprocess_config_id = self.form_result['reprocess_config_id']
        c.analysis_group_id = self.form_result['analysis_group_id']
        # check for thing in relational table
        if c.reprocess_config_id and c.analysis_group_id:
            rec = Session.execute(select([agr]).where(and_(agr.c.analysis_group_id==int(c.analysis_group_id),
                                                           agr.c.reprocess_config_id==int(c.reprocess_config_id))))
            # check for an existing record
            if rec.rowcount > 0:
                # awesome, get the reprocess config name
                c.reprocess_config = Session.query(ReprocessConfig).get(c.reprocess_config_id)
                c.analysis_group = Session.query(AnalysisGroup).get(c.analysis_group_id)

                # get the plate metric for the plate
                c.well_metric = Session.query(WellMetric)\
                                        .join(PlateMetric)\
                                        .filter(and_(WellMetric.well_id==c.well.id,
                                                     PlateMetric.reprocess_config_id==c.reprocess_config_id))\
                                        .options(joinedload_all(WellMetric.well_channel_metrics, innerjoin=True)).first()
            else:
                c.reprocess_config = None
                c.analysis_group = None
        else:
            c.reprocess_config = None
            c.analysis_group = None
        
        if not c.reprocess_config:
            # try to find an existing well metric
            c.well_metric = Session.query(WellMetric)\
                                   .join(PlateMetric)\
                                   .filter(and_(WellMetric.well_id==c.well.id,
                                                PlateMetric.reprocess_config_id==None))\
                                   .options(joinedload_all(WellMetric.well_channel_metrics, innerjoin=True)).first()

        if not c.well_metric:
            c.cluster_calc_mode = False
        else:
            c.cluster_calc_mode = c.well_metric.cnv_calc_mode == QLWellChannelStatistics.CONC_CALC_MODE_CLUSTER

    
    def __plate_path(self):
        if not c.reprocess_config:
            storage = QLStorageSource(config)
            path = storage.qlbplate_path(c.well.plate)
        else:
            source = QLPReprocessedFileSource(config['qlb.reprocess_root'], c.reprocess_config)
            path = source.full_path(c.analysis_group, c.well.plate.plate)
        
        return path
    
    def __well_path(self):
        storage = QLStorageSource(config)
        return storage.qlbwell_path(c.well)
    
    def __set_threshold_context(self, qlwell):
        thresholds = [self.form_result['fam_threshold'], self.form_result['vic_threshold']]
        if not thresholds[0]:
            c.fam_threshold = qlwell.channels[0].statistics.threshold
        else:
            c.fam_threshold = thresholds[0]
        if not thresholds[1]:
            c.vic_threshold = qlwell.channels[1].statistics.threshold
        else:
            c.vic_threshold = thresholds[1]


    @help_at('features/well_view.html')
    @validate(schema=ThresholdForm(), form='view', post_only=False, on_get=True)
    @block_contractor_internal_wells
    def view(self, id=None, *args, **kwargs):
        file_ok = False
        qlwell = None
        try:
            qlwell = self.__qlwell_from_threshold_form(id)
            file_ok = True
        except IOError:
            path = self.__plate_path()
            session['flash'] = "Could not read file: %s" % path
            session['flash_class'] = 'error'

        
        # this may be easier/more efficient to ascertain via direct SQL, but going ORM route
        well_ids = Session.query(QLBWell.id, QLBWell.well_name).filter(and_(QLBWell.plate_id == c.well.plate_id,
                                                      QLBWell.file_id != None)).\
                                          order_by(QLBWell.id).all()
        
        current_idx = -1
        for idx, (id, well_name) in enumerate(well_ids):
            if c.well.id == id:
                current_idx = idx
                break
        
        if current_idx == 0:
            c.prev_well_id = None
            c.prev_well_name = None
        else:
            c.prev_well_id, c.prev_well_name = well_ids[current_idx-1]
        
        if current_idx == len(well_ids)-1:
            c.next_well_id = None
            c.next_well_name = None
        else:
            c.next_well_id, c.next_well_name = well_ids[current_idx+1]
        
        thresholds = [self.form_result['fam_threshold'], self.form_result['vic_threshold']]
        c.fam_threshold, c.vic_threshold = thresholds
        for i, t in enumerate(thresholds):
            if t == 0:
                thresholds[i] = None
        
        max_amplitudes = [self.form_result['max_fam_amplitude'], self.form_result['max_vic_amplitude']]
        c.max_fam_amplitude, c.max_vic_amplitude = max_amplitudes

        if file_ok and qlwell:
            # get at well first
            statistics, cluster_data = stats_for_qlp_well(qlwell, compute_clusters=True, override_thresholds=thresholds)
            fam_cnv = get_cnv(statistics[0].positives, statistics[0].negatives,
                              statistics[1].positives, statistics[1].negatives,
                              reference_copies=statistics.ref_copy_num)
            vic_cnv = get_cnv(statistics[1].positives, statistics[1].negatives,
                              statistics[0].positives, statistics[0].negatives,
                              reference_copies=statistics.ref_copy_num)

            c.cluster_data = cluster_data
            c.statistics = statistics
            c.fam_cnv = fam_cnv
            c.vic_cnv = vic_cnv
            c.alg_version = statistics.alg_version

            if h.wowo('numpy.well_frag') and hasattr(c, 'cluster_data'):
                from qtools.lib.nstats import frag
                from pyqlb.nstats import chisquare_2d, zscore_2d, linkage_2d, balance_score_2d
                from pyqlb.nstats.well import BSCORE_MINIMUM_CLUSTER_SIZE
                n00 = len(c.cluster_data['negative_peaks']['negative_peaks'])
                n01 = len(c.cluster_data['negative_peaks']['positive_peaks'])
                n10 = len(c.cluster_data['positive_peaks']['negative_peaks'])
                n11 = len(c.cluster_data['positive_peaks']['positive_peaks'])

                frag_stats = frag.prob_of_frag(n10,n11,n00,n01,
                                               statistics[0].positives+statistics[0].negatives)
                c.frag_stats = frag_stats

                chi_stat, chi_p = chisquare_2d(n11,n10,n01,n00,
                                               yates_correction=True)
                c.chi_stat = chi_stat
                c.chi_p = chi_p

                z_fpvn, z_fpvp_vn, z_fpvp_fn, z_fnvp = \
                    zscore_2d(n11,n10,n01,n00)

                c.zscores = (z_fpvn, z_fpvp_vn, z_fpvp_fn, z_fnvp)
                c.linkage = linkage_2d(n11,n10,n01,n00)

                c.bscore =  balance_score_2d(n00,n01,n10,n11)[0]
                #if n00 >= BSCORE_MINIMUM_CLUSTER_SIZE \
                #   and n01 >= BSCORE_MINIMUM_CLUSTER_SIZE \
                #   and n10 >= BSCORE_MINIMUM_CLUSTER_SIZE \
                #   and n11 >= BSCORE_MINIMUM_CLUSTER_SIZE:
               
        return render('/well/view.html')
    
    def __qlwell_from_threshold_form(self, id):
        from qtools.lib.qlb_factory import get_plate

        self.__setup_db_context(int(id))
        path = self.__plate_path()
        plate = get_plate(path)

        qlwell = plate.analyzed_wells.get(c.well.well_name, None)
        if not qlwell:
            abort(404)
        else:
            return qlwell
    
    def __get_1d_background_rgbs(self, qlwell):
        rgbs = [None, None]
        if well_channel_automatic_classification(qlwell, 0):
            rgbs[0] = AUTO_THRESHOLD_FAM_BGCOLOR
        else:
            rgbs[0] = MANUAL_THRESHOLD_FAM_BGCOLOR
        if well_channel_automatic_classification(qlwell, 1):
            rgbs[1] = AUTO_THRESHOLD_VIC_BGCOLOR
        else:
            rgbs[1] = MANUAL_THRESHOLD_VIC_BGCOLOR
        
        return rgbs
    
    @validate(schema=ThresholdForm(), post_only=False, on_get=True)
    @block_contractor_internal_wells
    def threshold(self, id=None, show_only_gated=True, *args, **kwargs):
        from qtools.lib.mplot import plot_fam_vic_peaks, cleanup, render as plt_render
        from qtools.lib.nstats.peaks import accepted_peaks
        response.content_type = 'image/png'
        
        qlwell = self.__qlwell_from_threshold_form(id)
        self.__set_threshold_context(qlwell)
        max_amplitudes = [self.form_result['max_fam_amplitude'], self.form_result['max_vic_amplitude']]
        
        # to emulate current behavior -- include gated events
        if show_only_gated != 'False':
            peaks = accepted_peaks(qlwell)
        else:
            peaks = qlwell.peaks
        
        fig = plot_fam_vic_peaks(peaks, thresholds=(c.fam_threshold, c.vic_threshold),
                                 max_amplitudes=max_amplitudes,
                                 background_rgbs=self.__get_1d_background_rgbs(qlwell))
        response.content_type = 'image/png'
        imgdata = plt_render(fig, dpi=72)
        cleanup(fig)
        return imgdata
    
    @validate(schema=ThresholdForm(), form='view', post_only=False, on_get=True)
    @block_contractor_internal_wells
    def noreject(self, id=None, *args, **kwargs):
        from qtools.lib.mplot import plot_gated_types, cleanup, render as plt_render
        response.content_type = 'image/png'
        
        qlwell = self.__qlwell_from_threshold_form(id)
        self.__set_threshold_context(qlwell)
        max_amplitudes = [self.form_result['max_fam_amplitude'], self.form_result['max_vic_amplitude']]
        
        fig = plot_gated_types(qlwell,
                               max_amplitudes=max_amplitudes)
        response.content_type = 'image/png'
        imgdata = plt_render(fig, dpi=72)
        cleanup(fig)
        return imgdata
    
    @validate(schema=ThresholdForm(), post_only=False, on_get=True)
    @block_contractor_internal_wells
    def amphist(self, id=None, channel_num=0, *args, **kwargs):
        from qtools.lib.mplot import plot_amp_hist, cleanup, render as plt_render
        from pyqlb.nstats.well import accepted_peaks

        response.content_type = 'image/png'
        c.channel_num = int(channel_num)
        qlwell = self.__qlwell_from_threshold_form(id)
        
        self.__set_threshold_context(qlwell)
        peaks = accepted_peaks(qlwell)
        fig = plot_amp_hist(peaks,
                            title='%s - %s' % (c.well.plate.plate.name, c.well.well_name),
                            channel_num=c.channel_num,
                            threshold=(c.vic_threshold if c.channel_num == 1 else c.fam_threshold))
        imgdata = plt_render(fig, dpi=72)
        cleanup(fig)
        return imgdata
    
    @validate(schema=ThresholdForm(), post_only=False, on_get=True)
    @block_contractor_internal_wells
    def amptime(self, id=None, channel_num=0, *args, **kwargs):
        from qtools.lib.mplot import amptime, cleanup, render as plt_render

        response.content_type = 'image/png'
        c.channel_num = int(channel_num)
        qlwell = self.__qlwell_from_threshold_form(id)

        self.__set_threshold_context(qlwell)
        peaks = qlwell.peaks

        title = 'Intensity/Time - %s - %s, %s' % (c.well.plate.plate.name, c.well.well_name, 'VIC' if c.channel_num == 1 else 'FAM')
        fig = amptime(title, peaks, c.vic_threshold if c.channel_num == 1 else c.fam_threshold, c.channel_num)
        response.content_type = 'image/png'
        imgdata = plt_render(fig, dpi=72)
        cleanup(fig)
        return imgdata
   
    # calculates droplet width plot 
    @validate(schema=ThresholdForm(), post_only=False, on_get=True)
    @block_contractor_internal_wells
    def width(self, id=None, *args, **kwargs):
        from qtools.lib.mplot import plot_widths, cleanup, render as plt_render

        response.content_type = 'image/png'
        qlwell = self.__qlwell_from_threshold_form(id)
        
        # assume widths are same on channel 0 as on 1
        fig = plot_widths(qlwell.peaks,
                          min_width_gate=qlwell.channels[0].statistics.min_width_gate,
                          max_width_gate=qlwell.channels[0].statistics.max_width_gate,
                          max_width=20,
                          background_rgbs=self.__get_1d_background_rgbs(qlwell))
        imgdata = plt_render(fig, dpi=72)
        cleanup(fig)
        return imgdata
    
    @validate(schema=ThresholdForm(), post_only=False, on_get=True)
    @block_contractor_internal_wells
    def nds(self, id=None, *args, **kwargs):
        from pyqlb.nstats.well import above_min_amplitude_peaks, NARROW_NORMALIZED_DROPLET_SPACING
        from qtools.lib.mplot import nds, cleanup, render as plt_render

        qlwell = self.__qlwell_from_threshold_form(id)

        title = 'NDS Histogram - %s - %s' % (c.well.plate.plate.name, c.well.well_name)

        ok_peaks = above_min_amplitude_peaks(qlwell)
        fig = nds(title, ok_peaks, NARROW_NORMALIZED_DROPLET_SPACING)
        response.content_type = 'image/png'
        imgdata = plt_render(fig, dpi=72)
        cleanup(fig)
        return imgdata
    
    @validate(schema=ThresholdForm(), post_only=False, on_get=True)
    @block_contractor_internal_wells
    def cluster(self, id=None, *args, **kwargs):
        from qtools.lib.mplot import plot_threshold_2d, cleanup, render as plt_render
        from qtools.lib.nstats.peaks import accepted_peaks
        
        response.content_type = 'image/png'
        qlwell = self.__qlwell_from_threshold_form(id)
        self.__set_threshold_context(qlwell)
        max_amplitudes = [self.form_result['max_fam_amplitude'], self.form_result['max_vic_amplitude']]
        boundaries = (-2000,-2000,max_amplitudes[1],max_amplitudes[0])

        # to emulate current behavior -- include gated events
        peaks = accepted_peaks(qlwell)
        fig = plot_threshold_2d(peaks,
                                thresholds=(c.fam_threshold, c.vic_threshold),
                                boundaries=boundaries)
        response.content_type = 'image/png'
        imgdata = plt_render(fig, dpi=72)
        cleanup(fig)
        return imgdata

    @validate(schema=ThresholdForm(), post_only=False, on_get=True)
    @block_contractor_internal_wells
    def cluster2d(self, id=None, *args, **kwargs):
        from qtools.lib.mplot import plot_cluster_2d, cleanup, render as plt_render
        from qtools.lib.nstats.peaks import accepted_peaks
        
        response.content_type = 'image/png'
        qlwell = self.__qlwell_from_threshold_form(id)
        self.__set_threshold_context(qlwell)
        max_amplitudes = [self.form_result['max_fam_amplitude'], self.form_result['max_vic_amplitude']]
        boundaries = (-2000,-2000,max_amplitudes[1],max_amplitudes[0])

        # to emulate current behavior -- include gated events
        peaks = accepted_peaks(qlwell)
        threshold_fallback = qlwell.clustering_method == QLWell.CLUSTERING_TYPE_THRESHOLD
        fig = plot_cluster_2d(peaks,
                              thresholds=(c.fam_threshold, c.vic_threshold),
                              boundaries=boundaries,
                              use_manual_clusters=not well_channel_automatic_classification(qlwell),
                              highlight_thresholds=threshold_fallback)
        response.content_type = 'image/png'
        imgdata = plt_render(fig, dpi=72)
        cleanup(fig)
        return imgdata
    
    @validate(schema=ThresholdForm(), post_only=False, on_get=True)
    @block_contractor_internal_wells
    def conc_trend(self, id=None, channel_num=0, *args, **kwargs):
        from qtools.lib.mplot import plot_conc_rolling_window, cleanup, render as plt_render
        
        response.content_type = 'image/png'
        c.channel_num = int(channel_num)
        qlwell = self.__qlwell_from_threshold_form(id)
        
        chan = 'FAM' if c.channel_num == 0 else 'VIC'
        fig = plot_conc_rolling_window(qlwell, c.channel_num, title="%s - %s (%s)" % (c.well.plate.plate.name, c.well.well_name, chan))
        imgdata = plt_render(fig, dpi=72)
        cleanup(fig)
        return imgdata
    
    @validate(schema=ThresholdForm(), post_only=False, on_get=True)
    @block_contractor_internal_wells
    def bscore_trend(self, id=None, *args, **kwargs):
        from qtools.lib.mplot import plot_bscore_rolling_window, cleanup, render as plt_render

        response.content_type = 'image/png'
        qlwell = self.__qlwell_from_threshold_form(id)

        fig = plot_bscore_rolling_window(qlwell, title="%s - %s" % (c.well.plate.plate.name, c.well.well_name))
        imgdata = plt_render(fig, dpi=72)
        cleanup(fig)
        return imgdata
    
    @validate(schema=ThresholdForm(), post_only=False, on_get=True)
    @block_contractor_internal_wells
    def temporal(self, id=None, channel_num=0, *args, **kwargs):
        from qtools.lib.mplot import temporal, cleanup, render as plt_render
        
        response.content_type = 'image/png'
        qlwell = self.__qlwell_from_threshold_form(id)
        self.__set_threshold_context(qlwell)
        channel = int(request.params.get("channel", 0))
        
        if not request.params.get('threshold', None):
            threshold = c.vic_threshold if channel == 1 else c.fam_threshold
        else:
            threshold = float(request.params.get('threshold'))

        title = 'Temporal Width Lite - %s - %s' % (c.well.plate.plate.name, c.well.well_name)
        fig = temporal(title, qlwell.peaks, threshold, qlwell.channels[channel].statistics.min_width_gate,
                       qlwell.channels[channel].statistics.max_width_gate, channel)
        imgdata = plt_render(fig, dpi=72)
        cleanup(fig)
        return imgdata
    
    @validate(schema=ThresholdForm(), post_only=False, on_get=True)
    @block_contractor_internal_wells
    def temporal2d(self, id=None, *args, **kwargs):
        from qtools.lib.nstats.peaks import accepted_peaks
        from pyqlb.nstats.peaks import peak_times, fam_amplitudes, vic_amplitudes
        qlwell = self.__qlwell_from_threshold_form(id)
        
        self.__set_threshold_context(qlwell)

        ok_peaks = accepted_peaks(qlwell)
        c.tvf = zip(peak_times(ok_peaks), vic_amplitudes(ok_peaks), fam_amplitudes(ok_peaks))

        return render('/well/temporal2d.html')
    
    @validate(schema=ThresholdForm(), post_only=False, on_get=True)
    @block_contractor_internal_wells
    def galaxy(self, id=None, channel_num=0, *args, **kwargs):
        from qtools.lib.nstats.peaks import above_min_amplitude_peaks
        from pyqlb.nstats.well import well_static_width_gates

        qlwell = self.__qlwell_from_threshold_form(id)
        self.__set_threshold_context(qlwell)
        channel_idx = int(request.params.get("channel", 0))

        from qtools.lib.mplot import galaxy, cleanup, render as plt_render

        peaks = above_min_amplitude_peaks(qlwell)
        title = 'Galaxy Lite - %s - %s, %s' % (c.well.plate.plate.name, c.well.well_name, 'VIC' if channel_idx == 1 else 'FAM')
        threshold = c.vic_threshold if channel_idx == 1 else c.fam_threshold
        min_width_gate, max_width_gate = well_static_width_gates(qlwell)
        fig = galaxy(title, peaks, threshold, min_width_gate, max_width_gate, channel_idx)
        response.content_type = 'image/png'
        imgdata = plt_render(fig, dpi=72)
        cleanup(fig)
        return imgdata
    
    @validate(schema=ThresholdForm(), post_only=False, on_get=True)
    @block_contractor_internal_wells
    def galaxy_disperse(self, id=None, *args, **kwargs):
        from pyqlb.nstats.well import above_min_amplitude_peaks
        from qtools.lib.mplot import galaxy_polydisperse, cleanup, render as plt_render
        from qtools.lib.nstats.peaks import polydisperse_peaks

        qlwell = self.__qlwell_from_threshold_form(id)
        self.__set_threshold_context(qlwell)
        channel_idx = int(request.params.get("channel", 0))

        peaks = above_min_amplitude_peaks(qlwell)
        threshold = c.vic_threshold if channel_idx == 1 else c.fam_threshold

        polydisperse_data = polydisperse_peaks(qlwell, channel_idx, threshold=threshold)
        poly_peaks, rain_boundaries, width_gates = polydisperse_data
        pos_peaks, midhigh_peaks, midlow_peaks, neg_peaks = poly_peaks
        pos, midhigh, midlow, neg = rain_boundaries
        min_gate, max_gate = width_gates
        title = 'GalaxyPD - %s, %s, %s' % (c.well.plate.plate.name, c.well.well_name, 'VIC' if channel_idx == 1 else 'FAM')
        fig = galaxy_polydisperse(title, peaks, channel_idx, threshold, min_gate, max_gate,
                                  pos, midhigh, midlow, neg,
                                  pos_peaks, midhigh_peaks, midlow_peaks, neg_peaks,
                                  min_amplitude_excluded=True)
        response.content_type = 'image/png'
        imgdata = plt_render(fig, dpi=72)
        cleanup(fig)
        return imgdata
    
    @validate(schema=ThresholdForm(), post_only=False, on_get=True)
    @block_contractor_internal_wells
    def galaxy_disperse_revb(self, id=None, *args, **kwargs):
        from pyqlb.nstats.well import above_min_amplitude_peaks
        from qtools.lib.mplot import galaxy_polydisperse_revb, cleanup, render as plt_render, empty_fig
        from qtools.lib.nstats.peaks import revb_polydisperse_peaks

        response.content_type = 'image/png'

        qlwell = self.__qlwell_from_threshold_form(id)
        self.__set_threshold_context(qlwell)
        channel_idx = int(request.params.get("channel", 0))

        peaks = above_min_amplitude_peaks(qlwell)
        threshold = c.vic_threshold if channel_idx == 1 else c.fam_threshold

        title = 'GalaxyPDB - %s, %s, %s' % (c.well.plate.plate.name, c.well.well_name, 'VIC' if channel_idx == 1 else 'FAM')
        if hasattr(qlwell, 'sum_amplitude_bins') and len(qlwell.sum_amplitude_bins) > 0:
            polydisperse_data = revb_polydisperse_peaks(qlwell, channel_idx, threshold=threshold)
            poly_peaks, rain_boundaries, mean_amplitudes = polydisperse_data
            pos_peaks, midhigh_peaks, midlow_peaks, neg_peaks = poly_peaks
            pos, midhigh, midlow, neg = rain_boundaries
            fam_mean, vic_mean = mean_amplitudes
            
            fig = galaxy_polydisperse_revb(title, peaks, channel_idx, threshold,
                                           pos, midhigh, midlow, neg,
                                           pos_peaks, midhigh_peaks, midlow_peaks, neg_peaks,
                                           min_amplitude_excluded=True,
                                           sum_amplitude_bins=qlwell.sum_amplitude_bins, other_channel_mean=fam_mean if channel_idx == 1 else vic_mean)
            
        else:
            fig = empty_fig()
            ax = fig.add_subplot(111, title=title)
            ax.text(0.33,0.5, "No amplitude bins for this well.")
        imgdata = plt_render(fig, dpi=72)
        cleanup(fig)
        return imgdata

    @validate(schema=ThresholdForm(), post_only=False, on_get=True)
    @block_contractor_internal_wells
    def galaxy_extra(self, id=None, *args, **kwargs):
        from pyqlb.nstats.well import above_min_amplitude_peaks
        from qtools.lib.mplot import galaxy_extracluster, cleanup, render as plt_render
        from qtools.lib.nstats.peaks import extracluster_peaks

        response.content_type = 'image/png'

        qlwell = self.__qlwell_from_threshold_form(id)
        self.__set_threshold_context(qlwell)
        channel_idx = int(request.params.get("channel", 0))

        peaks = above_min_amplitude_peaks(qlwell)
        threshold = c.vic_threshold if channel_idx == 1 else c.fam_threshold
        extra_data = extracluster_peaks(qlwell, channel_idx, threshold=threshold)
        extra_peaks, rain_boundaries, width_gates = extra_data
        pos, midhigh, midlow, neg = rain_boundaries
        min_gate, max_gate = width_gates
        title = 'GalaxyEX - %s, %s, %s' % (c.well.plate.plate.name, c.well.well_name, 'VIC' if channel_idx == 1 else 'FAM')
        fig = galaxy_extracluster(title, peaks, channel_idx, threshold, min_gate, max_gate,
                                  pos, midhigh, midlow, neg,
                                  extra_peaks,
                                  min_amplitude_excluded=True)
        imgdata = plt_render(fig, dpi=72)
        cleanup(fig)
        return imgdata

    @validate(schema=ThresholdForm(), post_only=False, on_get=True)
    @block_contractor_internal_wells
    def galaxy_extra_region(self, id=None, *args, **kwargs):
        from pyqlb.nstats.well import above_min_amplitude_peaks
        from qtools.lib.mplot import graph_extracluster_by_region, cleanup, render as plt_render
        from qtools.lib.nstats.peaks import revb_extracluster_peaks_by_region

        response.content_type = 'image/png'

        qlwell = self.__qlwell_from_threshold_form(id)
        self.__set_threshold_context(qlwell)
        channel_idx = int(request.params.get("channel", 0))
        peaks = above_min_amplitude_peaks(qlwell)
        threshold = c.vic_threshold if channel_idx == 1 else c.fam_threshold
        extra_data = revb_extracluster_peaks_by_region(qlwell, channel_idx, threshold=threshold)
        peaks_by_region, rain_gates, means = extra_data
        title = "GalaxyEXR - %s, %s, %s" % (c.well.plate.plate.name, c.well.well_name, 'VIC' if channel_idx == 1 else 'FAM')
        fig = graph_extracluster_by_region(title, peaks, channel_idx, threshold,
                                           peaks_by_region, rain_gates,
                                           sum_amplitude_bins=qlwell.sum_amplitude_bins,
                                           other_channel_mean=means[channel_idx])
        imgdata = plt_render(fig, dpi=72)
        cleanup(fig)
        return imgdata
    
    @validate(schema=ThresholdForm(), post_only=False, on_get=True)
    @block_contractor_internal_wells
    def galaxy_sum_bins(self, id=None, *args, **kwargs):
        from qtools.lib.mplot import galaxy_sum_width_bins, cleanup, render as plt_render
        response.content_type = 'image/png'

        qlwell = self.__qlwell_from_threshold_form(id)
        self.__set_threshold_context(qlwell)

        title = 'Sum Amps/Width Bins - %s, %s' % (c.well.plate.plate.name, c.well.well_name)
        fig = galaxy_sum_width_bins(title, qlwell)
        imgdata = plt_render(fig, dpi=72)
        cleanup(fig)
        return imgdata

    
    @validate(schema=ThresholdForm(), post_only=False, on_get=True)
    @block_contractor_internal_wells
    def temporal_galaxy(self, id=None, channel_num=0, *args, **kwargs):
        from qtools.lib.nstats.peaks import above_min_amplitude_peaks
        from pyqlb.nstats.peaks import peak_times, channel_amplitudes, channel_widths
        
        qlwell = self.__qlwell_from_threshold_form(id)
        self.__set_threshold_context(qlwell)
        c.channel_num = int(channel_num)

        ok_peaks = above_min_amplitude_peaks(qlwell)
        c.taw = zip(peak_times(ok_peaks), channel_amplitudes(ok_peaks, c.channel_num), channel_widths(ok_peaks, c.channel_num))
        if c.channel_num == 0:
            c.channel_name = 'FAM'
        else:
            c.channel_name = 'VIC'

        return render('/well/temporal_galaxy.html')
    
    @validate(schema=ThresholdForm(), post_only=False, on_get=True)
    @block_contractor_internal_wells
    def outliers(self, id=None, *args, **kwargs):
        from qtools.lib.nstats.peaks import total_events_amplitude_vals
        from qtools.lib.mplot import plot_cluster_outliers, cleanup, render as plt_render

        qlwell = self.__qlwell_from_threshold_form(id)
        means0,stds0 = total_events_amplitude_vals(qlwell,0) 
        means1,stds1 = total_events_amplitude_vals(qlwell,1) 
        title = 'Outliers - Well:%s FAM:(Mean: %.0f, Stdev:%.0f) \n                   VIC/HEX:(Mean: %.0f, Stdev: %.0f)' % (c.well.well_name,means0,stds0,means1,stds1)

	peaks = qlwell.peaks
        fig = plot_cluster_outliers(title, peaks)
        response.content_type = 'image/png'
        imgdata = plt_render(fig, dpi=72)
        cleanup(fig)
        return imgdata
    
    @validate(schema=ThresholdForm(), post_only=False, on_get=True)
    @block_contractor_internal_wells
    def widthbin(self, id=None, *args, **kwargs):
        from qtools.lib.nstats.peaks import above_min_amplitude_peaks
        from qtools.lib.mplot import plot_cluster_widthbins, cleanup, render as plt_render

        qlwell = self.__qlwell_from_threshold_form(id)
        title = 'Width Bins - %s, %s' % (c.well.plate.plate.name, c.well.well_name)

        min_gate = qlwell.channels[0].statistics.min_width_gate
        max_gate = qlwell.channels[0].statistics.max_width_gate

        peaks = above_min_amplitude_peaks(qlwell)
        fam_threshold = qlwell.channels[0].statistics.threshold
        vic_threshold = qlwell.channels[1].statistics.threshold
        fig = plot_cluster_widthbins(title, peaks, qlwell.sum_amplitude_bins, min_gate, max_gate,
                                     fam_threshold=fam_threshold, vic_threshold=vic_threshold)
        response.content_type = 'image/png'
        imgdata = plt_render(fig, dpi=72)
        cleanup(fig)
        return imgdata
    
    @validate(schema=ThresholdForm(), post_only=False, on_get=True)
    def air_plot(self, id=None, channel_num=0, *args, **kwargs):
        from qtools.lib.nstats.peaks import gap_air
        from qtools.lib.mplot import airtime, cleanup, render as plt_render

        qlwell = self.__qlwell_from_threshold_form(id)
        self.__set_threshold_context(qlwell)
        c.channel_num = int(channel_num)
        threshold = c.vic_threshold if c.channel_num == 1 else c.fam_threshold
        #cutoff = request.params.get('cutoff', 500)

        air_drops = gap_air(qlwell, c.channel_num, threshold=threshold)
        title = 'Air - %s - %s, %s' % (c.well.plate.plate.name, c.well.well_name, 'VIC' if c.channel_num == 1 else 'FAM')
        fig = airtime(title, qlwell.peaks, air_drops, c.vic_threshold if c.channel_num == 1 else c.fam_threshold, c.channel_num)
        response.content_type = 'image/png'
        imgdata = plt_render(fig, dpi=72)
        cleanup(fig)
        return imgdata

    
    @validate(schema=ThresholdForm(), post_only=False, on_get=True)
    @block_contractor_internal_wells
    def air_hist(self, id=None, channel_num=0, *args, **kwargs):
        from qtools.lib.nstats.peaks import gap_air
        from pyqlb.nstats.well import accepted_peaks
        from pyqlb.nstats.peaks import color_uncorrected_peaks, channel_amplitudes, peak_times
        from qtools.lib.mplot import air_hist, cleanup, render as plt_render

        qlwell = self.__qlwell_from_threshold_form(id)
        self.__set_threshold_context(qlwell)
        c.channel_num = int(channel_num)
        threshold = c.vic_threshold if c.channel_num == 1 else c.fam_threshold
        cutoff = request.params.get('cutoff', 500)

        # can detect air on either channel (especially if VICs super low)
        # but always report VIC amplitude
        air_drops = gap_air(qlwell, c.channel_num, threshold=threshold)
        uncorrected_air = color_uncorrected_peaks(air_drops, qlwell.color_compensation_matrix)

        # count number of accepted peak times
        air_drop_times = peak_times(air_drops)
        accepted_times = peak_times(accepted_peaks(qlwell))
        num_air_accepted = len([t for t in air_drop_times if t in accepted_times])

        # always gate on VIC
        air_amps = channel_amplitudes(uncorrected_air, 1)

        title = 'Air Droplet Histogram - %s, %s (%s)' % (c.well.plate.plate.name, c.well.well_name, 'VIC' if c.channel_num == 1 else 'FAM')
        fig = air_hist(title, air_amps, cutoff=cutoff, num_accepted=num_air_accepted)
        response.content_type = 'image/png'
        imgdata = plt_render(fig, dpi=72)
        cleanup(fig)
        return imgdata
    
    @validate(schema=ThresholdForm(), post_only=False, on_get=True)
    @block_contractor_internal_wells
    def svilen(self, id=None, *args, **kwargs):
        from pyqlb.nstats.well import accepted_peaks
        from pyqlb.nstats.peaks import cluster_2d, peak_times, fam_widths
        from pyqlb.factory import QLNumpyObjectFactory
        from qtools.lib.mplot import svilen, cleanup, render as plt_render

        qlwell = self.__qlwell_from_threshold_form(id)
        self.__set_threshold_context(qlwell)
        well_path = self.__well_path()
        # oh shit
        factory = QLNumpyObjectFactory()
        raw_well = factory.parse_well(well_path)

        crap, crap, gold, crap = cluster_2d(accepted_peaks(qlwell), c.fam_threshold,
                                            c.vic_threshold)
        
        times = peak_times(gold)
        widths = fam_widths(gold)

        title = "VIC+/FAM- droplet traces (accepted events)"
        ranges = [(int(t-(w*2)), int(t+(w*2))) for t, w in zip(times, widths)]
        if c.fam_threshold == 0 or c.vic_threshold == 0:
            ranges = []
            title = "%s (no events in quadrant)" % title
        elif len(ranges) > 100:
            ranges = ranges[:100]
            title = "%s (truncated at first 100)" % title

        
        fig = svilen(title, raw_well.samples, ranges, widths)
        response.content_type = 'image/png'
        imgdata = plt_render(fig, dpi=72)
        cleanup(fig)
        return imgdata


    
    @block_contractor_internal_wells
    def download(self, id=None, *args, **kwargs):
        if id is None:
            abort(404)
        
        qlbwell = Session.query(QLBWell).get(id)
        if not qlbwell:
            abort(404)
        
        if not qlbwell.file:
            abort(404)
        
        storage = QLStorageSource(config)
        response.headers['Content-Type'] = 'application/quantalife-raw'
        h.set_download_response_header(request, response, qlbwell.file.basename)
        return forward(FileApp(storage.qlbwell_path(qlbwell), response.headerlist))
    
    @jsonify
    def tag_error(self):
        return {'error': 'form submission error'}
    
    @jsonify
    @restrict('POST')
    @validate(schema=WellTagForm(), view='tag_error')
    def tag(self):
        well = Session.query(QLBWell).get(self.form_result['well_id'])
        if not well:
            abort(500)
        
        tag_ids = [tag.id for tag in well.tags]
        new_id = self.form_result['tag_id']
        if new_id not in tag_ids:
            new_tag = Session.query(WellTag).get(new_id)
            if not new_tag:
                abort(500)
            tag = QLBWellTag(well=well, well_tag=new_tag, tagger_id=self.form_result['tagger_id'])
            Session.add(tag)
            Session.commit()
        
        if self.form_result['tagger_id']:
            session['person_id'] = self.form_result['tagger_id']
            session.save()
        return {'tag_id': new_id, 'tag_names': [tag.name for tag in well.tags]}
    
    @jsonify
    @restrict('POST')
    @validate(schema=WellTagForm(), view='tag_error')
    def untag(self):
        well = Session.query(QLBWell).get(self.form_result['well_id'])
        if not well:
            abort(500)
        
        tag_ids = [tag.id for tag in well.tags]
        new_id = self.form_result['tag_id']
        if new_id in tag_ids:
            well_tag = [tag for tag in well.well_tags if tag.well_tag_id == new_id][0]
            Session.delete(well_tag)
            Session.commit()
        
        if self.form_result['tagger_id']:
            session['person_id'] = self.form_result['tagger_id']
            session.save()
        return {'tag_id': new_id, 'tag_names': [tag.name for tag in well.tags]}
    
    @validate(schema=ThresholdForm(), post_only=False, on_get=True)
    @block_contractor_internal_wells
    def peak_csv(self, id=None, show_only_gated=True, *args, **kwargs):
        from qtools.lib.nstats.peaks import accepted_peaks
        qlwell = self.__qlwell_from_threshold_form(id)

        if show_only_gated != 'False':
            peaks = accepted_peaks(qlwell)
        else:
            peaks = qlwell.peaks

        from pyqlb.nstats.peaks import fam_amplitudes, fam_widths, fam_quality, vic_amplitudes, vic_widths, vic_quality, peak_times

        response.headers['Content-Type'] = 'text/csv'
        h.set_download_response_header(request, response, "%s_%s%s.csv" % \
            (str(c.well.plate.plate.name), str(c.well.well_name), '' if show_only_gated != 'False' else '_all'))
        out = StringIO.StringIO()
        csvwriter = csv_pkg.writer(out)
        csvwriter.writerow(['Plate',c.well.plate.plate.name])
        csvwriter.writerow(['Well',c.well.well_name])
        csvwriter.writerow([])
        csvwriter.writerow(['FAMThreshold',qlwell.channels[0].statistics.threshold])
        csvwriter.writerow(['VICThreshold',qlwell.channels[1].statistics.threshold])
        csvwriter.writerow(['WidthGate',qlwell.channels[0].statistics.min_width_gate,qlwell.channels[0].statistics.max_width_gate])
        csvwriter.writerow(['MinQualityGate',qlwell.channels[0].statistics.min_quality_gate])
        csvwriter.writerow([])
        csvwriter.writerow(['Time','FAMAmplitude','FAMWidth','FAMQuality','VICAmplitude','VICWidth','VICQuality'])
        csvwriter.writerow([])

        pts = peak_times(peaks)
        fas = fam_amplitudes(peaks)
        fws = fam_widths(peaks)
        fqs = fam_quality(peaks)
        vas = vic_amplitudes(peaks)
        vws = vic_widths(peaks)
        vqs = vic_quality(peaks)

        for row in zip(pts, fas, fws, fqs, vas, vws, vqs):
            csvwriter.writerow(row)
        csv = out.getvalue()
        out.close()
        return csv

    @validate(schema=ThresholdForm(), post_only=False, on_get=True)
    @block_contractor_internal_wells
    def cluster_csv(self, id=None, show_only_gated=True, *args, **kwargs):
        from pyqlb.nstats.well import accepted_peaks
        qlwell = self.__qlwell_from_threshold_form(id)

        if show_only_gated != 'False':
            peaks = accepted_peaks(qlwell)
        else:
            peaks = qlwell.peaks

        from pyqlb.nstats.peaks import fam_amplitudes, fam_widths, vic_amplitudes, vic_widths, peak_times
        from pyqlb.nstats.well import well_observed_cluster_assignments

        response.headers['Content-Type'] = 'text/csv'
        h.set_download_response_header(request, response, "%s_%s%s.csv" % \
            (str(c.well.plate.plate.name), str(c.well.well_name), '' if show_only_gated != 'False' else '_all'))
        out = StringIO.StringIO()
        csvwriter = csv_pkg.writer(out)
        csvwriter.writerow(['Plate',c.well.plate.plate.name])
        csvwriter.writerow(['Well',c.well.well_name])
        csvwriter.writerow([])
        csvwriter.writerow(['Time','FAMAmplitude','FAMWidth','VICAmplitude','VICWidth','Cluster'])
        csvwriter.writerow([])

        pts = peak_times(peaks)
        fas = fam_amplitudes(peaks)
        fws = fam_widths(peaks)
        vas = vic_amplitudes(peaks)
        vws = vic_widths(peaks)
        cls = well_observed_cluster_assignments(qlwell, peaks)

        for row in zip(pts, fas, fws, vas, vws, cls):
            csvwriter.writerow(row)
        csv = out.getvalue()
        out.close()
        return csv


    
    def __image_path(self, id=None):
        if id is None:
            return None
        qlbwell = Session.query(QLBWell).get(id)
        if not qlbwell:
            return None
        
        storage = QLStorageSource(config)
        return storage.qlbwell_path(qlbwell)
    
    def __csv_path(self, algwell):
        """
        @deprecated, may not work
        """
        storage = QLStorageSource(config)
        file_source = storage.file_source(algwell.well.plate.plate.box2.fileroot)
        return file_source.real_path(algwell.csv_file_path)
    
    def __txt_path(self, algwell):
        """
        @deprecated, may not work
        """
        storage = QLStorageSource(config)
        file_source = storage.file_source(algwell.well.plate.plate.box2.fileroot)
        return file_source.real_path(algwell.txt_file_path)
