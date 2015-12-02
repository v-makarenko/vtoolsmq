import logging, simplejson, re, operator, itertools, StringIO, datetime, shutil, os, csv as csv_pkg

from collections import defaultdict
from pylons import request, response, session, tmpl_context as c, url, config
from pylons.controllers.util import abort, redirect, forward
from pylons.decorators import validate, jsonify
from pylons.decorators.rest import restrict

from paste.fileapp import FileApp

from repoze.what.predicates import has_permission
from qtools.lib.auth import RestrictedWowoActionProtector

from qtools.constants.plate import *
from qtools.lib.base import BaseController, render
import qtools.lib.cookie as cookie
from qtools.lib.decorators import block_contractor, block_contractor_internal_plates, help_at
from qtools.lib.queryform import QueryForm
from qtools.model import Session, Assay, PlateTemplate, Project, Experiment, LotNumber, Plate, Box2, Person, PlateTag, DGUsed 
from qtools.model import QLBPlate, QLBWell, QLBWellChannel, AlgorithmWell, WellTag, ThermalCycler, PlateType, PhysicalPlate
from qtools.model import PlateMetric, WellMetric, WellChannelMetric, AnalysisGroup, ReprocessConfig, SystemVersion
from qtools.model import analysis_group_plate_table as agp, analysis_group_reprocess_table as agr
from qtools.model.platewell import *
from qtools.lib.inspect import class_properties
from qtools.lib.metrics.colorcal import DYES_FAM_VIC, DYES_FAM_HEX,  DYES_EVA, DYES_FAM_VIC_LABEL, DYES_FAM_HEX_LABEL, DYES_EVA_LABEL
from qtools.lib.metrics.colorcal import  single_well_calibration_clusters
from qtools.lib.metrics.db import dbplate_tree
from qtools.lib.plate import make_plate_name
from qtools.lib.platescan import scan_plate, trigger_plate_rescan
from qtools.lib.well import width_gate_sigma
from qtools.lib.qlb import cnv_ratio_numeric
from qtools.lib.storage import QLStorageSource, QLPReprocessedFileSource, QLBPlateSource, QLBImageSource
from qtools.lib.stringutils import militarize, camelize
from qtools.lib.upload import save_plate_from_upload_request, get_create_plate_box
from qtools.lib.validators import OneOfInt, PlateNameSegment, MetricPattern, IntKeyValidator, NullableStringBool, PlateUploadConverter, SaveNewIdFields

import qtools.lib.fields as fl
import qtools.lib.helpers as h

import formencode
from formencode import htmlfill
from formencode.variabledecode import NestedVariables

from sqlalchemy.orm import joinedload_all, joinedload
from sqlalchemy import func, and_, select

import webhelpers.paginate as paginate

END_NUMBER_RE = re.compile("_(\d+)$")
HOST_DATETIME_SPLIT_RE = re.compile(r'[\:\s\/]+')
PATHSEP_RE = re.compile(r'[\\/]+')

CURRENT_ALGORITHM_VERSION='0.4043'

log = logging.getLogger(__name__)

REPLICATE_TYPE_TECHNICAL_REPLICATES = 0
REPLICATE_TYPE_BY_COL = 1
REPLICATE_TYPE_BY_ROW = 2
REPLICATE_TYPE_BY_TARGET = 3
REPLICATE_TYPE_BY_SAMPLE = 4

def replicate_type_field(selected=None):
    return {'value': selected or 0,
            'options': [(REPLICATE_TYPE_TECHNICAL_REPLICATES, 'Technical Replicates'),
                        (REPLICATE_TYPE_BY_COL, 'By Column'),
                        (REPLICATE_TYPE_BY_ROW, 'By Row'),
                        (REPLICATE_TYPE_BY_SAMPLE, 'By Sample Name'),
                        (REPLICATE_TYPE_BY_TARGET, 'By Assay/Target')]}

# TODO find some way to cache this
def mfg_plate_type_field(selected=None):
    field = {'value': selected or '',
             'options': [('','All'),
                         (Session.query(PlateType).filter_by(code='mfgco').first().id,'Fluidics Verification'),
                         (Session.query(PlateType).filter_by(code='scc').first().id,'1-Well Dye Calibration'),
                         (Session.query(PlateType).filter_by(code='mfgcc').first().id,'4-Well Dye Calibration'),
                         (Session.query(PlateType).filter_by(code='fvtitr').first().id,'Calibration Verification')]}
    return field

# add names to this field if you need 'em
def beta_name_field(selected=None):
    field = {'value': selected or '',
             'options': [('',''),
                         ('Carryover','Carryover'),
                         ('CNV','CNV'),
                         ('ColorComp','ColorComp'),
                         ('DNALoad','DNALoad'),
                         ('Duplex','Duplex'),
                         ('Dye','Dye'),
                         ('Events','Events'),
                         ('FPFN','FPFN'),
                         ('HighDNR','HighDNR'),
                         ('QuadPlex','QuadPlex'),
                         ('RED','RED'),
                         ('Singleplex', 'Singleplex')]}
    return field

class PlateForm(formencode.Schema):
    allow_extra_fields = True
    filter_extra_fields = True
    
    # single user
    user = IntKeyValidator(Person, "id", not_empty=False)
    system_version = IntKeyValidator(SystemVersion, "id", not_empty=False)
    project = IntKeyValidator(Project, "id", not_empty=False)
    description = formencode.validators.String()
    
    thermal_cycler = IntKeyValidator(ThermalCycler, "id", not_empty=False, if_missing=None)
    dg_oil = formencode.validators.Int(not_empty=False, if_missing=None)
    dr_oil = formencode.validators.Int(not_empty=False, if_missing=None)
    master_mix = formencode.validators.Int(not_empty=False, if_missing=None)
    gasket = formencode.validators.Int(not_empty=False, if_missing=None)
    fluidics_routine = formencode.validators.Int(not_empty=False, if_missing=None)
    droplet_generation_method = formencode.validators.Int(not_empty=False, if_missing=None)
    dg_used_id = IntKeyValidator(DGUsed, 'id', not_empty=False, if_missing=None)
    droplet_maker = IntKeyValidator(Person, "id", not_empty=False, if_missing=None)
    mfg_exclude = formencode.validators.Bool(not_empty=False, if_missing=False)
    plate_type_id = IntKeyValidator(PlateType, "id", not_empty=False, if_missing=None)
    physical_plate_id = IntKeyValidator(PhysicalPlate, "id", not_empty=False, if_missing=None)
    
    pre_validators = [SaveNewIdFields(('project', Project, 'id', 'name', {}),)]
    
    tags = formencode.foreach.ForEach(IntKeyValidator(PlateTag, "id"))

class PlateTemplateCreateForm(formencode.Schema):
    allow_extra_fields = True
    filter_extra_fields = True
    
    user = IntKeyValidator(Person, "id", not_empty=True, if_missing=None)
    project = IntKeyValidator(Project, "id", not_empty=True, if_missing=None)
    experiment_name = PlateNameSegment(not_empty=True)
    plate_type = IntKeyValidator(PlateType, "id", not_empty=False, if_missing=None)
    
    dg_oil = formencode.validators.Int(not_empty=False, if_missing=None)
    dr_oil = formencode.validators.Int(not_empty=False, if_missing=None)
    master_mix = formencode.validators.Int(not_empty=False, if_missing=None)
    physical_plate_id = IntKeyValidator(PhysicalPlate, "id", not_empty=False, if_missing=None)
    
    droplet_generation_method = formencode.validators.Int(not_empty=False, if_missing=None)
    droplet_maker = IntKeyValidator(Person, 'id', not_empty=False, if_missing=None)

    dg_used_id = IntKeyValidator(DGUsed, 'id', not_empty=False, if_missing=None)
    
    pre_validators = [SaveNewIdFields(('project', Project, 'id', 'name', {}),)]

class PlateMetadataSearchForm(QueryForm):
    allow_extra_fields = True
    filter_extra_fields = True
    include_id_fields = True
    allow_empty_fields = True
    
    entity = Plate

class PlateListForm(formencode.Schema):
    allow_extra_fields = True
    filter_extra_fields = True
    
    project_id = IntKeyValidator(Project, "id", not_empty=False, if_missing=None)
    operator_id = IntKeyValidator(Person, "id", not_empty=False, if_missing=None)
    box2_id = IntKeyValidator(Box2, "id", not_empty=False, if_missing=None)
    plate_type_id = IntKeyValidator(PlateType, "id", not_empty=False, if_missing=None)
    analysis_group_id = IntKeyValidator(AnalysisGroup, "id", not_empty=False, if_missing=None)
    onsite = NullableStringBool(not_empty=False, if_missing=None)

class AlgorithmVersionForm(formencode.Schema):
    allow_extra_fields = True
    filter_extra_fields = True
    
    plate_id = formencode.validators.Int(not_empty=True)
    major_version = formencode.validators.Int(not_empty=True)
    minor_version = formencode.validators.Int(not_empty=True)

class MIPCNVForm(formencode.Schema):
    allow_extra_fields = True
    filter_extra_fields = True

    reference_channel = OneOfInt((0,1))
    fam_fpr = formencode.validators.Number(not_empty=True, if_missing=0)
    vic_fpr = formencode.validators.Number(not_empty=True, if_missing=0)
    ignore_wells = formencode.validators.String(not_empty=False, if_missing=None)
    analysis_group_id = formencode.validators.Number(not_empty=False, if_missing=None)
    reprocess_config_id = formencode.validators.Number(not_empty=False, if_missing=None)

class PlateVersionForm(formencode.Schema):
    allow_extra_fields = True
    filter_extra_fields = True
    
    analysis_group_id = formencode.validators.Number(not_empty=False, if_missing=None)
    reprocess_config_id = formencode.validators.Number(not_empty=False, if_missing=None)

class AmplitudeCSVForm(formencode.Schema):
    allow_extra_fields = True
    filter_extra_fields = True

    wells = formencode.validators.String(not_empty=False, if_missing='')
    analysis_group_id = formencode.validators.Number(not_empty=False, if_missing=None)
    reprocess_config_id = formencode.validators.Number(not_empty=False, if_missing=None)

class OnsitePlateUploadForm(formencode.Schema):
    allow_extra_fields = True
    filter_extra_fields = True

    box2_id = IntKeyValidator(Box2, 'id', not_empty=False, if_missing='unknown')
    plate_type = IntKeyValidator(PlateType, 'id', not_empty=False, if_missing=None)
    project = IntKeyValidator(Project, "id", not_empty=False, if_missing=None)
    plate = PlateUploadConverter(not_empty=True)
    plate_origin = formencode.validators.Int(not_empty=False, if_missing=0)

    pre_validators = [SaveNewIdFields(('project', Project, 'id', 'name', {}),)]

class ReplicateForm(PlateVersionForm):
    pre_validators = [NestedVariables()]

    metrics = formencode.ForEach(MetricPattern(), not_empty=False)
    channel = OneOfInt((0,1))
    replicate_type = OneOfInt((REPLICATE_TYPE_TECHNICAL_REPLICATES,
                               REPLICATE_TYPE_BY_COL,
                               REPLICATE_TYPE_BY_ROW,
                               REPLICATE_TYPE_BY_TARGET,
                               REPLICATE_TYPE_BY_SAMPLE),
                              not_empty=False, if_missing=REPLICATE_TYPE_TECHNICAL_REPLICATES)
    ignore_wells = formencode.validators.String(not_empty=False, if_missing=None)

class ExperimentForm(PlateVersionForm):
    pre_validators = [NestedVariables()]
    control = formencode.validators.String(not_empty=True)
    experiments = formencode.ForEach(formencode.validators.String, not_empty=False)
    metrics = formencode.ForEach(MetricPattern(), not_empty=False)
    channel = OneOfInt((0,1))
    ignore_wells = formencode.validators.String(not_empty=False, if_missing=None)

class PlateWellSearchForm(formencode.Schema):
    allow_extra_fields = True
    filter_extra_fields = True

    sample_name = formencode.validators.String(not_empty=False, if_missing=None)
    any_assay = formencode.validators.String(not_empty=False, if_missing=None)
    fam_assay = formencode.validators.String(not_empty=False, if_missing=None)
    vic_assay = formencode.validators.String(not_empty=False, if_missing=None)


def next_plate_name(name):
    if END_NUMBER_RE.search(name):
        name_base = name[:name.rindex('_')]
    else:
        name_base = name
        
    like_plates = Session.query(Plate).filter(Plate.name.like('%s%%' % name_base)).all()
    if len(like_plates) == 0:
        return name_base
    else:
        max_idx = 1
        for plate in like_plates:
            match = END_NUMBER_RE.search(plate.name)
            if match:
                idx = int(match.group(1))
                if idx > max_idx:
                    max_idx = idx
        return "%s_%s" % (name_base, max_idx+1)


def add_cnv_to_well(well):
    fam_positives = well.channels[0].positive_peaks
    fam_negatives = well.channels[0].negative_peaks
    vic_positives = well.channels[1].positive_peaks
    vic_negatives = well.channels[1].negative_peaks
    well.fam_vic_cnv_ratio = cnv_ratio_numeric(fam_positives, fam_negatives, vic_positives, vic_negatives)
    well.vic_fam_cnv_ratio = cnv_ratio_numeric(vic_positives, vic_negatives, fam_positives, fam_negatives)

def add_width_sigma_disp_to_well(well):
    for channel in well.channels:
        if not channel.width_sigma:
            sigma = width_gate_sigma(well)
            channel.width_sigma_disp = ((channel.max_width_gating or 0) - (channel.min_width_gating or 0))/(2*sigma)
        else:
            channel.width_sigma_disp = ((channel.max_width_gating or 0) - (channel.min_width_gating or 0))/(float(2*channel.width_sigma))

# need reverse lookup here
def make_replicate_field(qlbplate, selected=None):
    records = replicate_well_records(qlbplate)
    record_tuples = [(replicate_key(sample, targets), replicate_display(sample, targets)) \
                        for ((sample, targets), well_list) in records.items()]
    return {'value': selected or '',
            'options': sorted(record_tuples, key=operator.itemgetter(1))}

def replicate_key(sample, targets):
    return h.alphabify(replicate_display(sample, targets))

def replicate_display(sample, targets):
    return "%s %s" % (sample, ("(%s)" % ", ".join([t or '?' for t in targets])) if any(targets) else '')

class PlateController(BaseController):

    def _name_base(self):
        c.validation_mode = request.params.get('mode', '') == 'validation'
        self.__setup_plate_name_form_context(for_validation=c.validation_mode)
        return render('/plate/name.html')

    @help_at('features/plate_name.html')
    def name(self, *args, **kwargs):
        response = self._name_base()
        project_id = request.params.get('project_id', '')
        operator_id = request.params.get('operator_id', '')
        experiment_name = request.params.get('experiment_name', '')
        physical_plate = Session.query(PhysicalPlate).filter_by(name='Eppendorf twin.tec PCR plate 96').first()

        defaults = {'physical_plate_id': physical_plate.id if physical_plate else '',
                    'droplet_generation_method': DG_METHOD_THINXXS_V2C_DIMPLED,
                    'dg_oil': DG_OIL_QLF1_4,
                    'dr_oil': DR_OIL_QLF2_2,
                    'master_mix': MMIX_1_2_HEX,
                    'project': project_id,
                    'user': operator_id,
                    'experiment_name': experiment_name}
        return h.render_bootstrap_form(response, defaults=defaults)
    
    def index(self):
        return render('/plate/index.html')

    @RestrictedWowoActionProtector(has_permission('view-login'))
    def login(self):
        response.content_type = 'text/plain'
        return 'OK'
    
    def __setup_db_context(self, id):
        if id is None:
            abort(404)
        
        c.plate = Session.query(Plate).get(int(id))
        if not c.plate:
            abort(404)

    def __setup_reprocess_context(self, plate=None):
        c.reprocess_config_id = self.form_result['reprocess_config_id'] if hasattr(self, 'form_result') else None
        # really need to ditch this
        c.analysis_group_id = self.form_result['analysis_group_id'] if hasattr(self, 'form_result') else None

        # TODO make this util func (used in well as well)
        if c.reprocess_config_id and c.analysis_group_id:
            rec = Session.execute(select([agr]).where(and_(agr.c.analysis_group_id==int(c.analysis_group_id),
                                                           agr.c.reprocess_config_id==int(c.reprocess_config_id))))
            # check for an existing record
            if rec.rowcount > 0:
                # awesome, get the reprocess config name
                c.reprocess_config = Session.query(ReprocessConfig).get(c.reprocess_config_id)
                c.reprocess_config_id = c.reprocess_config_id
                c.analysis_group = Session.query(AnalysisGroup).get(c.analysis_group_id)
            else:
                c.reprocess_config = None
                c.reprocess_config_id = None
                c.analysis_group = None
        elif c.reprocess_config_id and plate:
            c.reprocess_config = Session.query(ReprocessConfig).get(c.reprocess_config_id)
            if not c.reprocess_config:
                c.analysis_group = None
            
            rec = Session.execute(select([agp]).where(and_(agp.c.analysis_group_id.in_([ag.id for ag in c.reprocess_config.analysis_groups]),
                                                           agp.c.plate_id == plate.id)))
            if rec.rowcount > 0:
                c.analysis_group_id = rec.fetchone()[1]
                c.analysis_group = Session.query(AnalysisGroup).get(c.analysis_group_id)
            else:
                c.analysis_group = None
        else:
            c.reprocess_config = None
            c.analysis_group = None
    
    # TODO: use plate instead of relying on context?
    def __plate_path(self):
        if not c.reprocess_config:
            storage = QLStorageSource(config)
            path = storage.qlbplate_path(c.plate.qlbplate)
        else:
            source = QLPReprocessedFileSource(config['qlb.reprocess_root'], c.reprocess_config)
            path = source.full_path(c.analysis_group, c.plate)
        
        return path

    def __plate_relative_path(self):
        plate_path = self.__plate_path()
        if not c.reprocess_config:
            storage = QLStorageSource(config)
            root = storage.plate_root(c.plate)
        else:
            root = config['qlb.reprocess_root']
        return os.path.relpath(plate_path, root)
    
    def __setup_plate_metric_context(self, plate):
        # should be called after setup_reprocess_context; maybe would be best
        # to add a compute_plate_metric flag to setup_reprocess_context.
        # or do it automatically.

        # TODO replace with plate.metric_for_reprocess_config_id(c.reprocess_config_id)
        c.plate_metric = Session.query(PlateMetric).filter(
                            and_(PlateMetric.plate_id==plate.id,
                                 PlateMetric.reprocess_config_id==c.reprocess_config_id))\
                                .options(joinedload_all(PlateMetric.well_metrics, WellMetric.well_channel_metrics, innerjoin=True)).first()
        
        # need to support plates with or without metrics.  ugh.
        # will want to roll this into metrics only eventually, not for this distribution
        if c.plate_metric:
            c.well_metric_dict = dict([(wm.well_name, wm) for wm in c.plate_metric.well_metrics])
            c.clusters_available = any([wm.cnv_calc_mode == 1 for wm in c.plate_metric.well_metrics])
        else:
            c.clusters_available = False
            c.well_metric_dict = dict()
    
    def __get_possible_reprocess_configs(self, plate):
        plate_metrics = Session.query(PlateMetric).filter(PlateMetric.plate_id==plate.id)\
                               .options(joinedload_all(PlateMetric.reprocess_config,
                                                       ReprocessConfig.analysis_groups)).all()

        tuples = [(url(controller='plate', action='view', id=plate.id),'Original (%s)' % plate.qlbplate.host_software)]
        other_tuples = []
        for p in plate_metrics:
            if p.reprocess_config:
                rec = Session.execute(select([agp]).where(and_(agp.c.analysis_group_id.in_([ag.id for ag in p.reprocess_config.analysis_groups]),
                                                               agp.c.plate_id == plate.id)))
                if rec.rowcount > 0:
                    ag = rec.fetchone()
                    other_tuples.append((url(controller='plate', action='view', id=plate.id, reprocess_config_id=p.reprocess_config.id, analysis_group_id=ag.analysis_group_id), p.reprocess_config.name))
        
        if not other_tuples:
            return None
        
        tuples = tuples + sorted(other_tuples, key=operator.itemgetter(1))
        return tuples

    
    @restrict('POST')
    @validate(schema=PlateForm(), form='new')
    def create(self):
        plate = Plate()
        # this is a little tedious
        plate = self.__set_plate_attrs(plate)
        
        # name
        name = make_plate_name(plate)
        plate.name = next_plate_name(name)
        
        Session.add(plate)
        Session.commit()
        session['flash'] = 'Plate created.'
        session.save()
        redirect(url(controller='plate', action='edit', id=plate.id))

    @help_at('features/plate_name.html')
    @restrict('POST')
    @validate(schema=PlateTemplateCreateForm(), form='_name_base', error_formatters=h.tw_bootstrap_error_formatters)
    def create_template(self, *args, **kwargs):
        plate_template = PlateTemplate()
        plate_template.operator_id = self.form_result['user']
        plate_template.project_id = self.form_result['project']
        plate_name = make_plate_name(plate_template, self.form_result['experiment_name'])
        plate_template.prefix = plate_name
        plate_template.dg_oil = self.form_result['dg_oil']
        plate_template.dr_oil = self.form_result['dr_oil']
        plate_template.master_mix = self.form_result['master_mix']
        plate_template.droplet_generation_method = self.form_result['droplet_generation_method']
        plate_template.droplet_maker_id = self.form_result['droplet_maker']
        #plate_template.plate_type_id = self.form_result['plate_type']
        plate_template.physical_plate_id = self.form_result['physical_plate_id']
        plate_template.dg_used_id = self.form_result['dg_used_id']
        
        # just blow through on refresh -- TODO: make more elegant
        existing_query = Session.query(PlateTemplate).filter_by(prefix=plate_template.prefix)
        for existing_record in existing_query:
            Session.delete(existing_record)
        Session.commit()
        
        Session.add(plate_template)
        Session.commit()

        if request.params.get('mode', None) == 'validation':
            session['flash'] = 'Plate name created.'
            session.save()
            return redirect(url(controller='template', action='validation', plate_template_id = plate_template.id))
        else:
            c.prefix = plate_name
            c.plate_template_id = plate_template.id
            return render('/plate/named.html')
        
    @block_contractor
    def edit(self, id=None, *args, **kwargs):
        if id is None:
            abort(404)
        
        plate = Session.query(Plate).get(id)
        if not plate:
            abort(404)
        
        c.plate = plate
        c.plate_form = self.__plate_form()
        
        values = {'user': plate.operator_id,
                  'system_version': plate.qlbplate.system_version,
                  'plate_type_id': plate.plate_type_id,
                  'project': plate.project_id,
                  'dr_oil': plate.dr_oil,
                  'dg_oil': plate.dg_oil,
                  'dg_used_id': plate.dg_used_id,
                  'physical_plate_id': plate.physical_plate_id,
                  'master_mix': plate.master_mix,
                  'gasket': plate.gasket, 
                  'fluidics_routine': plate.fluidics_routine,
                  'thermal_cycler': plate.thermal_cycler,
                  'description': plate.description,
                  'droplet_generation_method': plate.droplet_generation_method,
                  'droplet_maker': plate.droplet_maker_id,
                  'tags': [tag.id for tag in plate.tags],
                  'mfg_exclude': [u'0', u'1' if plate.mfg_exclude else u'0']}
        return htmlfill.render(render('/plate/edit.html'), values)
    
    @validate(schema=PlateVersionForm(), form='index', post_only=False, on_get=True)
    @block_contractor_internal_plates
    @help_at('features/plate_view.html')
    def view(self, id=None, *args, **kwargs):
        if id is None:
            abort(status_code=404, detail='Plate id is missing.' )
        
        c.plate = self.__plate_query(id)
        if not c.plate:
            abort(status_code=404, detail="Plate ID '%s' not found in DB." % str(id) )
        
        self.__setup_reprocess_context()
        self.__setup_plate_metric_context(c.plate)
        c.reprocess_urls = self.__get_possible_reprocess_configs(c.plate)
        
        c.show_stats_metrics = False
        c.show_prod_metrics = False
        if c.plate.plate_type:
            ## add new plate types here to view plate type specific stats
            if c.plate.plate_type.code in ('bsplex','bdplex','bcnv','gcnv','bred','2x10',
                                           'gdnr','fam350', 'fm350l', 'gload','av','dplex200', 
                                           'dnr200', 'eg200', 'tq200','cnv200'):
                c.show_stats_metrics = True
            elif c.plate.plate_type.code in ('mfgco','bcc','mfgcc','scc','bcarry','betaec',
                                             'probeec', 'evaec'):
                c.show_prod_metrics = True


        rows = dict([('A',{}),('B',{}),('C',{}),('D',{}),('E',{}),('F',{}),('G',{}),('H',{})])
        if c.plate.qlbplate:
            wells = [well for well in c.plate.qlbplate.wells if well.file_id is not None]
            for well in wells:
                well_row = well.well_name[0]
                well_col = well.well_name[1:]
                rows[well_row][well_col] = well

                # if a plate metric exists, make the binding here (no join)
                if c.plate_metric and c.well_metric_dict.get(well.well_name):
                    well.metric = c.well_metric_dict[well.well_name]
                else:
                    add_cnv_to_well(well)
            
            c.wells = sorted(wells, key=operator.attrgetter('id'))
        else:
            c.wells = []
        
        c.rows = rows
        c.well_tags = Session.query(WellTag).order_by('name').all()

        # check session
        person_field = fl.person_field(unicode(session.get('person_id', '')))
        dg_method_field = fl.droplet_generation_method_field(selected=c.plate.droplet_generation_method)

        # TODO: helper method for this?
        c.dg_method_text = fl.field_display_value(dg_method_field)
        c.tag_form = h.LiteralFormSelectPatch(
            value = {'tagger_id': person_field['value']},
            option = {'tagger_id': person_field['options']}
        )

        c.plate_folder = os.path.dirname(self.__plate_relative_path())
        
        return render('/plate/view.html')
    
    @validate(schema=PlateVersionForm(), form='index', post_only=False, on_get=True)
    @block_contractor_internal_plates
    def tabular(self, id=None, *args, **kwargs):
        if id is None:
            abort(404)
        
        # TODO make this a common function (view, )
        c.plate = self.__plate_query(id)
        if not c.plate:
            abort(404)
        
        self.__setup_reprocess_context()
        self.__setup_plate_metric_context(c.plate)
        
        c.show_thumbs = request.params.get('show_thumbs', False)
        
        if c.plate.qlbplate:
            # TODO: helper function
            wells = [well for well in c.plate.qlbplate.wells if well.file_id is not None]
            for well in wells:
                if c.plate_metric and c.well_metric_dict.get(well.well_name):
                    well.metric = c.well_metric_dict[well.well_name]
                else:
                    add_cnv_to_well(well)
                    add_width_sigma_disp_to_well(well)
            c.wells = sorted(wells, key=operator.attrgetter('id'))
        else:
            c.wells = []
        
        self.__warn_if_old_algorithm(c.plate)
        return render('/plate/tabular.html')
    
    @validate(schema=PlateVersionForm(), form='index', post_only=False, on_get=True)
    @block_contractor_internal_plates
    def concbias(self, id=None, *args, **kwargs):
        if id is None:
            abort(404)
        
        c.plate = self.__plate_query(id)
        if not c.plate:
            abort(404)
        
        from qtools.lib.mplot import plot_conc_bias, cleanup, render as plt_render
        
        self.__setup_reprocess_context()
        self.__setup_plate_metric_context(c.plate)
        fig = plot_conc_bias(c.plate_metric, title='Bias - %s - %s (FAM)' % (c.plate.name, c.reprocess_config.name if c.reprocess_config else 'Original'))

        response.content_type = 'image/png'
        imgdata = plt_render(fig, dpi=72)
        cleanup(fig)
        return imgdata
    
    @block_contractor_internal_plates
    def csv_old(self, id=None, *args, **kwargs):
        """
        Initially for Simant.
        """
        if id is None:
            abort(404)
        
        plate = self.__plate_query(id)
        if not plate:
            abort(404)
        
        response.headers['Content-Type']= 'text/csv'
        h.set_download_response_header(request, response, "%s.csv" % plate.name)
        out = StringIO.StringIO()
        csv = ''
        if plate.qlbplate:
            wells = [well for well in plate.qlbplate.wells if well.file_id is not None]
            for well in sorted(wells, key=operator.attrgetter('id')):
                fam = well.channels[0]
                arr = [well.well_name, well.sample_name, well.event_count, fam.positive_peaks, fam.negative_peaks, fam.quantitation_threshold_conf, fam.concentration]
                out.write(','.join([str(a) for a in arr]))
                out.write('\n')
            for well in sorted(wells, key=operator.attrgetter('id')):
                vic = well.channels[1]
                arr = [well.well_name, well.sample_name, well.event_count, vic.positive_peaks, vic.negative_peaks, vic.quantitation_threshold_conf, vic.concentration]
                out.write(','.join([str(a) for a in arr]))
                out.write('\n')
            
        csv = out.getvalue()
        out.close()
        return csv

    
    def algorithms(self):
        abort(404)
        # mothball this for now until metric transition done
        #plates = Session.query(QLBPlate,
        #                       AlgorithmWell.algorithm_major_version,
        #                       AlgorithmWell.algorithm_minor_version,
        #                       func.count('*').label('well_count')).\
        #                 join(AlgorithmWell).\
        #                 group_by(QLBPlate.id, AlgorithmWell.algorithm_major_version, AlgorithmWell.algorithm_minor_version).\
        #                 order_by('qlbplate.id desc, algorithm_major_version desc, algorithm_minor_version desc').\
        #                 options(joinedload_all(QLBPlate.plate, innerjoin=True)).all()
        
        # may be a better way to do this
        #plate_well_count = Session.query(QLBPlate.id,
        #                                 func.count('*').label('well_count')).\
        #                   join(QLBWell).\
        #                   group_by(QLBPlate.id)
        
        #plate_length = dict([(p.id, p.well_count) for p in plate_well_count])
        
        
        #c.plates = [(plate, [tup for tup in list(algorithm_wells) if tup[3] == plate_length[plate.id]]) for plate, algorithm_wells in itertools.groupby(plates, lambda tup: tup[0])]
        #c.plates = [(plate, tup) for plate, tup in c.plates if tup]
        
        #return render('/plate/algorithms.html')
    
    @validate(schema=AlgorithmVersionForm(), on_get=True, post_only=False, form='algorithms')
    def alg_compare(self):
        abort(404)
        #qlbplate_id = self.form_result['plate_id']
        #major = self.form_result['major_version']
        #minor = self.form_result['minor_version']
        #plate = Session.query(QLBPlate).get(qlbplate_id)
        #if not plate:
        #    abort(404)
        
        # this is always going to return an aggregate of the wells, but I think that's OK for now.
        # allows for more sophisticated analysis later.
        #plate = Session.query(QLBPlate).\
        #                filter(QLBPlate.id == qlbplate_id).\
        #                options(joinedload_all(QLBPlate.wells, QLBWell.channels, innerjoin=True),
        #                        joinedload_all(QLBPlate.wells, QLBWell.algorithm_wells, AlgorithmWell.channels, innerjoin=True),
        #                        joinedload_all(QLBPlate.plate, innerjoin=True)).one()
        
        # TODO: duplicate plate display logic?
        #rows = dict([('A',{}),('B',{}),('C',{}),('D',{}),('E',{}),('F',{}),('G',{}),('H',{})])
        #wells = [well for well in plate.wells if well.file_id is not None]
        #for well in wells:
        #    well_row = well.well_name[0]
        #    well_col = well.well_name[1:]
        #    rows[well_row][well_col] = well
        #    well.compare_well = [w for w in well.algorithm_wells if (w.algorithm_major_version == major and w.algorithm_minor_version == minor)][0]
        #    add_cnv_to_well(well)
        #    add_cnv_to_well(well.compare_well)
            
        #c.wells = sorted(wells, key=operator.attrgetter('id'))
        #c.rows = rows
        #c.qlbplate = plate
        #c.plate = plate.plate
        #c.major_version = major
        #c.minor_version = minor
        
        #return render('/plate/alg_compare.html')
    
    def alg_notes(self):
        c.versions = [('0.32','2011/02/14','Major','Switched to Gaussian fit method to compute width gates'),
                      ('0.31','2011/02/01','Minor',['Changed peak quality metric to penalize peaks only adjacent to FWHM boundaries',
                                                    'Resolved MATLAB/C++ discrepancy in doublet separation']),
                      ('0.27','2011/01/07','Minor','Resolved another MATLAB/C++ discrepancy for threshold estimation, detects saturated peaks'),
                      ('0.26','2010/12/23','Minor','Resolved MATLAB/C++ discrepancy for threshold calling in results with low s, or for single clusters.'),
                      ('0.25','2010/12/20','Bugfix','Relaxed criteria for inclusion of samples for the purposes of baseline estimation.'),
                      ('0.24','2010/12/17','Major',['Widened width gate sigma to 3.5 from 2.5.  Should allow a few more negative events where the detector is railed',
                                                    'Uses sum of widths on 2 channels to call events.  Will affect runs where negatives on one channel were quenched below baseline']),
                      ('0.22','2010/12/09','Minor',['Make sure baseline estimation excludes samples above 10000, to avoid being fooled by early flat-top peaks.',
                                                    'Change smoothing filter to 13-tap Savitsky-Golay filter']),
                      ('0.20','2010/12/06','Major',[h.literal('<strong>Uses global histograms approach to estimate threshold.</strong>'),
                                                    'Allow negative amplitudes in processed file.',
                                                    'Increase width sigma from 2.0 to 2.5',
                                                    'Flush A/D samples in the last baseline estimation window (bugfix)',
                                                    h.literal('<strong>Define noisy flat-top peaks as singlet</strong>')]),
                      ('0.14','2010/11/05','Bugfix','Base QuantaSoft 0.1.2.0 version')]
        return render('/plate/alg_notes.html')
    
    
    @validate(schema=PlateVersionForm(), form='index', post_only=False, on_get=True)
    @block_contractor_internal_plates
    def download(self, id=None, *args, **kwargs):
        if id is None:
            abort(404)
        
        c.plate = Session.query(Plate).get(id)
        if not c.plate:
            abort(404)
        
        if not c.plate.qlbplate:
            abort(404)
        
        self.__setup_reprocess_context()
        
        # this is kind of weird to specify, for write only.  separate read-only/write-only source?
        if not c.reprocess_config:
            storage = QLStorageSource(config)
            path = storage.plate_path(c.plate)
        else:
            source = QLPReprocessedFileSource(config['qlb.reprocess_root'], c.reprocess_config)
            path = source.full_path(c.analysis_group, c.plate)
        
        response.headers['Content-Type'] = 'application/quantalife-processed'
        h.set_download_response_header(request, response, c.plate.qlbplate.file.basename)
        return forward(FileApp(path, response.headerlist))
    
    @restrict('POST')
    @validate(schema=PlateForm(), form='edit')
    @block_contractor
    def save(self, id=None, *args, **kwargs):
        if id is None:
            abort(404)
        plate = Session.query(Plate).get(id)
        if plate is None:
            abort(404)
    
        self.__set_plate_attrs(plate)
        Session.commit()
        session['flash'] = 'Plate updated.'
        session.save()
        redirect(url(controller='plate', action='edit', id=plate.id))
    
    
    def __setup_analysis_group_context(self):
        ag_id = cookie.get(cookie.ACTIVE_ANALYSIS_GROUP_ID, as_type=int)
        if ag_id is not None:
            ag = Session.query(AnalysisGroup).get(ag_id)
            if ag:
                c.active_analysis_group = ag

    # UGH.  Why can't it handle both?  Easier way would be to not use
    # validate decorator, I guess.
    def list(self):
        self.__setup_analysis_group_context()
        plate_q = self.__plate_list_query()
        project_field = fl.project_field()
        operator_field = fl.person_field(active_only=False)
        box2_field = fl.box2_field(empty='All')
        plate_type_field = mfg_plate_type_field()
        c.plate_type_id = ''
        c.analysis_group_id = ''
        c.onsite = ''
        c.form = h.LiteralForm(
            value = {'project_id': project_field['value'],
                     'operator_id': operator_field['value'],
                     'box2_id': box2_field['value'],
                     'plate_type_id': plate_type_field['value']},
            option = {'project_id': project_field['options'],
                      'operator_id': operator_field['options'],
                      'box2_id': box2_field['options'],
                      'plate_type_id': plate_type_field['options']}
        )
        c.lab_box2_field = {'value': '',
                            'options': fl.lab_reader_group_field(empty='All')}
        return self.__show_list(plate_q)
   
 
    @block_contractor
    def beta(self, id=None, *args, **kwargs):
        if id not in ('bielas','tewari','roche','snyder','nmi','harvard','belgrader'):
            abort(404)
        
        id_map = {'bielas': 'b00',
                  'tewari': 'bt',
                  'snyder': 'bs',
                  'roche': 'br',
                  'nmi': 'bn',
                  'harvard': 'bh',
                  'belgrader': 'bb'}
        
        box2 = Session.query(Box2).filter_by(code=id_map[id]).one() 
        plate_q = self.__plate_list_query().filter(Plate.box2==box2)
        
        self.__setup_analysis_group_context()
        return self.__show_list(plate_q, title='Plate List: %s' % box2.name, pageclass=id)

    def beta_qx100(self, *args, **kwargs):
        return render('/plate/beta_qx100.html')

    def val_qx200(self, *args, **kwargs):
        return render('/plate/val_qx200.html') 

    def qx200( self, id=None, *args, **kwargs):
        if 'p3900' not in id:
            abort(404)

        box2 = Session.query(Box2).filter_by(code=id).one()
        plate_q = self.__plate_list_query().filter(Plate.box2==box2)

        self.__setup_analysis_group_context()
        return self.__show_list(plate_q, title='Plate List: %s' % box2.name, pageclass=id)

    @block_contractor
    def revz(self, id=None, *args, **kwargs):
        if id not in ('bielas'):
            abort(404)
        
        id_map = {'bielas': 'zb'}
        
        box2 = Session.query(Box2).filter_by(code=id_map[id]).one() 
        plate_q = self.__plate_list_query().filter(Plate.box2==box2)
        
        self.__setup_analysis_group_context()
        return self.__show_list(plate_q, title='Plate List: %s' % box2.name, pageclass=id)

    def list_box2(self, id):
        box2 = Session.query(Box2).filter_by(code=id).first()
        if not box2:
            abort(404)

        else:
            return redirect(url(controller='plate', action='list_filter', box2_id=box2.id))
    
    @validate(schema=PlateListForm(), post_only=False, on_get=True, form='list')
    def list_filter(self):
        self.__setup_analysis_group_context()
        c.project_id = self.form_result['project_id']
        c.operator_id = self.form_result['operator_id']
        c.box2_id = self.form_result['box2_id']
        c.plate_type_id = self.form_result['plate_type_id']
        c.analysis_group_id = self.form_result['analysis_group_id']
        c.onsite = self.form_result['onsite'] or ''

        plate_type = None
        if c.plate_type_id:
            plate_type = Session.query(PlateType).get(int(c.plate_type_id))
            if plate_type:
                c.custom_title = "Plate List: %s" % plate_type.name
        
        plate_q = self.__plate_list_query()
        if self.form_result['project_id']:
            plate_q = plate_q.filter(Plate.project_id==c.project_id)
        
        if self.form_result['operator_id']:
            plate_q = plate_q.filter(Plate.operator_id==c.operator_id)
        
        if self.form_result['box2_id']:
            plate_q = plate_q.filter(Plate.box2_id==c.box2_id)
        
        if self.form_result['plate_type_id']:
            plate_q = plate_q.filter(Plate.plate_type_id==c.plate_type_id)
        
        if self.form_result['analysis_group_id']:
            ids = Session.execute(select([agp.c.plate_id])\
                      .where(agp.c.analysis_group_id == self.form_result['analysis_group_id'])).fetchall()
            plate_ids = [i[0] for i in ids]
            plate_q = plate_q.filter(Plate.id.in_(plate_ids))
        
        if self.form_result['onsite'] is not None:
            plate_q = plate_q.filter(Plate.onsite == self.form_result['onsite'])
        
        project_field = fl.project_field(c.project_id)
        operator_field = fl.person_field(c.operator_id, active_only=False)
        box2_field = fl.box2_field(c.box2_id, empty='All')
        plate_type_field = mfg_plate_type_field(plate_type.code if plate_type else None)
        c.form = h.LiteralFormSelectPatch(
            value = {'project_id': unicode(project_field['value']),
                     'operator_id': unicode(operator_field['value']),
                     'box2_id': unicode(box2_field['value']),
                     'plate_type_id': unicode(c.plate_type_id) if c.plate_type_id else ''},
            option = {'project_id': project_field['options'],
                      'operator_id': operator_field['options'],
                      'box2_id': box2_field['options'],
                      'plate_type_id': plate_type_field['options']}
        )
        c.lab_box2_field = {'value': c.box2_id or '',
                            'options': fl.lab_reader_group_field(empty='All')}
        return self.__show_list(plate_q)
    
    def search(self, id=None):
        if id is None:
            return render('/plate/search.html')
        elif id == 'plate_metadata':
            return self._plate_metadata_search()
        elif id == 'plate_name':
            return self._plate_name_search()
        elif id == "dr_time":
            return self._plate_time_search()
        elif id == "well":
            return h.render_bootstrap_form(self._plate_well_search())
        else:
            abort(404)
    
    def search_results(self, id=None):
        if id == 'plate_metadata':
            return self.__plate_metadata_search_results()
        elif id == 'plate_name':
            return self.__plate_name_search_results()
        elif id == 'dr_time':
            return self.__plate_time_search_results()
        elif id == 'well':
            return self.__plate_well_search_results()
    
    @validate(schema=PlateVersionForm(), form='index', post_only=False, on_get=True)
    @block_contractor_internal_plates
    def mip_cnv(self, id=None, *args, **kwargs):
        if id is None:
            abort(404)
        c.plate = Session.query(Plate).get(int(id))
        if not c.plate:
            abort(404)
        c.form = h.LiteralFormSelectPatch(
                    value = {'reference_channel': '0',
                             'fam_fpr': '0',
                             'vic_fpr': '0'},
                    option = {'reference_channel': (('0', 'FAM'),
                                                   ('1', 'VIC'))}
                )
        c.reprocess_config_id = self.form_result['reprocess_config_id']
        c.analysis_group_id = self.form_result['analysis_group_id']
        return render('/plate/mip_cnv.html')
    
    @validate(schema=MIPCNVForm(), form='mip_cnv')
    @block_contractor_internal_plates
    def mip_cnv_compute(self, id=None, *args, **kwargs):
        from qtools.lib.nstats.mip import process_replicate
        from qtools.lib.qlb_factory import get_plate

        if id is None:
            abort(404)
        c.plate = Session.query(Plate).get(int(id))
        if not c.plate:
            abort(404)
        
        self.__setup_reprocess_context()
        
        # TODO make the extraction of a plate given a reprocess config and analysis group
        # a common lib function (shared between plates, wells)
        if not c.reprocess_config:
            storage = QLStorageSource(config)
            path = storage.plate_path(c.plate)
        else:
            source = QLPReprocessedFileSource(config['qlb.reprocess_root'], c.reprocess_config)
            path = source.full_path(c.analysis_group, c.plate)
        
        qlplate = get_plate(path)
        ignored_wells = [k.strip().upper() for k in self.form_result['ignore_wells'].split(',')]

        # this is a little janky, but it'll work for now -- ideally,
        # the abstraction would be process_replicate, not process_replicates
        replicates = dict()
        for repl, well_kv in qlplate.replicates.items():
            repl_dict = {}
            for k, v in well_kv.items():
                if k not in ignored_wells:
                    repl_dict[k] = v
            if len(repl_dict) > 0:
                replicates[repl] = repl_dict
        
        replicate_stats = []
        for sample, wells in sorted(replicates.items(), key=lambda tup: sorted(tup[1].keys())[0]):
            replicate_stats.append((sample, len(wells), process_replicate(wells,
                                                     self.form_result['fam_fpr']/1000.0,
                                                     self.form_result['vic_fpr']/1000.0,
                                                     self.form_result['reference_channel'])))


        c.reference_channel = 'FAM' if self.form_result['reference_channel'] == 0 else 'VIC'
        c.fam_fpr = self.form_result['fam_fpr']
        c.vic_fpr = self.form_result['vic_fpr']
        c.replicates = replicate_stats
        return render('/plate/mip_cnv_results.html')

    def __setup_compare_context(self):
        c.columns = fl.comparable_metric_field()

    def __setup_replicate_context(self):
        self.__setup_compare_context()
        c.channels = fl.channel_field()
        c.replicate_types = replicate_type_field()

    def __setup_replicate_compare_context(self, plate):
        # identify plate replicates
        c.replicate_names = make_replicate_field(plate.qlbplate)

    def __get_replicate_well_names(self):
        """
        Return the replicate groups, ignored wells, well columns, and channel columns
        to use in a replicate/experiment analysis.
        """
        c.technical_replicates = False
        if self.form_result['replicate_type'] == REPLICATE_TYPE_TECHNICAL_REPLICATES:
            replicate_well_names = replicate_well_record_names(c.plate.qlbplate)
            c.technical_replicates = True
        elif self.form_result['replicate_type'] == REPLICATE_TYPE_BY_COL:
            replicate_well_names = colwise_well_record_names(c.plate.qlbplate)
        elif self.form_result['replicate_type'] == REPLICATE_TYPE_BY_ROW:
            replicate_well_names = rowwise_well_record_names(c.plate.qlbplate)
        elif self.form_result['replicate_type'] == REPLICATE_TYPE_BY_TARGET:
            replicate_well_names = targetwise_well_record_names(c.plate.qlbplate, self.form_result['channel'])
        elif self.form_result['replicate_type'] == REPLICATE_TYPE_BY_SAMPLE:
            replicate_well_names = samplewise_well_record_names(c.plate.qlbplate)

        return replicate_well_names

    def __get_ignored_wells(self):
        return [k.strip().upper() for k in self.form_result['ignore_wells'].split(',')]

    def __get_metric_cols(self):
        well_metric_names = [tup[1] for tup in self.form_result['metrics'] if tup[0] == 'well']
        channel_metric_names = [tup[1] for tup in self.form_result['metrics'] if tup[0] == 'channel']

        well_metric_cols = []
        channel_metric_cols = []
        for name in well_metric_names:
            wm_col = get_well_metric_col_info(name)
            if wm_col is not None:
                well_metric_cols.append((name, wm_col))

        for name in channel_metric_names:
            wcm_col = get_well_channel_metric_col_info(name)
            if wcm_col is not None:
                channel_metric_cols.append((name, wcm_col))

        return well_metric_cols, channel_metric_cols

    def _replicate_base(self, id=None):
        if id is None:
            abort(404)

        c.plate = self.__plate_query(id)
        if not c.plate:
            abort(404)

        self.__setup_reprocess_context()
        self.__setup_plate_metric_context(c.plate)
        self.__setup_replicate_context()

        return render('/plate/replicates.html')

    @help_at('features/replicate_tools.html')
    @validate(schema=PlateVersionForm(), form='index', post_only=False, on_get=True)
    def replicates(self, id=None, *args, **kwargs):
        response = self._replicate_base(id)
        return h.render_bootstrap_form(response, defaults=self.form_result)

    def __replicate_statistics(self, replicate_well_names, ignored_wells, well_metric_cols, channel_metric_cols, channel=None):
        import numpy as np

        if not hasattr(c, 'well_metric_dict'):
            return []

        ok_wells = [wn for wn in replicate_well_names if wn not in ignored_wells]
        row = [len(ok_wells)]
        stats = []
        well_metrics = [c.well_metric_dict[wn] for wn in ok_wells]
        for name, col in well_metric_cols:
            percent_attr = getattr(col, 'info', {}).get('percent', False)
            multiplier = 100 if percent_attr else 1
            vals = [(getattr(wm, name) or 0)*multiplier for wm in well_metrics]
            stats.append((np.mean(vals), np.std(vals)))
        channel_metrics = [wcm for wm in well_metrics for wcm in wm.well_channel_metrics if wcm.channel_num == channel]
        for name, col in channel_metric_cols:
            percent_attr = getattr(col, 'info', {}).get('percent', False)
            multiplier = 100 if percent_attr else 1
            vals = [(getattr(wcm, name) or 0)*multiplier for wcm in channel_metrics]
            stats.append((np.mean(vals), np.std(vals)))
        row.append(stats)
        return row


    @help_at('features/replicate_tools.html')
    @validate(schema=ReplicateForm(), form='_replicate_base', post_only=False, on_get=True)
    def replicates_compute(self, id=None, *args, **kwargs):
        if id is None:
            abort(404)

        c.plate = self.__plate_query(id)
        if not c.plate:
            abort(404)

        self.__setup_reprocess_context()
        self.__setup_plate_metric_context(c.plate)
        self.__setup_replicate_context()

        replicate_well_names = self.__get_replicate_well_names()
        ignored_wells = self.__get_ignored_wells()
        well_metric_cols, channel_metric_cols = self.__get_metric_cols()

        replicate_data = []

        for name, well_names in sorted(replicate_well_names.items()):
            stats = self.__replicate_statistics(well_names, ignored_wells, well_metric_cols, channel_metric_cols, self.form_result['channel'])
            stats.insert(0, name)
            replicate_data.append(stats)

        c.well_metric_cols = [col.doc for name, col in well_metric_cols]
        c.channel_metric_cols = [col.doc for name, col in channel_metric_cols]

        c.replicate_data = sorted(replicate_data)
        response = render('/plate/replicate_results.html')
        return h.render_bootstrap_form(response, defaults=self.form_result)

    def _experiment_base(self, id=None):
        if id is None:
            abort(404)

        c.plate = self.__plate_query(id)
        if not c.plate:
            abort(404)

        self.__setup_reprocess_context()
        self.__setup_compare_context()
        c.channels = fl.channel_field()
        self.__setup_replicate_compare_context(c.plate)

        response = render('/plate/experiment.html')
        return response

    @help_at('features/replicate_tools.html')
    @validate(schema=PlateVersionForm(), form='index', post_only=False, on_get=True)
    def experiment(self, id=None, *args, **kwargs):
        response = self._experiment_base(id)
        return h.render_bootstrap_form(response, defaults=self.form_result)

    @help_at('features/replicate_tools.html')
    @validate(schema=ExperimentForm(), form='_experiment_base', post_only=False, on_get=True)
    def experiment_compute(self, id=None, *args, **kwargs):
        import numpy as np

        if id is None:
            abort(404)

        c.plate = self.__plate_query(id)
        if not c.plate:
            abort(404)

        self.__setup_reprocess_context()
        self.__setup_replicate_compare_context(c.plate)
        self.__setup_plate_metric_context(c.plate)
        c.channels = fl.channel_field()
        c.channel_display = 'FAM' if self.form_result['channel'] == 0 else 'VIC/HEX'

        ignored_wells = self.__get_ignored_wells()
        well_metric_cols, channel_metric_cols = self.__get_metric_cols()
        control_key = self.form_result['control']
        experiment_keys = self.form_result['experiments']


        records = replicate_well_records(c.plate.qlbplate)
        replicate_well_displays = dict([(replicate_key(sample, targets), replicate_display(sample, targets)) \
                                        for ((sample, targets), well_list) in records.items()])
        replicate_wells = dict([(replicate_key(sample, targets), well_list) \
                            for ((sample, targets), well_list) in records.items()])


        if not experiment_keys:
            experiment_keys = replicate_wells.keys()

        if control_key in experiment_keys:
            experiment_keys.remove(control_key)

        control_well_names = [w.well_name for w in replicate_wells[control_key]]
        control_stats = self.__replicate_statistics(control_well_names, ignored_wells,
                                                    well_metric_cols, channel_metric_cols,
                                                    self.form_result['channel'])

        experiment_stats = dict()
        for ek in experiment_keys:
            ex_well_names = [w.well_name for w in replicate_wells[ek]]
            replicate_stats = self.__replicate_statistics(ex_well_names, ignored_wells,
                                                          well_metric_cols, channel_metric_cols,
                                                          self.form_result['channel'])
            replicate_diff_stats = [replicate_stats[0], []]
            for exp, control in zip(replicate_stats[1], control_stats[1]):
                replicate_diff_stats[1].append((exp[0], exp[1], ((exp[0]/control[0])-1)*100 if control[0] != 0 else float('nan')))

            experiment_stats[replicate_well_displays[ek]] = replicate_diff_stats

        c.well_metric_cols = [col.doc for name, col in well_metric_cols]
        c.channel_metric_cols = [col.doc for name, col in channel_metric_cols]

        c.control_stat_name = replicate_well_displays[control_key]
        c.control_stats = control_stats
        c.experimental_stats = sorted(experiment_stats.items())
        response = render('/plate/experiment_results.html')
        return h.render_bootstrap_form(response, defaults=self.form_result)

    
    @validate(schema=PlateVersionForm(), form='index', post_only=False, on_get=True)
    @block_contractor_internal_plates
    def frag(self, id=None, *args, **kwargs):
        from qtools.lib.nstats import frag
        from pyqlb.nstats.well import accepted_peaks, well_cluster_peaks
        from qtools.lib.qlb_factory import get_plate

        if id is None:
            abort(404)
        c.plate = Session.query(Plate).get(int(id))
        if not c.plate:
            abort(404)
        
        self.__setup_reprocess_context()
        if not c.reprocess_config:
            storage = QLStorageSource(config)
            path = storage.plate_path(c.plate)
        else:
            source = QLPReprocessedFileSource(config['qlb.reprocess_root'], c.reprocess_config)
            path = source.full_path(c.analysis_group, c.plate)
        
        qlplate = get_plate(path)

        c.frag_stats = []
        for well_name, well in sorted(qlplate.analyzed_wells.items()):
            if not (well.channels[0].statistics.threshold or \
                   well.channels[1].statistics.threshold):
                continue
            
            clusters = well_cluster_peaks(well)
            #if len(clusters['negative_peaks']['negative_peaks']) == 0:
            #    continue

            data = frag.prob_of_frag(len(clusters['positive_peaks']['negative_peaks']),
                                     len(clusters['positive_peaks']['positive_peaks']),
                                     len(clusters['negative_peaks']['negative_peaks']),
                                     len(clusters['negative_peaks']['positive_peaks']),
                                     len(accepted_peaks(well)))
            
            if not data:
                continue
            else:
                prob, fam, vic, linked = data
            c.frag_stats.append(
                (well_name, well.sample_name, well.channels[0].statistics.concentration,
                well.channels[1].statistics.concentration,prob[0],max(0, prob[1]),min(100, prob[2]),int(linked[0]), fam[3], vic[3], linked[3])
            )
        
        if request.params.get('format', None) == 'csv':
            response.headers['Content-Type'] = 'text/csv'
            h.set_download_response_header(request, response, "%s_frag.csv" % c.plate.name)
            out = StringIO.StringIO()
            out.write('Well,Sample,FAM Conc,VIC Conc,Frag Prob%,Frag% CI Low,Frag% CI High,Linked Molecules,FAM Only Conc,VIC Only Conc,Linked Conc\n')
            for stat in c.frag_stats:
                out.write('%s\n' % ','.join([str(s) for s in stat]))
            csv = out.getvalue()
            out.close()
            return csv
        else:
            return render('/plate/frag.html')
    
    @validate(schema=PlateVersionForm(), form='index', post_only=False, on_get=True)
    @block_contractor_internal_plates
    def grid(self, id=None, *args, **kwargs):
        if id is None:
            abort(404)
        
        c.plate = self.__plate_query(id)
        if not c.plate:
            abort(404)
        
        self.__setup_reprocess_context()
        self.__setup_plate_metric_context(c.plate)

        c.class_decorator = lambda w: ''
        rows = dict([('A',{}),('B',{}),('C',{}),('D',{}),('E',{}),('F',{}),('G',{}),('H',{})])
        if c.plate.qlbplate:
            wells = [well for well in c.plate.qlbplate.wells if well.file_id is not None]
            for well in wells:
                well_row = well.well_name[0]
                well_col = well.well_name[1:]
                rows[well_row][well_col] = well

                # if a plate metric exists, make the binding here (no join)
                if c.plate_metric and c.well_metric_dict.get(well.well_name):
                    well.metric = c.well_metric_dict[well.well_name]
                else:
                    add_cnv_to_well(well)
            
            c.wells = rows
        else:
            c.wells = {}
        
        return render('/plate/view2.html')

    
    @validate(schema=AmplitudeCSVForm(), form='grid')
    @block_contractor_internal_plates
    def amplitude_csv(self, id=None, *args, **kwargs):
        from qtools.lib.qlb_factory import get_plate
        from pyqlb.nstats.peaks import fam_amplitudes, vic_amplitudes
        from pyqlb.nstats.well import accepted_peaks
        from pyqlb.factory import peak_dtype
        import numpy as np
        if id is None:
            abort(404)
        
        c.plate = self.__plate_query(id)
        if not c.plate:
            abort(404)
        
        self.__setup_reprocess_context()
        if not c.reprocess_config:
            storage = QLStorageSource(config)
            path = storage.plate_path(c.plate)
        else:
            source = QLPReprocessedFileSource(config['qlb.reprocess_root'], c.reprocess_config)
            path = source.full_path(c.analysis_group, c.plate)
        
        qlplate = get_plate(path)

        with_well_names = request.params.get('with_well_names', None)

        io = StringIO.StringIO()
        wells = self.form_result['wells'].split(',')
        for well in wells:
            qlwell = qlplate.analyzed_wells.get(well, None)
            if qlwell:
                peaks = accepted_peaks(qlwell)
                fam = fam_amplitudes(peaks)
                vic = vic_amplitudes(peaks)
                if with_well_names:
                    for f, v in zip(fam, vic):
                        io.write('%s,%s,%s\n' % (qlwell.name, f, v))
                else:
                    for f, v in zip(fam, vic):
                        io.write('%s,%s\n' % (f, v))
        
        csv = io.getvalue()
        io.close()


        response.headers['Content-Type'] = 'text/csv'
        filename = '%s_%s' % (c.plate.name, '_'.join(wells))
        h.set_download_response_header(request, response, "%s.csv" % filename[:128])
        return csv

    @block_contractor_internal_plates
    def bias_inspect(self, id=None, *args, **kwargs):
        if id is None:
            abort(404)
        
        c.plate = self.__plate_query(id)
        if not c.plate:
            abort(404)
        
        # hard coded -- 
        ag8 = Session.query(AnalysisGroup).get(8)
        c.analysis_group_id = ag8.id
        c.reprocess_config_id = 19

        plates = ag8.plates
        plate_ids = [p.id for p in plates]
        if c.plate.id not in plate_ids:
            c.eligible = False
        else:
            c.eligible = True
        
            ok_wells = [w for w in c.plate.qlbplate.wells if (w.file_id and w.file_id != -1)]
            c.well_select = [('','Plate')]+\
                            [(str(w.id),w.well_name) for w in sorted(ok_wells, key=operator.attrgetter('well_name'))]
            
            rp_configs = Session.query(ReprocessConfig).filter(and_(ReprocessConfig.id >= 19,
                                                                    ReprocessConfig.id <= 24)).order_by('id').all()
            
            c.rp_select = [(str(rp.id), rp.name) for rp in rp_configs]

        return render('/plate/bias_inspect.html')
    
    def __setup_upload_context(self, box2_id=None, customer_plate=False):
        if box2_id is None:
            abort(404)
        
        if box2_id == 'unknown':
            pass
        else:
            box2 = Session.query(Box2).filter_by(code=box2_id).first()
       
            if not box2:
                abort(404)
        
            c.dr = box2
    
        c.project_field = fl.project_field(active_only=True)    
        c.plate_types = fl.beta_type_field()
        c.plate_origins = {'value': customer_plate and '1' or '0',
                           'options': (('0','Manufacturing'),('1', 'Customer'))}
    
    ## upload plate from customer to known DR
    def _onsite_base(self, id=None):
        self.__setup_upload_context(box2_id=id)
        return render('/plate/upload.html')
    
    @block_contractor
    def onsite(self, id=None, *args, **kwargs):
        response = self._onsite_base(id)
        formvars = {'plate_origin': '1', 'box2_id': c.dr.id or ''}
        return h.render_bootstrap_form(response, defaults=formvars)
  
    ## upload plate from unknown DR 
    def _unknown_base(self):
        self.__setup_upload_context(box2_id='unknown')
        return render('/plate/upload.html')

    @block_contractor
    def unknown(self, *args, **kwargs):
        response = self._unknown_base()
        formvars = {'plate_origin': '1', 'box2_id': 'unknown'}
        return h.render_bootstrap_form(response, defaults=formvars)
 
    ## upload plate from  MF
    def _dropship_base(self, id=None):
        self.__setup_upload_context(box2_id=id)
        # override form]
        carryover = Session.query(PlateType).filter(PlateType.code == 'mfgco').first()
        colorcomp = Session.query(PlateType).filter(PlateType.code == 'mfgcc').first()
        events = Session.query(PlateType).filter(PlateType.code == 'betaec').first()
        probe_events = Session.query(PlateType).filter(PlateType.code == 'probeec').first()
        eva_events = Session.query(PlateType).filter(PlateType.code == 'evaec').first()

        c.plate_types = {'options': [('','--'),
                                     (carryover.id, 'MFG Carryover'),
                                     (colorcomp.id, 'MFG ColorComp'),
                                     (events.id, 'Events'),
                                     (probe_events.id, 'Probe Events'),
                                     (eva_events.id, 'Eva Events')]}
                                    
        return render('/plate/dropship.html')
    
    def dropship(self, id=None):
        response = self._dropship_base(id)
        formvars = {'plate_origin': '0', 'box2_id': c.dr.id or ''}
        return h.render_bootstrap_form(response, defaults=formvars)

    def __save_plate_from_upload(self, upload_plate, box2, plate_type ):
        """
        UNSAFE METHOD.

        Saves the plate from the upload folder.  Writes a directory to disk in the
        right place in order to do so.

        Returns a plateobj, which needs to be committed.
        """
        if plate_type:
            plate_type_obj = Session.query(PlateType).get(plate_type)
        else:
            plate_type_obj = None

        form_plate = request.POST['plate']
        return save_plate_from_upload_request(form_plate, upload_plate, box2, plate_type_obj=plate_type_obj)
    
    @restrict('POST')
    @validate(schema=OnsitePlateUploadForm(), form='_onsite_base', error_formatters=h.tw_bootstrap_error_formatters)
    @block_contractor
    def onsite_upload(self, id=None, *args, **kwargs):
        """
        TODO figure out a way to do process isolation/throttle multiple uploads
            id is box2_id
        """
        # get the plate data
        if id is None:
            abort(404)
        
        box2 = Session.query(Box2).filter_by(code=id).first()
        if not box2:
            abort(404)
        
        plateobj = self.__save_plate_from_upload(self.form_result['plate'], box2, self.form_result['plate_type'])
        if plateobj is None:
            Session.rollback()
            session['flash'] = h.literal('Plate upload failed')
             #   (c.alg_version, CURRENT_ALGORITHM_VERSION, url(controller='plate', action='alg_notes')))
            session['flash_class'] = 'warning'

            return redirect(url(controller='plate', action='onsite', id=id))
        else:

            if self.form_result['plate_origin'] == 1:
                plateobj.onsite = True
            if self.form_result['project'] is not None:
                 plateobj.project_id = self.form_result['project']
            Session.commit()
        
            session['flash'] = 'Plate uploaded.'
            session.save()
            redirect(url(controller='plate', action='view', id=plateobj.id))
    
    @restrict('POST')
    @validate(schema=OnsitePlateUploadForm(), form='_dropship_base', error_formatters=h.tw_bootstrap_error_formatters)
    def dropship_upload(self, id=None):
        """
        TODO figure out a way to do process isolation/throttle multiple uploads (RabbitMQ?)
        """
        self.__setup_upload_context(box2_id=id)
        plateobj = self.__save_plate_from_upload(self.form_result['plate'], c.dr, self.form_result['plate_type'])
        plateobj.dropship = True
        Session.commit()

        session['flash'] = 'Plate uploaded.'
        session.save()
        if self.form_result['plate_type']:
            redirect(url(controller='metrics', action='per_plate', id=plateobj.id))
        else:
            redirect(url(controller='plate', action='view', id=plateobj.id))

    @restrict('POST')
    @validate(schema=OnsitePlateUploadForm(), form='_unknown_base', error_formatters=h.tw_bootstrap_error_formatters)
    def unknown_upload(self, id=None):
        """
        TODO figure out a way to do process isolation/throttle multiple uploads (RabbitMQ?)
        """

        plate = self.form_result['plate']
        box2 = get_create_plate_box( plate )

        if not box2:
            abort(404, 'A DR for this plate could not be found or made')

        plateobj = self.__save_plate_from_upload(self.form_result['plate'], box2, self.form_result['plate_type'] )
        
    
        if self.form_result['plate_origin'] == 1:
            plateobj.onsite = True
        if self.form_result['project'] is not None:
            plateobj.project_id = self.form_result['project']

        Session.commit()

        session['flash'] = 'Plate uploaded.'
        session.save()
        if self.form_result['plate_type']:
            redirect(url(controller='metrics', action='per_plate', id=plateobj.id))
        else:
            redirect(url(controller='plate', action='view', id=plateobj.id))   

 
    @validate(schema=PlateVersionForm(), form='index', post_only=False, on_get=True)
    @block_contractor_internal_plates
    def csv(self, id=None, *args, **kwargs):
        if not id:
            abort(404)
        
        self.__setup_reprocess_context()
        plate_metric = Session.query(PlateMetric)\
                              .filter(and_(PlateMetric.plate_id == int(id),
                                           PlateMetric.reprocess_config_id==c.reprocess_config_id))\
                              .options(joinedload_all(PlateMetric.plate, innerjoin=True),
                                       joinedload_all(PlateMetric.well_metrics, WellMetric.well, QLBWell.channels, innerjoin=True),
                                       joinedload_all(PlateMetric.well_metrics, WellMetric.well_channel_metrics, innerjoin=True)).first()
        if plate_metric:
            metrics = True
            plate = plate_metric.plate
        else:
            metrics = False
            plate = dbplate_tree(int(id))
        
        if not plate:
            abort(404)

        response.headers['Content-Type'] = 'text/csv'
        if c.reprocess_config:
            h.set_download_response_header(request, response, '%s_%s_data.csv' % (plate.name, c.reprocess_config.code))
        else:
            h.set_download_response_header(request, response, '%s_data.csv' % plate.name)

        well_metrics = []
        wells = []
        if metrics:
            well_metrics = sorted(plate_metric.well_metrics, key=lambda wm: wm.well.well_name)
        else:
            wells = sorted(plate.qlbplate.wells, key=operator.attrgetter('well_name'))
        
        if not (wells or well_metrics):
            return ''
        else:
            column_headings = ['WellName','SampleName','ExperimentName','ExperimentType','FamTarget','FamType','VicTarget','VicType']
            if metrics:
                wm = plate_metric.well_metrics[0]
                wm_columns = [cl for cl in sorted(wm.__table__.columns.keys()) if cl != 'well_name' and not cl.endswith('id')]
                column_headings.extend(wm_columns)
                wcm = wm.well_channel_metrics[0]
                wcm_columns = [cl for cl in sorted(wcm.__table__.columns.keys()) if cl != 'channel_num' and not cl.endswith('id')]
                column_headings.extend(['FAM_%s' % cl for cl in wcm_columns])
                column_headings.extend(['VIC_%s' % cl for cl in wcm_columns])
            else:
                column_headings.extend(['event_count'])
                qc = wells[0].channels[0]
                qc_columns = [cl for cl in sorted(qc.__table__.columns.keys()) if cl not in ('channel_num', 'target', 'type') and not cl.endswith('version') and not cl.endswith('id')]
                column_headings.extend(['FAM_%s' % cl for cl in qc_columns])
                column_headings.extend(['VIC_%s' % cl for cl in qc_columns])
        
        outfile = StringIO.StringIO()
        outfile.write(','.join(['"%s"' % col for col in column_headings]))
        outfile.write('\n')

        csvwriter = csv_pkg.writer(outfile)
        if metrics:
            for wm in well_metrics:
                line = [wm.well.well_name, wm.well.sample_name, wm.well.experiment_name, wm.well.experiment_type,
                        wm.well.channels[0].target, wm.well.channels[0].type, wm.well.channels[1].target, wm.well.channels[1].type]
                line.extend([getattr(wm, cl) for cl in wm_columns])
                line.extend([getattr(wm.well_channel_metrics[0], cl) for cl in wcm_columns])
                line.extend([getattr(wm.well_channel_metrics[1], cl) for cl in wcm_columns])

                csvwriter.writerow(line)
        else:
            for well in wells:
                line = [well.well_name, well.sample_name, well.experiment_name, well.experiment_type,
                        well.channels[0].target, well.channels[0].type, well.channels[1].target, well.channels[1].type]
                line.append(well.event_count)
                line.extend([getattr(well.channels[0], cl) for cl in qc_columns])
                line.extend([getattr(well.channels[1], cl) for cl in qc_columns])
            
                csvwriter.writerow(line)
        
        csv = outfile.getvalue()
        outfile.close()
        return csv

    
    def _plate_metadata_search(self):
        c.search_id = 'plate_metadata'
        box2_field = fl.box2_field(empty='Any')
        dg_oil_field = fl.droplet_generator_oil_field(empty='Any')
        dr_oil_field = fl.droplet_reader_oil_field(empty='Any')
        master_mix_field = fl.master_mix_field(empty='Any')
        dg_method_field = fl.droplet_generation_method_field(empty='Any')
        physical_plate_field = fl.physical_plate_field(empty='Any')
        dg_used_field = fl.dg_used_field(request.params.get('dg_used_id', None))
        
        # todo: better pylons way for this?
        c.form = h.LiteralFormSelectPatch(
            value = {'conditions-0.value': box2_field['value'],
                     'conditions-1.value': dg_method_field['value'],
                     'conditions-2.value': dg_oil_field['value'],
                     'conditions-3.value': dr_oil_field['value'],
                     'conditions-4.value': master_mix_field['value'],
                     'conditions-5.value': physical_plate_field['value'],
                     'conditions-6.value': dg_used_field['value']},
            option =  {'conditions-0.value': box2_field['options'],
                       'conditions-1.value': dg_method_field['options'],
                       'conditions-2.value': dg_oil_field['options'],
                       'conditions-3.value': dr_oil_field['options'],
                       'conditions-4.value': master_mix_field['options'],
                       'conditions-5.value': physical_plate_field['options'],
                       'conditions-6.value': dg_used_field['options']}
        )
        return render('/plate/search/plate_metadata.html')

    def _plate_well_search(self):
        c.search_id = 'well'
        c.assay_field = {'value': None,
                         'options': [('','')]+Session.query(Assay.name, Assay.name)\
                                                     .filter(Assay.rejected != True)\
                                                     .order_by(Assay.name).all()}
        return render('/plate/search/well.html')
    
    def _plate_name_search(self):
        c.search_id = 'plate_name'
        
        c.form = h.LiteralForm(
            value = {'conditions-0.value': ''}
        )
        return render('/plate/search/plate_name.html')
    
    def _plate_time_search(self):
        c.search_id = 'dr_time'
        box2_field = fl.box2_field(empty='Any')

        c.form = h.LiteralFormSelectPatch(
            value = {'conditions-0.value': box2_field['value'],
                     'conditions-1.value': '',
                     'conditions-2.value': ''},
            option = {'conditions-0.value': box2_field['options']}
        )
        return render('/plate/search/dr_time.html')
    
    @validate(schema=PlateMetadataSearchForm(), form='_plate_metadata_search', variable_decode=True, post_only=False, on_get=True)
    def __plate_metadata_search_results(self):
        c.search_id = 'plate_metadata'
        conditions, sort_column = self.__plate_search_condition_sort()
        
        query = self.__plate_list_query().filter(conditions).order_by(sort_column)
        # this is hacky.
        fields = [fl.box2_field(), fl.droplet_generation_method_field(),
                  fl.droplet_generator_oil_field(), fl.droplet_reader_oil_field(),
                  fl.master_mix_field(), fl.physical_plate_field(),fl.dg_used_field()]
        
        self.__prepare_search_results_context(query, fields)
        return render('/plate/search/results.html')
    
    @validate(schema=PlateMetadataSearchForm(), form='_plate_name_search', post_only=False, on_get=True)
    def __plate_name_search_results(self):
        c.search_id = 'plate_name'
        conditions, sort_column = self.__plate_search_condition_sort()
        name = self.form_result['conditions'][0]['value']
        
        query = self.__plate_list_query().filter(Plate.name.like("%%%s%%" % name)).order_by(sort_column)
        self.__prepare_search_results_context(query)
        
        # ugh
        c.query_conditions = [{'field': 'plate.name', 'value': name, 'display_value': name}]
        return render('/plate/search/results.html')
    
    @validate(schema=PlateMetadataSearchForm(), form='_plate_time_search', post_only=False, on_get=True)
    def __plate_time_search_results(self):
        c.search_id = 'dr_time'
        conditions, sort_column = self.__plate_search_condition_sort()
        dr_id = self.form_result['conditions'][0]['value']
        start_time = self.form_result['conditions'][1]['value']
        end_time = self.form_result['conditions'][2]['value']

        query = self.__plate_list_query()
        if dr_id:
            query = query.filter(Plate.box2_id == dr_id)
        if start_time:
            query = query.filter(Plate.run_time >= start_time)
        if end_time:
            # make entire day inclusive -- runtime is datetime, input field is date
            query = query.filter(Plate.run_time <= (end_time+datetime.timedelta(1)))

        query = query.order_by('run_time desc')
        self.__prepare_search_results_context(query)
        
        if dr_id:
            dr = Session.query(Box2).get(dr_id)
            if not dr:
                dr_name = '?'
            else:
                dr_name = dr.name
        else:
            dr_name = 'All'
        c.query_conditions = [{'field': 'DR', 'value': dr_name, 'display_value': dr_name},
                              {'field': 'Start Date', 'value': start_time, 'display_value': start_time.strftime('%m/%d/%Y') if start_time else ''},
                              {'field': 'End Date', 'value': end_time, 'display_value': end_time.strftime('%m/%d/%Y') if end_time else ''}]
        return render('/plate/search/results.html')

    @validate(schema=PlateWellSearchForm(), form='_plate_well_search', post_only=False, on_get=True, error_formatters=h.tw_bootstrap_error_formatters)
    def __plate_well_search_results(self):
        c.search_id = 'well'

        sample_name = self.form_result['sample_name']
        any_assay = self.form_result['any_assay']
        fam_assay = self.form_result['fam_assay']
        vic_assay = self.form_result['vic_assay']

        if not (sample_name or any_assay or fam_assay or vic_assay):
            c.paginator = paginate.Page([])
        else:
            query = self.__plate_well_query()

            if sample_name:
                query = query.filter(QLBWell.sample_name.like("%%%s%%" % sample_name))
            if any_assay or fam_assay or vic_assay:
                query = query.join(QLBWellChannel)
            if any_assay:
                query = query.filter(QLBWellChannel.target.like("%%%s%%" % any_assay))
            if fam_assay:
                query = query.filter(and_(QLBWellChannel.target.like("%%%s%%" % fam_assay),
                                          QLBWellChannel.channel_num == 0))
            if vic_assay:
                query = query.filter(and_(QLBWellChannel.target.like("%%%s%%" % vic_assay),
                                          QLBWellChannel.channel_num == 1))

            query = query.order_by("run_time desc")

            c.paginator = paginate.Page(
                query,
                page=int(request.params.get('page', 1)),
                items_per_page = 15
            )
        c.pager_kwargs = dict(self.form_result)
        return render('/plate/search/well_results.html')

    
    def __show_list(self, query, title=None, pageclass=None):

        self.__setup_analysis_group_context()

        query = query.order_by('run_time desc')
        c.paginator = paginate.Page(
            query,
            page=int(request.params.get('page', 1)),
            items_per_page = 15
        )
        
        #self.__setup_analysis_group_context()
        c.pager_kwargs = {}
        if hasattr(c, 'project_id'):
            c.pager_kwargs['project_id'] = c.project_id
        if hasattr(c, 'operator_id'):
            c.pager_kwargs['operator_id'] = c.operator_id
        if hasattr(c, 'box2_id'):
            c.pager_kwargs['box2_id'] = c.box2_id
        if hasattr(c, 'plate_type_id'):
            c.pager_kwargs['plate_type_id'] = c.plate_type_id
        if hasattr(c, 'analysis_group_id'):
            c.pager_kwargs['analysis_group_id'] = c.analysis_group_id
        if hasattr(c, 'onsite'):
            c.pager_kwargs['onsite'] = c.onsite
        
        if title:
            c.custom_title = title
        if pageclass:
            c.custom_pageclass = pageclass
        return render('/plate/list.html')
    
    def __qlplate_from_plate_version_form(self, id):
        """
        Returns a reference to the QLPLate object
        from the PlateVersionForm parameters.

        :param id: The id of the plate.
        """
        from qtools.lib.qlb_factory import get_plate
        self.__setup_db_context(int(id))
        self.__setup_reprocess_context(c.plate)
        path = self.__plate_path()

        plate = get_plate(path)
        return plate
    
    
    @restrict('POST')
    @block_contractor
    def delete(self, id=None, *args, **kwargs):
        if id is None:
            abort(404)
        plate_q = Session.query(Plate)
        plate = plate_q.filter_by(id=id).first()
        if plate is None:
            abort(404)
        
        Session.delete(plate)
        Session.commit()
        session['flash'] = 'Plate deleted.'
        session.save()
        redirect(url(controller='plate', action='list'))
    
    @validate(schema=PlateVersionForm(), post_only=False, on_get=True)
    @block_contractor_internal_plates
    def galaxy(self, id=None, *args, **kwargs):
        from qtools.lib.mplot import multi_galaxy, cleanup, render as plt_render

        plate = self.__qlplate_from_plate_version_form(id)
        wells = plate.analyzed_wells.values()
        channel_idx = int(request.params.get("channel", 0))

        title = 'Galaxy Plate - %s, %s' % (c.plate.name, 'VIC' if channel_idx == 1 else 'FAM')
        fig = multi_galaxy(title, wells, channel=channel_idx, draw_threshold=True, draw_width_gates=True)
        response.content_type = 'image/png'
        imgdata = plt_render(fig, dpi=72)
        cleanup(fig)
        return imgdata
    
    @validate(schema=PlateVersionForm(), post_only=False, on_get=True)
    @block_contractor_internal_plates
    def carryover(self, id=None, *args, **kwargs):
        from qtools.lib.mplot import galaxy_carryover, cleanup, render as plt_render
        from qtools.lib.metrics import CarryoverPlateMetric

        plate = self.__qlplate_from_plate_version_form(id)
        wells = plate.analyzed_wells.values()
        channel_idx = int(request.params.get("channel", 0))

        quality_gate = request.params.get("quality_gate", None)
        if quality_gate:
            quality_gate = True
        else:
            quality_gate = False

        carryover_computer = CarryoverPlateMetric(channel_num=channel_idx)
        all_contamination, gated_contamination, carryover, num_wells, well_peak_dict = \
            carryover_computer.contamination_carryover_peaks(plate)
        
        title = 'Carryover - %s, %s (%sw)' % (c.plate.name, 'VIC' if channel_idx == 1 else 'FAM', num_wells)
        fig = galaxy_carryover(title, wells, all_contamination, gated_contamination, carryover,
                               channel=channel_idx, draw_threshold=True, draw_width_gates=True, quality_gate=quality_gate)
        response.content_type = 'image/png'
        imgdata = plt_render(fig, dpi=72)
        cleanup(fig)
        return imgdata
    
    def __well_attr_csv(self, objlist, *attrs, **kwargs):
        outfile = StringIO.StringIO()
        if not objlist:
            empty = outfile.getvalue()
            outfile.close()
            return empty
        
        sample = objlist[0]
        csvwriter = csv_pkg.writer(outfile)
        real_attrs = [attr for attr in attrs if hasattr(sample, attr)]

        csvwriter.writerow(real_attrs)
        for obj in objlist:
            csvwriter.writerow([str(getattr(obj, attr)) for attr in real_attrs])
        
        csv = outfile.getvalue()
        outfile.close()
        return csv
    
    def __channel_attr_csv(self, welllist, chanlist, *attrs, **kwargs):
        # assuming 2-channel FAM/VIC case for now
        outfile = StringIO.StringIO()
        csvwriter = csv_pkg.writer(outfile)
        if not chanlist:
            empty = outfile.getvalue()
            outfile.close()
            return empty
        
        sample = chanlist[0][0]
        real_attrs = [attr for attr in attrs if hasattr(sample, attr)]

        col_names = ['well_name']
        for attr in real_attrs:
            col_names.extend(['fam_%s' % attr, 'vic_%s' % attr])
        
        csvwriter.writerow(col_names)
        for well, channels in zip(welllist, chanlist):
            row  = []
            row.append(well.well_name)
            for attr in real_attrs:
                row.extend([str(getattr(c, attr)) for c in channels])
            csvwriter.writerow(row)
        
        csv = outfile.getvalue()
        outfile.close()
        return csv


    @validate(schema=PlateVersionForm(), post_only=False, on_get=True)
    @block_contractor_internal_plates
    def well_attr_csv(self, id=None, attribute=None, *args, **kwargs):
        attrstr = str(attribute)
        c.plate = self.__plate_query(id)
        self.__setup_reprocess_context()
        response.headers['Content-Type'] = 'text/csv'
        if c.reprocess_config:
            h.set_download_response_header(request, response, "%s_%s_%s.csv" % (c.plate.name, c.reprocess_config.code, attrstr))
        else:
            h.set_download_response_header(request, response, "%s_%s.csv" % (c.plate.name, attrstr))
        wells = sorted(c.plate.qlbplate.wells, key=operator.attrgetter('well_name'))
        csv = self.__well_attr_csv(wells, 'well_name', attrstr)

        return csv
    
    @validate(schema=PlateVersionForm(), post_only=False, on_get=True)
    @block_contractor_internal_plates
    def well_metric_csv(self, id=None, attribute=None, *args, **kwargs):
        attrstr = str(attribute)
        c.plate = self.__plate_query(id)
        self.__setup_reprocess_context()
        self.__setup_plate_metric_context(c.plate)
        response.headers['Content-Type'] = 'text/csv'
        if c.reprocess_config:
            h.set_download_response_header(request, response, "%s_%s_%s.csv" % (c.plate.name, c.reprocess_config.code, attrstr))
        else:
            h.set_download_response_header(request, response, "%s_%s.csv" % (c.plate.name, attrstr))
        wells = sorted(c.plate_metric.well_metrics, key=operator.attrgetter('well_name'))
        csv = self.__well_attr_csv(wells, 'well_name', attrstr)

        return csv
    
    @validate(schema=PlateVersionForm(), post_only=False, on_get=True)
    @block_contractor_internal_plates
    def channel_attr_csv(self, id=None, attribute=None, *args, **kwargs):
        attrstr = str(attribute)
        c.plate = self.__plate_query(id)
        self.__setup_reprocess_context()
        response.headers['Content-Type'] = 'text/csv'
        if c.reprocess_config:
            h.set_download_response_header(request, response, "%s_%s_%s.csv" % (c.plate.name, c.reprocess_config.code, attrstr))
        else:
            h.set_download_response_header(request, response, "%s_%s.csv" % (c.plate.name, attrstr))
        wells = sorted(c.plate.qlbplate.wells, key=operator.attrgetter('well_name'))
        channels = [w.channels for w in wells]
        csv = self.__channel_attr_csv(wells, channels, attrstr)
        return csv
    
    @validate(schema=PlateVersionForm(), post_only=False, on_get=True)
    @block_contractor_internal_plates
    def channel_metric_csv(self, id=None, attribute=None, *args, **kwargs):
        attrstr = str(attribute)
        c.plate = self.__plate_query(id)
        self.__setup_reprocess_context()
        self.__setup_plate_metric_context(c.plate)
        response.headers['Content-Type'] = 'text/csv'
        if c.reprocess_config:
            h.set_download_response_header(request, response, "%s_%s_%s.csv" % (c.plate.name, c.reprocess_config.code, attrstr))
        else:
            h.set_download_response_header(request, response, "%s_%s.csv" % (c.plate.name, attrstr))
        well_metrics = sorted(c.plate_metric.well_metrics, key=operator.attrgetter('well_name'))
        channel_metrics = [wm.well_channel_metrics for wm in well_metrics]
        csv = self.__channel_attr_csv(well_metrics, channel_metrics, attrstr)
        return csv

    @validate(schema=PlateVersionForm(), post_only=False, on_get=True)
    @block_contractor_internal_plates
    def colorcal(self, id=None, *args, **kwargs):
        import numpy as np
        from pyqlb.nstats.peaks import channel_amplitudes
        if id is None:
            abort(404)
        
        c.plate = self.__plate_query(id)
        if not c.plate:
            abort(404)

        qlplate = self.__qlplate_from_plate_version_form(id)

        if qlplate.is_fam_hex:
            dyeset = DYES_FAM_HEX
            c.chan0_label = 'FAM'
            c.chan1_label = 'HEX'
        else:
            dyeset = DYES_FAM_VIC
            c.chan0_label = 'FAM'
            c.chan1_label = 'VIC'

        colorcal_stats = defaultdict(dict)
        for name, qlwell in qlplate.analyzed_wells.items():
            blue_hi, blue_lo, green_hi, green_lo = single_well_calibration_clusters(qlwell, dyeset)

            colorcal_stats[name]['blue_hi_count'] = len(blue_hi)
            blue_hi_amplitudes = channel_amplitudes(blue_hi, 0)
            colorcal_stats[name]['blue_hi_mean'] = np.mean(blue_hi_amplitudes)
            colorcal_stats[name]['blue_hi_stdev'] = np.std(blue_hi_amplitudes)
            
            colorcal_stats[name]['blue_lo_count'] = len(blue_lo)
            blue_lo_amplitudes = channel_amplitudes(blue_lo, 0)
            colorcal_stats[name]['blue_lo_mean'] = np.mean(blue_lo_amplitudes)
            colorcal_stats[name]['blue_lo_stdev'] = np.std(blue_lo_amplitudes)

            colorcal_stats[name]['green_hi_count'] = len(green_hi)
            green_hi_amplitudes = channel_amplitudes(green_hi, 1)
            colorcal_stats[name]['green_hi_mean'] = np.mean(green_hi_amplitudes)
            colorcal_stats[name]['green_hi_stdev'] = np.std(green_hi_amplitudes)

            colorcal_stats[name]['green_lo_count'] = len(green_lo)
            green_lo_amplitudes = channel_amplitudes(green_lo, 1)
            colorcal_stats[name]['green_lo_mean'] = np.mean(green_lo_amplitudes)
            colorcal_stats[name]['green_lo_stdev'] = np.std(green_lo_amplitudes)

        c.colorcal_stats = sorted(colorcal_stats.items())
        c.mean_stats = dict()
        for group in ('blue_hi', 'blue_lo', 'green_hi', 'green_lo'):
            for attr in ('count', 'mean', 'stdev'):
                c.mean_stats['%s_%s' % (group, attr)] = np.mean([v['%s_%s' % (group, attr)] for k, v in c.colorcal_stats])

        c.plate_well_dict = dict([(w.well_name, w) for w in c.plate.qlbplate.wells])
        return render('/plate/colorcal.html')

    
    def __plate_form(self):
        user_field = fl.person_field(request.params.get('user', None))
        system_version_field = fl.system_version_field(request.params.get('system_version',None))
        project_field = fl.project_field(request.params.get('project', None))
        dg_used_field = fl.dg_used_field(request.params.get('dg_used_id', None))
        thermal_cycler_field = fl.thermal_cycler_field(request.params.get('thermal_cycler', None))
        plate_tag_field = fl.plate_tag_field()
        
        dg_oil_field = fl.droplet_generator_oil_field()
        dr_oil_field = fl.droplet_reader_oil_field()
        master_mix_field = fl.master_mix_field()
        gasket_field = fl.gasket_field()
        fluidics_routine_field = fl.fluidics_routine_field()
        droplet_method_field = fl.droplet_generation_method_field()
        droplet_maker_field = fl.person_field()
        mfg_exclude_field = fl.checkbox_field()
        plate_type_field = fl.beta_type_field()
        physical_plate_field = fl.physical_plate_field()
        
        # TODO: there is probably a way to at least make a base LiteralForm
        # out of fields-- make in fields.py?
        return h.LiteralFormSelectPatch(
            value = {'user': user_field['value'],
                     'system_version': system_version_field['value'],
                     'project': project_field['value'],
                     'dg_used_id': dg_used_field['value'],
                     'thermal_cycler': thermal_cycler_field['value'],
                     'dg_oil': dg_oil_field['value'],
                     'plate_type_id': plate_type_field['value'],
                     'dr_oil': dr_oil_field['value'],
                     'master_mix': master_mix_field['value'],
                     'gasket': gasket_field['value'],
                     'fluidics_routine': fluidics_routine_field['value'],
                     'droplet_generation_method': droplet_method_field['value'],
                     'physical_plate_id': physical_plate_field['value'],
                     'droplet_maker': droplet_maker_field['value']},
            option = {'user': user_field['options'],
                      'system_version': system_version_field['options'],
                      'project': project_field['options'],
                      'dg_used_id': dg_used_field['options'],
                      'thermal_cycler': thermal_cycler_field['options'],
                      'tags': plate_tag_field['options'],
                      'dg_oil': dg_oil_field['options'],
                      'dr_oil': dr_oil_field['options'],
                      'master_mix': master_mix_field['options'],
                      'gasket': gasket_field['options'],
                      'fluidics_routine': fluidics_routine_field['options'],
                      'droplet_generation_method': droplet_method_field['options'],
                      'droplet_maker': droplet_maker_field['options'],
                      'mfg_exclude': mfg_exclude_field['options'],
                      'physical_plate_id': physical_plate_field['options'],
                      'plate_type_id': plate_type_field['options']}
        )

    def __setup_plate_name_form_context(self, for_validation=True):
        c.for_validation = for_validation
        c.project_field = fl.project_field(active_only=True, validation_only=for_validation)
        c.user_field = fl.person_field()
        c.dg_used_field = fl.dg_used_field(request.params.get('dg_used_id', None))

        if for_validation:
            c.experiment_name_field = beta_name_field()

        c.physical_plate_field = fl.physical_plate_field()
        c.droplet_method_field = fl.droplet_generation_method_field()
        c.dg_oil_field = fl.droplet_generator_oil_field()
        c.dr_oil_field = fl.droplet_reader_oil_field()
        c.master_mix_field = fl.master_mix_field()


    def __plate_name_form(self):
        user_field = fl.person_field(request.params.get('user', None))
        dg_used_field = fl.dg_used_field(request.params.get('dg_used_id', None))
        project_field = fl.project_field(request.params.get('project', None), active_only=True)
        dg_oil_field = fl.droplet_generator_oil_field(selected=u'14')
        dr_oil_field = fl.droplet_reader_oil_field(selected=u'22')
        master_mix_field = fl.master_mix_field(selected=u'12')
        physical_plate_field = fl.physical_plate_field(selected=u'1')
        droplet_method_field = fl.droplet_generation_method_field(selected=u'201')
        droplet_maker_field = fl.person_field()
        plate_type_field = fl.beta_type_field()
        
        # TODO: there is probably a way to at least make a base LiteralForm
        # out of fields-- make in fields.py?
        return h.LiteralFormSelectPatch(
            value = {'user': user_field['value'],
                     'dg_used_id':dg_used_field['value'],
                     'project': project_field['value'],
                     'dg_oil': dg_oil_field['value'],
                     'dr_oil': dr_oil_field['value'],
                     'master_mix': master_mix_field['value'],
                     'droplet_generation_method': droplet_method_field['value'],
                     'physical_plate_id': physical_plate_field['value'],
                     'droplet_maker': droplet_maker_field['value'],
                     'plate_type': plate_type_field['value']},
            option = {'user': user_field['options'],
                     'dg_used_id':dg_used_field['options'],
                      'project': project_field['options'],
                      'dg_oil': dg_oil_field['options'],
                      'dr_oil': dr_oil_field['options'],
                      'master_mix': master_mix_field['options'],
                      'droplet_generation_method': droplet_method_field['options'],
                      'droplet_maker': droplet_maker_field['options'],
                      'physical_plate_id': physical_plate_field['options'],
                      'plate_type': plate_type_field['options']}
        )
    
    def __set_plate_attrs(self, plate):
        plate.operator_id = self.form_result['user']
        plate.qlbplate.system_version = self.form_result['system_version']
        plate.project_id = self.form_result['project']
        plate.thermal_cycler = self.form_result['thermal_cycler']
        plate.description = self.form_result['description']
        plate.dr_oil = self.form_result['dr_oil']
        plate.dg_oil = self.form_result['dg_oil']
        plate.master_mix = self.form_result['master_mix']
        plate.gasket = self.form_result['gasket']
        plate.fluidics_routine = self.form_result['fluidics_routine']
        plate.droplet_generation_method = self.form_result['droplet_generation_method']
        plate.droplet_maker_id = self.form_result['droplet_maker']
        plate.mfg_exclude = self.form_result['mfg_exclude']
        plate.dg_used_id = self.form_result['dg_used_id']
        
        if self.form_result['plate_type_id'] != plate.plate_type_id:
            plate.plate_type_id = self.form_result['plate_type_id']
            trigger_plate_rescan(plate)
        
        plate.physical_plate_id = self.form_result['physical_plate_id']
        
        plate.tags = []
        for tag_id in self.form_result['tags']:
            plate.tags.append(Session.query(PlateTag).filter_by(id=tag_id).first())
        
        return plate
    
    def __plate_query(self, id):
        plates = Session.query(Plate). \
                     filter(Plate.id == id). \
                     options(joinedload_all(Plate.qlbplate, QLBPlate.wells, QLBWell.channels, innerjoin=True),
                             joinedload_all(Plate.qlbplate, QLBPlate.wells, QLBWell.well_tags)). \
                     all()
        if not len(plates):
            return None
        else:
            return plates[0]
    
    def __plate_list_query(self):
        query = Session.query(Plate).join(Plate.box2)\
                                    .options(joinedload(Plate.box2),
                                            joinedload(Plate.project),
                                            joinedload(Plate.operator))
        
        if h.wowo('contractor'):
            # TODO reusable query
            query = query.filter(Box2.prod_query())

        return query

    def __plate_well_query(self):
        query = Session.query(Plate, func.group_concat(QLBWell.well_name).label('result_wells'))\
                       .join(Box2)\
                       .join(QLBPlate)\
                       .join(QLBWell)\
                       .group_by(Plate.id)\
                       .options(joinedload(Plate.operator))
        if h.wowo('contractor'):
            query = query.filter(Box2.prod_query())

        return query
    
    def __plate_search_condition_sort(self):
        """
        Return the plate condition and sort column from any QueryForm-based request.
        """
        conditions = and_(*[getattr(cond['field'], cond['compare'])(cond['value']) for cond in self.form_result['conditions'] if cond['value'] is not None])
        
        if self.form_result['order_by_direction'] == "desc":
            sort_column = self.form_result['order_by'].desc()
        else:
            sort_column = self.form_result['order_by']
        
        return conditions, sort_column
    
    def __prepare_search_results_context(self, query, fields=None):
        
        self.__setup_analysis_group_context()

        if not fields:
            fields = []
        c.paginator = paginate.Page(
            query,
            page=int(request.params.get('page', 1)),
            items_per_page = 15
        )
        
        query_conditions = [(idx, cond) for idx, cond in enumerate(self.form_result['conditions']) if cond['value'] is not None]
        c.query_conditions = []
        if fields:
            for idx, cond in query_conditions:
                for key, disp in fields[idx]['options']:
                    if unicode(cond['value']) == unicode(key):
                        cond['display_value'] = disp
                        break
                c.query_conditions.append(cond)
        
        c.form_params = dict([(k,v) for k, v in request.params.items() \
                                      if (k.startswith('condition') or k.startswith('order_by')) \
                                        and v is not ''])
    
    def __warn_if_old_algorithm(self, plate):
        c.alg_version = plate.qlbplate.quantitation_algorithm
        if c.alg_version != CURRENT_ALGORITHM_VERSION:
            session['flash'] = h.literal('This plate was processed with algorithm version %s.  The current version is %s.  To see release notes, <a href="%s">click here.</a>' %\
                (c.alg_version, CURRENT_ALGORITHM_VERSION, url(controller='plate', action='alg_notes')))
            session['flash_class'] = 'warning'
