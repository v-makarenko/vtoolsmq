import logging, itertools, time, os, datetime, shutil
from mimetypes import guess_type

from pylons import request, response, session, tmpl_context as c, url, config
from pylons.controllers.util import abort, redirect, forward
from pylons.decorators import validate, jsonify
from pylons.decorators.rest import restrict

from sqlalchemy.orm import aliased, contains_eager, joinedload_all
from sqlalchemy import and_, func

from qtools.model import Session, QLBWell, QLBFile, QLBPlate, Plate, Project, Experiment, Assay, Person, WellTag, Box2, Box2File

from qtools.lib.base import BaseController, render
from qtools.lib.decorators import deprecated_action
from qtools.lib.queryform import QueryForm, ColumnValidator, CompareValidator, SortByValidator, full_column_name
from qtools.lib.storage import QLStorageSource
from qtools.lib.validators import IntKeyValidator, FileUploadFilter
from qtools.lib.upload import upload_basename

import qtools.lib.helpers as h
import qtools.lib.fields as fl

import formencode

from paste.fileapp import FileApp

log = logging.getLogger(__name__)

class QLBPlateForm(QueryForm):
    entity = QLBPlate
    join_entities = (QLBFile, Plate, Project, Experiment, Assay, Person)
    
    col_display_names = {'qlbfile.dirname': 'Directory Name',
                         'qlbfile.basename': 'File Name',
                         'qlbplate.host_datetime': 'Date/Time',
                         'qlbplate.host_machine': 'Box 2',
                         'qlbplate.host_software': 'QuantaSoft Version',
                         'plate.droplet_generator': 'Droplet Generator',
                         'plate.thermal_cycler': 'Thermal Cycler',
                         'plate.name': 'Plate Name',
                         'project.name': 'Project Name',
                         'experiment.name': 'Experiment Name',
                         'assay.name': 'Assay Name',
                         'person.name_code': 'Operator',
                         'assay.gene': 'Gene',
                         'assay.quencher': 'Assay Quencher',
                         'qlbplate.equipment_make': 'Equipment Make',
                         'qlbplate.equipment_model': 'Equipment Model'}
    
    # TODO: figure out how to better link the lot number, thermo cycler fields
    # (if it is deemed necessary)
    
    # this is clunky but whatever
    exclude_fields = ('qlbfile.mtime', 'qlbfile.runtime', 'qlbfile.type', 'qlbfile.read_status', 'qlbfile.version',
                      'qlbplate.equipment_serial', 'qlbplate.file_desc', 'qlbplate.channel_map', 'qlbplate.host_user',
                      'plate.run_time', 'plate.description', 'plate.type', 'plate.program_version',
                      'project.code', 'project.description',
                      'experiment.code', 'experiment.description',
                      'assay.added', 'assay.amplicon_width','assay.primer_fwd','assay.primer_rev','assay.probe_pos','assay.chromosome','assay.snp_rsid','assay.dye','assay.probe_seq',
                      'person.first_name','person.last_name','person.email')


class QLBWellForm(QueryForm):
    entity = QLBWell
    join_entities = (QLBFile,)
    
    col_display_names = {'qlbfile.dirname': 'Directory Name',
                         'qlbfile.basename': 'File Name',
                         'qlbwell.host_machine': 'Box 2',
                         'qlbfile.mtime': 'Processed Time',
                         'qlbfile.runtime': 'Recorded Time'}
    
    group_by_directory = formencode.validators.Bool(if_empty=0)
    
    exclude_fields = ('setup_version', 'read_status', 'type', 'raw_data', 'daq_version', 'version')

class WellTagForm(formencode.Schema):
    allow_extra_fields = True
    filter_extra_fields = True
    
    well_tag = IntKeyValidator(WellTag, 'id', not_empty=True)
    group_by_plate = formencode.validators.Bool(if_empty=0)


class QLBPlateDistinctForm(formencode.Schema):
    allow_extra_fields = True
    filter_extra_fields = True
    
    column = ColumnValidator(QLBPlate, (QLBFile, Plate, Project, Experiment, Assay, Person))
    field_name = formencode.validators.NotEmpty()


class QLBWellDistinctForm(formencode.Schema):
    allow_extra_fields = True
    filter_extra_fields = True
    
    column = ColumnValidator(QLBWell, (QLBFile,))
    field_name = formencode.validators.NotEmpty()

class RobocopyForm(formencode.Schema):
    allow_extra_fields = True
    filter_extra_fields = True

    box2_id = IntKeyValidator(Box2, 'id', not_empty=True)

class FileUploadForm(formencode.Schema):
    file = FileUploadFilter(not_empty=True)
    file_id = IntKeyValidator(Box2File, 'id', not_empty=False, if_missing=None)
    description = formencode.validators.String(not_empty=False, if_missing=None)

class FileIDForm(formencode.Schema):
    file_id = IntKeyValidator(Box2File, 'id', not_empty=True)


class Box2Controller(BaseController):
    """
    TODO: still a lot of duplication here.  See if there is a sensible way to refactor
    such that there will be a single query form.
    """
    
    def __setup_box2_code_context(self, code=None):
        if code is None:
            abort(404)

        box2 = Session.query(Box2).filter_by(code=code).first()
        if not box2:
            abort(404)
        else:
            c.box2 = box2

    def index(self):
        return render('/box2/index.html')
    
    @deprecated_action
    def plates(self):
        qform = QLBPlateForm()
        c.form = h.LiteralForm(
            option = {'conditions-0.field': qform.field_tuples,
                      'conditions-0.compare': [(disp, disp) for disp, val in CompareValidator.comparators],
                      'order_by': qform.field_tuples,
                      'order_by_direction': SortByValidator.directions,
                      'return_fields': qform.field_tuples},
            value = {'order_by': 'qlbplate.host_datetime',
                     'order_by_direction': 'desc'}
    
        )
        c.submit_action = 'plate_query'
        c.distinct_action = 'plate_distinct'
        return render('/box2/plate.html')
    
    @deprecated_action
    def wells(self):
        qform = QLBWellForm()
        c.form = h.LiteralForm(
            option = {'conditions-0.field': qform.field_tuples,
                      'conditions-0.compare': [(disp, disp) for disp, val in CompareValidator.comparators],
                      'order_by': qform.field_tuples,
                      'order_by_direction': SortByValidator.directions,
                      'return_fields': qform.field_tuples,
                      'group_by_directory': [(u'1', '')]},
            value = {'order_by': 'qlbwell.host_datetime',
                     'group_by_directory': [u'0', u'0'],
                     'order_by_direction': 'desc'},
            checked = {'group_by_directory': True}
    
        )
        
        c.submit_action = 'well_query'
        c.distinct_action = 'well_distinct'
        
        return render('/box2/well.html')
    
    @validate(QLBPlateForm(), form='plates', post_only=False, on_get=True, variable_decode=True)
    def plate_query(self):
        # simple AND case
        labels = []
        for idx, cond in enumerate(self.form_result['conditions']):
            labels.append(cond['field'].label("condition%s" % idx))
        
        conditions = and_(*[getattr(cond['field'], cond['compare'])(cond['value']) for cond in self.form_result['conditions']])
        labels = []
        label_names = []
        for idx, cond in enumerate(self.form_result['conditions']):
            field_name = 'field%s' % idx
            labels.append(cond['field'].label(field_name))
            label_names.append(QLBPlateForm.col_display_names.get(full_column_name(cond['field']), cond['field'].name))
        
        if self.form_result['order_by'].name not in [cond['field'].name for cond in self.form_result['conditions']]:
            order_by = self.form_result['order_by']
            field_name = 'field%s' % len(label_names)
            labels.append(order_by.label(field_name))
            label_names.append(QLBPlateForm.col_display_names.get(full_column_name(order_by), order_by.name))
        
        for col in self.form_result['return_fields']:
            field_name = 'field%s' % len(label_names)
            labels.append(col.label(field_name))
            label_names.append(QLBPlateForm.col_display_names.get(full_column_name(col), col.name))
                
        if self.form_result['order_by_direction'] == "desc":
            sort_column = self.form_result['order_by'].desc()
        else:
            sort_column = self.form_result['order_by']
        
        c.plates = Session.query(QLBPlate, *labels).join(QLBFile).outerjoin(Plate, Project, Experiment, Assay, Person).filter(conditions) \
                                                 .order_by(sort_column) \
                                                 .options(contains_eager(QLBPlate.file))
        c.grouped_results = False
        
        # TODO: support and, or
        c.field = self.form_result['conditions'][0]['field']
        # TODO: fix (hack)
        c.compare = request.params.get('conditions-0.compare')
        c.value = self.form_result['conditions'][0]['value']
        c.label_names = label_names
        return render('/box2/plate_list.html')
    
    @deprecated_action
    def well_tag(self):
        well_tag_field = fl.well_tag_field()
        c.form = h.LiteralFormSelectPatch(
            value = {'well_tag': well_tag_field['value'],
                     'group_by_plate': [u'0']},
            option = {'well_tag': [('--','--')]+well_tag_field['options'],
                      'group_by_plate': [(u'1', '')]}
        )
        return render('/box2/well_tag.html')
    
    @validate(WellTagForm(), post_only=False, on_get=True, form='well_tag')
    def by_well_tag(self):
        well_tag_field = fl.well_tag_field(str(self.form_result['well_tag']))
        c.group_by_plate = self.form_result['group_by_plate']
        c.tag_id = self.form_result['well_tag']
        c.tag_name = Session.query(WellTag).get(c.tag_id).name
        c.form = h.LiteralFormSelectPatch(
            value = {'well_tag': well_tag_field['value'],
                     'group_by_plate': [u'1' if c.group_by_plate else u'0']},
            option = {'well_tag': [('--','--')]+well_tag_field['options'],
                      'group_by_plate': [(u'1', '')]}
        )
        
        well_tags = Session.query(WellTag).\
                            filter_by(id=c.tag_id).\
                            options(joinedload_all(WellTag.tag_wells, QLBWell.plate, QLBPlate.file, innerjoin=True),
                                    joinedload_all(WellTag.tag_wells, QLBWell.plate, QLBPlate.plate, innerjoin=True)).\
                            all()
        
        c.label_names = []
        
        if not len(well_tags):
            c.wells = []
            c.well_groups = []
        elif c.group_by_plate:
            wells = sorted(well_tags[0].wells, key=lambda well: (well.plate_id, well.well_name))
            well_groups = [(plate, list(wells)) for plate, wells in itertools.groupby(wells, lambda well: well.plate)]
            c.well_groups = sorted(well_groups, key=lambda tup: tup[0].host_datetime)
            c.well_groups.reverse()
        else:
            c.wells = sorted(well_tags[0].wells, key=lambda well: well.host_datetime)
            c.wells.reverse()
        
        return render('/box2/by_well_tag.html')
    
    
    @validate(QLBWellForm(), post_only=False, on_get=True, form='wells', variable_decode=True)
    def well_query(self):
        # simple AND case
        labels = []
        for idx, cond in enumerate(self.form_result['conditions']):
            labels.append(cond['field'].label("condition%s" % idx))
        
        conditions = and_(*[getattr(cond['field'], cond['compare'])(cond['value']) for cond in self.form_result['conditions']])
        labels = []
        label_names = []
        for idx, cond in enumerate(self.form_result['conditions']):
            field_name = 'field%s' % idx
            labels.append(cond['field'].label(field_name))
            label_names.append(QLBWellForm.col_display_names.get(full_column_name(cond['field']), cond['field'].name))
        
        if self.form_result['order_by'].name not in [cond['field'].name for cond in self.form_result['conditions']]:
            order_by = self.form_result['order_by']
            field_name = 'field%s' % len(label_names)
            labels.append(order_by.label(field_name))
            label_names.append(QLBWellForm.col_display_names.get(full_column_name(order_by), order_by.name))
        
        for col in self.form_result['return_fields']:
            field_name = 'field%s' % len(label_names)
            labels.append(col.label(field_name))
            label_names.append(QLBWellForm.col_display_names.get(full_column_name(col), col.name))
                
        
        if self.form_result['group_by_directory']:
            field_name = 'field%s' % len(label_names)
            if self.form_result['order_by_direction'] == 'desc':
                order_by_dir = "desc"
                sort_column = func.max(self.form_result['order_by'])
            else:
                order_by_dir = "asc"
                sort_column = func.min(self.form_result['order_by'])
            
            labels.append(sort_column.label('group_col'))
            
            well_extremes = Session.query(QLBWell, *labels).join(QLBFile).filter(conditions) \
                                                           .group_by('qlbfile_dirname') \
                                                           .order_by('group_col %s' % order_by_dir) \
                                                           .options(contains_eager(QLBWell.file))
            
            c.wells = self.__well_dirname_iterator(well_extremes, Session.query(QLBWell, *labels[:-1]).join(QLBFile), conditions)
            
            c.grouped_results = True
        else:
            if self.form_result['order_by_direction'] == "desc":
                sort_column = self.form_result['order_by'].desc()
            else:
                sort_column = self.form_result['order_by']
                
            c.wells = Session.query(QLBWell, *labels).join(QLBFile).filter(conditions) \
                                                     .order_by(sort_column) \
                                                     .options(contains_eager(QLBWell.file))
            c.grouped_results = False
        
        
        # TODO: support and, or
        c.field = self.form_result['conditions'][0]['field']
        # TODO: fix (hack)
        c.compare = request.params.get('conditions-0.compare')
        c.value = self.form_result['conditions'][0]['value']
        c.label_names = label_names
        return render('/box2/well_list.html')
    
    @validate(QLBPlateDistinctForm(), post_only=False, on_get=True, variable_decode=False)
    def plate_distinct(self):
        values = Session.query(self.form_result['column']).distinct()
        
        field = None
        # special values
        if self.form_result['column'] == Plate.thermal_cycler:
            field = fl.thermal_cycler_field()
        elif self.form_result['column'] == Plate.droplet_generator:
            field = fl.droplet_generator_field()
        
        if field:
            c.form = h.LiteralForm(
                option = {self.form_result['field_name']: field['options']}
            )
        else:
            c.form = h.LiteralForm(
                option = {self.form_result['field_name']: sorted([(tup[0], str(tup[0])) for tup in values if tup[0] is not None])}
            )
        c.field_name = self.form_result['field_name']
        
        return render('/box2/select.html')
    
    @validate(QLBWellDistinctForm(), post_only=False, on_get=True, variable_decode=False)
    def well_distinct(self):
        values = Session.query(self.form_result['column']).distinct()
        
        c.form = h.LiteralForm(
            option = {self.form_result['field_name']: sorted([(tup[0], str(tup[0])) for tup in values if tup[0] is not None])}
        )
        c.field_name = self.form_result['field_name']
        
        return render('/box2/select.html')
    
    def __well_dirname_iterator(self, wells, base_query, conditions):
        for value_tuple in wells:
            well = value_tuple[0]
            
            group_conditions = and_(conditions, QLBFile.dirname == well.file.dirname)
            well_group = base_query.filter(group_conditions) \
                                   .order_by('well_name') \
                                   .options(contains_eager(QLBWell.file))
            for group_well in well_group:
                yield group_well

    def __setup_robocopy_context(self):
        c.box2_field = fl.box2_field()

    def robocopy(self):
        self.__setup_robocopy_context()
        response = render("/box2/robocopy.html")
        return h.render_bootstrap_form(response)

    @validate(RobocopyForm(), form='robocopy', error_formatters=h.tw_bootstrap_error_formatters)
    def robocopy_generate(self):
        self.__setup_robocopy_context()
        box2 = Session.query(Box2).get(self.form_result['box2_id'])
        c.src_dir = box2.src_dir
        c.params = ' ' # reserve later to do QLP-only
        response.content_type = 'text/cmd'
        h.set_download_response_header(request, response, 'Robocopy %s.cmd' % box2.name)
        return render('/box2/robocopy.mako')

    def _upload_base(self, code=None):
        self.__setup_box2_code_context(code)
        c.upload_title = "%s: Add File" % c.box2.name
        c.upload_explanation = "Add a file to %s's space." % c.box2.name
        c.upload_label = "Add File"
        return render("/box2/upload.html")

    def metrics(self, id=None):
        # bring stuff back out of metrics controller?
        return redirect(url(controller='metrics', action='certification', id=id))

    def upload(self, id=None):
        response = self._upload_base(code=id)
        return h.render_bootstrap_form(response)

    def __file_id_query(self, box2_id, file_id):
        return Session.query(Box2File).filter_by(box2_id=box2_id, id=file_id).first()

    def __file_name_query(self, box2_id, name):
        return Session.query(Box2File).filter_by(box2_id=box2_id, name=name).first()

    def __upload_file_dir(self, box2):
        source = QLStorageSource(config)
        return source.box2_relative_path(box2, '', 'qtools_attachments')

    def __upload_file_path(self, box2, path):
        source = QLStorageSource(config)
        return source.box2_relative_path(box2, 'qtools_attachments', path)

    def _update_base(self, file_id, code=None):
        self.__setup_box2_code_context(code)
        thefile = self.__file_id_query(c.box2.id, file_id)
        if not thefile:
            abort(404)

        c.upload_title = '%s: Update File' % c.box2.name
        c.upload_explanation = 'Update "%s" by replacing it with another file.' % thefile.name
        c.upload_label = 'Update File'
        return render('/box2/upload.html')

    @validate(schema=FileIDForm(), form='_update_base')
    def update(self, id=None):
        file_id = self.form_result['file_id']
        response = self._update_base(file_id, id)
        thefile = self.__file_id_query(c.box2.id, file_id)
        
        return h.render_bootstrap_form(response, defaults={'file_id': thefile.id, 'description': thefile.description})

    @validate(schema=FileUploadForm(), form='_upload_base', error_formatters=h.tw_bootstrap_error_formatters)
    def upload_file(self, id=None):
        self.__setup_box2_code_context(id)
        source = QLStorageSource(config)
        basename = upload_basename(self.form_result['file'].filename)
        errors = {}

        existing_path = self.__file_name_query(c.box2.id, basename)
        if existing_path and not self.form_result['file_id'] == existing_path.id:
            # todo, if existing update path
            errors = dict(file='File with this name already exists for this reader.  Use the Update page.')

        path = "%s_%s" % (int(round(time.time())), basename)
        thefile = self.form_result['file'].file

        filerec = self.__file_id_query(c.box2.id, self.form_result['file_id'])
        new_record = False
        if not filerec:
            filerec = Box2File(box2_id=c.box2.id)
            new_record = True

        filerec.name = basename
        filerec.deleted = False
        filerec.path = path
        filerec.updated = datetime.datetime.now()
        filerec.description = self.form_result['description']
        filerec.mime_type = guess_type(basename)[0] or 'text/plain'


        if errors:
            response = self._upload_base(id)
            return h.render_bootstrap_form(response, errors=errors, error_formatters=h.tw_bootstrap_error_formatters)

        try:
            attachment_dir = self.__upload_file_dir(c.box2)
            if not os.path.exists(attachment_dir):
                os.mkdir(attachment_dir)

            permanent_path = self.__upload_file_path(c.box2, path)
            permanent_file = open(permanent_path, 'wb')
            shutil.copyfileobj(thefile, permanent_file)
            thefile.close()
            permanent_file.close()

            filerec.size = os.stat(permanent_path).st_size
            if new_record:
                Session.add(filerec)
            else:
                Session.merge(filerec)
            Session.commit()
            session['flash'] = 'File uploaded.'
            write_success = True
        except Exception, e:
            session['flash'] = 'Could not upload file: %s' % str(e)
            session['flash_class'] = 'error'
            write_success = False
        session.save()

        if write_success:
            return redirect(url(controller='metrics', action='certification', id=c.box2.code))
        else:
            return redirect(url(controller='box2', action='upload', id=c.box2.code))

    @validate(schema=FileIDForm(), form='metrics', on_get=True, post_only=False)
    def download_file(self, id=None):
        self.__setup_box2_code_context(id)
        thefile = self.__file_id_query(c.box2.id, self.form_result['file_id'])
        if not thefile:
            abort(404)

        h.set_download_response_header(request, response, thefile.name)
        response.content_type = thefile.mime_type
        file_path = self.__upload_file_path(c.box2, thefile.path)
        response.headers['Pragma'] = 'no-cache'
        response.headers['Cache-Control'] = 'no-cache'
        return forward(FileApp(file_path, response.headerlist))

    @validate(schema=FileIDForm(), form='metrics')
    def delete_file(self, id=None):
        self.__setup_box2_code_context(id)
        thefile = self.__file_id_query(c.box2.id, self.form_result['file_id'])
        if not thefile:
            abort(404)

        Session.delete(thefile)
        Session.commit()
        session['flash'] = 'File deleted.'
        session.save()
        return redirect(url(controller='metrics', action='certification', id=c.box2.code))


