import logging, operator

from pylons import request, response, session, tmpl_context as c, url
from pylons.controllers.util import abort, redirect
from pylons.decorators import validate
from pylons.decorators.rest import restrict

from qtools.components.manager import get_manager_from_pylonsapp_context
from qtools.constants.job import *
from qtools.controllers import populate_multiform_context

from qtools.lib.base import BaseController, render
from qtools.lib.collection import groupinto, AttrDict
from qtools.lib.decorators import session_validate, session_validate_flow, session_clear_startswith, multi_validate, flash_if_form_errors
import qtools.lib.helpers as h
import qtools.lib.helpers.sequence as seqh
import qtools.lib.fields as fl
from qtools.lib.validators import DNASequence, Chromosome, SNPName, FormattedDateConverter, IntKeyValidator, SanitizedString, OneOfInt
from qtools.lib.variabledecode import variable_encode_except

from qtools.messages.sequence import *

from qtools.model import Person, Session, QLBWellChannel, QLBWell, QLBPlate, Plate
from qtools.model.sequence import Sequence, SequenceGroup, SequenceGroupComponent, SequenceGroupTag, Amplicon, AmpliconSequenceCache, SequenceGroupCondition
from qtools.model.sequence.pcr import pcr_sequences_snps_for_group, transcript_sequences_snps_for_group
from qtools.model.sequence.util import sequence_group_unlink_sequences, active_sequence_group_query

import formencode
from formencode import htmlfill, Schema
from formencode.variabledecode import NestedVariables, variable_decode, variable_encode

from sqlalchemy import desc, func, distinct, and_, or_
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import joinedload_all

log = logging.getLogger(__name__)

def assay_chemistry_field(selected=SequenceGroup.CHEMISTRY_TYPE_TAQMAN):
    field = {'value': selected,
             'options': SequenceGroup.chemistry_type_display_options()}
    return field

def assay_structure_field(selected=None):
    field = {'value': selected or '',
             'options': SequenceGroup.kit_type_display_options()}
    return field

def assay_type_field(selected=None):
    field = {'value': selected or '',
             'options': SequenceGroup.assay_type_display_options()}
    return field

# this is buggy.
def assay_status_field(selected=None, include_blank=False):
    field = {'value': selected or '',
             'options': SequenceGroup.status_display_options(include_blank=include_blank)}
    return field

def assay_condition_status_field(selected=None, include_blank=False):
    field = {'value': selected or '',
             'options': SequenceGroupCondition.status_display_options()}

    if include_blank:
        field['options'].insert(0, ('','--'))
    return field

class AssayFilterForm(Schema):
    allow_extra_fields = True
    filter_extra_fields = True

    owner_id = IntKeyValidator(Person, 'id', not_empty=False, if_missing=None)
    status   = formencode.validators.Int(not_empty=False, if_missing=None)
    type     = formencode.validators.Int(not_empty=False, if_missing=None)
    category = IntKeyValidator(SequenceGroupTag, 'id', not_empty=False, if_missing=None)
    since    = FormattedDateConverter(date_format='%Y/%m/%d', not_empty=False, if_missing=None)
    gene     = SanitizedString(not_empty=False, if_missing=None)

class AssaySearchForm(Schema):
    allow_extra_fields = True
    filter_extra_fields = True

    name = SanitizedString(not_empty=False, if_missing=None)
    gene = SanitizedString(not_empty=False, if_missing=None)

class AssayLocationForm(Schema):
    allow_extra_fields = True
    filter_extra_fields = True

    chromosome = Chromosome(not_empty=True)
    location   = formencode.validators.Int(not_empty=True, min=0)

class AssayFlowForm(Schema):
    allow_extra_fields = True
    filter_extra_fields = True

    submit           = SanitizedString(not_empty=False, if_missing=None)
    flow             = SanitizedString(not_empty=False, if_missing='default')

class AssayBasicForm(AssayFlowForm):
    name             = SanitizedString(not_empty=True, maxlength=50)
    gene             = SanitizedString(not_empty=False, maxlength=50)
    chemistry        = OneOfInt([k for k, v in SequenceGroup.chemistry_type_display_options()], not_empty=False, if_missing=SequenceGroup.CHEMISTRY_TYPE_TAQMAN)
    assay_type       = OneOfInt([k for k, v in SequenceGroup.assay_type_display_options()], not_empty=False, if_missing=None)
    tags             = formencode.ForEach(IntKeyValidator(SequenceGroupTag, 'id'), not_empty=False)
    assay_structure  = OneOfInt([k for k, v in SequenceGroup.kit_type_display_options()], not_empty=True)
    status           = OneOfInt([k for k, v in SequenceGroup.status_display_options()], not_empty=True)
    owner            = IntKeyValidator(Person, 'id', not_empty=False, if_missing=None)

class PrimerForm(Schema):
    allow_extra_fields = True
    filter_extra_fields = True

    sequence         = DNASequence(not_empty=True)
    primary          = formencode.ForEach(formencode.validators.Bool(not_empty=False, if_missing=False))

class UnknownPrimerForm(Schema):
    allow_extra_fields = True

    barcode_label    = SanitizedString(not_empty=True, maxlength=50)
    primary          = formencode.ForEach(formencode.validators.Bool(not_empty=False, if_missing=False))

    def __init__(self, *args, **kwargs):
        emptyval = kwargs.pop('if_empty', None)
        super(UnknownPrimerForm, self).__init__(*args, **kwargs)
        if emptyval is not None:
            self.fields['barcode_label'] = SanitizedString(not_empty=False, maxlength=50, if_empty=emptyval, if_missing=emptyval)


class ProbeForm(Schema):
    allow_extra_fields = True
    filter_extra_fields = True

    sequence         = DNASequence(not_empty=True)
    primary          = formencode.ForEach(formencode.validators.Bool(not_empty=False, if_missing=False))
    dye              = SanitizedString(not_empty=False)
    quencher         = SanitizedString(not_empty=False)

class UnknownProbeForm(Schema):
    allow_extra_fields = True
    filter_extra_fields = True

    barcode_label    = SanitizedString(not_empty=True, maxlength=50)
    primary          = formencode.ForEach(formencode.validators.Bool(not_empty=False, if_missing=False))
    dye              = SanitizedString(not_empty=False)
    quencher         = SanitizedString(not_empty=False)

    def __init__(self, *args, **kwargs):
        emptyval = kwargs.pop('if_empty', None)
        super(UnknownProbeForm, self).__init__(*args, **kwargs)
        if emptyval is not None:
            self.fields['barcode_label'] = SanitizedString(not_empty=False, maxlength=50, if_empty=emptyval, if_missing=emptyval)

class SNPPrimerForm(UnknownPrimerForm):
    allele           = SanitizedString(not_empty=False, maxlength=50)

class SNPProbeForm(UnknownProbeForm):
    allele           = SanitizedString(not_empty=False, maxlength=50)

class SinglePrimaryForm(formencode.ForEach):
    def attempt_convert(self, value, state, validate):
        entities = super(SinglePrimaryForm, self).attempt_convert(value, state, validate)
        found_primary = False
        for entity in entities:
            if entity['primary'] and found_primary:
                raise formencode.Invalid('There cannot be multiple primary elements selected.', value, state)
            elif entity['primary']:
                found_primary = True

        if not found_primary:
            entities[0]['primary'] = [True]

        return entities

class UniqueLabelPrimaryForm(formencode.ForEach):
    def attempt_convert(self, value, state, validate):
        entities = super(UniqueLabelPrimaryForm, self).attempt_convert(value, state, validate)
        label_names = dict()
        for entity in entities:
            if entity['barcode_label']:
                if entity['barcode_label'] in label_names:
                    raise formencode.Invalid('All labels must be unique.', value, state)
                else:
                    label_names[entity['barcode_label']] = 1

        return entities

class UniqueLabelSinglePrimaryForm(SinglePrimaryForm, UniqueLabelPrimaryForm):
    def attempt_convert(self, value, state, validate):
        # to check validation
        entities = UniqueLabelPrimaryForm.attempt_convert(self, value, state, validate)
        # to populate values
        return SinglePrimaryForm.attempt_convert(self, value, state, validate)

class DesignedAssayForm(AssayFlowForm):
    pre_validators   = [NestedVariables()]
    forward_primers  = SinglePrimaryForm(PrimerForm(), not_empty=True, if_missing=formencode.NoDefault)
    reverse_primers  = SinglePrimaryForm(PrimerForm(), not_empty=True, if_missing=formencode.NoDefault)
    probes           = SinglePrimaryForm(ProbeForm(), not_empty=False, if_missing=None)

class LocationAssayForm(AssayFlowForm):
    pre_validators   = [NestedVariables()]
    chromosome       = Chromosome(not_empty=True)
    location         = formencode.validators.Int(not_empty=True, min=1)
    amplicon_length  = formencode.validators.Int(not_empty=False, if_empty=100)
    forward_primers  = UniqueLabelSinglePrimaryForm(UnknownPrimerForm(if_empty='FP'), not_empty=True, if_missing=formencode.NoDefault)
    reverse_primers  = UniqueLabelSinglePrimaryForm(UnknownPrimerForm(if_empty='RP'), not_empty=True, if_missing=formencode.NoDefault)
    probes           = UniqueLabelSinglePrimaryForm(UnknownProbeForm(if_empty='Probe'), not_empty=False, if_missing=None)

class SNPAssayForm(AssayFlowForm):
    pre_validators   = [NestedVariables()]
    snp_rsid         = SNPName(not_empty=True)
    amplicon_length  = formencode.validators.Int(not_empty=False, if_empty=100)
    forward_primers  = UniqueLabelSinglePrimaryForm(SNPPrimerForm(if_empty='FP'), not_empty=True, if_missing=formencode.NoDefault)
    reverse_primers  = UniqueLabelSinglePrimaryForm(SNPPrimerForm(if_empty='RP'), not_empty=True, if_missing=formencode.NoDefault)
    probes           = UniqueLabelSinglePrimaryForm(SNPProbeForm(if_empty='Probe'), not_empty=False, if_missing=None)

class AssayNotesForm(AssayFlowForm):
    notes            = SanitizedString(not_empty=False, if_missing=None)
    reference_source = SanitizedString(not_empty=False, if_missing=None)


class CreateConditionForm(Schema):
    allow_extra_fields  = True
    filter_extra_fields = True

    status = formencode.validators.Int(not_empty=True)
    author_id = IntKeyValidator(Person, 'id', not_empty=True)
    plate_id = IntKeyValidator(Plate, 'id', not_empty=False, if_missing=None)
    wells = SanitizedString(not_empty=False, if_missing=None)
    optimal_temp = SanitizedString(not_empty=False, if_missing=None)
    custom_thermal_protocol = SanitizedString(not_empty=False, if_missing=None)
    mmix_standard_status = formencode.validators.Int(not_empty=False, if_missing=None)
    mmix_afree_status = formencode.validators.Int(not_empty=False, if_missing=None)
    mmix_1step_status = formencode.validators.Int(not_empty=False, if_missing=None)
    mmix_groove_status = formencode.validators.Int(not_empty=False, if_missing=None)
    notes = SanitizedString(not_empty=False, if_missing=None)

class CreateConditionPlateForm(Schema):
    allow_extra_fields  = True
    filter_extra_fields = True

    status = formencode.validators.Int(not_empty=True)
    assay_id = IntKeyValidator(SequenceGroup, 'id', not_empty=True)
    author_id = IntKeyValidator(Person, 'id', not_empty=True)
    wells = SanitizedString(not_empty=False, if_missing=None)
    optimal_temp = SanitizedString(not_empty=False, if_missing=None)
    custom_thermal_protocol = SanitizedString(not_empty=False, if_missing=None)
    mmix_standard_status = formencode.validators.Int(not_empty=False, if_missing=None)
    mmix_afree_status = formencode.validators.Int(not_empty=False, if_missing=None)
    mmix_1step_status = formencode.validators.Int(not_empty=False, if_missing=None)
    mmix_groove_status = formencode.validators.Int(not_empty=False, if_missing=None)
    notes = SanitizedString(not_empty=False, if_missing=None)


class SequenceController(BaseController):
    """
    Replacement controller for the assay controller, using the new
    sequence/sequence group model.
    """
    def __before__(self, action, **params):
        # TODO: revert to previous state if id already exists
        if request.POST.get('do_action', None) == 'Reset':
            flow = params.get('flow', None)
            if flow:
                if session.get(flow, None):
                    del session[flow]
            session['flash'] = 'Assay in progress cleared.'
            session.save()
            return redirect(url(controller='sequence', action='start', flow=flow))
        elif request.POST.get('do_action', None) == 'Revert':
            flow = params.get('flow', None)
            prev_id = None
            if flow:
                prev_id = session[flow].get('model_id', None)
                del session[flow]
            session['flash'] = 'Changes to assay reverted.'
            session.save()
            if prev_id:
                return redirect(url(controller='sequence', action='view_details', id=prev_id))
            else:
                return redirect(url(controller='sequence', action='list'))

        c.flow = params.get('flow', None)

    def __render_form_flow(self, response, flow):
        formvars = {'flow': flow}
        formvars.update(variable_encode_except(session.get(flow, {}), 'tags', add_repetitions=False))
        #raise Exception, formvars
        return h.render_bootstrap_form(response, defaults=formvars)

    def __setup_list_context(self):
        c.owners          = fl.person_field()
        c.tags            = fl.sequence_group_tag_field()
        c.assay_types     = assay_type_field()
        c.chemistry_types = assay_chemistry_field()
        c.statuses        = assay_status_field(include_blank=True)
        c.chromosomes     = fl.chromosome_field()
        c.all_assays      = fl.sequence_group_field(blank=True, include_without_amplicons=True, empty='')

    def __frontload_sequence_group_list_query(self, query):
        query = query.options(joinedload_all(SequenceGroup.owner),
                              joinedload_all(SequenceGroup.tags),
                              joinedload_all(SequenceGroup.conditions))
        return query

    def __form_to_list_query(self, form):
        query = active_sequence_group_query()
        if form['category'] is not None:
            tag = Session.query(SequenceGroupTag).get(form['category'])
            group_ids = [sg.id for sg in tag.sequence_groups]
            query = query.filter(SequenceGroup.id.in_(group_ids))
        if form['status'] is not None:
            query = query.filter(SequenceGroup.status == form['status'])
        if form['type'] is not None:
            query = query.filter(SequenceGroup.type == form['type'])
        if form['owner_id'] is not None:
            query = query.filter(SequenceGroup.owner_id == form['owner_id'])
        if form['since'] is not None:
            query = query.filter(and_(SequenceGroup.added != None,
                                      SequenceGroup.added >= form['since']))

        query = self.__frontload_sequence_group_list_query(query.order_by(SequenceGroup.name))
        return query

    def __form_to_search_query(self, form):
        query = active_sequence_group_query()
        if form['name'] is not None:
            query = query.filter(SequenceGroup.name.like('%%%s%%' % form['name']))
        if form['gene'] is not None:
            query = query.filter(SequenceGroup.gene.like('%%%s%%' % form['gene']))

        query = self.__frontload_sequence_group_list_query(query.order_by(SequenceGroup.name))
        return query

    def __form_to_locate_query(self, form, within=10000):
        location = form['location']
        query = active_sequence_group_query().join(Amplicon, AmpliconSequenceCache)\
                                            .filter(and_(AmpliconSequenceCache.chromosome == form['chromosome'],
                                                    or_(AmpliconSequenceCache.start_pos.between(location-10000, location+10000),
                                                        AmpliconSequenceCache.end_pos.between(location-10000, location+10000))))\
                                            .distinct()
        query = self.__frontload_sequence_group_list_query(query.order_by(SequenceGroup.name))
        return query

    def list(self):
        # TODO pagination
        self.__setup_list_context()
        query = active_sequence_group_query().order_by(SequenceGroup.name)
        query = self.__frontload_sequence_group_list_query(query)
        c.groups = query.all()
        c.tab    = 'list'
        response = render('/sequence/list.html')
        return h.render_bootstrap_form(response)

    @validate(schema=AssayFilterForm(), form='list', post_only=False, on_get=True)
    def list_filter(self):
        # TODO pagination
        self.__setup_list_context()
        c.groups = self.__form_to_list_query(self.form_result).all()
        c.tab    = 'list'
        response = render('/sequence/list.html')
        # TODO: need to do from_python?
        return h.render_bootstrap_form(response, defaults=AssayFilterForm.from_python(self.form_result))

    @validate(schema=AssaySearchForm(), form='list', post_only=False, on_get=True)
    def list_search(self):
        # TODO pagination
        self.__setup_list_context()
        c.groups = self.__form_to_search_query(self.form_result).all()
        c.tab    = 'search'
        response = render('/sequence/list.html')
        # TODO: need to do from_python?
        return h.render_bootstrap_form(response, defaults=AssaySearchForm.from_python(self.form_result))

    def approved_list(self):
        self.__setup_list_context()
        query = active_sequence_group_query().filter_by(approved_for_release=True).order_by(SequenceGroup.name)
        query = self.__frontload_sequence_group_list_query(query)
        c.groups = query.all()
        c.tab    = 'list'
        response = render('/sequence/approved_list.html')
        return h.render_bootstrap_form(response)

    def _list_locate_base(self):
        self.__setup_list_context()
        c.tab = 'locate'
        c.groups = []
        return render('/sequence/list.html')

    @validate(schema=AssayLocationForm(), form='_list_locate_base', post_only=False, on_get=True, error_formatters=h.tw_bootstrap_error_formatters)
    def list_locate(self):
        # TODO pagination
        self.__setup_list_context()
        c.groups = self.__form_to_locate_query(self.form_result).all()
        c.tab    = 'locate'
        response = render('/sequence/list.html')
        # TODO: need to do from_python?
        return h.render_bootstrap_form(response, defaults=AssayLocationForm.from_python(self.form_result))

    # sequence flow methods
    def start(self, id=None, flow='sequence.new'):
        response = self._start_base(flow)
        return self.__render_form_flow(response, flow)

    def load(self, id=None):
        # TODO: signal something if deleted?
        model = Session.query(SequenceGroup).get(id)
        if not model:
            # TODO add session flash
            return redirect(url(controller='sequence', action='start', flow='sequence.new'))
        else:
            self.__model_to_session('sequence.edit', model)
            session['sequence.edit']['model_id'] = id
            session['sequence.edit']['save_target'] = True
            session['sequence.edit']['save_notes'] = True
            session.save()
            return redirect(url(controller='sequence', action='start', flow='sequence.edit'))

    def _start_base(self, flow):
        c.assay_types = assay_type_field()
        c.tags = fl.sequence_group_tag_field()
        c.assay_structure = assay_structure_field()
        c.owner = fl.person_field()
        c.chemistry = assay_chemistry_field()
        c.statuses = assay_status_field()
        return render('/sequence/start.html')

    @restrict('POST')
    @validate(schema=AssayBasicForm, form='_start_base', error_formatters=h.tw_bootstrap_error_formatters)
    def save_start(self, flow='sequence.new'):
        # TODO: store flow on session itself after this?
        if flow == 'sequence.new' and not session.get(flow):
            session[flow] = dict()
        elif flow == 'sequence.edit' and session[flow]['name'] != self.form_result['name']:
            ######
            # Signal a name change on save
            ######
            session[flow]['name_change'] = True

        session[flow]['name']            = self.form_result['name']
        session[flow]['gene']            = self.form_result['gene']
        session[flow]['chemistry']       = self.form_result['chemistry']
        session[flow]['assay_type']      = self.form_result['assay_type']
        session[flow]['tags']            = self.form_result['tags']
        session[flow]['assay_structure'] = self.form_result['assay_structure']
        session[flow]['owner']           = self.form_result['owner']
        session[flow]['status']          = self.form_result['status']

        # in case assay renamed (must rename component labels)
        if session[flow].get('name_change', False):
            self.__apply_component_labels(flow, overwrite_existing=True)
        session.save()

        save_now = request.params.get('save_now', None)
        if flow != 'sequence.new' and save_now:
            return self.__save_assay_now(flow)
        else:
            return redirect(url(controller='sequence', action='components', flow=flow))

    # may not be the right abstraction for now, but we'll work with it
    @flash_if_form_errors()
    def _dispatch_component(self, flow='sequence.new'):
        c.assay_dye_types = fl.assay_dye_field()
        c.assay_quencher_types = fl.assay_quencher_field()
        c.include_probes = session[flow]['chemistry'] == SequenceGroup.CHEMISTRY_TYPE_TAQMAN
        c.chromosomes = fl.chromosome_field()
        templates = {SequenceGroup.TYPE_DESIGNED: '/sequence/designed.html',
                     SequenceGroup.TYPE_SNP: '/sequence/snp.html',
                     SequenceGroup.TYPE_LOCATION: '/sequence/location.html'}
        return render(templates[session[flow]['assay_structure']])

    @session_validate_flow('name', fallback='start')
    def components(self, flow='sequence.new'):
        #raise Exception, session['sequence.new']
        populate_multiform_context(self, session[flow])
        response = self._dispatch_component(flow)
        self.__init_component_fields(flow)
        return self.__render_form_flow(response, flow)

    def __clear_component_fields(self, flow):
        for var in ('forward_primers', 'reverse_primers', 'probes', 'chromosome', 'location', 'amplicon_length', 'snp_rsid'):
            if var in session[flow]:
                del session[flow][var]

    def __init_component_fields(self, flow, include_probes=True):
        if not 'forward_primers' in session[flow]:
            session[flow]['forward_primers'] = [dict()]
        if not 'reverse_primers' in session[flow]:
            session[flow]['reverse_primers'] = [dict()]
        if session[flow].get('chemistry', None) != SequenceGroup.CHEMISTRY_TYPE_SYBR and not 'probes' in session[flow]:
            session[flow]['probes'] = [dict()]
        self.__apply_component_labels(flow)

    def __apply_component_labels(self, flow, overwrite_existing=False):
        for role, collection in ((SequenceGroupComponent.FORWARD_PRIMER, 'forward_primers'),
                                 (SequenceGroupComponent.REVERSE_PRIMER, 'reverse_primers'),
                                 (SequenceGroupComponent.PROBE, 'probes')):
            if session[flow].get(collection, None) is not None:
                for idx, component in enumerate(session[flow][collection]):
                    if overwrite_existing or component.get('barcode_label', None) is None:
                        if role == SequenceGroupComponent.PROBE:
                            component['barcode_label'] = SequenceGroupComponent.create_label(session[flow]['name'],
                                                                                  role, idx, component.get('dye', ''), component.get('quencher',''))
                        else:
                            component['barcode_label'] = SequenceGroupComponent.create_label(session[flow]['name'],
                                                                                  role, idx)


    @restrict('POST')
    @multi_validate(schema=DesignedAssayForm, form='_dispatch_component', error_formatters=h.tw_bootstrap_alert_error_formatters)
    def save_designed(self, flow='sequence.new'):
        self.__clear_component_fields(flow)
        session[flow]['forward_primers'] = self.form_result['forward_primers']
        session[flow]['reverse_primers'] = self.form_result['reverse_primers']
        session[flow]['probes']          = self.form_result['probes']
        session[flow]['save_target']     = True
        self.__apply_component_labels(flow)

        # TODO this could be smarter (detect actual primer change) but ignore for now
        session[flow]['sequence_change'] = True
        session.save()

        save_now = request.params.get('save_now', None)
        if flow != 'sequence.new' and save_now:
            return self.__save_assay_now(flow)
        else:
            return redirect(url(controller='sequence', action='notes', flow=flow))

    @restrict('POST')
    @multi_validate(schema=LocationAssayForm, form="_dispatch_component", error_formatters=h.tw_bootstrap_alert_error_formatters)
    def save_location(self, flow='sequence.new'):
        self.__clear_component_fields(flow)
        session[flow]['forward_primers'] = self.form_result['forward_primers']
        session[flow]['reverse_primers'] = self.form_result['reverse_primers']
        session[flow]['probes']          = self.form_result['probes']
        session[flow]['chromosome']      = self.form_result['chromosome']
        session[flow]['location']        = self.form_result['location']
        session[flow]['amplicon_length'] = self.form_result['amplicon_length']
        session[flow]['save_target']     = True
        session[flow]['sequence_change'] = True
        session.save()

        save_now = request.params.get('save_now', None)
        if flow != 'sequence.new' and save_now:
            return self.__save_assay_now(flow)
        else:
            return redirect(url(controller='sequence', action='notes', flow=flow))

    @restrict('POST')
    @multi_validate(schema=SNPAssayForm, form='_dispatch_component', error_formatters=h.tw_bootstrap_alert_error_formatters)
    def save_snp(self, flow='sequence.new'):
        self.__clear_component_fields(flow)
        session[flow]['forward_primers'] = self.form_result['forward_primers']
        session[flow]['reverse_primers'] = self.form_result['reverse_primers']
        session[flow]['probes']          = self.form_result['probes']
        session[flow]['snp_rsid']        = self.form_result['snp_rsid']
        session[flow]['amplicon_length'] = self.form_result['amplicon_length']
        session[flow]['save_target']     = True
        session[flow]['sequence_change'] = True
        session.save()

        save_now = request.params.get('save_now', None)
        if flow != 'sequence.new' and save_now:
            return self.__save_assay_now(flow)
        else:
            return redirect(url(controller='sequence', action='notes', flow=flow))

    def _notes_base(self):
        return render('/sequence/notes.html')

    @session_validate_flow('save_target', fallback='start')
    def notes(self, flow='sequence.new'):
        response = self._notes_base()
        return self.__render_form_flow(response, flow)

    @restrict('POST')
    @validate(schema=AssayNotesForm, form='_notes_base', error_formatters=h.tw_bootstrap_error_formatters)
    def save_notes(self, flow='sequence.new'):
        session[flow]['notes'] = self.form_result['notes']
        session[flow]['reference_source'] = self.form_result['reference_source']
        session[flow]['save_notes'] = True
        session.save()

        save_now = request.params.get('save_now', None)
        if flow != 'sequence.new' and save_now:
            return self.__save_assay_now(flow)
        else:
            return redirect(url(controller='sequence', action='review', flow=flow))

    def __setup_review_context(self, flow):
        c.assay_structure = session[flow]['assay_structure']
        c.show_primer_table = c.assay_structure == SequenceGroup.TYPE_DESIGNED
        c.show_location_table = c.assay_structure == SequenceGroup.TYPE_LOCATION
        c.show_snp_table = c.assay_structure == SequenceGroup.TYPE_SNP
        c.assay = AttrDict(session[flow])
        if c.assay.owner:
            c.owner = Session.query(Person).get(c.assay.owner)
        else:
            c.owner = None
        c.assay_type = fl.field_display_value(assay_type_field(selected=session[flow]['assay_type']))
        if session[flow]['tags']:
            c.tags = Session.query(SequenceGroupTag).filter(SequenceGroupTag.id.in_(session[flow]['tags'])).order_by(SequenceGroupTag.name).all()
        else:
            c.tags = []
        c.status = dict(SequenceGroup.status_display_options()).get(session[flow]['status'], h.literal('&nbsp;'))
        c.chemistry_type = dict(SequenceGroup.chemistry_type_display_options()).get(session[flow]['chemistry'], h.literal('&nbsp;'))

        if c.show_location_table:
            c.chromosome      = session[flow]['chromosome']
            c.location        = session[flow]['location']
            c.amplicon_length = session[flow]['amplicon_length']

        if c.show_snp_table:
            c.snp_rsid        = session[flow]['snp_rsid']
            c.amplicon_length = session[flow]['amplicon_length']


    def _review_base(self, flow):
        self.__setup_review_context(flow)
        return render('/sequence/review.html')

    @session_validate_flow('save_notes', fallback='start')
    def review(self, flow='sequence.new'):
        response = self._review_base(flow)
        return self.__render_form_flow(response, flow)

    def __model_to_session(self, key, model):
        """
        Loads a model into the session.
        """
        if not key in session:
            session[key] = dict()

        session[key]['name']             = model.name
        session[key]['owner']            = model.owner_id
        session[key]['gene']             = model.gene
        session[key]['assay_type']       = model.type
        session[key]['assay_structure']  = model.kit_type
        session[key]['notes']            = model.notes
        session[key]['chemistry']        = model.chemistry_type
        session[key]['reference_source'] = model.reference_source
        session[key]['status']           = model.status
        session[key]['added']            = model.added
        session[key]['approved_for_release'] = model.approved_for_release

        if model.snp_rsid is not None:
            session[key]['snp_rsid']     = model.snp_rsid
        if model.location_chromosome is not None:
            session[key]['chromosome']   = model.location_chromosome
            session[key]['location']     = model.location_base

        if model.amplicon_length is not None:
            session[key]['amplicon_length'] = model.amplicon_length

        session[key]['tags']         = [p.id for p in model.tags]
        session[key]['forward_primers']  = []
        session[key]['reverse_primers']  = []
        session[key]['probes']           = []

        fps = session[key]['forward_primers']
        for fp in model.forward_primers:
            fps.append({'sequence'      : fp.sequence.sequence if fp.sequence else None,
                        'primary'       : [True] if fp.primary else [],
                        'barcode_label' : fp.barcode_label,
                        'allele'        : fp.snp_allele})

        rps = session[key]['reverse_primers']
        for rp in model.reverse_primers:
            rps.append({'sequence'      : rp.sequence.sequence if rp.sequence else None,
                        'primary'       : [True] if rp.primary else [],
                        'barcode_label' : rp.barcode_label,
                        'allele'        : rp.snp_allele})

        ps = session[key]['probes']
        for p in model.probes:
            ps.append({'sequence'      : p.sequence.sequence if p.sequence else None,
                       'primary'       : [True] if p.primary else [],
                       'dye'           : p.dye,
                       'quencher'      : p.quencher,
                       'barcode_label' : p.barcode_label,
                       'allele'        : p.snp_allele})


    def __session_to_model(self, key, model=None):
        """
        puts the session parameters on the model.  YIKES.

        just assume new for now to make it work, we'll see how it evolves.
        """
        # if session[sequence.new]['sequence_changed']
        # delete existing sequences
        # mark as job to be done
        if not model:
            model = SequenceGroup()
            Session.add(model)

        model.name             = session[key]['name']
        model.owner_id         = session[key]['owner']
        model.gene             = session[key]['gene']
        model.kit_type         = session[key]['assay_structure']
        model.type             = session[key]['assay_type']
        model.chemistry_type   = session[key]['chemistry']
        model.status           = session[key]['status']

        model.notes            = session[key]['notes']
        model.reference_source = session[key]['reference_source']

        if model.kit_type == SequenceGroup.TYPE_SNP:
            model.snp_rsid            = session[key]['snp_rsid']
        else:
            model.snp_rsid            = None

        if model.kit_type == SequenceGroup.TYPE_LOCATION:
            model.location_chromosome = session[key]['chromosome']
            model.location_base       = session[key]['location']
        else:
            model.location_chromosome = None
            model.location_base       = None

        # TODO SNP bug here, I believe
        if model.kit_type in (SequenceGroup.TYPE_SNP, SequenceGroup.TYPE_LOCATION):
            model.amplicon_length     = session[key]['amplicon_length']

        model.tags = []
        for tag_id in session[key]['tags']:
            tag = Session.query(SequenceGroupTag).get(tag_id)
            model.tags.append(tag)

        # only change if marked as changed
        if session[key].get('sequence_change', False):
            sequence_group_unlink_sequences(model)

            for idx, fp in enumerate(session[key]['forward_primers']):
                if fp.get('sequence', None):
                    seq = Sequence(sequence=fp['sequence'],
                                   strand='+')
                    seqc = SequenceGroupComponent(sequence=seq,
                                                  role=SequenceGroupComponent.FORWARD_PRIMER,
                                                  barcode_label=fp['barcode_label'],
                                                  primary=fp['primary'] and True or False,
                                                  order=idx,
                                                  snp_allele=fp.get('allele', None))
                else:
                    seqc = SequenceGroupComponent(role=SequenceGroupComponent.FORWARD_PRIMER,
                                                  barcode_label=fp['barcode_label'],
                                                  primary=fp['primary'] and True or False,
                                                  order=idx,
                                                  snp_allele=fp.get('allele', None))
                model.forward_primers.append(seqc)

            for idx, rp in enumerate(session[key]['reverse_primers']):
                if rp.get('sequence', None):
                    seq = Sequence(sequence=rp['sequence'],
                                   strand='-')
                    seqc = SequenceGroupComponent(sequence=seq,
                                                  role=SequenceGroupComponent.REVERSE_PRIMER,
                                                  barcode_label=rp['barcode_label'],
                                                  primary=rp['primary'] and True or False,
                                                  order=idx,
                                                  snp_allele=rp.get('allele', None))
                else:
                    seqc = SequenceGroupComponent(role=SequenceGroupComponent.REVERSE_PRIMER,
                                                  barcode_label=rp['barcode_label'],
                                                  primary=rp['primary'] and True or False,
                                                  order=idx,
                                                  snp_allele=rp.get('allele', None))
                model.forward_primers.append(seqc)

            if session[key]['probes']: # SYBR case
                for idx, p in enumerate(session[key]['probes']):
                    if p.get('sequence', None):
                        seq = Sequence(sequence=p['sequence'],
                                       strand='+')
                        seqc = SequenceGroupComponent(sequence=seq,
                                                      role=SequenceGroupComponent.PROBE,
                                                      primary=p['primary'] and True or False,
                                                      dye=p['dye'],
                                                      quencher=p['quencher'],
                                                      barcode_label=p['barcode_label'],
                                                      order=idx,
                                                      snp_allele=p.get('allele', None))
                    else:
                        seqc = SequenceGroupComponent(role=SequenceGroupComponent.PROBE,
                                                      primary=p['primary'] and True or False,
                                                      dye=p['dye'],
                                                      quencher=p['quencher'],
                                                      barcode_label=p['barcode_label'],
                                                      order=idx,
                                                      snp_allele=p.get('allele', None))
                    model.probes.append(seqc)
        elif session[key].get('name_change', False):
            #####
            # If the name of the assay has been changed, rename the oligos.
            #####
            for sfp, fp in zip(session[key]['forward_primers'], model.forward_primers):
                fp.barcode_label = sfp['barcode_label']
            for srp, rp in zip(session[key]['reverse_primers'], model.reverse_primers):
                rp.barcode_label = srp['barcode_label']
            for sp, p in zip(session[key]['probes'], model.probes):
                p.barcode_label = sp['barcode_label']


        Session.merge(model)
        return model


    @restrict('POST')
    @session_validate_flow('save_notes', fallback='start')
    def save_assay(self, flow='sequence.new'):
        return self.__save_assay_now(flow)

    def __save_assay_now(self, flow):
        try:
            if session[flow].get('model_id'):
                prev = Session.query(SequenceGroup).get(session[flow]['model_id'])
                model = self.__session_to_model(flow, prev)
            else:
                model = self.__session_to_model(flow)
            Session.commit()

            if session[flow].get('sequence_change', False):
                self.__start_process_job(model)
            Session.commit()
            session['flash'] = "Assay saved."
            del session[flow]
            session.save()
            return redirect(url(controller='sequence', action='view_details', id=model.id))
        except IntegrityError, e:
            # TODO handle this beforehand
            Session.rollback()
            session['flash'] = 'There is already an assay saved with this name.'
            session['flash_class'] = "error"
            session.save()
            return redirect(url(controller='sequence', action='start', flow=flow))

    def __load_view_context(self, id):
        if id is None:
            abort(404)

        group = Session.query(SequenceGroup).get(int(id))
        if not group:
            abort(404)

        c.sequence_group = group

    # hrm.
    def view(self, id=None):
        return self.view_details(id=id)

    def view_details(self, id=None):
        self.__load_view_context(id)
        self.__model_to_session('sequence.view', c.sequence_group)
        c.tab = 'details'
        self.__setup_review_context('sequence.view')
        response = render('/sequence/view_details.html')
        return h.render_bootstrap_form(response)

    def view_sequences(self, id=None):
        self.__load_view_context(id)

        c.tab = 'sequences'
        c.display_mode = 'transcript' if c.sequence_group.type == SequenceGroup.ASSAY_TYPE_GEX else 'amplicon'
        c.sequences = []
        c.transcripts = []
        if c.sequence_group.analyzed:
            if c.sequence_group.type == SequenceGroup.ASSAY_TYPE_GEX:
                transcripts = transcript_sequences_snps_for_group(c.sequence_group)
                same_genome_transcripts = groupinto(transcripts, operator.attrgetter('exon_span_string'))
                for exon_span, ts in same_genome_transcripts:
                    for t in ts:
                        t.positive_display_sequence = t.positive_genomic_strand_sequence.lower()
                        t.negative_display_sequence = t.negative_genomic_strand_sequence.lower()[::-1]
                c.transcripts = same_genome_transcripts
                c.primer_amplicons = True

            else:
                amplicons = pcr_sequences_snps_for_group(c.sequence_group)

                for amp, pseqs in amplicons:
                    for pseq in pseqs:
                        pseq.positive_display_sequence = pseq.amplicon.positive_strand_sequence.lower()
                        pseq.negative_display_sequence = pseq.amplicon.negative_strand_sequence.lower()[::-1]

                sequences = []
                for amp, pseqs in amplicons:
                    sequences.extend(pseqs)

                if c.sequence_group.kit_type == SequenceGroup.TYPE_DESIGNED:
                    c.primer_amplicons = True
                else:
                    c.primer_amplicons = False
                c.sequences = sorted(sequences, key=operator.attrgetter('chromosome', 'start'))
        else:
            c.pending_job = None
            cm = get_manager_from_pylonsapp_context()
            job_queue = cm.jobqueue()
            if c.sequence_group.pending_job_id:
                job = job_queue.by_uid(c.sequence_group.pending_job_id)
                if job:
                    c.pending_job = job

        response = render('/sequence/view_sequences.html')
        return h.render_bootstrap_form(response)

    def view_validation(self, id=None):
        self.__load_view_context(id)

        c.tab = 'validation'
        c.display_mode = 'transcript' if c.sequence_group.type == SequenceGroup.ASSAY_TYPE_GEX else 'amplicon'
        c.snp_mode = c.sequence_group.type == SequenceGroup.ASSAY_TYPE_SNP

        c.sequences = []
        c.transcripts = []
        # TODO: presentation assumes single primer-probe combo (one amplicon)
        if c.sequence_group.analyzed:
            if c.sequence_group.type == SequenceGroup.ASSAY_TYPE_GEX:
                transcripts = c.sequence_group.transcripts
                same_genome_transcripts = groupinto(transcripts, operator.attrgetter('exon_regions'))
                c.transcripts = same_genome_transcripts
            else:
                amplicons = c.sequence_group.amplicons
                sequences = []
                for amp in amplicons:
                    sequences.extend(amp.cached_sequences)

                c.sequences = sorted(sequences, key=operator.attrgetter('chromosome', 'start_pos'))

        if h.wowo('show_sequence_validation'):
            response = render('/sequence/view_validation_heuristic.html')
        else:
            response = render('/sequence/view_validation.html')
        #
        #
        # VALIDATION RULES
        #
        # primer-primer interaction
        # primer-rest of ampl interaction
        # use comp_seq
        #
        # >=8 consec R
        # >=6 consec Y
        #
        # GENOMIC REGIONS
        # CNV OK, else >1 yellow
        #
        # look for uniqueness of 12bp primers on either end (ask Ryan)
        return h.render_bootstrap_form(response)

    def view_plates(self, id=None):
        self.__load_view_context(id)
        c.tab = 'plates'
        # TODO paginate here -- expensive query, methinks
        query = Session.query(QLBPlate.plate_id,
                              func.count(distinct(QLBWell.id))).\
                        join(QLBWell, QLBWellChannel).\
                        filter(QLBWellChannel.sequence_group_id == c.sequence_group.id).\
                        group_by(QLBWell.plate_id).\
                        order_by(desc(QLBPlate.host_datetime))

        counts = query.all()
        plates = Session.query(Plate).\
                         filter(Plate.id.in_([plate_id for plate_id, num in counts])).\
                         order_by(desc(Plate.run_time)).all()

        plate_counts = dict(counts)
        c.plate_counts = [(plate, plate_counts[plate.id]) for plate in plates]
        response = render('/sequence/view_plates.html')
        return h.render_bootstrap_form(response)

    def view_conditions(self, id=None):
        self.__load_view_context(id)
        c.tab = 'conditions'
        response = render('/sequence/view_conditions.html')
        return h.render_bootstrap_form(response)

    @restrict('POST')
    def delete(self, id=None):
        self.__load_view_context(id)

        c.sequence_group.deleted = True
        Session.commit()
        session['flash'] = '%s has been marked as deleted.  It will no longer appear in assay lists.' % c.sequence_group.name
        session.save()
        return redirect(url(controller='sequence', action='list'))

    def __start_process_job(self, model):
        model.analyzed = False
        Session.commit()
        cm = get_manager_from_pylonsapp_context()
        job_queue = cm.jobqueue()
        job = job_queue.add(JOB_ID_PROCESS_ASSAY, ProcessSequenceGroupMessage(model.id))
        model.pending_job_id = job.id
        Session.commit()


    """
    Assay conditions
    """
    def _add_condition_base(self, id=None):
        self.__load_view_context(id)
        c.person_field = fl.person_field()
        c.condition_status_field = assay_condition_status_field()
        c.mmix_standard_status_field = assay_condition_status_field(include_blank=True)
        c.mmix_afree_status_field = assay_condition_status_field(include_blank=True)
        c.mmix_1step_status_field = assay_condition_status_field(include_blank=True)
        c.mmix_groove_status_field = assay_condition_status_field(include_blank=True)

        return render('/sequence/add_condition.html')

    def add_condition(self, id=None):
        self.__load_view_context(id)
        c.action = 'create_condition'
        c.call_to_action = 'Add Condition'
        c.target_id = id
        c.plate = None
        return h.render_bootstrap_form(self._add_condition_base(id), defaults={'plate_id': c.plate.id if c.plate else None})

    def __load_condition_context(self, id):
        if id is None:
            abort(404)

        cond = Session.query(SequenceGroupCondition).get(int(id))
        if not cond:
            abort(404)

        c.condition = cond

    def _edit_condition_base(self, id=None):
        self.__load_condition_context(id)
        if c.condition.plate_id:
            c.plate = Session.query(Plate).get(c.condition.plate_id)
        else:
            c.plate = None

        c.action = 'update_condition'
        c.call_to_action = 'Edit Condition'
        response = self._add_condition_base(c.condition.sequence_group.id)
        return response

    def edit_condition(self, id=None):
        c.target_id = id
        response = self._edit_condition_base(id)
        defaults = {'plate_id': c.plate.id if c.plate else None}
        defaults.update(c.condition.__dict__)
        return h.render_bootstrap_form(response, defaults=defaults)

    def _add_condition_plate_base(self, id=None):
        if id is None:
            abort(404)

        c.plate = Session.query(Plate).get(int(id))
        if not c.plate:
            abort(404)


        c.assays = fl.sequence_group_field(blank=True, include_without_amplicons=True, selected=request.params.get('assay', None))
        c.person_field = fl.person_field()
        c.condition_status_field = assay_condition_status_field()
        c.mmix_standard_status_field = assay_condition_status_field(include_blank=True)
        c.mmix_afree_status_field = assay_condition_status_field(include_blank=True)
        c.mmix_1step_status_field = assay_condition_status_field(include_blank=True)
        c.mmix_groove_status_field = assay_condition_status_field(include_blank=True)

        return render('/sequence/add_condition_plate.html')

    def add_condition_plate(self, id=None):
        c.action = 'create_condition_plate'
        c.target_id = id
        c.call_to_action = 'Add Condition'
        return h.render_bootstrap_form(self._add_condition_plate_base(id), defaults={'plate_id': c.plate.id})



    @restrict('POST')
    @validate(schema=CreateConditionForm(), form='_add_condition_base', error_formatters=h.tw_bootstrap_error_formatters)
    def create_condition(self, id=None):
        self.__load_view_context(id)
        cond = SequenceGroupCondition(author_id=self.form_result['author_id'],
                                      plate_id=self.form_result['plate_id'],
                                      status=self.form_result['status'],
                                      optimal_temp=self.form_result['optimal_temp'],
                                      custom_thermal_protocol=self.form_result['custom_thermal_protocol'],
                                      mmix_standard_status=self.form_result['mmix_standard_status'],
                                      mmix_afree_status=self.form_result['mmix_afree_status'],
                                      mmix_1step_status=self.form_result['mmix_1step_status'],
                                      mmix_groove_status=self.form_result['mmix_groove_status'],
                                      notes=self.form_result['notes'],
                                      wells=self.form_result['wells'])
        c.sequence_group.conditions.append(cond)
        Session.add(c.sequence_group)
        Session.commit()
        session['flash'] = "Condition added."
        session.save()
        return redirect(url(controller='sequence', action='view_conditions', id=c.sequence_group.id))

    @restrict('POST')
    @validate(schema=CreateConditionPlateForm(), form='_add_condition_plate_base', error_formatters=h.tw_bootstrap_error_formatters)
    def create_condition_plate(self, id=None):
        #self.__load_view_context(id)
        sg = Session.query(SequenceGroup).get(self.form_result['assay_id'])
        if not sg:
            abort(404)

        plate = Session.query(Plate).get(int(id))
        if not plate:
            abort(404)

        cond = SequenceGroupCondition(author_id=self.form_result['author_id'],
                                      plate_id=plate.id,
                                      status=self.form_result['status'],
                                      optimal_temp=self.form_result['optimal_temp'],
                                      custom_thermal_protocol=self.form_result['custom_thermal_protocol'],
                                      mmix_standard_status=self.form_result['mmix_standard_status'],
                                      mmix_afree_status=self.form_result['mmix_afree_status'],
                                      mmix_1step_status=self.form_result['mmix_1step_status'],
                                      mmix_groove_status=self.form_result['mmix_groove_status'],
                                      notes=self.form_result['notes'],
                                      wells=self.form_result['wells'])
        sg.conditions.append(cond)
        Session.add(sg)
        Session.commit()
        session['flash'] = "Condition added."
        session.save()
        return redirect(url(controller='sequence', action='view_conditions', id=sg.id))

    @restrict('POST')
    @validate(schema=CreateConditionForm(), form='_edit_condition_base', error_formatters=h.tw_bootstrap_error_formatters)
    def update_condition(self, id=None):
        self.__load_condition_context(id)
        c.condition.author_id = self.form_result['author_id']
        c.condition.plate_id = self.form_result['plate_id']
        c.condition.status = self.form_result['status']
        c.condition.optimal_temp = self.form_result['optimal_temp']
        c.condition.custom_thermal_protocol = self.form_result['custom_thermal_protocol']
        c.condition.mmix_standard_status = self.form_result['mmix_standard_status']
        c.condition.mmix_afree_status = self.form_result['mmix_afree_status']
        c.condition.mmix_1step_status = self.form_result['mmix_1step_status']
        c.condition.mmix_groove_status = self.form_result['mmix_groove_status']
        c.condition.notes = self.form_result['notes']
        c.condition.wells = self.form_result['wells']
        Session.commit()
        session['flash'] = "Condition updated."
        session.save()
        return redirect(url(controller='sequence', action='view_conditions', id=c.condition.sequence_group.id))

