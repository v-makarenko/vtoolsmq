import logging, os
from collections import defaultdict
from datetime import datetime

from pylons import request, response, session, tmpl_context as c, url, config
from pylons.controllers.util import abort, redirect, forward
from pylons.decorators import validate
from pylons.decorators.rest import restrict

from pyqlb.constants import ROWCOL_ORDER_ROW, ROWCOL_ORDER_COL
from pyqlb.objects import QLPlate, QLWell
from pyqlb.writers import QLTWriter

from qtools.lib.decorators import help_at
from qtools.lib.storage import QLStorageSource
from qtools.lib.qlb_factory import ExperimentMetadataObjectFactory
from qtools.lib.qlb_objects import ExperimentMetadataQLPlate, ExperimentMetadataQLWell

from qtools.lib.base import BaseController, render
import qtools.lib.fields as fl
import qtools.lib.helpers as h
from qtools.lib.validators import OneOfInt, IntKeyValidator, PlateUploadConverter, KeyValidator

from qtools.model import Session, Plate, PlateTemplate, PlateSetup, PlateType

import formencode
from formencode.variabledecode import NestedVariables

from paste.fileapp import FileApp

log = logging.getLogger(__name__)

class QLTString(formencode.validators.MaxLength):
    def _to_python(self, value, state):
        #val = super(QLTString, self)._to_python(value, state)
        if value == '' or value is None:
            return ''
        else:
            return str(value)

class CellForm(formencode.Schema):
    allow_extra_fields = True
    filter_extra_fields = True

    # TODO change this to OneOf or special cell validator
    cell_name = QLTString(3, not_empty=True)
    sample = QLTString(64, not_empty=False, if_missing=None) # sample_id?
    # TODO change this to OneOf
    experiment_type = QLTString(31, not_empty=False, if_missing=None)
    experiment_name = QLTString(255, not_empty=False, if_missing=None)
    experiment_comment = QLTString(255, not_empty=False, if_missing=None)

    # TODO change this to OneOf
    fam_type = QLTString(31, not_empty=False, if_missing=None)
    fam_target = QLTString(255, not_empty=False, if_missing=None) # assay_id?
    vic_type = QLTString(31, not_empty=False, if_missing=None)
    vic_target = QLTString(255, not_empty=False, if_missing=None) # assay_id?

    temperature = QLTString(8, not_empty=False, if_missing=None)
    enzyme = QLTString(16, not_empty=False, if_missing=None)
    enzyme_conc = QLTString(8, not_empty=False, if_missing=None)
    additive = QLTString(32, not_empty=False, if_missing=None)
    additive_conc = QLTString(8, not_empty=False, if_missing=None)
    expected_cpd = QLTString(8, not_empty=False, if_missing=None)
    expected_cpul = QLTString(8, not_empty=False, if_missing=None)
    target_copy_num = formencode.validators.Number(not_empty=False, if_missing=1)
    ref_copy_num = formencode.validators.Number(not_empty=False, if_missing=2)
    
    cartridge = QLTString(255, not_empty=False, if_missing=None)
    supermix =  QLTString(255, not_empty=False, if_missing=None)


class PlateMetadataForm(formencode.Schema):
    allow_extra_fields = True
    filter_extra_fields = True

    plate_template_id = IntKeyValidator(PlateTemplate, 'id', not_empty=False, if_missing=None)
    plate_setup_id = IntKeyValidator(PlateSetup, 'id', not_empty=False, if_missing=None)

class TemplateForm(formencode.Schema):
    allow_extra_fields = True
    filter_extra_fields = True

    pre_validators = [NestedVariables()]
    cells = formencode.foreach.ForEach(CellForm(), not_empty=False)
    rowcol_order = OneOfInt((ROWCOL_ORDER_COL, ROWCOL_ORDER_ROW), not_empty=True)

    plate_template_id = IntKeyValidator(PlateTemplate, 'id', not_empty=False, if_missing=None)
    plate_setup_id = IntKeyValidator(PlateSetup, 'id', not_empty=False, if_missing=None)

class UploadForm(formencode.Schema):
    allow_extra_fields = True
    filter_extra_fields = True

    plate = PlateUploadConverter(not_empty=True)

    plate_template_id = IntKeyValidator(PlateTemplate, 'id', not_empty=False, if_missing=None)
    plate_setup_id = IntKeyValidator(PlateSetup, 'id', not_empty=False, if_missing=None)

class ValidationDownloadForm(formencode.Schema):
    allow_extra_fields = True
    filter_extra_fields = True

    plate_template_id = IntKeyValidator(PlateTemplate, 'id', not_empty=True)
    template_name = formencode.validators.String(not_empty=True)
    plate_type_code = KeyValidator(PlateType, 'code', not_empty=True)

def icon_class_decorator(well):
    classes = []
    if not well:
        return ''
    if well.temperature:
        classes.append('conditions_active')
    if well.enzyme or well.enzyme_conc or well.additive or well.additive_conc:
        classes.append('additives_active')
    if well.expected_cpd or well.expected_cpul:
        classes.append('expected_active')
    return ' '.join(classes)


class TemplateController(BaseController):

    def __display(self, rowcol_order=ROWCOL_ORDER_COL):
        c.assay_field = fl.sequence_group_name_field(blank=True, include_without_amplicons=True, empty='')
        c.class_decorator = icon_class_decorator
        c.re_field = fl.instock_enzyme_field()

        c.form = h.LiteralForm(
            value = {'rowcol_order': str(rowcol_order)},
            option = {'rowcol_order': [(ROWCOL_ORDER_ROW, 'By Row (Left->Right)'),
                                       (ROWCOL_ORDER_COL, 'By Column (Top->Bottom)')]}
        )

        if getattr(c, 'plate_setup_id', None):
            c.plate_setup = Session.query(PlateSetup).get(c.plate_setup_id)
        elif getattr(c, 'plate_template_id', None):
            c.plate_template = Session.query(PlateTemplate).get(c.plate_template_id)
        return render('/template/design.html')

    @validate(PlateMetadataForm, form='error', on_get=True, post_only=False)
    def design(self):
        c.plate_template_id = self.form_result['plate_template_id']
        c.plate_setup_id = self.form_result['plate_setup_id']
        return self.__display()
    
    def error(self):
        return 'Template Error: Could not create the plate.'
    
    def from_plate(self, id=None):
        if not id:
            abort(404)
        
        plate = Session.query(Plate).get(id)
        if not plate:
            abort(404)
        
        # ignore possibility of reprocess config for now
        storage = QLStorageSource(config)
        path = storage.plate_path(plate)
        factory = ExperimentMetadataObjectFactory()
        qlp = factory.parse_plate(path)
        c.wells = qlp.analyzed_wells
        c.original_source = plate.name
        c.plate_template_id = None
        c.plate_setup_id = None
        c.id = id
        return self.__display(rowcol_order=qlp.acquisition_order)
    
    @validate(PlateMetadataForm, form='error', on_get=True, post_only=False)
    def upload(self):
        c.form = h.LiteralForm()
        c.plate_template_id = self.form_result['plate_template_id']
        c.plate_setup_id = self.form_result['plate_setup_id']
        return render('/template/upload.html')
    
    @restrict('POST')
    @validate(schema=UploadForm, form='upload')
    def do_upload(self):
        c.wells = self.form_result['plate'].analyzed_wells
        c.plate_template_id = self.form_result['plate_template_id']
        c.plate_setup_id = self.form_result['plate_setup_id']
        return self.__display(rowcol_order=self.form_result['plate'].acquisition_order)
    
    @restrict('POST')
    @validate(schema=TemplateForm, form='design')
    def save(self):
        if self.form_result['plate_setup_id']:
            ps = Session.query(PlateSetup).get(self.form_result['plate_setup_id'])
            prefix = ps.prefix
        elif self.form_result['plate_template_id']:
            pt = Session.query(PlateTemplate).get(self.form_result['plate_template_id'])
            prefix = pt.prefix
        else:
            prefix = 'output'
        
        response.headers['Content-Type'] = 'application/quantalife-template'
        h.set_download_response_header(request, response, "%s.qlt" % prefix)
        response.headers['Pragma'] = 'no-cache'

        # build a plate
        # TODO: add default fields
        plate = ExperimentMetadataQLPlate(channel_names=['FAM','VIC'],
                        host_datetime=datetime.now(),
                        host_machine='QTools',
                        host_user='qtools',
                        plate_template_id=self.form_result['plate_template_id'],
                        plate_setup_id=self.form_result['plate_setup_id'])
        
        for cell in sorted(self.form_result['cells'], key=lambda c: c['cell_name']):
            well = ExperimentMetadataQLWell(name=cell['cell_name'],
                                            num_channels=2,
                                            sample=cell['sample'],
                                            experiment_comment=cell['experiment_comment'],
                                            experiment_name=cell['experiment_name'],
                                            experiment_type=cell['experiment_type'],
                                            temperature=cell['temperature'],
                                            enzyme=cell['enzyme'],
                                            enzyme_conc=cell['enzyme_conc'],
                                            additive=cell['additive'],
                                            additive_conc=cell['additive_conc'],
                                            expected_cpd=cell['expected_cpd'],
                                            expected_cpul=cell['expected_cpul'],
                                            target_copy_num=cell['target_copy_num'],
                                            ref_copy_num=cell['ref_copy_num'],
                                            dg_cartridge=cell['cartridge'],
                                            supermix=cell['supermix'])
            
            well.channels[0].target = cell['fam_target']
            well.channels[0].type = cell['fam_type']
            well.channels[1].target = cell['vic_target']
            well.channels[1].type = cell['vic_type']

            plate.wells[str(cell['cell_name'])] = well
        
        # generate QLT
        # TODO: rowcol order

        writer = QLTWriter(rowcol_order=self.form_result['rowcol_order'],
                           fgcolorfunc=self.__qlt_fgcolorfunc,
                           bgcolorfunc=self.__qlt_bgcolorfunc)
        qlt = writer.getbytes(plate)
        return qlt

    
    @staticmethod
    def __qlt_fgcolorfunc(well):
        if not well.experiment_name:
            return {'alpha': 0, 'red': 0, 'green': 0, 'blue': 0}
        else:
            return {'alpha': 255, 'red': 255, 'green': 255, 'blue': 255}
    
    @staticmethod
    def __qlt_bgcolorfunc(well):
        if not well.experiment_name:
            return {'alpha': 0, 'red': 0, 'green': 0, 'blue': 0}
        else:
            return {'alpha': 255, 'red': 255, 'green': 140, 'blue': 0}

    def _validation_base(self):
        plate_template_id = request.params.get('plate_template_id', None)
        if not plate_template_id:
            abort(404)

        c.plate_template = Session.query(PlateTemplate).get(plate_template_id)
        if not c.plate_template:
            abort(404)

        c.template_field = fl.validation_template_field()
        c.template_field['options'].insert(0,('','-- Select a Template --'))
        c.quadrant_field = {
            'value': '',
            'options': [('A','Upper Left'),
                        ('B','Upper Right'),
                        ('C','Lower Left'),
                        ('D','Lower Right')]
        }

        c.cnv_field = {
            'value': '',
            'options': [('A','Columns 1-3'),
                        ('B','Columns 4-6'),
                        ('C','Columns 7-9'),
                        ('D','Columns 10-12')]
        }

        c.vhalf_field = {
            'value': '',
            'options': [('A','Left Half'),
                        ('B','Right Half')]
        }

        c.half_field = {
            'value': '',
            'options': [('A','Top Half'),
                        ('B','Bottom Half')]
        }

        c.quadplex_field = {
            'value': '',
            'options': [('A','Plate A'),
                        ('B','Plate B')]
        }
        
        c.third_field = {
            'value': '',
            'options': [('A','Columns 1-4'),
                        ('B','Columns 5-8'),
                        ('C','Columns 9-12')]
        }

        return render('/template/validation.html')

    @help_at('features/plate_name.html')
    def validation(self, *args, **kwargs):
        response = self._validation_base()
        plate_template_id = request.params.get('plate_template_id', '')
        return h.render_bootstrap_form(response, defaults={'plate_template_id': plate_template_id})

    def preview(self):
        template = os.path.basename(request.params.get('template'))
        # this is hacky, should be QLTStorageSource
        qlt_path = "%s/%s" % (config['qlb.setup_template_store'], template)

        factory = ExperimentMetadataObjectFactory()
        qlp = factory.parse_plate(qlt_path)
        c.wells = qlp.analyzed_wells
        c.original_source = None
        c.plate_template_id = None
        c.plate_setup_id = None
        c.id = None

        # this is ugly
        c.assay_field = {'value': '', 'options': [('','')]}
        c.class_decorator = lambda well: ''
        c.re_field = fl.instock_enzyme_field()

        c.form = h.LiteralForm(
            value = {'rowcol_order': str(ROWCOL_ORDER_ROW)},
            option = {'rowcol_order': [(ROWCOL_ORDER_ROW, 'By Row (Left->Right)')]}
        )
        c.preview_mode = True
        return render('/template/design.html')

    @validate(schema=ValidationDownloadForm(), form='_validation_base', post_only=False, on_get=True, error_formatters=h.tw_bootstrap_error_formatters)
    def validation_download(self):
        plate_template = Session.query(PlateTemplate).get(self.form_result['plate_template_id'])
        plate_type = Session.query(PlateType).filter_by(code=self.form_result['plate_type_code']).first()
        plate_template.plate_type_id = plate_type.id
        Session.commit()

        response.headers['Content-Type'] = 'application/quantalife-template'
        h.set_download_response_header(request, response, "%s.qlt" % plate_template.prefix)
        response.headers['Pragma'] = 'no-cache'

        # yeah, this is somewhat dangerous...
        template_path = "%s/%s" % (config['qlb.setup_template_store'], os.path.basename(self.form_result['template_name']))

        return forward(FileApp(template_path, response.headerlist))



