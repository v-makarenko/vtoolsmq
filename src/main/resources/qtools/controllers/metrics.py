import logging, StringIO, operator

from pylons import request, response, session, tmpl_context as c, url
from pylons.controllers.util import abort, redirect
from pylons.decorators import validate, jsonify
from pylons.decorators.rest import restrict

from qtools.lib.base import BaseController, render
import qtools.lib.cookie as cookie
from qtools.lib.decorators import help_at
from qtools.lib.fields import beta_type_field, box2_field, checkbox_field, person_field
from qtools.lib import helpers as h
from qtools.lib.compare import *
from qtools.lib.metrics.spec import AnalysisGroupMetrics, DRCertificationMetrics, PlateDRCertificationMetrics, SinglePlateMetrics
from qtools.lib.validators import MetricPattern, IntKeyValidator
from qtools.model import Session, AnalysisGroup, Plate, PlateMetric, WellMetric, WellChannelMetric, ReprocessConfig
from qtools.model import Box2, DropletGenerator, PlateType, Person
from qtools.model.batchplate import ManufacturingPlate # such that backref will work (unforeseen consequence of breaking up qtools.model)
from sqlalchemy.orm import joinedload_all
from sqlalchemy import and_, or_, not_

# move into lib.qlb?
from pyqlb.objects import QLWellChannel
from collections import defaultdict

import formencode
import numpy as np

log = logging.getLogger(__name__)

class MetricFilterForm(formencode.Schema):
    allow_extra_fields = True
    filter_extra_fields = True

    dr_id = IntKeyValidator(Box2, 'id', not_empty=False, if_missing=None)
    dg_id = IntKeyValidator(DropletGenerator, 'id', not_empty=False, if_missing=None)
    pt_id = IntKeyValidator(PlateType, 'id', not_empty=False, if_missing=None)
    operator_id = IntKeyValidator(Person, 'id', not_empty=False, if_missing=None)
    gated_filter = formencode.validators.String(not_empty=False, if_missing=None)
    channel = formencode.validators.Int(not_empty=False, if_missing=None)
    pattern = formencode.validators.String(not_empty=False, if_missing=None)

COMPARE_PCT_DELTA = 'compare_pct'
COMPARE_ABS_DELTA = 'compare_abs'
COMPARE_ZERO_NONZERO = 'compare_zero_nonzero'
COMPARE_CLOSER_TO_ZERO = 'compare_closer_to_zero'
COMPARE_CLOSER_TO_ONE = 'compare_closer_to_one'
COMPARE_ANYDIFF = 'compare_anydiff'

COMPARE_FUNC_MAP = {COMPARE_PCT_DELTA: pct_diff,
                    COMPARE_ABS_DELTA: abs_diff,
                    COMPARE_ZERO_NONZERO: compare_zero_nonzero,
                    COMPARE_CLOSER_TO_ZERO: compare_closer_to_zero,
                    COMPARE_CLOSER_TO_ONE: compare_closer_to_one,
                    COMPARE_ANYDIFF: compare_anydiff}

COMPARE_FUNC_DISPLAY_MAP = {COMPARE_ABS_DELTA: lambda d: d,
                            COMPARE_PCT_DELTA: lambda p: "%.01f%%" % (100*p),
                            COMPARE_ZERO_NONZERO: lambda d: d,
                            COMPARE_CLOSER_TO_ZERO: lambda d: d,
                            COMPARE_CLOSER_TO_ONE: lambda d: d,
                            COMPARE_ANYDIFF: lambda d: d} # TODO: change to 'diff'?

class CompareMetricFilterForm(MetricFilterForm):
    metric = MetricPattern(not_empty=True)
    left_config_id = IntKeyValidator(ReprocessConfig, 'id', not_empty=False, if_missing=None)
    right_config_id = IntKeyValidator(ReprocessConfig, 'id', not_empty=False, if_missing=None)
    cmp_method = formencode.validators.OneOf(COMPARE_FUNC_MAP.keys(), not_empty=False, if_missing=COMPARE_ABS_DELTA)
    minmax_number = formencode.validators.Int(not_empty=False, if_missing=30)
    channel_num = formencode.validators.Int(not_empty=False, if_missing=0)
    exclude_nodiff = formencode.validators.Bool(not_empty=False, if_missing=False)
    min_range = formencode.validators.Number(not_empty=False, if_missing=None)
    max_range = formencode.validators.Number(not_empty=False, if_missing=None)

class AnalysisGroupForm(formencode.Schema):
    allow_extra_fields = True
    filter_extra_fields = True

    name = formencode.validators.MaxLength(50, not_empty=True)


PATTERN_FILTERS = defaultdict(lambda: lambda w: True, {
    'odd': lambda name: int(name[1:]) % 2 == 1,
    'even': lambda name: int(name[1:]) % 2 == 0,
    'tlq': lambda name: name[0] in ('A','B','C','D') and int(name[1:]) < 7,
    'trq': lambda name: name[0] in ('A','B','C','D') and int(name[1:]) >= 7,
    'blq': lambda name: name[0] in ('E','F','G','H') and int(name[1:]) < 7,
    'brq': lambda name: name[0] in ('E','F','G','H') and int(name[1:]) >= 7,
    'lh': lambda name: int(name[1:]) < 7,
    'rh': lambda name: int(name[1:]) >= 7,
    'oler': lambda name: (int(name[1:]) < 7 and int(name[1:]) % 2 == 1) or \
                         (int(name[1:]) >= 7 and int(name[1:]) % 2 == 0),
    'elor': lambda name: (int(name[1:]) < 7 and int(name[1:]) % 2 == 0) or \
                         (int(name[1:]) >= 7 and int(name[1:]) % 2 == 1)
})

class MetricsController(BaseController):

    def _index_base(self):
        c.analysis_groups = Session.query(AnalysisGroup).filter_by(active=True).order_by(AnalysisGroup.id).all()
        c.active_analysis_group_id = cookie.get(cookie.ACTIVE_ANALYSIS_GROUP_ID, as_type=int)
        return render('/metrics/index.html')

    @help_at('datasets/analysisgroups.html')
    def index(self, *args, **kwargs):
        return h.render_bootstrap_form(self._index_base())

    def agactivate(self, id=None):
        ag = Session.query(AnalysisGroup).get(id)
        if not ag:
            session['flash'] = 'Invalid analysis group.'
            session['flash_class'] = 'error'
        else:
            cookie.set_session(cookie.ACTIVE_ANALYSIS_GROUP_ID, ag.id)
            session['flash'] = '%s is now the active analysis group.' % ag.name
        session.save()
        return redirect(url(controller='metrics', action='index'))

    def agdeactivate(self):
        cookie.clear(cookie.ACTIVE_ANALYSIS_GROUP_ID)
        session['flash'] = 'Analysis group deactivated.'
        session.save()
        return redirect(url(controller='metrics', action='index'))

    @jsonify
    @restrict('POST')
    def agadd(self, id=None):
        plate_id = request.params.get('plate_id')
        ag = Session.query(AnalysisGroup).get(id)
        plate = Session.query(Plate).get(plate_id)
        if not ag:
            return {'code': 404, 'message': 'Invalid analysis group.'}
        if not plate:
            return {'code': 404, 'message': 'Invalid plate.'}

        if plate.id not in [p.id for p in ag.plates]:
            ag.plates.append(plate)
            Session.commit()
            return {'code': 200, 'message': 'Plate added.'}
        else:
            return {'code': 412, 'message': 'Plate already part of this analysis group.'}

    @jsonify
    @restrict('POST')
    def agremove(self, id=None):
        plate_id = request.params.get('plate_id')
        ag = Session.query(AnalysisGroup).get(id)
        plate = Session.query(Plate).get(plate_id)
        if not ag:
            return {'code': 404, 'message': 'Invalid analysis group.'}
        if not plate:
            return {'code': 404, 'message': 'Invalid plate.'}

        if plate.id in [p.id for p in ag.plates]:
            ag.plates.remove(plate)
            Session.commit()
            return {'code': 200, 'message': 'Plate removed.'}
        else:
            return {'code': 412, 'message': 'Plate not part of this analysis group.'}

    # TODO this should be a POST but I'm lazy (more complicated UI)
    def agdisable(self, id=None):
        ag = Session.query(AnalysisGroup).get(id)
        if not ag:
            session['flash'] = 'Invalid analysis group.'
            session['flash_class'] = 'error'
        else:
            ag.active = False
            Session.commit()
            session['flash'] = 'Analysis group retired.'

        session.save()
        return redirect(url(controller='metrics', action='index'))

    @restrict('POST')
    @validate(AnalysisGroupForm, form='_index_base', error_formatters=h.tw_bootstrap_error_formatters)
    def agcreate(self):
        ag = AnalysisGroup(name=self.form_result['name'],
                           active=True)
        Session.add(ag)
        Session.commit()
        session['flash'] = 'Analysis group created.'
        session.save()
        return redirect(url(controller='metrics', action='index'))



    def __get_analysis_group_form_kwargs(self):
        kwargs = dict()
        if self.form_result['dr_id']:
            kwargs['plate_filter'] = lambda p: p.box2_id == self.form_result['dr_id']
        if self.form_result['dg_id']:
            kwargs['well_filter'] = lambda w: w.droplet_generator_id == self.form_result['dg_id']
        if self.form_result['channel']:
            func = kwargs.get('well_filter', lambda w: True)
            kwargs['well_filter'] = lambda w: func(w) and w.consumable_channel_num == self.form_result['channel']
        if self.form_result['pt_id']:
            kwargs['plate_type_filter'] = lambda pt: pt and pt.id == self.form_result['pt_id']
        if self.form_result['operator_id']:
            func = kwargs.get('plate_filter', lambda p: True)
            kwargs['plate_filter'] = lambda p: func(p) and p.operator_id == self.form_result['operator_id']
        if self.form_result['pattern']:
            func = kwargs.get('well_filter', lambda w: True)
            kwargs['well_filter'] = lambda w: func(w) and PATTERN_FILTERS[self.form_result['pattern']](w.well_name)
         
        if self.form_result['gated_filter']:
            gated_filter = self.form_result['gated_filter']
            if gated_filter == 'gated_only':
                kwargs['well_metric_filter'] = lambda wm: any([cl.auto_threshold_expected and (cl.decision_tree_flags & 4096 == 4096) for cl in wm.well_channel_metrics])
            elif gated_filter == 'not_gated':
                kwargs['well_metric_filter'] = lambda wm: all([((cl.decision_tree_flags & 4096 != 4096) or not cl.auto_threshold_expected) for cl in wm.well_channel_metrics])
            else:
                kwargs['well_metric_filter'] = lambda wm: True
        return kwargs
    
    def __setup_metric_form_context(self):
        dg_q = Session.query(DropletGenerator).order_by(DropletGenerator.name)
        dgs = dg_q.all()

        plate_types = beta_type_field(selected=str(self.form_result['pt_id']) or '', empty='All')
        operators = person_field(selected=str(self.form_result['operator_id']) or '')

        box_field = box2_field(selected=str(self.form_result['dr_id']) or '', empty='All')
        c.form = h.LiteralFormSelectPatch(
            value = {'dr_id': box_field['value'],
                     'dg_id': str(self.form_result['dg_id']) or '',
                     'pt_id': plate_types['value'],
                     'operator_id': operators['value'],
                     'gated_filter': self.form_result['gated_filter'] or '',
                     'channel': str(self.form_result['channel']) or '',
                     'pattern': str(self.form_result['pattern']) or ''},
            option = {'dr_id': box_field['options'],
                      'dg_id': [('','All')]+
                               [(dg.id, dg.name) for dg in dgs],
                      'pt_id': plate_types['options'],
                      'operator_id': operators['options'],
                      'gated_filter': [('','All'),
                                       ('gated_only', 'Gated Events > N'),
                                       ('not_gated', 'Gated Events <= N')],
                      'channel': [('','All'),
                                  ('1','1'),
                                  ('2','2'),
                                  ('3','3'),
                                  ('4','4'),
                                  ('5','5'),
                                  ('6','6'),
                                  ('7','7'),
                                  ('8','8')],
                      'pattern': [('', 'All'),
                                  ('odd', 'Odd Columns'),
                                  ('even', 'Even Columns'),
                                  ('tlq', 'Top Left Quadrant'),
                                  ('trq', 'Top Right Quadrant'),
                                  ('blq', 'Bottom Left Quadrant'),
                                  ('brq', 'Bottom Right Quadrant'),
                                  ('lh', 'Left Half'),
                                  ('rh', 'Right Half'),
                                  ('oler', 'Odd Left/Even Right'),
                                  ('elor', 'Even Left/Odd Right')]}
        )

        # TODO validate these to prevent passage if illegal
        c.dr_id = self.form_result['dr_id'] or ''
        c.dg_id = self.form_result['dg_id'] or ''
        c.pt_id = self.form_result['pt_id'] or ''
        c.gated_filter = self.form_result['gated_filter'] or ''
        c.pattern = self.form_result['pattern'] or ''
        c.operator_id = self.form_result['operator_id'] or ''


    def __setup_metrics_context(self, id, mode='group', reprocess_config_code=None):
        """
        TODO: OK, this code is now a little less spaghetti-like;
        we can break this up into group, dr and plate methods since the common filtering
        stuff is in separate methods.
        """
        c.mode = mode
        c.qc_metrics = None
        c.qc_plate = None
        if mode == 'group':
            analysis_group_id = int(id)
            box2_id = None
            c.id = analysis_group_id
        elif mode == 'dr':
            analysis_group_id = None
            box2_id = id
            c.id = box2_id
        elif mode in ('plate','plate_non_cert'):
            analysis_group_id = None
            box2_id = None
            plate_id = int(id)
            c.id = plate_id
        
        if analysis_group_id:
            c.group = Session.query(AnalysisGroup).get(int(analysis_group_id))
            c.name = c.group.name
        else:
            c.group = None
        
        c.analysis_group_id = analysis_group_id or ''
        
        if reprocess_config_code:
            rp = Session.query(ReprocessConfig).filter_by(code=reprocess_config_code).first()
            c.rp_id = rp.id
            c.rp_code = rp.code
        else:
            c.rp_id = '' # used in HTML -- reprocess_config_id to AnalysisGroupMetrics should be None
            c.rp_code = ''
        
        if hasattr(self, 'form_result'):
            kwargs = self.__get_analysis_group_form_kwargs()
            c.channel = self.form_result['channel'] or ''
        else:
            kwargs = dict()
            c.channel = request.params.get('channel', '')
        
        if analysis_group_id:
            c.metrics = AnalysisGroupMetrics(c.group.id, reprocess_config_id=c.rp_id, **kwargs)
            c.configs = [cf for cf in sorted(c.group.reprocesses, key=lambda r: r.name) if cf.active]
            c.box2 = None
        elif box2_id:
            c.box2 = Session.query(Box2).filter(Box2.code==id).first()
            if not c.box2:
                abort(404)
            c.name = c.box2.name
            c.metrics = DRCertificationMetrics(c.box2.id, **kwargs)
            c.configs = None
        elif plate_id:
            c.box2 = None
            c.plate = Session.query(Plate).get(plate_id)
            if not c.plate:
                abort(404)
            c.name = c.plate.name
            if c.mode == 'plate':
                c.metrics = PlateDRCertificationMetrics(c.plate.id, reprocess_config_id=c.rp_id or None, **kwargs)
            elif c.mode == 'plate_non_cert':
                c.metrics = SinglePlateMetrics(c.plate.id, reprocess_config_id=c.rp_id or None, **kwargs)
            if c.plate.mfg_record and c.plate.mfg_record.batch_qc_plate and c.plate.mfg_record.batch_qc_plate.id != c.plate.id:
                c.qc_plate = c.plate.mfg_record.batch_qc_plate
                qc_metrics = PlateDRCertificationMetrics(c.plate.mfg_record.batch_qc_plate.id, reprocess_config_id=c.rp_id or None, **kwargs)
                if qc_metrics.metric_plates:
                    c.qc_metrics = qc_metrics
            c.configs = None
            self.__setup_plate_warning_context(c.plate, c.metrics)
        else:
            abort(404)
        
        if c.mode != 'plate_non_cert':
            self.__setup_metric_form_context()
        
    def __plate_box_type_query(self, box_code, plate_type_code):
        # WHY WHY WHY DID I SPLIT mfgco/bcarry
        query = Session.query(Plate).join(Box2, PlateType)\
                                   .filter(and_(Box2.code == box_code,
                                                or_(Plate.onsite == None, not_(Plate.onsite)),
                                                or_(Plate.mfg_exclude == None, not_(Plate.mfg_exclude))))
        if plate_type_code in ('mfgcc', 'bcc', 'scc'):
            query = query.filter(PlateType.code.in_(('mfgcc', 'bcc', 'scc')))
        elif plate_type_code in ('mfgco', 'bcarry'):
            query = query.filter(PlateType.code.in_(('mfgco', 'bcarry')))
        else:
            query = query.filter(PlateType.code == plate_type_code)
        
        return query.order_by(Plate.run_time).all()
    
    def __setup_pagination_context(self, id, plates):
        index = None
        for i, p in enumerate(plates):
            if p.id == id:
                index = i
                # todo: put here?  diff pagination contexts?
                c.box_code = p.box2.code
                c.plate_type_code = p.plate_type.code
                c.plate_type_name = p.plate_type.name
                break
        if index is None:
            c.box_code = ''
            c.prev_index = None
            c.next_index = None
            return
        
        # prev
        if index > 0:
            c.prev_index = index # urls 1-based
        else:
            c.prev_index = None
        if index < len(plates)-1:
            c.next_index = index+2 # urls 1-based
        else:
            c.next_index = None
    

    def __setup_plate_warning_context(self, plate, metrics):
        if not plate.plate_type:
            return False
        
        warning = None
        error = None
        if plate.plate_type.code in ('bcarry', 'mfgco'):
            if len(plate.qlbplate.wells) < 96:
                warning = h.literal("This is not a full carryover plate&ndash;some wells were skipped.")
            elif len([w for w in metrics.carryover_eventful_wells if w.total_event_count > 0]) < 48:
                error = "This plate was interrupted."
        
        if plate.plate_type.code in ('bcc', 'mfgcc'):
            if len(plate.qlbplate.wells) < 4:
                warning = h.literal("This is not a full colorcomp plate&ndash;some wells were skipped.")
            elif len([w for w in metrics.event_count_wells if w.total_event_count > 0]) < 4:
                error = "This plate was interrupted."
        
        c.plate_warning = None
        c.plate_error = None
        if error:
            c.plate_error = error
        elif warning:
            c.plate_warning = warning

    
    @validate(schema=MetricFilterForm(), form='index', post_only=False, on_get=True)
    def overview(self, id=None, reprocess_config_id=None):
        self.__setup_metrics_context(id, 'group', reprocess_config_code=reprocess_config_id)
        if c.group and c.group.type_code:
            return render('/metrics/%s.html' % c.group.type_code)
        else:
            return render('/metrics/overview.html')
    
    @validate(schema=MetricFilterForm(), form='index', post_only=False, on_get=True)
    def certification(self, id=None, reprocess_config_id=None):
        self.__setup_metrics_context(id, 'dr')
        c.tab = request.params.get('tab', 'metrics')
        # this is a hack.  return the latest carryover and colorcomp plate
        plates = set([wm.plate_metric.plate for wm in c.metrics.all_well_metrics])
        c.carryover_plates = [p for p in plates if p.plate_type.code in ('bcarry','mfgco')]
        c.colorcomp_plates = [p for p in plates if p.plate_type.code in ('bcc','mfgcc')]
        c.singlewell_colorcomp_plate_metrics = [p for p in plates if p.plate_type.code == 'scc']
        c.singlewell_famvic_plate = c.metrics.singlewell_famvic_colorcomp_plate.plate if c.metrics.singlewell_famvic_colorcomp_plate else None
        c.singlewell_famhex_plate = c.metrics.singlewell_famhex_colorcomp_plate.plate if c.metrics.singlewell_famhex_colorcomp_plate else None
        c.events_plates = [p for p in plates if p.plate_type.code == 'betaec']
        c.probe_event_plates = [p for p in plates if p.plate_type.code == 'probeec']
        c.eva_event_plates = [p for p in plates if p.plate_type.code == 'evaec']

        c.plate_list = Session.query(Plate).filter_by(box2_id=c.box2.id).order_by('run_time desc').all()
        c.file_list = sorted(c.box2.files, key=operator.attrgetter('name'))

        return render('/metrics/box2.html')
    
    @validate(schema=MetricFilterForm(), form='index', post_only=False, on_get=True)
    def per_plate(self, id=None, reprocess_config_id=None):
        self.__setup_metrics_context(id, 'plate', reprocess_config_code=reprocess_config_id)
        plates = self.__plate_box_type_query(c.plate.box2.code, c.plate.plate_type.code)
        self.__setup_pagination_context(int(id), plates)
        return render('/metrics/per_plate.html')

    @validate(schema=MetricFilterForm(), form='')
    def stats(self, id=None, reprocess_config_id=None):
        c.plate = Session.query(Plate).get(int(id))
        c.mode = 'plate_non_cert'
        self.__setup_metrics_context(id, c.mode, reprocess_config_code=reprocess_config_id)
        return render('/metrics/stats/%s.html' % c.plate.plate_type.code)
    
    @validate(schema=MetricFilterForm(), form='index', post_only=False, on_get=True)
    def history(self, box_code=None, plate_type=None, plate_order=None, reprocess_config_id=None):
        # find the nth id
        plates = self.__plate_box_type_query(box_code, plate_type)
        plate_order = int(plate_order)
        if plate_order < 1 or plate_order > len(plates):
            abort(404)
        
        id = plates[plate_order-1].id
        self.__setup_metrics_context(id, 'plate')
        self.__setup_pagination_context(id, plates)
        return render('/metrics/per_plate.html')
    
    @validate(schema=MetricFilterForm(), form='index', post_only=False, on_get=True)
    def history_csv(self, box_code=None, plate_type=None, reprocess_config_id=None):
        # this is a hack, basically
        if plate_type not in ('bcarry', 'bcc', 'betaec', 'mfgco', 'mfgcc','scc','probeec','evaec'):
            abort(404)

        plates = self.__plate_box_type_query(box_code, plate_type)
        metrics = []
        for p in plates:
            # set up the context, get the metrics
            # might be a good idea to get the metric retrieval out of the __setup method
            self.__setup_metrics_context(p.id, 'plate')
            metrics.append(c.metrics) # relying on setup's side effect; not great
        
        response.content_type = 'text/csv'
        h.set_download_response_header(request, response,
                                       "%s-%s_r%s.csv" % (box_code, plate_type, len(plates)))
        
        if plate_type in ('bcarry','mfgco'):
            grid = self.__carryover_grid(metrics)
        elif plate_type in ('bcc','mfgcc','scc'):
            grid = self.__colorcomp_grid(metrics)
        elif plate_type in ('betaec','probeec','evaec'):
            # TODO events plates
            pass
        
        sio = StringIO.StringIO()
        for row in grid:
            sio.write(','.join(['"%s"' % col for col in row]))
            sio.write('\n')
        
        return sio.getvalue()

    
    def __carryover_grid(self, metrics):
        """
        hate
        """
        cols = ('Plate',
                'Date',
                'URL',
                'Event Count Mean*',
                'Events < 12000*',
                'Event Quality < 0.85*',
                'Singleplex Uniformity %*',
                'Carryover/8 Wells*',
                'Width Avg*',
                'Wells',
                'QS Check Wells',
                'Singleplex Mean',
                'Singleplex Mean Low CI', # change to mean/variance/ci95?
                'Singleplex Mean High CI',
                'Quartile Ratio',
                'Quartile Low CI', # change to mean/variance/ci95?
                'Quartile High CI',
                'Positive Amplitude Mean',
                'Positive Amplitude Stdev',
                'Negative Amplitude Mean',
                'Negative Amplitude Stdev',
                'S Mean',
                'S Stdev',
                'Event Count Mean',
                'Event Count Stdev',
                'Air Droplets Mean',
                'Air Droplets Stdev',
                'Carryover Wells',
                'Carryover/8 Wells',
                'Gated Contamination/8 Wells',
                'Contaminants/8 Wells',
                'Rejected Peaks, Eventful Wells',
                'Rejected Peaks, Eventful Wells Stdev',
                'Rejected Peaks, Stealth Wells',
                'Rejected Peaks, Stealth Wells Stdev',
                'Width Mean',
                'Width Stdev',
                'WidthStdev Mean',
                'WidthStdev Stdev',
                'NDS < 2.5 %Mean',
                'NDS < 2.5 %Stdev',
                '%Peaks Width Gated Mean',
                '%Peaks Width Gated Stdev',
                '%Peaks Quality Gated Mean',
                '%Peaks Quality Gated Stdev',
                '%Peaks In Vertical Streaks Mean',
                '%Peaks In Vertical Streaks Stdev',
                '%Peaks Rejected Mean',
                '%Peaks Rejected Stdev',
                '%Peaks Middle Rain Mean',
                '%Peaks Middle Rain Stdev',
                '%Peaks Negative Rain Mean',
                '%Peaks Negative Rain Stdev',
                'Sum Baseline Mean Mean',
                'Sum Baseline Mean Stdev',
                'Sum Baseline Stdev Mean',
                'Sum Baseline Stdev Stdev',
                'FAM Baseline Mean Mean',
                'FAM Baseline Mean Stdev',
                'FAM Baseline Stdev Mean',
                'FAM Baseline Stdev Stdev',
                'VIC Baseline Mean Mean',
                'VIC Baseline Mean Stdev',
                'VIC Baseline Stdev Mean',
                'VIC Baseline Stdev Stdev')

        
        stats = []
        for m in metrics:
            singleplex_stats = m.all_singleplex_conc_ci95
            rise_ratio = m.singleplex_conc_rise_ratio_ci95
            awm = m.all_well_metrics
            positive_stats = m.positive_mean_variance_ci95(m.singleplex_wells, 0)
            negative_stats = m.negative_mean_variance_ci95(m.singleplex_wells, 0)
            s_stats = m.s_value_mean_variance_ci95(m.singleplex_wells, 0)
            ec_stats = m.event_count_count_mean_variance_ci95
            air_stats = m.air_droplets_stats
            carryover_stats = m.total_carryover_stats
            eventful_rejected_stats = m.carryover_eventful_rejected_peaks_ci95
            stealth_rejected_stats = m.carryover_stealth_rejected_peaks_ci95
            width_stats = m.mean_width_mean_variance_ci95
            width_variance_stats = m.width_variance_mean_variance_ci95
            short_droplet_stats = m.short_droplet_spacing_ci95
            width_gated_stats = m.width_gated_pct_mean_variance
            quality_gated_stats = m.quality_gated_pct_mean_variance
            vertical_streak_stats = m.vertical_streak_pct_mean_variance
            rejected_count_stats = m.rejected_peak_pct_mean_variance
            middle_rain_stats = m.carryover_event_middle_rain_stats
            negative_rain_stats = m.carryover_event_negative_rain_stats
            sum_baseline_mean_stats = m.sum_baseline_mean_mean_variance_ci95
            sum_baseline_stdev_stats = m.sum_baseline_stdev_mean_variance_ci95
            fam_baseline_mean_stats = m.fam_baseline_mean_mean_variance_ci95
            fam_baseline_stdev_stats = m.fam_baseline_stdev_mean_variance_ci95
            vic_baseline_mean_stats = m.vic_baseline_mean_mean_variance_ci95
            vic_baseline_stdev_stats = m.vic_baseline_stdev_mean_variance_ci95

            # assume one plate in each metric
            stats.append([
                m.metric_plates[0].name,
                m.metric_plates[0].run_time.strftime('%Y-%m-%d %H:%M'),
                'http://qtools%s' % url(controller='plate', action='view', id=m.metric_plates[0].id),
                m.test_event_count_mean[0],
                m.test_event_count_low[0],
                m.test_quality_low[0],
                m.test_singleplex_uniformity[0]*100,
                m.test_carryover[0],
                m.test_widths[0],
                len(awm),
                len(m.check_quality_wells),
                singleplex_stats[0],
                singleplex_stats[1],
                singleplex_stats[2],
                rise_ratio[0],
                rise_ratio[1],
                rise_ratio[2],
                positive_stats[0],
                positive_stats[1],
                negative_stats[0],
                negative_stats[1],
                s_stats[0],
                s_stats[1],
                ec_stats[0],
                ec_stats[1],
                air_stats[0],
                air_stats[1],
                # assume num wells > 0 here, otherwise divide by zero
                carryover_stats[-1],
                carryover_stats[1]*(float(m.carryover_n_wells)/carryover_stats[-1]),
                carryover_stats[2]*(float(m.carryover_n_wells)/carryover_stats[-1]),
                carryover_stats[3]*(float(m.carryover_n_wells)/carryover_stats[-1]),
                eventful_rejected_stats[0],
                eventful_rejected_stats[1],
                stealth_rejected_stats[0],
                stealth_rejected_stats[1],
                width_stats[0],
                width_stats[1],
                width_variance_stats[0],
                width_variance_stats[1],
                short_droplet_stats[0]*100,
                short_droplet_stats[1]*100,
                width_gated_stats[0],
                width_gated_stats[1],
                quality_gated_stats[0],
                quality_gated_stats[1],
                vertical_streak_stats[0],
                vertical_streak_stats[1],
                rejected_count_stats[0],
                rejected_count_stats[1],
                middle_rain_stats[0]*100,
                middle_rain_stats[1]*100,
                negative_rain_stats[0]*100,
                negative_rain_stats[1]*100,
                sum_baseline_mean_stats[0],
                sum_baseline_mean_stats[1],
                sum_baseline_stdev_stats[0],
                sum_baseline_stdev_stats[1],
                fam_baseline_mean_stats[0],
                fam_baseline_mean_stats[1],
                fam_baseline_stdev_stats[0],
                fam_baseline_stdev_stats[1],
                vic_baseline_mean_stats[0],
                vic_baseline_mean_stats[1],
                vic_baseline_stdev_stats[0],
                vic_baseline_stdev_stats[1]

            ])
        
        stats.insert(0, cols)
        return zip(*stats)
    
    def __colorcomp_grid(self, metrics):
        """
        hate, x2
        """
        cols = ('Plate',
                'Date',
                'URL',
                'Event Count Mean*',
                'Events < 12000*',
                'FAM 350nM Amplitude Mean*',
                'FAM 350nM Amplitude %CV*',
                'VIC 350nM Amplitude Mean*',
                'VIC 350nM Amplitude %CV*',
                'Width Avg*',
                'Wells',
                'Event Count Mean',
                'Event Count Stdev',
                'Air Droplets Mean',
                'Air Droplets Stdev',
                'Width Mean',
                'Width Stdev',
                'WidthStdev Mean',
                'WidthStdev Stdev',
                'NDS < 2.5 %Mean',
                'NDS < 2.5 %Stdev',
                '%Peaks Width Gated Mean',
                '%Peaks Width Gated Stdev',
                '%Peaks Quality Gated Mean',
                '%Peaks Quality Gated Stdev',
                '%Peaks In Vertical Streaks Mean',
                '%Peaks In Vertical Streaks Stdev',
                '%Peaks Rejected Mean',
                '%Peaks Rejected Stdev',
                '%FAM350 Peaks Rain',
                '%VIC350 Peaks Rain',
                'Sum Baseline Mean Mean',
                'Sum Baseline Mean Stdev',
                'Sum Baseline Stdev Mean',
                'Sum Baseline Stdev Stdev',
                'FAM Baseline Mean Mean',
                'FAM Baseline Mean Stdev',
                'FAM Baseline Stdev Mean',
                'FAM Baseline Stdev Stdev',
                'VIC Baseline Mean Mean',
                'VIC Baseline Mean Stdev',
                'VIC Baseline Stdev Mean',
                'VIC Baseline Stdev Stdev')

        
        stats = []
        for m in metrics:
            awm = m.all_well_metrics
            ec_stats = m.event_count_count_mean_variance_ci95
            air_stats = m.air_droplets_stats
            width_stats = m.mean_width_mean_variance_ci95
            width_variance_stats = m.width_variance_mean_variance_ci95
            short_droplet_stats = m.short_droplet_spacing_ci95
            width_gated_stats = m.width_gated_pct_mean_variance
            quality_gated_stats = m.quality_gated_pct_mean_variance
            vertical_streak_stats = m.vertical_streak_pct_mean_variance
            rejected_count_stats = m.rejected_peak_pct_mean_variance
            fam_rain_stats = m.colorcomp_fam_rain_stats
            vic_rain_stats = m.colorcomp_vic_rain_stats
            sum_baseline_mean_stats = m.sum_baseline_mean_mean_variance_ci95
            sum_baseline_stdev_stats = m.sum_baseline_stdev_mean_variance_ci95
            fam_baseline_mean_stats = m.fam_baseline_mean_mean_variance_ci95
            fam_baseline_stdev_stats = m.fam_baseline_stdev_mean_variance_ci95
            vic_baseline_mean_stats = m.vic_baseline_mean_mean_variance_ci95
            vic_baseline_stdev_stats = m.vic_baseline_stdev_mean_variance_ci95

            # assume one plate in each metric
            stats.append([
                m.metric_plates[0].name,
                m.metric_plates[0].run_time.strftime('%Y-%m-%d %H:%M'),
                'http://qtools%s' % url(controller='plate', action='view', id=m.metric_plates[0].id),
                m.test_event_count_mean[0],
                m.test_event_count_low[0],
                m.test_fam350_amplitude('bcc')[0],
                m.test_fam350_cv('bcc')[0]*100,
                m.test_vic350_amplitude('bcc')[0],
                m.test_vic350_cv('bcc')[0]*100,
                m.test_widths[0],
                len(awm),
                ec_stats[0],
                ec_stats[1],
                air_stats[0],
                air_stats[1],
                width_stats[0],
                width_stats[1],
                width_variance_stats[0],
                width_variance_stats[1],
                short_droplet_stats[0]*100,
                short_droplet_stats[1]*100,
                width_gated_stats[0],
                width_gated_stats[1],
                quality_gated_stats[0],
                quality_gated_stats[1],
                vertical_streak_stats[0],
                vertical_streak_stats[1],
                rejected_count_stats[0],
                rejected_count_stats[1],
                fam_rain_stats[0]*100,
                vic_rain_stats[0]*100,
                sum_baseline_mean_stats[0],
                sum_baseline_mean_stats[1],
                sum_baseline_stdev_stats[0],
                sum_baseline_stdev_stats[1],
                fam_baseline_mean_stats[0],
                fam_baseline_mean_stats[1],
                fam_baseline_stdev_stats[0],
                fam_baseline_stdev_stats[1],
                vic_baseline_mean_stats[0],
                vic_baseline_mean_stats[1],
                vic_baseline_stdev_stats[0],
                vic_baseline_stdev_stats[1]

            ])
        
        stats.insert(0, cols)
        return zip(*stats)
    
    def __setup_metric_compare_form_context(self):
        plate_compares = []
        for col in PlateMetric.__mapper__.columns:
            if col.info.get('comparable'):
                plate_compares.append((col.name, col.doc))
            
        well_compares = []
        for col in WellMetric.__mapper__.columns:
            if col.info.get('comparable'):
                well_compares.append((col.name, col.doc))
        
        well_channel_compares = []
        for col in WellChannelMetric.__mapper__.columns:
            if col.info.get('comparable'):
                well_channel_compares.append((col.name, col.doc))
        
        c.plate_compares = sorted(plate_compares, key=operator.itemgetter(1))
        c.well_compares = sorted(well_compares, key=operator.itemgetter(1))
        c.well_channel_compares = sorted(well_channel_compares, key=operator.itemgetter(1))
        c.form_metric_attr = '%s.%s' % tuple(self.form_result['metric']) if hasattr(self, 'form_result') else ''
        exclude_nodiff = checkbox_field(checked=self.form_result['exclude_nodiff'] if hasattr(self, 'form_result') else True)
        dr_field = box2_field(empty='All', selected=self.form_result['dr_id'] if hasattr(self, 'form_result') else '')
        plate_type_field = beta_type_field(empty='All', selected=self.form_result['pt_id'] if hasattr(self, 'form_result') else '')
        c.metric_form = h.LiteralFormSelectPatch(
            value = {'metric': '%s.%s' % tuple(self.form_result['metric']) if hasattr(self, 'form_result') else '',
                     'minmax_number': self.form_result['minmax_number'] if hasattr(self, 'form_result') else 30,
                     'min_range': self.form_result['min_range'] if hasattr(self, 'form_result') else '',
                     'max_range': self.form_result['max_range'] if hasattr(self, 'form_result') else '',
                     'cmp_method': self.form_result['cmp_method'] if hasattr(self, 'form_result') else COMPARE_ABS_DELTA,
                     'channel_num': str(self.form_result['channel_num']) if hasattr(self, 'form_result') else '0',
                     'exclude_nodiff': exclude_nodiff['value'],
                     'dr_id': str(dr_field['value']),
                     'pt_id': str(plate_type_field['value'])},
            option = {'cmp_method': [(COMPARE_ABS_DELTA,'Absolute Difference'),
                                     (COMPARE_PCT_DELTA,'Percent Difference')],
                                     #(COMPARE_CLOSER_TO_ZERO,'Distance Delta from Zero'),
                                     #(COMPARE_CLOSER_TO_ONE,'Distance Delta from One')],
                      'channel_num': [(0,'FAM'),(1,'VIC')],
                      'exclude_nodiff': exclude_nodiff['options'],
                      'dr_id': dr_field['options'],
                      'pt_id': plate_type_field['options']}
        )

    def compare(self, id=None):
        if id is None:
            abort(404)
            
        c.group = Session.query(AnalysisGroup).get(int(id))
        if not c.group:
            abort(404)
        
        c.analysis_group_id = int(id)
        reprocesses = sorted([(str(r.id), r.name) for r in c.group.reprocesses if r.active], key=operator.itemgetter(1))

        c.process_form = h.LiteralFormSelectPatch(
            value = {'left_config_id': '',
                     'right_config_id': ''},
            option = {'left_config_id': [('','Original')]+reprocesses,
                      'right_config_id': [('','Original')]+reprocesses}
        )

        self.__setup_metric_compare_form_context()

        return render('/metrics/compare.html')
    
    @validate(schema=CompareMetricFilterForm(), form='compare', post_only=False, on_get=True)
    def compare_algs(self, id=None):
        c.group = Session.query(AnalysisGroup).get(int(id))
        if not c.group:
            abort(404)
        
        if not self.form_result['left_config_id']:
            c.left_config_id = ''
            c.left_config_name = 'Original'
        else:
            left_alg = Session.query(ReprocessConfig).get(self.form_result['left_config_id'])
            c.left_config_id = left_alg.id
            c.left_config_name = left_alg.name
        
        if not self.form_result['right_config_id']:
            c.right_config_id = ''
            c.right_config_name = 'Original'
        else:
            right_alg = Session.query(ReprocessConfig).get(self.form_result['right_config_id'])
            c.right_config_id = right_alg.id
            c.right_config_name = right_alg.name
        
        kwargs = self.__get_analysis_group_form_kwargs()
        self.__setup_metric_compare_form_context()
        original_metrics = AnalysisGroupMetrics(c.group.id, reprocess_config_id=self.form_result['left_config_id'], **kwargs)
        test_metrics = AnalysisGroupMetrics(c.group.id, reprocess_config_id=self.form_result['right_config_id'], **kwargs)
        
        if self.form_result['minmax_number']:
            c.divider_row = self.form_result['minmax_number']
        else:
            c.divider_row = None
        metric_type, attr = self.form_result['metric']
        if metric_type == 'plate':
            return self.__plate_compare_algs(original_metrics, test_metrics, attr)
        elif metric_type == 'well':
            return self.__well_compare_algs(original_metrics, test_metrics, attr)
        elif metric_type == 'channel':
            return self.__channel_compare_algs(original_metrics, test_metrics, attr, self.form_result['channel_num'])
    
    def __filter_compare_results(self, results):
        filtered = results
        if self.form_result['minmax_number']:
            minmax = self.form_result['minmax_number']
            if minmax*2 < len(results):
                filtered = results[:minmax] + results[-minmax:]
        
        if self.form_result['min_range']:
            filtered = [f for f in filtered if f[1] >= self.form_result['min_range']]
        if self.form_result['max_range']:
            filtered = [f for f in filtered if f[1] <= self.form_result['max_range']]
        if self.form_result['exclude_nodiff']:
            filtered = [f for f in filtered if f[1]]
        
        return filtered
    
    def __setup_metric_compare_stats_context(self, results):
        if results is None or len(results) == 0:
            c.stats_mean = 0
            c.stats_median = 0
            c.stats_stdev = 0
            c.stats_max = 0
            c.stats_min = 0
            return
        
        numbers = [r[1] for r in results]
        if self.form_result['cmp_method'] == COMPARE_PCT_DELTA:
            numbers = [n*100 for n in numbers]
        c.stats_mean = np.mean(numbers)
        c.stats_median = np.median(numbers)
        c.stats_stdev = np.std(numbers)
        c.stats_max = np.max(numbers)
        c.stats_min = np.min(numbers)

    def __setup_additional_compare_fields_context(self, *mapper_hierarchy):
        additional_fields = request.params.get('additional_fields', '').split(',')

        c.additional_field_hierarchy = [[] for i in range(len(mapper_hierarchy))]
        for f in additional_fields:
            if not f:
                continue
            parents = f.split('.')
            mapper = mapper_hierarchy[len(parents)-1]
            col = mapper.columns.get(parents[-1], None)
            if col is None:
                continue
            c.additional_field_hierarchy[len(parents)-1].append((parents[-1], getattr(col, 'doc', f)))
    
    def __histogram_compare_results(self, results, bins=310):
        if results is None or len(results) == 0:
            c.zero_bin = 0
            c.hist = []
            return
        hist = np.histogram([r[1] for r in results], 310)
        c.hist = hist[0]
        bounds = hist[1]
        has_zero = np.extract(bounds < 0, np.arange(len(bounds)))
        if len(has_zero) != 0:
            c.zero_bin = has_zero[-1]
        else:
            c.zero_bin = 0

    def __plate_compare_algs(self, original_metrics, test_metrics, attr):
        # ensure matching
        original_plate_metrics = original_metrics.all_plate_metrics
        test_plate_metrics = test_metrics.all_plate_metrics
        
        original_plate_metrics_dict = dict([(pm.plate_id, pm) for pm in original_plate_metrics])
        test_plate_metrics_dict = dict([(pm.plate_id, pm) for pm in test_plate_metrics])
        plate_metrics = []
        for k, o in original_plate_metrics_dict.items():
            t = test_plate_metrics_dict.get(k, None)
            if t:
                plate_metrics.append((o, t))
        
        col = PlateMetric.__mapper__.columns.get(attr, None)
        if col is None or not getattr(col, 'doc', None):
            abort(404)
        
        compare_func = COMPARE_FUNC_MAP[self.form_result['cmp_method']](attr)
        c.cmp_display = COMPARE_FUNC_DISPLAY_MAP[self.form_result['cmp_method']]
        
        c.attr = attr
        c.attr_name = PlateMetric.__mapper__.columns[attr].doc

        results = sorted([(oldnew, compare_func(oldnew)) for oldnew in plate_metrics], key=operator.itemgetter(1))
        self.__histogram_compare_results(results)
        c.results = self.__filter_compare_results(results)
        self.__setup_metric_compare_stats_context(results)
        self.__setup_additional_compare_fields_context(PlateMetric.__mapper__)
        return render('/metrics/compare/plate_metric.html')
    
    def __well_compare_algs(self, original_metrics, test_metrics, attr):
        # ensure matching
        original_well_metrics = original_metrics.all_well_metrics
        test_well_metrics = test_metrics.all_well_metrics
        original_well_metrics_dict = dict([(wm.well_id, wm) for wm in original_well_metrics])
        test_well_metrics_dict = dict([(wm.well_id, wm) for wm in test_well_metrics])
        well_metrics = []
        for k, o in original_well_metrics_dict.items():
            t = test_well_metrics_dict.get(k, None)
            if t:
                well_metrics.append((o, t))
        
        col = WellMetric.__mapper__.columns.get(attr, None)
        if col is None or not getattr(col, 'doc', None):
            abort(404)
        
        compare_func = COMPARE_FUNC_MAP[self.form_result['cmp_method']](attr)
        c.cmp_display = COMPARE_FUNC_DISPLAY_MAP[self.form_result['cmp_method']]
        
        c.attr = attr
        c.attr_name = WellMetric.__mapper__.columns[attr].doc

        # TODO limit by number or max/min range
        results = sorted([(oldnew, compare_func(oldnew)) for oldnew in well_metrics], key=operator.itemgetter(1))
        self.__histogram_compare_results(results)
        c.results = self.__filter_compare_results(results)
        self.__setup_metric_compare_stats_context(results)
        self.__setup_additional_compare_fields_context(WellMetric.__mapper__, PlateMetric.__mapper__)
        return render('/metrics/compare/well_metric.html')

    def __channel_compare_algs(self, original_metrics, test_metrics, attr, channel):
        c.channel = channel
        c.channel_name = 'VIC' if channel == 1 else 'FAM'

        original_well_metrics = original_metrics.all_well_metrics
        test_well_metrics = test_metrics.all_well_metrics
        original_channel_metrics_dict = dict([(wm.well_channel_metrics[channel].well_channel_id, wm.well_channel_metrics[channel]) for wm in original_well_metrics])
        test_channel_metrics_dict = dict([(wm.well_channel_metrics[channel].well_channel_id, wm.well_channel_metrics[channel]) for wm in test_well_metrics])
        channel_metrics = []
        for k, o in original_channel_metrics_dict.items():
            t = test_channel_metrics_dict.get(k, None)
            if t:
                channel_metrics.append((o, t))
        
        col = WellChannelMetric.__mapper__.columns.get(attr, None)
        if col is None or not getattr(col, 'doc', None):
            abort(404)
        
        compare_func = COMPARE_FUNC_MAP[self.form_result['cmp_method']](attr)
        c.cmp_display = COMPARE_FUNC_DISPLAY_MAP[self.form_result['cmp_method']]
        
        c.attr = attr
        c.attr_name = WellChannelMetric.__mapper__.columns[attr].doc

        # TODO limit by number or max/min range
        results = sorted([(oldnew, compare_func(oldnew)) for oldnew in channel_metrics], key=operator.itemgetter(1))
        self.__histogram_compare_results(results)
        c.results = self.__filter_compare_results(results)
        self.__setup_metric_compare_stats_context(results)
        self.__setup_additional_compare_fields_context(WellChannelMetric.__mapper__, WellMetric.__mapper__, PlateMetric.__mapper__)
        return render('/metrics/compare/channel_metric.html')

    
    @validate(schema=MetricFilterForm(), form='index', post_only=False, on_get=True)
    def wells(self, id=None, reprocess_config_id=None, mode='group'):
        # todo box2 id
        self.__setup_metrics_context(id, mode, reprocess_config_code=reprocess_config_id)
        subgroup = request.params.get('wells', None)
        
        if subgroup in ('all_well_metrics', 'low_event_wells', 'low_quality_wells', 'check_quality_wells', 'event_count_undercount_wells', 'carryover_stealth_wells','high_event_wells', 'low_event_wells_qx200', 'low_quality_wells_qx200', 'check_quality_wells_qx200' ):
            c.well_metrics = getattr(c.metrics, subgroup)
        else:
            abort(404)
        
        c.well_metrics = sorted(c.well_metrics, key=lambda w: (w.well.plate.plate.box2.name, w.well.plate.plate.name, w.well.well_name))
        for wm in c.well_metrics:
            error_msg = []
            for wcm in wm.well_channel_metrics:
                if wcm.auto_threshold_expected and wcm.decision_tree_flags != 0:
                    if wcm.decision_tree_flags & 256:
                        error_msg.append(QLWellChannel.decision_tree_flags_verbose(wcm.decision_tree_flags - 256))
                    else:
                        error_msg.append(QLWellChannel.decision_tree_flags_verbose(wcm.decision_tree_flags))
            
            if len(error_msg) > 0:
                wm.qs_error_msg = ', '.join(error_msg)
            else:
                wm.qs_error_msg = ''
        
        return render('/metrics/wells.html')
    
    @validate(schema=MetricFilterForm(), form='index', post_only=False, on_get=True)
    def carryover_wells(self, id=None, reprocess_config_id=None, mode='group'):
        self.__setup_metrics_context(id, mode, reprocess_config_id)
        wells = request.params.get('wells', None)
        if wells in ('colorcomp_plate_wells',):
            carryover_plates = c.metrics.colorcomp_plate_metrics
        else:
            carryover_plates = c.metrics.carryover_plate_metrics
        c.plate_metrics = sorted(carryover_plates, key=lambda p: (p.plate.box2.name, p.plate.run_time))
        return render('/metrics/carryover_wells.html')
    
    @validate(schema=MetricFilterForm(), form='index', post_only=False, on_get=True)
    def stats_wells(self, id=None, reprocess_config_id=None, mode='group'):
        # todo setup dr
        self.__setup_metrics_context(id, mode, reprocess_config_code=reprocess_config_id)
        subgroup = request.params.get('wells', None)

        if subgroup in ('null_linkage_wells_sub1'):
            c.well_metrics = getattr(c.metrics, subgroup)
        else:
            abort(404)
        
        c.well_metrics = sorted(c.well_metrics, key=lambda w: (w.well.plate.plate.box2.name, w.well.plate.plate.name, w.well.well_name))        
        return render('/metrics/stats_wells.html')
    
    @validate(schema=MetricFilterForm(), form='index', post_only=False, on_get=True)
    def amp_wells(self, id=None, reprocess_config_id=None, mode='group'):
        self.__setup_metrics_context(id, mode, reprocess_config_code=reprocess_config_id)
        subgroup = request.params.get('wells', None)
        sample = request.params.get('sample', None)

        # to be safe; restrict permission (but this could be used for Dye plates)
        if subgroup == 'colorcomp_sample_wells':
            plate_type = 'bcc'
        elif subgroup == 'singlewell_colorcomp_well':
            plate_type = 'scc'
        else:
            abort(404)
        
        c.well_metrics = c.metrics.well_metrics_by_type_sample(plate_type, sample)
        
        c.well_metrics = sorted(c.well_metrics, key=lambda w: (w.well.plate.plate.box2.name, w.well.plate.plate.name, w.well.well_name))        
        return render('/metrics/amp_wells.html')
    
    @validate(schema=MetricFilterForm(), form='index', post_only=False, on_get=True)
    def fp_wells(self, id=None, reprocess_config_id=None, mode='group'):
        self.__setup_metrics_context(id, mode, reprocess_config_code=reprocess_config_id)
        subgroup = request.params.get('wells', None)

        if subgroup in ('fpfn_false_positive_wells', 'fpfn_false_negative_wells'):
            c.well_metrics = getattr(c.metrics, subgroup)
            c.channel_num = 1
        elif subgroup == 'red_lod_wells':
            c.cpd = request.params.get('cpd', None)
            if c.cpd == '1':
                sample_name = '0% Mutant, 1cpd WT'
            elif c.cpd == '2':
                sample_name = '0% Mutant, 2cpd WT'
            elif c.cpd == '5':
                sample_name = '0% Mutant, 5cpd WT'
            else:
                abort(404)
            c.well_metrics = c.metrics.red_lod_wells(sample_name)
            c.channel_num = 0
        else:
            abort(404)
        
        c.well_metrics = sorted(c.well_metrics, key=lambda w: (w.well.plate.plate.box2.name, w.well.plate.plate.name, w.well.well_name))
        return render('/metrics/fp_wells.html')
    
    @validate(schema=MetricFilterForm(), form='index', post_only=False, on_get=True)
    def conc_wells(self, id=None, mode='group', reprocess_config_id=None):
        self.__setup_metrics_context(id, mode, reprocess_config_code=reprocess_config_id)
        subgroup = request.params.get('wells', None)

        if subgroup in ('singleplex_wells','carryover_eventful_wells'):
            c.well_metrics = getattr(c.metrics, subgroup)
            c.channel_num = 0
        elif subgroup in ('duplex_wells','dplex200_wells'):
            c.conc = request.params.get('conc', None)
            if not c.conc:
                c.conc = ''
                c.well_metrics = c.metrics.duplex_wells
            else:
                c.well_metrics = c.metrics.duplex_fam_conc_well_metrics(int(c.conc))
            c.channel_num = int(request.params.get('channel_num', 0))
        elif subgroup in( 'dnr_wells', 'qx200_dnr_wells' ):
            c.conc = request.params.get('conc', None)
            c.well_metrics = c.metrics.dnr_conc_well_metrics(int(c.conc))
            c.channel_num = 0
            if not c.well_metrics:
                abort(404)
        elif subgroup in ('dnr_eva_staph_wells','dnr_eva_staph_bg_wells','dnr_eva_hgdna_wells'):
            well_metrics = getattr(c.metrics, subgroup)
            c.conc = request.params.get('conc', None)
            if not c.conc:
                c.conc = ''
                c.well_metrics = well_metrics
            else:
                c.well_metrics = c.metrics.fam_conc_well_metrics(well_metrics, int(c.conc))
            c.channel_num = int(request.params.get('channel_num', 0))
        else:
            abort(404)
        
        c.well_metrics = sorted(c.well_metrics, key=lambda w: (w.well.plate.plate.box2.name, w.well.plate.plate.name, w.well.well_name))
        return render('/metrics/conc_wells.html')
    
    @validate(schema=MetricFilterForm(), form='index', post_only=False, on_get=True)
    def bias_wells(self, id=None, mode='group', reprocess_config_id=None):
        self.__setup_metrics_context(id, mode, reprocess_config_code=reprocess_config_id)
        subgroup = request.params.get('wells', None)

        if subgroup in ('singleplex_wells',):
            c.well_metrics = getattr(c.metrics, subgroup)
        elif subgroup in ('duplex_wells',):
            c.conc = request.params.get('conc', None)
            if not c.conc:
                c.conc = ''
                c.well_metrics = c.metrics.duplex_wells
            else:
                c.well_metrics = c.metrics.duplex_fam_conc_well_metrics(int(c.conc))
        elif subgroup == 'dnr_wells':
            c.conc = request.params.get('conc', None)
            c.well_metrics = c.metrics.dnr_conc_well_metrics(int(c.conc))
            if not c.well_metrics:
                abort(404)
        else:
            abort(404)
        
        c.well_metrics = sorted(c.well_metrics, key=lambda w: (w.well.plate.plate.box2.name, w.well.plate.plate.name, w.well.well_name))
        return render('/metrics/bias_wells.html')
    
    @validate(schema=MetricFilterForm(), form='index', post_only=False, on_get=True)
    def rain_wells(self, id=None, mode='group', reprocess_config_id=None):
        self.__setup_metrics_context(id, mode, reprocess_config_code=reprocess_config_id)
        subgroup = request.params.get('wells', None)

        # for now, just these two groups
        if subgroup in ('fam_gap_rain_wells', 'vic_gap_rain_wells', 'carryover_eventful_wells', 'colorcomp_fam_high_wells', 'colorcomp_vic_high_wells'):
            c.well_metrics = getattr(c.metrics, subgroup)
            c.channel_num = int(request.params.get('channel_num', 0)) 
        else:
            abort(404)
            
        c.well_metrics = sorted(c.well_metrics, key=lambda w: (w.well.plate.plate.box2.name, w.well.plate.plate.name, w.well.well_name))
        return render('/metrics/rain_wells.html')

    
    @validate(schema=MetricFilterForm(), form='index', post_only=False, on_get=True)
    def cnv_wells(self, id=None, mode='group', reprocess_config_id=None):
        self.__setup_metrics_context(id, mode, reprocess_config_code=reprocess_config_id)
        subgroup = request.params.get('wells', None)

        if subgroup == 'cnv_wells':
            c.num = request.params.get('num', None)
            c.well_metrics = c.metrics.well_metrics_of_cnv_num(int(c.num))
            if not c.well_metrics:
                abort(404)
        else:
            abort(404)
        
        c.well_metrics = sorted(c.well_metrics, key=lambda w: (w.well.plate.plate.box2.name, w.well.plate.plate.name, w.well.well_name))
        return render('/metrics/cnv_wells.html')
    
    @validate(schema=MetricFilterForm(), form='index', post_only=False, on_get=True)
    def gated_wells(self, id=None, mode='group', reprocess_config_id=None):
        self.__setup_metrics_context(id, mode, reprocess_config_code=reprocess_config_id)
        wells = request.params.get('wells', None)
        if wells in ('carryover_eventful_wells', 'ok_carryover_eventful_wells', 'carryover_stealth_wells', 'colorcomp_wells', 'air_droplets_wells'):
            well_metrics = getattr(c.metrics, wells)
        else:
            well_metrics = c.metrics.all_well_metrics

        c.well_metrics = sorted(well_metrics, key=lambda w: (w.well.plate.plate.box2.name, w.well.plate.plate.name, w.well.well_name))
        return render('/metrics/gated_wells.html')
    
    @validate(schema=MetricFilterForm(), form='index', post_only=False, on_get=True)
    def baseline_wells(self, id=None, mode='group', reprocess_config_id=None):
        self.__setup_metrics_context(id, mode, reprocess_config_code=reprocess_config_id)
        wells = request.params.get('wells', None)
        if wells in ('carryover_eventful_wells', 'carryover_stealth_wells'):
            well_metrics = getattr(c.metrics, wells)
        else:
            well_metrics = c.metrics.all_well_metrics

        c.well_metrics = sorted(well_metrics, key=lambda w: (w.well.plate.plate.box2.name, w.well.plate.plate.name, w.well.well_name))
        return render('/metrics/baseline_wells.html')
    
    @validate(schema=MetricFilterForm(), form='index', post_only=False, on_get=True)
    def width_wells(self, id=None, mode='group', reprocess_config_id=None):
        self.__setup_metrics_context(id, mode, reprocess_config_code=reprocess_config_id)

        wells = request.params.get('wells', None)
        if wells in ('event_count_wells'):
            well_metrics = getattr(c.metrics, wells)
        else:
            well_metrics = c.metrics.all_well_metrics
        c.well_metrics = sorted(well_metrics, key=lambda w: (w.well.plate.plate.box2.name, w.well.plate.plate.name, w.well.well_name))
        return render('/metrics/width_wells.html')
