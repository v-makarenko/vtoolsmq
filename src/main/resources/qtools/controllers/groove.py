import logging, json, operator
from datetime import datetime
from collections import defaultdict

from pylons import request, response, session, tmpl_context as c, url, config
from pylons.controllers.util import abort, redirect, forward
from pylons.decorators import validate
from pylons.decorators.rest import restrict
from paste.fileapp import FileApp

from qtools.lib.base import BaseController, render
import qtools.lib.fields as fl
import qtools.lib.helpers as h
from qtools.lib.platesetup import plate_layouts
from qtools.lib.validators import IntKeyValidator, OneOfInt, FormattedDateConverter, SanitizedString

from qtools.model import Session, Project, PlateSetup, PlateType, DropletGenerator, Person, Plate

import formencode
import webhelpers.paginate as paginate

log = logging.getLogger(__name__)

def droplet_type_field(selected=None):
    field = {'value': selected or '',
             'options': [('1', 'Skinned Taq'),
                         ('2', 'Skinless EvaGreen'),
                         ('3', 'Skinless Taq')]}
    return field

class GrooveCreateSetupForm(formencode.Schema):
    allow_extra_fields = True
    filter_extra_fields = True

    plate_type = IntKeyValidator(PlateType, 'id', not_empty=True)
    droplet_type = OneOfInt([int(k) for k, v in droplet_type_field()['options']], not_empty=True)
    droplet_generator = IntKeyValidator(DropletGenerator, 'id', not_empty=False, if_missing=None)
    droplet_maker = IntKeyValidator(Person, 'id', not_empty=True)
    creation_date = FormattedDateConverter(date_format='%Y%m%d', not_empty=True)
    runs = formencode.validators.Int(not_empty=True)
    notes = SanitizedString(not_empty=False)
    identifier = SanitizedString(not_empty=False, max_length=10)

class GrooveUpdateSetupForm(formencode.Schema):
    allow_extra_fields = True
    filter_extra_fields = True

    droplet_generator = IntKeyValidator(DropletGenerator, 'id', not_empty=False, if_missing=None)
    notes = SanitizedString(not_empty=False)

def groove_plate_type_field(selected=None):
    return fl.plate_type_subset_field(('mfgcc','mfgco','scc','fvitr','bsplex','bdplex','bred','bfpfn','av'), selected=selected)

def groove_droplet_generator_field(selected=None):
    all_dgs = fl.droplet_generator_field(selected=selected)
    all_dgs['options'] = [(k, v) for k, v in all_dgs['options'] if not k or v.startswith('Groove')]
    return all_dgs

def groove_plate_layout_field(selected=None):
    return {'value': selected or '',
            'options': [(21, 'QuadPlex A/B'),
                        (1, 'Full Plate'),
                        (2, 'Half Plates'),
                        (4, 'Quarter Plates')]}

class GrooveController(BaseController):

    def _list_base(self):
        groove_test = Session.query(Project).filter_by(name='GrooveTest').first()
        query = Session.query(PlateSetup)\
            .filter_by(project_id=groove_test.id)\
            .order_by('time_updated desc, name')

        c.paginator = paginate.Page(
            query,
            page=int(request.params.get('page', 1)),
            items_per_page=20
        )

        c.pager_kwargs = {}
        c.plate_type_field = groove_plate_type_field()
        return render('/product/groove/list.html')

    def list(self):
        response = self._list_base()
        return h.render_bootstrap_form(response)

    def __setup_groove_fields(self):
        c.droplet_makers = fl.person_field()
        # TODO: limit?
        c.plate_types = groove_plate_type_field()
        c.droplet_types = droplet_type_field()
        c.droplet_generators = groove_droplet_generator_field()
        c.plate_layouts = groove_plate_layout_field()

    def _new_base(self):
        self.__setup_groove_fields()
        c.title = "Create Groove Plate"
        c.submit_action = url(controller='groove', action='create')
        c.call_to_action = 'Create Plate'
        c.record_exists = False
        c.allow_delete = False

        return render('/product/groove/edit.html')

    def new(self):
        response = self._new_base()
        now = datetime.now()
        return h.render_bootstrap_form(response, defaults={'creation_date': now.strftime('%Y%m%d')})

    @restrict('POST')
    @validate(schema=GrooveCreateSetupForm(), form='_new_base', error_formatters=h.tw_bootstrap_error_formatters)
    def create(self):
        setup, errors = self.__update_groove_record()
        if errors:
            response = self._new_base()
            defaults = GrooveCreateSetupForm().from_python(self.form_result)
            return h.render_bootstrap_form(response,
                defaults=defaults,
                errors=errors,
                error_formatters=h.tw_bootstrap_error_formatters)
        session['flash'] = 'Plate created.'
        session.save()
        return redirect(url(controller='groove', action='plates', id=setup.id))

    @property
    def __layout_map(self):
        if not hasattr(self, '_plate_layout_map'):
            self._plate_layout_map = defaultdict(lambda: defaultdict(dict))

            for layout_name, (layout_fn, name, layout_type, code, desc) in plate_layouts.items():
                self._plate_layout_map[code][layout_type] = layout_fn

        return self._plate_layout_map

    def __get_layout_qlts(self, plate_type, num_runs):
        """
        Returns a relative path to the QLTs if a combination plate
        type and number of runs exist.
        """
        # giant hack.
        layout_codes = None
        if plate_type.code in ('bcc','mfgcc'):
            layout_codes = ('o',)
        elif num_runs == 1:
            layout_codes = ('sw',)
        elif num_runs == 2:
            layout_codes = ('h', 'vh')
        elif num_runs == 21:
            layout_codes = ('qp',)
        elif num_runs == 4:
            layout_codes = ('q', 'c')

        if not layout_codes:
            return None
        for layout_code in layout_codes:
            file_path = self.__layout_map[plate_type.code][layout_code]
            if file_path:
                # HACK HACK
                if plate_type.code in ('av',):
                    return ([file_path % chr(ord('A')+i) for i in range(2)])
                elif plate_type.code in ('bcc','mfgcc'):
                    return ([file_path % chr(ord('A')+i) for i in range(num_runs)])
                elif num_runs == 1:
                    return (file_path,)
                else:
                    return ([file_path % chr(ord('A')+i) for i in range(num_runs)])

        return None

    def __name_for_groove_plate(self, plate_type, config_type, person, date, identifier, number):
        ptnames = {'bcarry': 'Carryover',
                   'mfgco': 'Carryover',
                   'gcnv': 'CNV',
                   'bcc': 'ColorComp',
                   'mfgcc': 'ColorComp',
                   'betaec': 'Events',
                   'bexp': 'Exception',
                   'fvtitr': 'FVTitration',
                   'gfv': 'FVTitration',
                   'bfpfn': 'FPFN',
                   'bapp': 'Other',
                   'bred': 'RED',
                   'bsplex': 'Singleplex',
                   'bdplex': 'Duplex',
                   '2x10': 'EvaDNRStaphBG',
                   'dgvol': 'DGPressureVol',
                   'gdnr': 'EvaDNRStaph',
                   'gload': 'EvaGreenDNALoad',
                   'egdnr': 'EvaDNRHuman',
                   'fam350': 'FAM350',
                   'fm350l': 'FAM350Load',
                   'av': 'Hamilton'}

        config_names = {1: 'Skinned',
                        2: 'SkinlessEG',
                        3: 'SkinlessTaq'}

        toks = ['AutoTest',
                config_names[config_type],
                ptnames[plate_type.code],
                date.strftime('%Y%m%d'),
                chr(ord('A')+number)]

        if person:
            toks.insert(3, person.name_code)

        if identifier:
            toks.insert(len(toks)-1, identifier)

        return "_".join(toks)

    def __update_groove_record(self, record=None):

        new_record = False
        errors = {}
        if not record:
            new_record = True
            plate_type = Session.query(PlateType).get(self.form_result['plate_type'])
            person = Session.query(Person).get(self.form_result['droplet_maker'])
            if self.form_result['droplet_generator']:
                dg = Session.query(DropletGenerator).get(self.form_result['droplet_generator'])
            else:
                dg = None
            if not plate_type:
                errors['plate_type'] = 'Unknown plate type.'
            else:
                qlt_paths = self.__get_layout_qlts(plate_type, self.form_result['runs'])
                if not qlt_paths:
                    errors['runs'] = 'Invalid layout for this plate type.'
                else:
                    # create the name
                    setup = []
                    for i, path in enumerate(qlt_paths):
                        name = self.__name_for_groove_plate(plate_type,
                            self.form_result['droplet_type'],
                            person,
                            self.form_result['creation_date'],
                            self.form_result['identifier'],
                            i)
                        setup.append((name, path))

                    plate_setup = PlateSetup(name=name[:-2],
                        prefix=name[:-2],
                        setup=json.dumps(setup),
                        time_updated=self.form_result['creation_date'],
                        project_id=Session.query(Project).filter_by(name='GrooveTest').first().id,
                        author_id=person.id,
                        droplet_maker_id=person.id,
                        dr_oil=22,
                        plate_type_id=plate_type.id,
                        droplet_generator_id=dg.id if dg else None,
                        notes=self.form_result['notes'])
                    dt = self.form_result['droplet_type']
                    if dt == 1: # TODO LITERALS
                        plate_setup.skin_type = Plate.SKIN_TYPE_SKINNED
                        plate_setup.dg_oil = 14
                        plate_setup.master_mix = 12
                    else:
                        plate_setup.skin_type = Plate.SKIN_TYPE_SKINLESS
                        plate_setup.dg_oil = 31

                    if dt == 2:
                        plate_setup.chemistry_type = Plate.CHEMISTRY_TYPE_GREEN
                        plate_setup.master_mix = 205
                    else:
                        plate_setup.chemistry_type = Plate.CHEMISTRY_TYPE_TAQMAN

                    if dt == 3:
                        plate_setup.master_mix = 501

                    Session.add(plate_setup)
                    Session.commit()
                    return plate_setup, None
        else:
            record.notes = self.form_result['notes']
            record.droplet_generator_id = self.form_result['droplet_generator']
            Session.commit()
            return record, None


        if errors:
            return None, errors


    def __load_groove_setup(self, id=None):
        if not id:
            return None

        project = Session.query(Project).filter_by(name='GrooveTest').first()
        setup = Session.query(PlateSetup).get(int(id))
        if not setup:
            return None

        if setup.project_id != project.id:
            return None

        return setup

    def __load_setup_into_formvars(self, setup):
        formvars = dict()
        formvars['plate_type'] = setup.plate_type_id
        formvars['droplet_generator'] = setup.droplet_generator_id
        formvars['droplet_maker'] = setup.droplet_maker_id
        formvars['creation_date'] = setup.time_updated.strftime('%Y%m%d')
        formvars['notes'] = setup.notes
        formvars['runs'] = len(json.loads(setup.setup))
        return formvars

    def _edit_base(self, id=None):
        self.__setup_groove_fields()
        c.setup = self.__load_groove_setup(id)
        if not c.setup:
            abort(404)

        c.title = c.setup.name
        c.submit_action = url(controller='groove', action='save', id=id)
        c.call_to_action = "Save Plate"
        c.record_exists = True

        # don't do bound plates yet
        c.allow_delete = not(c.setup.plates)
        return render('/product/groove/edit.html')

    def edit(self, id=None):
        response = self._edit_base(id)
        return h.render_bootstrap_form(response, defaults=self.__load_setup_into_formvars(c.setup))

    @restrict('POST')
    @validate(schema=GrooveUpdateSetupForm(), form='_edit_base', error_formatters=h.tw_bootstrap_error_formatters)
    def save(self, id=None):
        setup = self.__load_groove_setup(id)
        if not setup:
            abort(404)

        self.__update_groove_record(setup)
        session['flash'] = 'Plate updated.'
        session.save()
        return redirect(url(controller='groove', action='list'))


    @restrict('POST')
    def delete(self, id=None):
        setup = self.__load_groove_setup(id)
        if not setup:
            abort(404)

        if setup.plates:
            session['flash'] = "Cannot delete this setup; QTools has processed data for this plate."
            session['flash_class'] = 'error'
            session.save()
            return redirect(url(controller='groove', action='edit', id=id))
        else:
            Session.delete(setup)
            Session.commit()
            session['flash'] = "Plate deleted."
            session.save()
            return redirect(url(controller='groove', action='list'))

    def plates(self, id=None):
        if not id:
            abort(404)

        c.setup = self.__load_groove_setup(id)
        if not c.setup:
            abort(404)

        plates = c.setup.plates
        setup_specs = json.loads(c.setup.setup)

        c.plate_records = [[spec, None] for spec in setup_specs]
        for plate in sorted(plates, key=operator.attrgetter('run_time')):
            for tup in c.plate_records:
                if plate.name.startswith(tup[0][0]):
                    tup[1] = plate

        return render('/product/groove/plate_list.html')

    def template(self, id=None):
        run_id = int(request.params.get('run', 0))
        if not id:
            abort(404)

        c.setup = self.__load_groove_setup(id)
        if not c.setup:
            abort(404)

        setup_specs = json.loads(c.setup.setup)
        try:
            plate_spec = setup_specs[run_id]
            qlt_file = "%s/%s" % (config['qlb.setup_template_store'], plate_spec[1])
        except Exception, e:
            abort(404)

        response.headers['Content-Type'] = 'application/quantalife-template'
        h.set_download_response_header(request, response, "%s.qlt" % plate_spec[0])
        response.headers['Pragma'] = 'no-cache'
        response.headers['Cache-Control'] = 'no-cache'
        return forward(FileApp(qlt_file, response.headerlist))