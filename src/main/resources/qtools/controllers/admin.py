import logging, itertools, operator, os, glob
from collections import defaultdict

from pylons import request, response, session, tmpl_context as c, url, config
from pylons.controllers.util import abort, redirect
from pylons.decorators import validate
from pylons.decorators.rest import restrict

from qtools.lib.base import BaseController, render
from qtools.lib.storage import QLBPlateSource, QLStorageSource
from qtools.model import Session, Box2, Box2Log, Box2Circuit, DRStatusLog, DRFixLog, Person
from qtools.model import QLBPlate, Plate
from qtools.model.util import DocModelView
import qtools.lib.fields as fl
import qtools.lib.helpers as h
from qtools.lib.validators import OneOfInt, IntKeyValidator
from qtools.lib.wowo import wowo

from sqlalchemy import or_, and_, not_, exc, func
from sqlalchemy.orm import joinedload_all
from datetime import datetime, date, time, timedelta
import formencode
import re


log = logging.getLogger(__name__)

box2log_mv = DocModelView(Box2Log,
                          exclude_columns=['time_effective'],
                          include_columns=['circuit'],
                          column_label_transforms={'circuit': lambda k: 'Circuit'},
                          global_value_transform=lambda v: '' if v is None else v,
                          column_value_transforms={'circuit': lambda v: v.name if v else '',
                                                   'skin_on': lambda v: {None: 'No', False: 'No', True: 'Yes'}[v],
                                                   'door_type': lambda v: dict(fl.dr_door_type_field(v)['options']).get(v,'')})

class ReaderUpdateForm(formencode.Schema):
    allow_extra_fields = True
    filter_extra_fields = True

    box2_id = IntKeyValidator(Box2, 'id', not_empty=True)
    box2_circuit_id = IntKeyValidator(Box2Circuit, 'id', not_empty=False, if_missing=None)
    detector = formencode.validators.String(not_empty=False, if_missing=None)
    singulator_type = formencode.validators.String(not_empty=False, if_missing=None)
    singulator_material = formencode.validators.String(not_empty=False, if_missing=None)
    capillary = formencode.validators.String(not_empty=False, if_missing=None)
    tip_lot_number = formencode.validators.String(not_empty=False, if_missing=None)
    tip_supplier = formencode.validators.String(not_empty=False, if_missing=None)
    tip_material = formencode.validators.String(not_empty=False, if_missing=None)
    tip_size = formencode.validators.String(not_empty=False, if_missing=None)
    skin_on = formencode.validators.Bool(not_empty=False, if_missing=None)
    routine_version = formencode.validators.String(not_empty=False, if_missing=None)
    air_filter_location = formencode.validators.String(not_empty=False, if_missing=None)
    peristaltic_tubing = formencode.validators.String(not_empty=False, if_missing=None)
    bottle_trough_hold_in_status = formencode.validators.String(not_empty=False, if_missing=None)
    plate_sensor_status = formencode.validators.String(not_empty=False, if_missing=None)
    lid_sensor_status = formencode.validators.String(not_empty=False, if_missing=None)
    biochem_configuration = formencode.validators.String(not_empty=False, if_missing=None)
    quantasoft_version = formencode.validators.String(not_empty=False, if_missing=None)
    waste_bottle_empty = formencode.validators.String(not_empty=False, if_missing=None)
    carrier_bottle_empty = formencode.validators.String(not_empty=False, if_missing=None)
    waste_bottle_full = formencode.validators.String(not_empty=False, if_missing=None)
    carrier_bottle_full = formencode.validators.String(not_empty=False, if_missing=None)
    fluidics_circuit = formencode.validators.String(not_empty=False, if_missing=None)
    pickup_line = formencode.validators.String(not_empty=False, if_missing=None)
    reservoir_line = formencode.validators.String(not_empty=False, if_missing=None)
    waste_downspout  = formencode.validators.String(not_empty=False, if_missing=None)
    door_type = formencode.validators.String(not_empty=False, if_missing=None)
    firmware_mcu9 = formencode.validators.String(not_empty=False, if_missing=None)
    firmware_dll130 = formencode.validators.String(not_empty=False, if_missing=None)
    firmware_fpga16 = formencode.validators.String(not_empty=False, if_missing=None)
    firmware_fluidics = formencode.validators.String(not_empty=False, if_missing=None)
    firmware_motor = formencode.validators.String(not_empty=False, if_missing=None)
    day_effective = formencode.validators.DateConverter(not_empty=False, if_missing=None)
    time_effective = formencode.validators.TimeConverter(prefer_ampm=True, use_seconds=False, use_datetime=True, if_missing=None)

class SaveCircuitForm(formencode.Schema):
    allow_extra_fields = True
    filter_extra_fields = True

    log_id = IntKeyValidator(Box2Log, 'id', not_empty=True)
    name = formencode.validators.String(not_empty=True)

class DRStatusForm(formencode.Schema):
    allow_extra_fields = True
    filter_extra_fields = True

    box2_id = IntKeyValidator(Box2, 'id', not_empty=True)
    status = OneOfInt((0,1,2), not_empty=True)
    status_comment = formencode.validators.MaxLength(140, not_empty=False, if_missing=None)
    reporter_id = IntKeyValidator(Person, 'id', not_empty=True)

class DRFixForm(formencode.Schema):
    allow_extra_fields = True
    filter_extra_fields = True

    box2_id = IntKeyValidator(Box2, 'id', not_empty=True)
    problem = formencode.validators.String(not_empty=False, if_missing=None)
    root_cause = formencode.validators.String(not_empty=False, if_missing=None)
    fix = formencode.validators.String(not_empty=False, if_missing=None)
    reporter_id = IntKeyValidator(Person, 'id', not_empty=True)

class RegisterReaderForm(formencode.Schema):
    allow_extra_fields = True
    filter_extra_fields = True

    serial = formencode.validators.String(not_empty=True)
    reader_type = OneOfInt((Box2.READER_TYPE_WHOLE, Box2.READER_TYPE_FLUIDICS_MODULE,  
                            Box2.READER_TYPE_DETECTOR_MODULE), not_empty=True)

class RegisterLabReaderform(formencode.Schema):
    allow_extra_fields = True
    filter_extra_fields = True

    path = formencode.validators.Regex(r'[\W\s\-]+', not_empty=True)

class AdminController(BaseController):

    def __inhouse_readers(self, admin=True):
        if wowo('contractor'):
            return []
        # redmine 875 -- fix this with single flag
        box2_query = Session.query(Box2).filter(or_(Box2.name.like('Alpha 0%'),
                                                    Box2.name.like('Beta 0%'),
                                                    Box2.name.like('Beta 1%'),
                                                    Box2.name.like('ENG%'),
                                                    Box2.name.like('GXD%'),
                                                    Box2.name.like('RevC %'))).order_by(Box2.name)
       
        c.admin = admin != 'False' 
        if not c.admin:
            box2_query = box2_query.filter_by(active=True)
        
        box2s = box2_query.all()
        return box2s
    
    def __prod_readers(self):
        box2_query = Session.query(Box2).filter(Box2.reader_query()).order_by('name desc')
        box2s = box2_query.all()
        return box2s

    def __fluidics_modules(self):
        fm_query = Session.query(Box2).filter(Box2.fluidics_module_query()).order_by('name desc')
        box2s = fm_query.all()
        return box2s

    def __detector_modules(self):
        dm_query = Session.query(Box2).filter(Box2.detector_module_query()).order_by('name desc')
        box2s = dm_query.all()
        return box2s   
 
    def register(self, id):
        if id not in ('reader', 'module', 'detector'):
            abort(404)
        else:
            c.path_id = id
            if id == 'reader':
                c.reader_type = Box2.READER_TYPE_WHOLE
                c.reader_title = 'Reader'
                c.reader_help = '10640'
            elif id == 'module':
                c.reader_type = Box2.READER_TYPE_FLUIDICS_MODULE
                c.reader_title = 'Fluidics Module'
                c.reader_help = '4560345'
            elif id == 'detector':
                c.reader_type = Box2.READER_TYPE_DETECTOR_MODULE
                c.reader_title = 'Detector Module'
                c.reader_help = ''
        c.form = h.LiteralForm()
        c.admin = True
        return render('/admin/register.html')
    
    @restrict('POST')
    @validate(schema=RegisterReaderForm, form='register')
    def create(self, id):
        """
        KIND OF UNSAFE.  Creates/registers a reader.
        """
        serial = self.form_result['serial']
        reader_type = self.form_result['reader_type']
        if reader_type == Box2.READER_TYPE_WHOLE:
            ## check name is in correct format...
            if not re.search( '^771BR\d{4}$', serial ):
                session['flash'] = 'New Reader name must follow "771BR####" convention'
                session['flash_class'] = 'error'
                session.save()
                return redirect(url(controller='admin', action='register', id=id))
            elif ( len( serial ) > 15 ):
                session['flash'] = 'Reader name can not contain more then 15 characters'
                session['flash_class'] = 'error'
                session.save()
                return redirect(url(controller='admin', action='register', id=id))

            code = 'p%s' % serial
        elif reader_type == Box2.READER_TYPE_FLUIDICS_MODULE:
            serial = serial.upper()

            if ( len( serial ) > 15 ):
                session['flash'] = 'Fluidics name can not contain more then 15 characters'
                session['flash_class'] = 'error'
                session.save()
                return redirect(url(controller='admin', action='register', id=id))

            code = 'f%s' % serial
        elif reader_type == Box2.READER_TYPE_DETECTOR_MODULE:
            ## check to make sure someone isn't acidently adding a DR
            if  re.search( '^771BR\d*', serial ):
                session['flash'] = 'New Detector module names do not contain "771BR" '
                session['flash_class'] = 'error'
                session.save()
                return redirect(url(controller='admin', action='register', id=id) )
            elif ( len( serial ) > 15 ):
                session['flash'] = 'Detector name can not contain more then 15 characters'
                session['flash_class'] = 'error'
                session.save()
                return redirect(url(controller='admin', action='register', id=id))

            serial = serial.upper()
            code = 'd%s' % serial

        # check and catch if reader already exists
        box2 = Session.query(Box2).filter_by(code=code).first()
        if box2:
            session['flash'] = 'Unit %s is already registered.' % self.form_result['serial']
            session['flash_class'] = 'error'
            session.save()
            return redirect(url(controller='admin', action='register', id=id))
        
        #If not exists create one instead
        if reader_type == Box2.READER_TYPE_WHOLE:
            src_dir = "DR %s" % serial
            reader = Box2(name=u'Prod %s' % serial, code=code, src_dir=src_dir, \
                          reader_type = Box2.READER_TYPE_WHOLE, \
                          fileroot=config['qlb.fileroot.register_fileroot'], active=True)
        elif reader_type == Box2.READER_TYPE_FLUIDICS_MODULE:
            src_dir="FM %s" % serial
            reader = Box2(name=u'QL-FSA %s' % serial, code=code, src_dir=src_dir, \
                          reader_type = Box2.READER_TYPE_FLUIDICS_MODULE, \
                          fileroot=config['qlb.fileroot.register_fileroot'], active=True)
        elif reader_type == Box2.READER_TYPE_DETECTOR_MODULE:
            src_dir="DM %s" % serial
            reader = Box2(name=u'DET %s' % serial, code=code, src_dir=src_dir, \
                          reader_type = Box2.READER_TYPE_DETECTOR_MODULE, \
                          fileroot=config['qlb.fileroot.register_fileroot'], active=True)       

 
        Session.add(reader)
        reader.active = True

        local_plate_source = QLBPlateSource(config, [reader])
        dirname = local_plate_source.real_path(reader.fileroot, src_dir)
        try:
            os.mkdir(dirname)
            Session.commit()
            session['flash'] = 'Unit %s registered.' % serial
            session.save()
        except Exception, e:
            session['flash'] = 'Could not create a directory for unit %s' % serial
            session['flash_class'] = 'error'
            session.save()
            Session.rollback()
            return redirect(url(controller='admin', action='register', id=id))

        return_action = 'prod'
        if reader_type == Box2.READER_TYPE_FLUIDICS_MODULE:
            return_action = 'modules'
        elif reader_type == Box2.READER_TYPE_DETECTOR_MODULE:
            return_action = 'detectors'        

        return redirect(url(controller='admin', action=return_action))


    def readers(self, admin=True):
        box2s = self.__inhouse_readers(admin)
        
        # hack
        alphas = [b for b in box2s if b.name.startswith('Alpha')]
        betas = [b for b in box2s if b.name.startswith('Beta')]
        engs = [b for b in box2s if b.name.startswith('ENG') or b.name.startswith('GXD')]
        prods  = [b for b in box2s if b.code.startswith('p') ]
        #prods = [b for b in box2s if b.name.startswith('Prod') or b.name.startswith('Qtools')]
        revc = [b for b in box2s if b.name.startswith('RevC')]
        c.alphas = itertools.groupby(enumerate(alphas), lambda tup: tup[0]/6)
        c.betas = itertools.groupby(enumerate(betas), lambda tup: tup[0]/6)
        c.engs = itertools.groupby(enumerate(engs), lambda tup: tup[0]/6)
        c.prods = itertools.groupby(enumerate(prods), lambda tup: tup[0]/6)
        c.revc = itertools.groupby(enumerate(revc), lambda tup: tup[0]/6)
        c.admin = admin
        return render('/admin/readers.html')

    # TODO: once auth is working, limit this guy
    def _register_lab_base(self):
        """
        This works in reverse of create().  Instead, require that the user
        create a folder on HyperV, and then only show the new folders that
        have not yet been registered.
        """
        LAB_FILEROOT = 'main'

        file_source = QLStorageSource(config)
        dir_root = file_source.real_path(LAB_FILEROOT,'')
        rel_dirs = [os.path.relpath(path, dir_root) for path in glob.glob('%s/DR*' % dir_root)]

        # for now, assume that a lab reader will be at the top level
        lab_drs = [record[0].split('/')[0] for record in Session.query(Box2.src_dir).all()]
        new_dirs = set(rel_dirs) - set(lab_drs)

        # what should remain are new directories and misnamed directories
        c.reader_field = {'value': '',
                          'options': [(d, d[3:]) for d in new_dirs]}

        return render('/admin/register_lab.html')

    def register_lab(self):
        response = self._register_lab_base()
        return h.render_bootstrap_form(response)

    @validate(schema=RegisterLabReaderform(), form='_register_lab_base')
    def do_register_lab_reader(self):
        LAB_FILEROOT = 'main'
        storage = QLStorageSource(config)
        path = self.form_result['path']
        name = self.form_result['path'][3:] # sans DR
        new_reader_path = storage.real_path(LAB_FILEROOT, self.form_result['path'])

        new_reader = Box2(name=name,
                          code=name,
                          src_dir=path,
                          reader_type=Box2.READER_TYPE_WHOLE,
                          active=True,
                          fileroot=LAB_FILEROOT)
        Session.add(new_reader)
        Session.commit()
        session['flash'] = 'Reader %s added.' % name
        session.save()
        return redirect(url(controller='admin', action='register_lab'))

    def colorcomp(self, admin=True):
        box2 = self.__inhouse_readers(admin)
        box2_ids = [b.id for b in box2]

        inner_stmt = Session.query(func.min(QLBPlate.host_datetime).label('first_date'),
                                   QLBPlate.color_compensation_matrix_11,
                                   QLBPlate.color_compensation_matrix_12,
                                   QLBPlate.color_compensation_matrix_21,
                                   QLBPlate.color_compensation_matrix_22,
                                   Box2.id.label('box2_id'),
                                   Box2.name.label('box2_name'))\
                            .join(Plate, Box2)\
                            .filter(Box2.id.in_(box2_ids))\
                            .filter(not_(and_(QLBPlate.color_compensation_matrix_11 == 1,
                                              QLBPlate.color_compensation_matrix_12 == 0,
                                              QLBPlate.color_compensation_matrix_21 == 0,
                                              QLBPlate.color_compensation_matrix_22 == 1)))\
                            .group_by(Box2.id,
                                      QLBPlate.color_compensation_matrix_11,
                                      QLBPlate.color_compensation_matrix_12,
                                      QLBPlate.color_compensation_matrix_21,
                                      QLBPlate.color_compensation_matrix_22)\
                            .order_by(Box2.name, 'first_date')
        inner_records = inner_stmt.all()

        now = datetime.now()
        last_times = defaultdict(lambda: [datetime(2010, 1, 1, 0, 0, 0), (1, 0, 0, 1), 0])
        for dt, cc11, cc12, cc21, cc22, bid, bname in inner_records:
            if dt > last_times[bname][0]:
                last_times[bname][0] = dt
                last_times[bname][1] = (cc11, cc12, cc21, cc22)
                last_times[bname][2] = 2
                if now - dt > timedelta(45):
                    last_times[bname][2] = 1
                if now - dt > timedelta(90):
                    last_times[bname][2] = 0


        c.last_colorcomps = sorted(last_times.items(), key=operator.itemgetter(0))
        return render('/admin/colorcomps.html')

    
    def prod(self, admin=True):
        box2s = self.__prod_readers()
        # todo start adding
        c.admin = admin
        c.readers = box2s
        c.active_type = 'readers'
        c.reader_title = 'Reader'
        return render('/admin/prod_table.html')

    def modules(self, admin=True):
        modules = self.__fluidics_modules()
        c.admin = admin
        c.readers = modules
        c.active_type = 'modules'
        c.reader_title = 'Fluidics Module'
        return render('/admin/prod_table.html')
   
    def detectors(self, admin=True):
        detectors = self.__detector_modules()
        c.admin = admin
        c.readers = detectors
        c.active_type = 'detectors'
        c.reader_title = 'Detector Module'
        return render('/admin/prod_table.html')
 
    def reader_status_table(self, admin=True):
        box2s = self.__inhouse_readers(admin)
        
        c.readers = box2s
        c.admin = admin
        return render('/admin/readers_table.html')
    
    def reader(self, id=None):
        box2 = self.__setup_box2_context_by_code(id)
        
        c.admin = True
        circuit_id = request.params.get('circuit_id', None)
        circuit_log = None
        if circuit_id:
            circuit = Session.query(Box2Circuit).get(int(circuit_id))
            circuit_log = Session.query(Box2Log).get(circuit.log_template_id)
        logs = Session.query(Box2Log).filter_by(box2_id=box2.id).order_by('time_effective desc').all()
        if len(logs) > 0:
            last_log = logs[0]
        else:
            last_log = None
        
        c.dr = box2
        c.circuits = Session.query(Box2Circuit).order_by('name').all()

        value_dict = {'day_effective': date.today().strftime('%m/%d/%Y'),
                      'time_effective': datetime.now().time().strftime('%I:%M%p')}
        if last_log:
            value_dict.update({'box2_id': box2.id,
                         'box2_circuit_id': None,
                         'detector': last_log.detector,
                         'singulator_type': last_log.singulator_type,
                         'singulator_material': last_log.singulator_material,
                         'capillary': last_log.capillary,
                         'tip_lot_number': last_log.tip_lot_number,
                         'tip_supplier': last_log.tip_supplier,
                         'tip_material': last_log.tip_material,
                         'tip_size': last_log.tip_size,
                         'routine_version': last_log.routine_version,
                         'door_type': str(last_log.door_type),
                         'skin_on': last_log.skin_on,
                         'air_filter_location': last_log.air_filter_location,
                         'peristaltic_tubing': last_log.peristaltic_tubing,
                         'bottle_trough_hold_in_status': str(last_log.bottle_trough_hold_in_status),
                         'plate_sensor_status': str(last_log.plate_sensor_status),
                         'lid_sensor_status': str(last_log.lid_sensor_status),
                         'biochem_configuration': last_log.biochem_configuration,
                         'quantasoft_version': last_log.quantasoft_version,
                         'waste_bottle_empty': last_log.waste_bottle_empty,
                         'carrier_bottle_empty': last_log.carrier_bottle_empty,
                         'waste_bottle_full': last_log.waste_bottle_full,
                         'carrier_bottle_full': last_log.carrier_bottle_full,
                         'fluidics_circuit': last_log.fluidics_circuit,
                         'pickup_line': last_log.pickup_line,
                         'reservoir_line': last_log.reservoir_line,
                         'waste_downspout': last_log.waste_downspout,
                         'firmware_mcu9': last_log.firmware_mcu9,
                         'firmware_dll130': last_log.firmware_dll130,
                         'firmware_fpga16': last_log.firmware_fpga16,
                         'firmware_fluidics': last_log.firmware_fluidics,
                         'firmware_motor': last_log.firmware_motor})
        if circuit_log:
            value_dict.update({'box2_circuit_id': circuit_id,
                               'singulator_type': circuit_log.singulator_type,
                               'singulator_material': circuit_log.singulator_material,
                               'capillary': circuit_log.capillary,
                               'door_type': str(circuit_log.door_type),
                               'air_filter_location': circuit_log.air_filter_location,
                               'peristaltic_tubing': circuit_log.peristaltic_tubing,
                               'biochem_configuration': circuit_log.biochem_configuration,
                               'fluidics_circuit': circuit_log.fluidics_circuit,
                               'pickup_line': circuit_log.pickup_line,
                               'reservoir_line': circuit_log.reservoir_line,
                               'waste_downspout': circuit_log.waste_downspout})
            session['flash'] = 'Circuit %s selected.  Click "Update %s" to save these settings.' % (circuit.name, box2.name)
            session.save()
        

        skin_on = fl.checkbox_field(checked=value_dict.get('skin_on', u'1'))
        door_type = fl.dr_door_type_field(selected=value_dict.get('door_type', None))
        bottle_trough_field = fl.dr_installed_field(value_dict.get('bottle_trough_hold_in_status', None))
        plate_sensor_field = fl.dr_sensor_field(value_dict.get('plate_sensor_status', None))
        lid_sensor_field = fl.dr_sensor_field(value_dict.get('lid_sensor_status', None))
        
        # checkboxes suck
        value_dict['skin_on'] = skin_on['value']
        option_dict = {'skin_on': skin_on['options'],
                       'door_type': door_type['options'],
                       'bottle_trough_hold_in_status': bottle_trough_field['options'],
                       'plate_sensor_status': plate_sensor_field['options'],
                       'lid_sensor_status': lid_sensor_field['options']}
        
        c.form = h.LiteralForm(value = value_dict, option = option_dict)
        c.circuit_id = circuit_id or ''
        return render('/admin/reader.html')
    
    @restrict('POST')
    @validate(schema=ReaderUpdateForm(), form='reader')
    def update_reader(self):
        log_entry = self.__make_box2_log_entry(self.form_result)
        Session.add(log_entry)
        Session.commit()

        box2 = Session.query(Box2).get(self.form_result['box2_id'])
        session['flash'] = 'Configuration for %s updated.' % box2.name
        session.save()

        redirect(url(controller='admin', action='reader_history', id=box2.code))
    
    @restrict('POST')
    @validate(schema=ReaderUpdateForm(), form='reader')
    def update_reader_circuit(self):
        log_entry = self.__make_box2_log_entry(self.form_result)
        Session.add(log_entry)
        Session.commit()

        redirect(url(controller='admin', action='circuit', id=log_entry.id))
    
    def circuit(self, id=None):
        if not id:
            abort(404)
        
        log = Session.query(Box2Log).get(int(id))
        if not log:
            abort(404)
        
        c.admin = True
        c.dr = log.box2
        c.log = log
        c.form = h.LiteralForm()
        
        return render('/admin/circuit.html')

    @restrict('POST')
    @validate(schema=SaveCircuitForm(), form='circuit')
    def save_circuit(self):
        log = Session.query(Box2Log).get(self.form_result['log_id'])
        if not log:
            abort(404)
        try:
            circ = Box2Circuit(name=self.form_result['name'],
                               log_template_id=self.form_result['log_id'])
            Session.add(circ)
            Session.commit()
            log.box2_circuit_id = circ.id
            Session.commit()
            session['flash'] = 'Configuration for %s updated and circuit "%s" created.' % (log.box2.name, circ.name)
            session.save()
            redirect(url(controller='admin', action='reader_history', id=log.box2.code))
        except exc.IntegrityError, e:
            Session.rollback()
            session['flash'] = 'There is already a circuit by that name.'
            session['flash_class'] = 'error'
            session.save()
            redirect(url(controller='admin', action='circuit', id=log.id))
    
    def reader_history(self, id=None, admin=True):
        box2 = self.__setup_box2_context_by_code(id)
        c.admin = admin != 'False'
        logs = Session.query(Box2Log).filter_by(box2_id=box2.id)\
                                     .order_by('time_effective desc')\
                                     .options(joinedload_all(Box2Log.circuit))\
                                     .all()
        
        statuses = Session.query(DRStatusLog).filter_by(box2_id=box2.id)\
                                             .order_by('time_effective desc')\
                                             .options(joinedload_all(DRStatusLog.reporter))\
                                             .all()
        
        fixes = Session.query(DRFixLog).filter_by(box2_id=box2.id)\
                                       .order_by('time_effective desc')\
                                       .all()
        
        log_pairs = [(logs[i].time_effective, [logs[i],(logs[i+1] if i < len(logs)-1 else None)]) for i in range(len(logs))]
        for pair in log_pairs:
            pair[1].append((sorted(box2log_mv.labeleditems(pair[1][0]).items()),
                            sorted(box2log_mv.labeleditems(pair[1][1]).items())))
        status_pairs = [(status.time_effective, status) for status in statuses]
        fix_pairs = [(fix.time_effective, fix) for fix in fixes]
        changes = log_pairs + status_pairs + fix_pairs
        c.changes = sorted(changes, key=operator.itemgetter(0))
        c.changes.reverse()
        
        return render('/admin/reader_history.html')             
    
    
    def reader_status(self, id=None):
        box2 = self.__setup_box2_context_by_code(id)
        c.admin = True
        
        reporter_field = fl.person_field()
        c.form = h.LiteralForm(
            value = {'status': box2.status},
            option = {
                'status': [(0, 'Restricted/Off-line'),
                           (1, 'Caution'),
                           (2, 'OK')],
                'reporter_id': [('','--')] + reporter_field['options']
            }
        )

        return render('/admin/reader_status.html')
    
    @restrict('POST')
    @validate(schema=DRStatusForm(), form='reader_status')
    def update_reader_status(self):
        box2_id = self.form_result['box2_id']
        box = Session.query(Box2).get(box2_id)
        if not box:
            abort(404)
        
        box.status = self.form_result['status']
        box.status_comment = self.form_result['status_comment']

        log = DRStatusLog(box2_id=box.id,
                          status=box.status,
                          status_comment=box.status_comment,
                          time_effective=datetime.now(),
                          reporter_id=self.form_result['reporter_id'])
        Session.add(log)
        Session.commit()

        session['flash'] = 'Updated status for %s.' % box.name
        session.save()

        redirect(url(controller='admin', action='reader_history', id=box.code))

    def reader_fix(self, id=None):
        box2 = self.__setup_box2_context_by_code(id)
        c.admin = True
        
        reporter_field = fl.person_field()
        c.form = h.LiteralForm(
            option = {
                'reporter_id': [('','--')] + reporter_field['options']
            }
        )

        return render('/admin/reader_fix.html')
    
    @restrict('POST')
    @validate(schema=DRFixForm(), form='reader_fix')
    def add_reader_fix(self):
        box2_id = self.form_result['box2_id']
        box = Session.query(Box2).get(box2_id)
        if not box:
            abort(404)

        log = DRFixLog(box2_id=box.id,
                       problem=self.form_result['problem'],
                       root_cause=self.form_result['root_cause'],
                       fix=self.form_result['fix'],
                       time_effective=datetime.now(),
                       reporter_id=self.form_result['reporter_id'])
        
        Session.add(log)
        Session.commit()

        session['flash'] = 'Added fix for %s.' % box.name
        session.save()

        redirect(url(controller='admin', action='reader_history', id=box.code))
    
    def reader_summary(self, id=None, admin=True):
        c.admin = admin != 'False'
        box2 = self.__setup_box2_context_by_code(id)
        if not request.params.get('log_id', None):
            c.config = self.__last_box2_log_query(box2.id)
        else:
            c.config = Session.query(Box2Log)\
                              .options(joinedload_all(Box2Log.circuit))\
                              .get(int(request.params['log_id']))

        c.status = self.__last_box2_status_query(box2.id)
    
        c.mv = box2log_mv

        return render('/admin/reader_summary.html')

    def consumables(self):
        return render('/admin/consumables.html')
    
    def generators(self):
        return render('/admin/generators.html')
    
    def __last_box2_log_query(self, box2_id):
        return Session.query(Box2Log).filter_by(box2_id=box2_id)\
                                     .order_by('time_effective desc')\
                                     .options(joinedload_all(Box2Log.circuit))\
                                     .first()
    
    def __last_box2_status_query(self, box2_id):
        return Session.query(DRStatusLog).filter_by(box2_id=box2_id)\
                                         .order_by('time_effective desc')\
                                         .options(joinedload_all(DRStatusLog.reporter))\
                                         .first()
    
    def __setup_box2_context_by_code(self, code):
        if not code:
            abort(404)
        
        c.dr = Session.query(Box2).filter_by(code=code).first()
        if not c.dr:
            abort(404)
        
        # to daisy chain a bit
        return c.dr
    
    def __make_box2_log_entry(self, form):
        # TODO patternize?
        if form['day_effective'] is not None:
            d = form['day_effective']
            if form['time_effective'] is None:
                utime = datetime(d.year, d.month, d.day, 0, 0, 0)
            else:
                utime = datetime.combine(d, form['time_effective'])
        elif form['time_effective'] is not None:
            t = form['time_effective']
            utime = datetime.now()
            utime.hour = t.hour
            utime.minute = t.minute
        else:
            utime = datetime.now()
        
        entry = Box2Log(box2_id=form['box2_id'],
                        box2_circuit_id=form['box2_circuit_id'],
                        detector=form['detector'],
                        singulator_type=form['singulator_type'],
                        singulator_material=form['singulator_material'],
                        capillary=form['capillary'],
                        tip_lot_number=form['tip_lot_number'],
                        tip_supplier=form['tip_supplier'],
                        tip_material=form['tip_material'],
                        tip_size=form['tip_size'],
                        skin_on=form['skin_on'],
                        door_type=form['door_type'],
                        routine_version=form['routine_version'],
                        air_filter_location=form['air_filter_location'],
                        peristaltic_tubing=form['peristaltic_tubing'],
                        bottle_trough_hold_in_status=form['bottle_trough_hold_in_status'],
                        plate_sensor_status=form['plate_sensor_status'],
                        lid_sensor_status=form['lid_sensor_status'],
                        biochem_configuration=form['biochem_configuration'],
                        quantasoft_version=form['quantasoft_version'],
                        waste_bottle_empty=form['waste_bottle_empty'],
                        carrier_bottle_empty=form['carrier_bottle_empty'],
                        waste_bottle_full=form['waste_bottle_full'],
                        carrier_bottle_full=form['carrier_bottle_full'],
                        fluidics_circuit=form['fluidics_circuit'],
                        pickup_line=form['pickup_line'],
                        reservoir_line=form['reservoir_line'],
                        waste_downspout=form['waste_downspout'],
                        firmware_mcu9=form['firmware_mcu9'],
                        firmware_dll130=form['firmware_dll130'],
                        firmware_fpga16=form['firmware_fpga16'],
                        firmware_fluidics=form['firmware_fluidics'],
                        firmware_motor=form['firmware_motor'],
                        time_effective=utime)
        return entry
