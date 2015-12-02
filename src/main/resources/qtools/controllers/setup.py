import logging, simplejson as json
import formencode
from datetime import datetime

from pylons import request, response, session, tmpl_context as c, url, config
from pylons.controllers.util import abort, redirect, forward
from pylons.decorators import validate, jsonify
from pylons.decorators.rest import restrict
from paste.fileapp import FileApp

from sqlalchemy.orm import joinedload
from sqlalchemy import and_, not_

from qtools.lib.base import BaseController, render
from qtools.lib.beta import *
from qtools.lib import fields as fl
from qtools.lib import helpers as h
from qtools.lib.platesetup import make_setup_name, get_beta_project, get_validation_project
from qtools.lib.validators import PlateNameSegment, JSONValidator, IntKeyValidator, SaveNewIdFields
from qtools.model import Session, PlateSetup, Project, Person, DropletGenerator, ThermalCycler

import webhelpers.paginate as paginate

log = logging.getLogger(__name__)

class SetupForm(formencode.Schema):
    allow_extra_fields = True
    filter_extra_fields = True

    block = JSONValidator(not_empty=True)
    step = formencode.validators.OneOf(['consumable','progress'])

class SetupCreateForm(formencode.Schema):
    allow_extra_fields = True
    filter_extra_fields = True

    project_id = IntKeyValidator(Project, 'id', not_empty=True, if_missing=None)
    author_id = IntKeyValidator(Person, 'id', not_empty=True, if_missing=None)
    droplet_maker_id = IntKeyValidator(Person,'id', not_empty=False, if_missing=None)
    name = PlateNameSegment(not_empty=True)

    pre_validators = [SaveNewIdFields(('project_id', Project, 'id', 'name', {}),)]

class SetupListForm(formencode.Schema):
    allow_extra_fields = True
    filter_extra_fields = True

    project_id = IntKeyValidator(Project, 'id', not_empty=False, if_missing=None)
    author_id = IntKeyValidator(Person, 'id', not_empty=False, if_missing=None)

class SetupReagentForm(formencode.Schema):
    allow_extra_fields = True
    filter_extra_fields = True

    dr_oil = formencode.validators.Int(not_empty=False, if_missing=None)
    dg_oil = formencode.validators.Int(not_empty=False, if_missing=None)
    master_mix = formencode.validators.Int(not_empty=False, if_missing=None)

class SetupDGForm(formencode.Schema):
    allow_extra_fields = True
    filter_extra_fields = True

    droplet_generation_method = formencode.validators.Int(not_empty=False, if_missing=None)
    droplet_generator_id = IntKeyValidator(DropletGenerator, 'id', not_empty=False, if_missing=None)
    droplet_generation_day = formencode.validators.DateConverter(not_empty=False, if_missing=None)
    droplet_generation_time = formencode.validators.TimeConverter(prefer_ampm=True, use_seconds=False, use_datetime=True)

class SetupCyclerForm(formencode.Schema):
    allow_extra_fields = True
    filter_extra_fields = True

    thermal_cycler_id = IntKeyValidator(ThermalCycler, 'id', not_empty=False, if_missing=None)


class SetupController(BaseController):

    def index(self):
        c.beta = False
        return render('/setup/index.html')
    
    def list(self):
        self.__load_context()
        plate_q = self.__plate_setup_list_query()
        c.form = self.__plate_list_query_form()
        return self.__show_list(plate_q)
    
    @validate(schema=SetupListForm(), post_only=False, on_get=True, form='list')
    def list_filter(self):
        self.__load_context()
        c.project_id = self.form_result['project_id']
        c.author_id = self.form_result['author_id']
        plate_q = self.__plate_setup_list_query()
        if self.form_result['project_id']:
            plate_q = plate_q.filter_by(project_id=c.project_id)
        
        if self.form_result['author_id']:
            plate_q = plate_q.filter_by(author_id=c.author_id)
        
        c.form = self.__plate_list_query_form()
        return self.__show_list(plate_q)

    def new(self):
    	"""
        Like name, but invalidates the other ones
        """
        self.__load_context()
        c.next_url = url(controller='setup', action='create', beta=c.beta)
        c.name_form = self.__plate_setup_name_form()
        # take out beta test project id
        beta = get_beta_project()
        for tup in c.name_form.option['project_id']:
            if tup[0] == beta.id:
                c.name_form.option['project_id'].remove(tup)
                break
        return render('/setup/new.html')
    
    @restrict('POST')
    @validate(schema=SetupCreateForm(), form='new')
    def create(self):
        self.__load_context()
        plate_setup = PlateSetup()
        plate_setup.project_id = self.form_result['project_id']
        plate_setup.author_id = self.form_result['author_id']
        plate_setup.name = self.form_result['name']
        plate_setup.prefix = make_setup_name(plate_setup)

        Session.add(plate_setup)
        Session.commit()
        redirect(url(controller='setup', action='consumable', id=plate_setup.id, beta=c.beta))
    
    def __load_context(self):
        c.beta = request.urlvars.get('beta', None) == u'True' or request.params.get('beta', False)
    
    def __load_setup(self, id=None):
        if id is None:
            return None, None
        plate_setup = Session.query(PlateSetup).get(id)
        if not plate_setup:
            return None, None

        # TODO: make this default on DDL?
        struct = json.loads(plate_setup.setup or '{}')
        if ( type( struct ) is list ):
            struct = {}
        c.experiment_name = plate_setup.name and plate_setup.author_id
        c.experiment_consumable = struct.get('consumable', [])
        c.experiment_reagents = plate_setup.dr_oil or plate_setup.dg_oil or plate_setup.master_mix
        c.experiment_dg = plate_setup.droplet_generation_method not in (None, 1) or plate_setup.droplet_generator_id
        c.experiment_cycler = plate_setup.thermal_cycler_id
        c.setup = plate_setup
        return plate_setup, struct

    def __save_setup(self, setup, key, block):
        setup_obj = json.loads(setup.setup or '{}')
        # Hack.
        if type(block) == type(dict()) and block.get('notes', None) is not None:
            notes = block.pop('notes')
            setup.notes = notes
        setup_obj[key] = block
        setup.setup = json.dumps(setup_obj)
        if key == 'progress':
            setup.completed = (self.__check_progress(setup_obj) == 'Done')
        Session.commit()
    
    def __check_progress(self, setup):
        progress = setup.get('progress', {})
        if not progress.get('droplets_generated', False):
            return 'Not Started'
        if not progress.get('thermal_cycled', False):
            return 'In Cycler'
        
        readers = ['reader1', 'reader2', 'reader3', 'reader4', 'reader5', 'reader6', 'reader7', 'reader8']
        exec_order = setup.get('execution_order', [])
        if not exec_order:
            return 'Unknown'
        
        for i in range(len(exec_order)):
            if not progress.get(readers[i], False):
                return 'On Readers'
        return 'Done'


    def name(self, id=None):
        self.__load_context()
    	setup, struct = self.__load_setup(id)
        if not setup:
            abort(404)
        
        c.new_setup_form = c.name_form = self.__plate_setup_name_form(setup)
        c.next_url = url(controller='setup', action='save_name', id=setup.id, beta=c.beta)
    	return render('/setup/name.html')
    

    @restrict('POST')
    @validate(schema=SetupCreateForm(), form='name')
    def save_name(self, id=None):
        self.__load_context()
        setup, struct = self.__load_setup(id)
        if not setup:
            abort(404)
        
        for k, v in self.form_result.items():
            setattr(setup, k, v)
        setup.prefix = make_setup_name(setup)
        
        Session.commit()
        redirect(url(controller='setup', action='consumable', id=id, beta=c.beta))


    @jsonify
    @restrict('POST')
    def save(self, id=None):
        self.__load_context()
        # TODO: json form validator, like validate
        retval= {}
        if id is None:
            retval['status'] = 404
            retval['msg'] = "Null plate setup id specified."
            return retval
        
        plate_setup = Session.query(PlateSetup).get(id)
        if not plate_setup:
            retval['status'] = 404
            retval['msg'] = "Invalid plate setup id."
            return retval

        schema = SetupForm()
        try:
            c.form_result = schema.to_python(dict(request.params))
        except formencode.Invalid, error:
            retval = {}
            retval.update(error.error_dict)
            retval['status'] = 400
            retval['msg'] = "Invalid JSON data structure."
        else:
            # check for notes update?
            self.__save_setup(plate_setup, c.form_result['step'], c.form_result['block'])
            retval['status'] = 302
            if c.form_result['step'] == 'consumable':
                go_url = url(controller='setup', action='reagents', id=plate_setup.id, beta=c.beta)
            elif c.form_result['step'] == 'progress':
                go_url = url(controller='setup', action='list', beta=True)
            else:
                go_url = url(controller='setup', action='name', id=plate_setup.id, beta=c.beta)
            retval['next'] = go_url
            return retval


        return retval
    
    def consumable(self, id=None):
        self.__load_context()
    	plate_setup, struct = self.__load_setup(id)
        if not plate_setup:
            abort(404)
        
        c.default_lot_number = '3'
        c.default_bonding_temp = 134
        c.data = json.dumps(struct.get('consumable', None))
        c.dgs = fl.droplet_generator_field()['options']
        c.default_dg_run = ''
        c.default_dg_vacuum_time = ''
    	return render('/setup/consumable.html')
    
    def reagents(self, id=None):
        self.__load_context()
    	setup, struct = self.__load_setup(id)
        if not setup:
            abort(404)
        
        dg_oil = fl.droplet_generator_oil_field(selected=setup.dg_oil)
        dr_oil = fl.droplet_reader_oil_field(selected=setup.dr_oil)
        master_mix = fl.master_mix_field(selected=setup.master_mix)

        c.form = h.LiteralFormSelectPatch(
            value = {'dg_oil': unicode(dg_oil['value']),
                     'dr_oil': unicode(dr_oil['value']),
                     'master_mix': unicode(master_mix['value'])},
            option = {'dg_oil': dg_oil['options'],
                      'dr_oil': dr_oil['options'],
                      'master_mix': master_mix['options']}
        )
    	return render('/setup/reagents.html')

    @restrict('POST')
    @validate(schema=SetupReagentForm(), form='reagents')
    def save_reagents(self, id=None):
        self.__load_context()
        setup, struct = self.__load_setup(id)
        if not setup:
            abort(404)
        
        for k, v in self.form_result.items():
            setattr(setup, k, v)
        Session.commit()
        redirect(url(controller='setup', action='dg', id=id, beta=c.beta))
    
    def dg(self, id=None):
        self.__load_context()
        setup, struct = self.__load_setup(id)
        if not setup:
            abort(404)
        
        method = fl.droplet_generation_method_field(selected=setup.droplet_generation_method)
        dg_field = fl.droplet_generator_field(selected=setup.droplet_generator_id)

        c.form = h.LiteralFormSelectPatch(
            value = {'droplet_generation_method': unicode(method['value']),
                     'droplet_generator_id': unicode(dg_field['value']),
                     # how to get from_python to work?  am I doin it wrong?
                     'droplet_generation_day': setup.droplet_generation_time.strftime('%m/%d/%Y') if setup.droplet_generation_time else None,
                     'droplet_generation_time': setup.droplet_generation_time.strftime('%I:%M%p') if setup.droplet_generation_time else None},
            option = {'droplet_generation_method': method['options'],
                      'droplet_generator_id': dg_field['options']}
        )
        return render('/setup/dg.html')
    
    @restrict('POST')
    @validate(schema=SetupDGForm(), form='dg')
    def save_dg(self, id=None):
        self.__load_context()
        setup, struct = self.__load_setup(id)
        if not setup:
            abort(404)
        
        dg_date = self.form_result.pop('droplet_generation_day')
        dg_time = self.form_result.pop('droplet_generation_time')
        if dg_date and dg_time:
            setup.droplet_generation_time = datetime.combine(dg_date, dg_time)

        for k, v in self.form_result.items():
            setattr(setup, k, v)
        
        if setup.droplet_generator_id:
            setup.droplet_generation_method = 201 # DG/ThinXXS initial
        
        Session.commit()
        redirect(url(controller='setup', action='cycler', id=id, beta=c.beta))
    
    def cycler(self, id=None):
        self.__load_context()
        setup, struct = self.__load_setup(id)
        if not setup:
            abort(404)

        tc_field = fl.thermal_cycler_field(selected=setup.thermal_cycler_id)

        c.form = h.LiteralFormSelectPatch(
            value = {'thermal_cycler_id': unicode(tc_field['value'])},
            option = {'thermal_cycler_id': tc_field['options']}
        )
    	return render('/setup/cycler.html')

    @restrict('POST')
    @validate(schema=SetupCyclerForm(), form='cycler')
    def save_cycler(self, id=None):
        self.__load_context()
        setup, struct = self.__load_setup(id)
        if not setup:
            abort(404)
        
        for k, v in self.form_result.items():
            setattr(setup, k, v)
        Session.commit()
        if c.beta:
            redirect(url(controller='setup', action='plan', id=id, beta=c.beta))
        else:
            redirect(url(controller='setup', action='reader', id=id, beta=c.beta))
    
    def reader(self, id=None):
        c.beta = False
    	setup, struct = self.__load_setup(id)
        if not setup:
            abort(404)
    	return render('/setup/reader.html')

    def plan(self, id=None):
        c.beta = True
        setup, struct = self.__load_setup(id)
        if not setup:
            abort(404)
        
        c.plate_layout = struct.get('plate_layout',['Unknown','Unknown','u'])
        c.data = json.dumps(struct.get('progress', {}))
        c.exec_order = struct.get('execution_order', ['Unknown','Unknown','Unknown','Unknown'])
        c.use_reader34 = len(struct.get('execution_order', [])) == 4
        c.a_quadrant = len(struct.get('execution_order', [])) == 1
        return render('/setup/plan.html')
    
    @restrict('POST')
    def done(self, id=None):
        c.beta = True
        setup, struct = self.__load_setup(id)
        if not setup:
            abort(404)
        
        setup.completed = True
        Session.commit()
        session['flash'] = "Marked %s as completed." % setup.name
        session.save()
        redirect(url(controller='setup', action='list', beta=c.beta))

    @restrict('POST')
    def donotrun(self, id=None):
        c.beta = True
        setup, struct = self.__load_setup(id)
        if not setup:
            abort(404)
        
        setup.donotrun = True
        Session.commit()
        session['flash'] = "Marked %s as skipped." % setup.name
        session.save()
        redirect(url(controller='setup', action='list', beta=c.beta))
    
    def beta_qlt(self, id=None):
        c.beta = True

        setup, struct = self.__load_setup(id)
        if not setup:
            abort(404)
        
        quadrant = request.params.get('quadrant', None)
        if not quadrant or quadrant not in ('A','B','C','D','E','F','G','H'):
            abort(404)
        
        plate_layout = struct.get('plate_layout', None)
        if not plate_layout:
            abort(404)
        
        # TODO this line of code sucks (this whole thing sucks)
        if plate_layout[2] in ('s', 'sh', 'sw'):
            qlt_file = "%s/%s" % (config['qlb.setup_template_store'], plate_layout[0])
        else:
            qlt_file = "%s/%s" % (config['qlb.setup_template_store'], (plate_layout[0] % quadrant))
        
        # figure out which plate layout to load
        response.headers['Content-Type'] = 'application/quantalife-template'
        h.set_download_response_header(request, response, "%s.qlt" % ("%s_%s" % (setup.prefix, quadrant)))
        response.headers['Pragma'] = 'no-cache'
        response.headers['Cache-Control'] = 'no-cache'
        return forward(FileApp(qlt_file, response.headerlist))

    # TODO: common plate form?
    def __plate_setup_name_form(self, setup=None):
        project_field = fl.project_field(setup.project.id if setup and setup.project else None, active_only=True, empty='')
        author_field = fl.person_field(setup.author.id if setup and setup.author else None)
        person_field = fl.person_field(setup.droplet_maker_id if setup and setup.droplet_maker_id else None)
        return h.LiteralFormSelectPatch(
            value = {'author_id': unicode(author_field['value']),
                     'project_id': unicode(project_field['value']),
                     'droplet_maker_id': unicode(person_field['value']),
                     'name': setup.name if setup else ''},
            option = {'author_id': author_field['options'],
                      'project_id': project_field['options'],
                      'droplet_maker_id': person_field['options']}
        )

    # TODO: common decorator in list views? (see plate.py)
    def __plate_setup_list_query(self):
        return Session.query(PlateSetup).options(joinedload(PlateSetup.project),
                                                 joinedload(PlateSetup.author))
    
    def __plate_list_query_form(self):   
        project_field = fl.project_field(c.project_id if hasattr(c, 'project_id') else None)
        author_field = fl.person_field(c.author_id if hasattr(c, 'author_id') else None)
        return h.LiteralFormSelectPatch(
            value = {'project_id': unicode(project_field['value']),
                     'author_id': unicode(author_field['value'])},
            option = {'project_id': project_field['options'],
                      'author_id': author_field['options']}
        )
    
    # TODO: common decorator in list views (see plate.py)
    def __show_list(self, query):
        if c.beta:
            query = query.order_by(PlateSetup.id)
            beta_project = get_beta_project()
            validation_project = get_validation_project()
            query = query.filter(and_(PlateSetup.project_id.in_((beta_project.id, validation_project.id)),
                                      PlateSetup.completed == False,
                                      PlateSetup.donotrun != True))
        else:
            query = query.order_by('time_updated desc')
            beta_project = get_beta_project()
            validation_project = get_validation_project()
            query = query.filter(not_(PlateSetup.project_id.in_((beta_project.id, validation_project.id))))
        c.paginator = paginate.Page(
            query,
            page=int(request.params.get('page', 1)),
            items_per_page = 20
        )

        # decorate items
        for setup in c.paginator:
            myItems = json.loads(setup.setup or '{}')
            if  ( type( myItems ) is not list ): 
                setup.stage = self.__check_progress(myItems)
            else:
                setup.stage =  self.__check_progress({})
            #setup.stage = self.__check_progress(json.loads(setup.setup or '{}'))

        c.pager_kwargs = {}
        if hasattr(c, 'project_id'):
            c.pager_kwargs['project_id'] = c.project_id
        if hasattr(c, 'author_id'):
            c.pager_kwargs['author_id'] = c.author_id
        
        return render('/setup/list.html')
