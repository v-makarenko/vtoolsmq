import logging, operator, StringIO, os, re, shutil
from unidecode import unidecode

from pylons import request, response, session, tmpl_context as c, url, config
from pylons.controllers.util import abort, redirect, forward
from pylons.decorators import validate
from pylons.decorators.rest import restrict
from paste.fileapp import FileApp

import qtools.lib.helpers as h
import qtools.lib.fields as fl
from qtools.lib.base import BaseController, render
from qtools.lib.decorators import help_at
from qtools.lib.storage import QSAlgorithmSource
from qtools.lib.upload import save_plate_from_upload_request
from qtools.lib.validators import OneOfInt, validate_colorcomp_plate, FormattedDateConverter, NonCircularFolderPath
from qtools.lib.validators import IntKeyValidator, PlateUploadConverter, SanitizedString, FileUploadFilter, UniqueKeyValidator, VersionString
from qtools.model import Session, Project, Plate, Box2, QLBWell, QLBPlate, PlateType, Person, ThermalCycler, ReprocessConfig, AnalysisGroup
from qtools.model.batchplate import ManufacturingPlateBatch, ManufacturingPlate
from qtools.model.batchplate.util import query_plate_type_dg_method

from sqlalchemy import and_, or_, func
from sqlalchemy.exc import IntegrityError

from stella.platform.mark0.log import ErrorFilter, MagicFilter

import formencode

import webhelpers.paginate as paginate

from qtools.messages import JSONMessage

QUANTASOFT_DIR_VERSION_RE = re.compile(r'QuantaSoft((_\d+)+)')

log = logging.getLogger(__name__)

class CarryoverCountForm(formencode.Schema):
    allow_extra_fields = True
    filter_extra_fields = True

    start = IntKeyValidator(Plate, 'id', not_empty=True)
    end = IntKeyValidator(Plate, 'id', not_empty=False, if_missing=None)

class PlateTypeConverter(formencode.validators.OneOf):
    plate_type_dict = {'CC': Session.query(PlateType).filter_by(code='mfgcc').first().id,
                       'CO': Session.query(PlateType).filter_by(code='mfgco').first().id,
                       'CSFV': Session.query(PlateType).filter_by(code='fvtitr').first().id,
                       'QP': Session.query(PlateType).filter_by(code='scc').first().id}
    
    def __init__(self, *args, **kwargs):
        super(PlateTypeConverter, self).__init__(PlateTypeConverter.plate_type_dict.values(), *args, **kwargs)
    
    def _to_python(self, value, state):
        return PlateTypeConverter.plate_type_dict.get(value, None)
    
    def _from_python(self, value, state):
        for k, v in PlateTypeConverter.plate_type_dict.items():
            if value == v:
                return k
        
        return None

#class ProductionSerialValidator(formencode.validators.Int):
class ProductionSerialValidator(formencode.validators.String):
    messages = {'serial': 'Invalid serial number.'}

    def _to_python(self, value, state):
        prod_machine = Session.query(Box2).filter(or_(Box2.code=='p%s' % value, Box2.code=='f%s' % value, Box2.code=='d%s' % value)).first()
        if not prod_machine:
            raise formencode.Invalid(self.message('serial', state), value, state)
        else:
            return prod_machine
    
    def _from_python(self, value, state):
        box2 = value
        if not box2.is_prod:
            raise formencode.Invalid(self.message('serial', state), value, state)
        
        return box2.name.split(' ')[-1]

class PlateBatchForm(formencode.Schema):
    allow_extra_fields  = True
    filter_extra_fields = True

    name = formencode.validators.String(not_empty=True)
    plate_type = PlateTypeConverter(not_empty=True)
    creation_date = FormattedDateConverter(date_format='%Y%m%d', not_empty=True)
    dg_method = OneOfInt(dict(ManufacturingPlateBatch.dg_method_display_options()).keys(), not_empty=True)
    creator_id = IntKeyValidator(Person, 'id', not_empty=True)
    quantity = formencode.validators.Int(not_empty=True, min=1, max=99)
    notes = formencode.validators.String(not_empty=False, if_missing=None)
    fam_hi_size = formencode.validators.Number(not_empty=False, min=0, if_missing=None)
    vic_hi_size = formencode.validators.Number(not_empty=False, min=0, if_missing=None)
    hex_hi_size = formencode.validators.Number(not_empty=False, min=0, if_missing=None)
    
class PlateBatchUpdateForm(formencode.Schema):
    allow_extra_fields = True
    filter_extra_fields = True

    creator_id = IntKeyValidator(Person, 'id', not_empty=True)
    notes = formencode.validators.String(not_empty=False, if_missing=None)
    fam_hi_size = formencode.validators.Number(not_empty=False, min=0, if_missing=None)
    vic_hi_size = formencode.validators.Number(not_empty=False, min=0, if_missing=None)
    hex_hi_size = formencode.validators.Number(not_empty=False, min=0, if_missing=None)

class PlateUpdateForm(formencode.Schema):
    allow_extra_fields = True
    filter_extra_fields = True

    dg_method = OneOfInt(dict(ManufacturingPlateBatch.dg_method_display_options()).keys(), not_empty=True)
    qc_plate = formencode.validators.Bool()
    thermal_cycler_id = IntKeyValidator(ThermalCycler, 'id', not_empty=False, if_missing=None)
    plate_notes = formencode.validators.String()

class PlateUploadForm(formencode.Schema):
    allow_extra_fields = True
    filter_extra_fields = True

    box2 = ProductionSerialValidator(not_empty=True)
    plate = PlateUploadConverter(not_empty=True)
    qc_plate = formencode.validators.Bool(not_empty=False, if_missing=False)
    plate_notes = formencode.validators.String(not_empty=False)

class TemplateDownloadForm(formencode.Schema):
    allow_extra_fields = True
    filter_extra_fields = True

    box2_id = IntKeyValidator(Box2, 'id', not_empty=True)
    qc_plate = formencode.validators.Bool(not_empty=False, if_missing=False)

class UnhookCSFVForm(formencode.Schema):
    allow_extra_fields = True
    filter_extra_fields = True

    batch_plate_id = IntKeyValidator(ManufacturingPlate, 'id', not_empty=True)

class LogfileContentsField(FileUploadFilter):
    messages = {'read_error': 'Error reading log file.'}

    def _to_python(self, value, state=None):
        fileobj = super(LogfileContentsField, self)._to_python(value, state=state)
        thefile = fileobj.file
        try:
            contents = thefile.read()

            # TODO tell Kenny not to assume StringIO
            io = StringIO.StringIO(contents)
            magic_filter = MagicFilter()
            error_filter = ErrorFilter()
            filtered = magic_filter.filter(error_filter.filter(io))
            io.close()
            return unidecode(os.linesep.join(filtered.getvalue().split(error_filter._line_separator)))

        except Exception, e:
            raise formencode.Invalid(self.message('read_error', state), value, state)
        finally:
            thefile.close() # could do with here but not sure if I can open the file yet

class LogfileUploadForm(formencode.Schema):
    allow_extra_fields = True
    filter_extra_fields = True

    upload = LogfileContentsField(not_empty=True)

class AlgorithmRegisterForm(formencode.Schema):
    allow_extra_fields = True
    filter_extra_fields = True

    src_dir = formencode.validators.String(not_empty=True)
    code = UniqueKeyValidator(ReprocessConfig, 'code', not_empty=True)
    peak_detection_version = VersionString(not_empty=False, min_parts=2, if_empty=(0,0), if_missing=(0,0))
    peak_quantitation_version = VersionString(not_empty=False, min_parts=2, if_empty=(0,0), if_missing=(0,0))
    # todo: add clustering mode

class AlgorithmCommandForm(formencode.Schema):
    allow_extra_fields = True
    filter_extra_fields = True

    analysis_group_id = IntKeyValidator(AnalysisGroup, 'id', not_empty=True)
    reprocess_config_id = IntKeyValidator(ReprocessConfig, 'id', not_empty=True)

def dg_method_field(selected=None):
    field = {'value': selected or '',
             'options': [('','')]+ManufacturingPlateBatch.dg_method_display_options()}
    return field

def plate_type_field(selected=None):
    field = {'value': selected or '',
             'options': [('',''),
                         ('CO','Fluidics Verification'),
                         ('QP','Dye Calibration'),
                         ('CSFV','Calibration Verification'),
                         ('CC','4-Well Dye Calibration')]}
    return field

def dg_plate_type_field(selected=None):
    field = {'value': selected or '',
             'options': [('','All'),
                         ('CO','Fluidics Verification'),
                         ('QP','Dye Calibration'),
                         ('CSFV','Calibration Verification'),
                         ('CC','4-Well Dye Calibration')]}
    return field


class BatchFilterForm(formencode.Schema):
    allow_extra_fields = True
    filter_extra_fields = True

    plate_type = formencode.validators.OneOf(dict(dg_plate_type_field()['options']).keys(), not_empty=False, if_missing=None)

class ProductController(BaseController):

    def index(self):
        return render('/product/index.html')
    
    def __carryover_plate_field(self):
        plates = Session.query(Plate)\
                        .join(Project, Box2)\
                        .filter(Project.name == 'Carryover')\
                        .order_by(Box2.name, Plate.run_time)\
                        .all()
        
        return {'value': '',
                'options': [('','--')]+
                           [(p.id, "%s - %s" % (p.box2.name, p.name)) for p in plates]}

    def carryover(self):
        c_field = self.__carryover_plate_field()
        c.form = h.LiteralFormSelectPatch(
            value = {'start': c_field['value'],
                     'end': c_field['value']},
            option = {'start': c_field['options'],
                      'end': c_field['options']}
        )
        return render('/product/carryover.html')
    
    @restrict('POST')
    @validate(schema=CarryoverCountForm(), form='carryover')
    def carryover_count(self):
        start = Session.query(Plate).get(self.form_result['start'])
        if not start:
            abort(404)
        c.start = start
        c.end = None
        if self.form_result['end']:
            end = Session.query(Plate).get(self.form_result['end'])
            if not end:
                abort(404)
            c.end = end

            if start.box2_id != end.box2_id:
                session['flash'] = 'The plates must be from the same reader.'
                session['flash_class'] = 'error'
                session.save()
                redirect(url(controller='product', action='carryover'))
            
            results = Session.query(Plate,
                                    func.count(QLBWell.id),
                                    func.sum(QLBWell.event_count))\
                             .join(QLBPlate)\
                             .join(QLBWell)\
                             .filter(and_(Plate.run_time > start.run_time, Plate.run_time < end.run_time,
                                          Plate.box2_id == start.box2_id))\
                             .group_by(Plate.id).all()
            
        else:
            results = Session.query(Plate,
                                    func.count(QLBWell.id),
                                    func.sum(QLBWell.event_count))\
                             .join(QLBPlate)\
                             .join(QLBWell)\
                             .filter(and_(Plate.run_time > start.run_time,
                                          Plate.box2_id == start.box2_id))\
                             .group_by(Plate.id).all()
        
        c.plate_list = sorted([plate for plate, wells, events in results], key=operator.attrgetter('run_time'))
        c.well_sum = sum([(wells or 0) for plate, wells, events in results])
        c.event_sum = sum([(events or 0) for plate, wells, events in results])

        return render('/product/carryover_results.html')

    def __setup_batch_fields(self):
        c.people = fl.person_field()
        c.dg_method = dg_method_field()
        c.plate_type = plate_type_field()

    def batch_new(self):
        response = self._batch_new_base()
        return h.render_bootstrap_form(response)
    
    def _batch_new_base(self):
        self.__setup_batch_fields()
        c.title = "Create Batch"
        c.submit_action = url(controller='product', action='batch_create')
        c.call_to_action = "Create Batch"
        c.record_exists = False
        c.allow_delete = False

        response = render('/product/batch/edit.html')
        return response
    
    @restrict('POST')
    @validate(schema=PlateBatchForm(), form='_batch_new_base', error_formatters=h.tw_bootstrap_error_formatters)
    def batch_create(self):
        try:
            self.__update_batch_record()
        except IntegrityError:
            response = self._batch_new_base()
            defaults = PlateBatchForm().from_python(self.form_result)
            return h.render_bootstrap_form(response,
                                           defaults=defaults,
                                           errors={'name': 'A batch already exists with this name.'},
                                           error_formatters=h.tw_bootstrap_error_formatters)
        
        session['flash'] = 'Batch created.'
        session.save()
        return redirect(url(controller='product', action='batch_list'))
    
    def __update_batch_record(self, record=None):
        new_record = False
        if not record:
            new_record = True
            record = ManufacturingPlateBatch(name=self.form_result['name'],
                                             plate_type_id=self.form_result['plate_type'],
                                             creation_date=self.form_result['creation_date'],
                                             default_dg_method=self.form_result['dg_method'])
        
        record.creator_id = self.form_result['creator_id']
        record.notes = self.form_result['notes']
        record.fam_hi_size = self.form_result['fam_hi_size']
        record.vic_hi_size = self.form_result['vic_hi_size']
        record.hex_hi_size = self.form_result['hex_hi_size']

        try:
            Session.add(record)
            Session.commit()
        except IntegrityError, e:
            Session.rollback()
            raise e

        if new_record:
            qty = self.form_result['quantity']
            need_numerical_indices = qty > 26

            for i in range(qty):
                # special logic for making a QC plate on F+/V+
                if record.plate_type.code == 'fvtitr' and i == qty-1:
                    name = '%s__QC' % record.name
                elif record.plate_type.code == 'scc':
                    cols, extra = divmod(qty, 8)
                    partial_cols = cols+1 if extra else cols
                    if i < (extra * partial_cols):
                        row, col = divmod(i, partial_cols)
                        col_str = str(col+1).zfill(2)
                        row_str = chr(ord('A')+row)
                    else:
                        row_diff, col = divmod(i-(extra*partial_cols), cols)
                        col_str = str(col+1).zfill(2)
                        row_str = chr(ord('A')+extra+row_diff)
                    name = '%s_%s%s' % (record.name, row_str, col_str)
                elif record.plate_type.code in ('mfgcc', 'scc'):
                    if not need_numerical_indices:
                        name = '%s_%s' % (record.name, chr(ord('A')+i))
                    else:
                        div, rem = divmod(i, 26)
                        name = '%s_%s%s' % (record.name, div+1, chr(ord('A')+rem))
                # fvtitr, two wells six col apart, allocated from top to bottom
                elif record.plate_type.code == 'fvtitr':
                    row, pos = divmod(i, 6)
                    row_chr = chr(ord('A')+row)
                    col1_chr = str(pos+1).zfill(2)
                    col2_chr = str(pos+7).zfill(2)
                    name = '%s_%s%s_%s%s' % (record.name, row_chr, col1_chr, row_chr, col2_chr)

                else:
                    name = "%s_%02d" % (record.name, i+1)
                plate = ManufacturingPlate(name=name,
                                           mfg_batch_id=record.id,
                                           dg_method=record.default_dg_method,
                                           thermal_cycler_id=record.thermal_cycler_id)

                # make last F+/V+ plate a QC plate
                if record.plate_type.code == 'fvtitr' and i == self.form_result['quantity']-1:
                    plate.qc_plate = True
                record.plates.append(plate)
            Session.commit()
    
    def __load_batch(self, id=None):
        if not id:
            return None
        
        batch = Session.query(ManufacturingPlateBatch).get(int(id))
        if not batch:
            return None
        
        return batch
    
    def __load_batch_into_formvars(self, batch):
        formvars = dict()
        formvars['name'] = batch.name
        formvars['plate_type'] = PlateTypeConverter.from_python(batch.plate_type_id)
        formvars['creation_date'] = batch.creation_date
        formvars['creator_id'] = batch.creator_id
        formvars['dg_method'] = batch.default_dg_method
        formvars['notes'] = batch.notes
        formvars['quantity'] = len(batch.plates)
        formvars['fam_hi_size'] = batch.fam_hi_size
        formvars['vic_hi_size'] = batch.vic_hi_size
        formvars['hex_hi_size'] = batch.hex_hi_size
        return formvars
    
    def _batch_edit_base(self, id=None):
        self.__setup_batch_fields()
        c.batch = self.__load_batch(id)
        if not c.batch:
            abort(404)

        c.title = "Edit Batch"
        c.submit_action = url(controller = 'product', action='batch_save', id=id)
        c.call_to_action = "Save Batch"
        c.record_exists = True

        bound_plates= [p for p in c.batch.plates if p.plate_id is not None]
        c.allow_delete = (len(bound_plates) == 0)

        return render('/product/batch/edit.html')
    
    def batch_edit(self, id=None):
        response = self._batch_edit_base(id)
        return h.render_bootstrap_form(response, defaults=self.__load_batch_into_formvars(c.batch))
    
    @restrict('POST')
    @validate(schema=PlateBatchUpdateForm(), form='_batch_edit_base', error_formatters=h.tw_bootstrap_error_formatters)
    def batch_save(self, id=None):
        batch = self.__load_batch(id)
        if not batch:
            abort(404)
        
        self.__update_batch_record(batch)
        session['flash'] = 'Batch updated.'
        session.save()
        return redirect(url(controller='product', action='batch_plates', id=id))
    
    @restrict('POST')
    def batch_delete(self, id=None):
        batch = self.__load_batch(id)
        if not batch:
            abort(404)
        
        # check for bound plates
        bound_plates = [p for p in batch.plates if p.plate_id is not None]
        if bound_plates:
            session['flash'] = "Cannot delete this batch; there are run plates bound to it."
            session['flash_class'] = 'error'
            session.save()
            return redirect(url(controller='product', action='batch_edit', id=id))
        else:
            try:
                for plate in batch.plates:
                    Session.delete(plate)
                batch.plates = []
                Session.delete(batch)
                Session.commit()
                session['flash'] = "Batch deleted."
                session.save()
            except Exception, e:
                logging.exception("Error from batch deletion:")
                session['flash'] = "Could not delete the batch from the database."
                session['flash_class'] = 'error'
                session.save()
                return redirect(url(controller='product', action='batch_edit', id=id))
            
            # redirect = Exception!  good to know-- don't put in try block...
            return redirect(url(controller='product', action='batch_list'))

    
    def __setup_batch_plate_fields(self):
        c.dg_method = dg_method_field()
        c.plate_type = plate_type_field()
        c.thermal_cyclers = fl.thermal_cycler_field()
    
    def __load_batch_plate(self, id=None):
        if id is None:
            return None
        
        plate = Session.query(ManufacturingPlate).get(int(id))
        return plate
    
    def __load_batch_plate_into_formvars(self, plate):
        formvars = dict()
        formvars['name'] = plate.name
        formvars['plate_type'] = PlateTypeConverter.from_python(plate.batch.plate_type_id)
        formvars['dg_method'] = plate.dg_method
        formvars['qc_plate'] = [True] if plate.qc_plate else []
        formvars['plate_notes'] = plate.plate_notes
        formvars['thermal_cycler_id'] = plate.thermal_cycler_id
        return formvars
    
    def __update_batch_plate_record(self, record):
        record.dg_method = self.form_result['dg_method']
        record.qc_plate = self.form_result['qc_plate'] and True or False
        record.plate_notes = self.form_result['plate_notes']
        record.thermal_cycler_id = self.form_result['thermal_cycler_id']
        Session.add(record)
        Session.commit()

    def _batch_editplate_base(self, id=None):
        self.__setup_batch_plate_fields()
        c.plate = self.__load_batch_plate(id)
        
        if not c.plate:
            abort(404)
        
        # TODO fix case where there is a validation problem on edit, as all fields clear
        response = render('/product/batch/editplate.html')
        return response
    
    def batch_editplate(self, id=None):
        response = self._batch_editplate_base(id)
        return h.render_bootstrap_form(response, defaults=self.__load_batch_plate_into_formvars(c.plate))
    
    @restrict('POST')
    @validate(schema=PlateUpdateForm(), form='_batch_editplate_base', error_formatters=h.tw_bootstrap_error_formatters)
    def batch_saveplate(self, id=None):
        plate = self.__load_batch_plate(id)
        if not plate:
            abort(404)
        
        self.__update_batch_plate_record(plate)
        session['flash'] = 'Plate updated.'
        session.save()
        return redirect(url(controller='product', action='batch_plates', id=plate.mfg_batch_id))
    
    def _batch_list_base(self):
        # TODO make a subroutine if used in multiple locations
        query = Session.query(ManufacturingPlateBatch).order_by('creation_date desc, name')
        c.paginator = paginate.Page(
            query,
            page=int(request.params.get('page', 1)),
            items_per_page = 15
        )

        c.pager_kwargs = {}
        c.plate_type_field = dg_plate_type_field()
        return render('/product/batch/list.html')

    @restrict('POST')
    @validate(schema=UnhookCSFVForm(), form='_batch_list_base')
    def batch_csfv_unhook(self):
        plate = self.__load_batch_plate(self.form_result['batch_plate_id'])
        plate.plate_id = None
        Session.commit()
        session['flash'] = 'CSFV QC plate discarded.'
        session.save()
        return redirect(url(controller='product', action='batch_plates', id=plate.mfg_batch_id))
    
    def batch_list(self):
        response = self._batch_list_base()
        return h.render_bootstrap_form(response)
    
    @validate(schema=BatchFilterForm(), form='_batch_list_base', post_only=False, on_get=True)
    def batch_filter(self):
        criteria = self.form_result['plate_type']
        consumable_methods = (ManufacturingPlateBatch.DG_METHOD_WEIDMANN_V5,
                              ManufacturingPlateBatch.DG_METHOD_THINXXS_V2A,
                              ManufacturingPlateBatch.DG_METHOD_THINXXS_V2B,
                              ManufacturingPlateBatch.DG_METHOD_THINXXS_V2C)
        if criteria == 'CS' or criteria == 'CC':
            query = query_plate_type_dg_method(plate_type_code='mfgcc')
        elif criteria == 'CO':
            query = query_plate_type_dg_method(plate_type_code='mfgco')
        elif criteria == 'CSFV':
            query = query_plate_type_dg_method(plate_type_code='fvtitr')
        elif criteria == 'QP':
            query = query_plate_type_dg_method(plate_type_code='scc')
        else:
            query = Session.query(ManufacturingPlateBatch)
        
        query = query.order_by('creation_date desc, mfg_plate_batch.name')

        c.paginator = paginate.Page(
            query,
            page=int(request.params.get('page', 1)),
            items_per_page = 15
        )

        c.pager_kwargs = {'plate_type': self.form_result['plate_type']}
        c.plate_type_field = dg_plate_type_field()
        response = render('/product/batch/list.html')
        # TODO: need to do from_python?
        return h.render_bootstrap_form(response, defaults=self.form_result)
    
    def batch_plates(self, id=None):
        if not id:
            abort(404)
        
        c.batch = self.__load_batch(id)
        if not c.batch:
            abort(404)
        
        query = Session.query(ManufacturingPlate).filter_by(mfg_batch_id=c.batch.id).order_by('name')
        c.plates = query.all()
        return render('/product/batch/plate_list.html')
    
    def _batch_plate_upload_base(self, id=None):
        c.plate = self.__load_batch_plate(id)
        if not c.plate:
            abort(404)
        
        return render('/product/batch/plate_upload.html')
    
    def batch_plate_upload(self, id=None):
        response = self._batch_plate_upload_base(id)
        override_plate_type = request.params.get('plate_type_code', None)
        plate_defaults = self.__load_batch_plate_into_formvars(c.plate)
        if override_plate_type:
            plate_type = Session.query(PlateType).filter_by(code=override_plate_type).first()
            if plate_type:
                # weird
                plate_defaults['plate_type'] = PlateTypeConverter.from_python(plate_type.id)
        return h.render_bootstrap_form(response, defaults=plate_defaults)
    
    @restrict('POST')
    @validate(schema=PlateUploadForm(), form='_batch_plate_upload_base', error_formatters=h.tw_bootstrap_error_formatters)
    def batch_plate_do_upload(self, id=None):
        batch_plate = self.__load_batch_plate(id)
        if not batch_plate:
            abort(404)
        box2 = self.form_result['box2']
        plate = self.form_result['plate']
        plate_type = batch_plate.batch.plate_type
        if plate_type.code == 'fvtitr' and len(plate.analyzed_wells) == 4:
            # if four wells, it's really a MFGCC (FVTITR FAM+/VIC+ should have 2)
            plate_type = Session.query(PlateType).filter_by(code='mfgcc').one()

        plateobj = save_plate_from_upload_request(request.POST['plate'], plate, box2, plate_type_obj=plate_type)

        # I want to put this in the form validator, but it's field dependent, so not right now
        if plate_type.code in ('mfgcc', 'bcc'):
            ok, message = validate_colorcomp_plate(plate)
            if not ok:
                response = self._batch_plate_upload_base(id)
                Session.rollback()
                return h.render_bootstrap_form(response, errors={'plate': message})
        
        Session.add(plateobj)
        if batch_plate.batch.plate_type.code == plate_type.code:
            batch_plate.plate = plateobj
        else:
            batch_plate.secondary_plate = plateobj

        batch_plate.qc_plate = self.form_result['qc_plate']
        batch_plate.plate_notes = self.form_result['plate_notes']
        Session.commit()

        session['flash'] = 'Plate linked.'
        session.save()
        return redirect(url(controller='metrics', action='per_plate', id=plateobj.id))

    def _batch_plate_name_base(self, id=None):
        c.plate = self.__load_batch_plate(id)
        c.box2s = fl.box2_field(empty='', prod_only=True, order_by='id', order_desc=True)
        if not c.plate:
            abort(404)
        c.action = url(controller='product', action='batch_plate_name_display', id=id)
        c.subtitle = 'Name Plate'
        c.call_to_action = 'Get Name'
        
        return render('/product/batch/plate_template.html')
    
    def batch_plate_name(self, id=None):
        return h.render_bootstrap_form(self._batch_plate_name_base(id), defaults=self.__load_batch_plate_into_formvars(c.plate))
    
    @validate(schema=TemplateDownloadForm(), form='_batch_plate_name_base', on_get=True, post_only=False, error_formatters=h.tw_bootstrap_error_formatters)
    def batch_plate_name_display(self, id):
        c.plate = self.__load_batch_plate(id)
        
        if not c.plate:
            abort(404)
        
        if self.form_result['qc_plate']:
            c.plate.qc_plate = self.form_result['qc_plate']
            Session.commit()

        if c.plate.qc_plate:
            c.name = "QC_%s" % c.plate.name
        else:
            box2 = Session.query(Box2).get(self.form_result['box2_id'])
            if not box2:
                abort(404)
            c.name = "%s_%s" % (box2.name.split(' ')[-1], c.plate.name)
        return render('/product/batch/plate_name_display.html')
    
    def _batch_plate_template_base(self, id=None):
        c.plate = self.__load_batch_plate(id)
        c.box2s = fl.box2_field(empty='', prod_only=True)
        if not c.plate:
            abort(404)
        c.action = url(controller='product', action='batch_plate_template_download', id=id)
        c.subtitle = 'Download QLT'
        c.call_to_action = 'Download Template'
        
        return render('/product/batch/plate_template.html')

    def batch_plate_template(self, id=None):
        return h.render_bootstrap_form(self._batch_plate_template_base(id), defaults=self.__load_batch_plate_into_formvars(c.plate))
        
    @validate(schema=TemplateDownloadForm(), form='_batch_plate_template_base', on_get=True, post_only=False, error_formatters=h.tw_bootstrap_error_formatters)
    def batch_plate_template_download(self, id=None):
        plate = self.__load_batch_plate(id)
        box2 = Session.query(Box2).get(self.form_result['box2_id'])
        if not plate or not box2:
            abort(404)
            
        code = plate.batch.plate_type.code

        if self.form_result['qc_plate']:
            plate.qc_plate = self.form_result['qc_plate']
            Session.commit()

        # TODO FIXFIX or incorporate into model
        if plate.qc_plate:
            serial = 'QC'
        else:
            serial = box2.name.split(' ')[-1]
        # only mfgco supported right now
        if code == 'mfgco':
            qlt_file = "%s/carryover.qlt" % config['qlb.setup_template_store']
        elif code == 'fvtitr':
            qlt_file = "%s/fvbatch_QC.qlt" % config['qlb.setup_template_store']
        else:
            abort(404)
        
        response.headers['Content-Type'] = 'application/quantalife-template'
        h.set_download_response_header(request, response, "%s_%s.qlt" % (serial, plate.name))
        response.headers['Pragma'] = 'no-cache'
        response.headers['Cache-Control'] = 'no-cache'
        return forward(FileApp(qlt_file, response.headerlist))

    def _logfile_base(self):
        return render("/product/logfile/upload.html")


    def logfile(self):
        response = self._logfile_base()
        return h.render_bootstrap_form(response)

    @validate(schema=LogfileUploadForm(), form='_logfile_base', error_formatters=h.tw_bootstrap_error_formatters)
    def logfile_process(self):
        c.file_contents = self.form_result['upload'].strip()
        return render("/product/logfile/results.html")

    def _algorithms_base(self):
        storage = QSAlgorithmSource(config)
        existing_folders = [tup[0] for tup in Session.query(ReprocessConfig.original_folder).all()]
        new_folders = [folder for folder in storage.algorithm_folder_iter() if folder not in existing_folders]

        c.folder_opts = {'value': '',
                         'options': [(fld, fld.split('/')[0]) for fld in sorted(new_folders)]}
        return render('/product/algorithms/register.html')

    def algorithms(self):
        response = self._algorithms_base()
        return h.render_bootstrap_form(response)

    @validate(schema=AlgorithmRegisterForm(), form='_algorithms_base')
    def register_algorithm(self):
        storage = QSAlgorithmSource(config)
        existing_folders = [tup[0] for tup in Session.query(ReprocessConfig.original_folder).all()]

        errors = dict()
        src_dir = self.form_result['src_dir']
        if src_dir in existing_folders:
            errors['src_dir'] = 'This algorithm has already been registered.'

        elif not storage.source_path_exists(src_dir):
            errors['src_dir'] = 'This algorithm is not accessible in the file system.'

        if self.form_result['peak_detection_version'] == (0,0):
            # this is arbitrary
            peak_detection_version = (0, QUANTASOFT_DIR_VERSION_RE.search(src_dir).group(1).split('_')[-1])
        else:
            peak_detection_version = self.form_result['peak_detection_version']

        if self.form_result['peak_quantitation_version'] == (0,0):
            peak_quantitation_version = (0, QUANTASOFT_DIR_VERSION_RE.search(src_dir).group(1).split('_')[-1])
        else:
            peak_quantitation_version = self.form_result['peak_quantitation_version']

        if errors:
            resp = self._algorithms_base()
            defaults = AlgorithmRegisterForm.from_python(self.form_result)
            return h.render_bootstrap_form(resp,
                defaults=defaults,
                errors=errors,
                error_formatters=h.tw_bootstrap_error_formatters)

        try:
            rp = ReprocessConfig(name=src_dir.split(os.path.sep)[0],
                                 code=self.form_result['code'],
                                 peak_detection_major=peak_detection_version[0],
                                 peak_detection_minor=peak_detection_version[1],
                                 peak_quant_major=peak_quantitation_version[0],
                                 peak_quant_minor=peak_quantitation_version[1],
                                 trigger_fixed_width=100,
                                 active=True,
                                 cluster_mode=ReprocessConfig.CLUSTER_MODE_CLUSTER,
                                 original_folder=src_dir)

            storage.add_reprocessor(src_dir, self.form_result['code'])
            Session.add(rp)
            Session.commit()
            session['flash'] = 'New algorithm reprocessor created.'
            session.save()
            return redirect(url(controller='product', action='algorithms'))

        except shutil.Error:
            session['flash'] = 'Could not copy source algorithm to destination.'
            session['flash_class'] = 'error'
            session.save()
            return redirect(url(controller='product', action='algorithms'))
        except IOError:
            session['flash'] = "Could not access the algorithm's file system."
            session['flash_class'] = 'error'
            session.save()
            return redirect(url(controller='product', action='algorithms'))

    def _algcommand_base(self):
        ags = Session.query(AnalysisGroup).filter_by(active=True).order_by(AnalysisGroup.name).all()
        rps = Session.query(ReprocessConfig).filter_by(active=True).order_by(ReprocessConfig.name).all()

        c.analysis_groups = {'value': '',
                             'options': [(ag.id, ag.name) for ag in ags]}
        c.reprocess_configs = {'value': '',
                               'options': [(rp.id, rp.name) for rp in rps]}

        return render('/product/algorithms/select.html')

    @help_at('datasets/reprocess.html')
    def algcommand(self, *args, **kwargs):
        response = self._algcommand_base()
        return h.render_bootstrap_form(response)

    @validate(schema=AlgorithmCommandForm(), form='_algcommand_base')
    def get_algcommand(self):
        c.ag = Session.query(AnalysisGroup).get(self.form_result['analysis_group_id'])
        c.rp = Session.query(ReprocessConfig).get(self.form_result['reprocess_config_id'])

        return render('/product/algorithms/command.html')

    #@validate(schema=AlgorithmRegisterForm(), form='_algorithms_base')
    def run_algcommand(self):
        from qtools.components.manager import get_manager_from_pylonsapp_context
        from qtools.constants.job import *
    
        #c.ag = Session.query(AnalysisGroup).get(self.form_result['analysis_group_id'])
        #c.rp = Session.query(ReprocessConfig).get(self.form_result['reprocess_config_id']) 

        ## get requested ids for command...
        c.ag = Session.query(AnalysisGroup).get(request.params['analysis_group_id'])
        c.rp = Session.query(ReprocessConfig).get(request.params['reprocess_config_id']) 

        ## write new command to DB some how...
        message = JSONMessage(analysis_group_id=c.ag.id,reprocess_config_id=c.rp.id)

        cm = get_manager_from_pylonsapp_context()
        job_queue = cm.jobqueue()

        #check job is not yet in que (active or inprogress
        remaining = job_queue.remaining(job_type=JOB_ID_REPROCESS_QLTESTER)
        in_progress = job_queue.in_progress(job_type=JOB_ID_REPROCESS_QLTESTER)

        remaining_status  = check_job_exists(remaining, c.ag.id, c.rp.id )
        in_prgress_status = check_job_exists(in_progress, c.ag.id, c.rp.id )

        if ( remaining_status or in_prgress_status ):
            c.reprocess_launch_success = 'Unsuccessful'
            c.reprocess_launch_message = 'requested repocessing already in que'
        else:
            job = job_queue.add(JOB_ID_REPROCESS_QLTESTER, message )
            message = getattr( job, 'result_message' )
            c.reprocess_launch_success = 'Successful'
            c.reprocess_launch_message = message

        ## do we want to recored this ide somewhere?
        ## possibly with the repocess group?

        ## main line should return here..
        ## parent should go here...
        return( render('/product/algorithms/run_command.html') )

    def reprocess(self):
        return render('/product/algorithms/index.html')

def check_job_exists( job_list, analysis_group_id, reprocess_config_id):
        """
         returns 1 if job exists, else 0
        """
        for job in job_list:
            struct  = JSONMessage.unserialize(job.input_message)

            if( int( struct.analysis_group_id ) == int( analysis_group_id ) and \
                int( struct.reprocess_config_id )   == int( reprocess_config_id ) ):
                    return 1
        return 0

