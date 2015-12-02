import logging

from pylons import request, response, session, tmpl_context as c, url
from pylons.controllers.util import abort, redirect
from pylons.decorators import validate
from pylons.decorators.rest import restrict

from qtools.lib.base import BaseController, render
from qtools.lib.validators import IntKeyValidator
from qtools.model import Session, Sample, Person, Assay, Plate, AssaySampleCNV

import qtools.lib.fields as fl
import qtools.lib.helpers as h
import formencode

log = logging.getLogger(__name__)

class SampleForm(formencode.Schema):
    allow_extra_fields = True
    filter_extra_fields = True

    name = formencode.validators.String(not_empty=True)
    source = formencode.validators.String(not_empty=False)
    sex = formencode.validators.String(not_empty=False)
    ethnicity = formencode.validators.String(not_empty=False)
    notes = formencode.validators.String(not_empty=False)
    person_id = IntKeyValidator(Person, "id", not_empty=True)


class SampleAssayCNVForm(formencode.Schema):
    allow_extra_fields = True
    filter_extra_fields = True

    sample_id = IntKeyValidator(Sample, "id", not_empty=True)
    target_assay_id = IntKeyValidator(Assay, "id", not_empty=True)
    reference_assay_id = IntKeyValidator(Assay, "id", not_empty=False)
    cnv = formencode.validators.Int(min=1, not_empty=True)
    source_plate_id = IntKeyValidator(Plate, "id", not_empty=False)
    source_external_url = formencode.validators.String(not_empty=False)
    notes = formencode.validators.String(not_empty=False)
    author_id = IntKeyValidator(Person, "id", not_empty=True)

class SampleController(BaseController):

    def new(self):
        sex_field = fl.sex_field()
        ethnicity_field = fl.ethnicity_field()
        person_field = fl.person_field()
        c.form = h.LiteralFormSelectPatch(
            value = {'sex': sex_field['value'],
                     'ethnicity': ethnicity_field['value'],
                     'person_id': person_field['value']},
            option = {'sex': sex_field['options'],
                      'ethnicity': ethnicity_field['options'],
                      'person_id': person_field['options']}
        )

        return render('/sample/new.html')

    @restrict('POST')
    @validate(schema=SampleForm(), form='new')
    def create(self):
        sample = Sample()
        for k, v in self.form_result.items():
            setattr(sample, k, v)
        Session.add(sample)
        Session.commit()
        # TODO: add flash msg?
        redirect(url(controller='sample', action='view', id=sample.id))

    @restrict('POST')
    @validate(schema=SampleForm(), form='edit')
    def save(self, id=None):
        if id is None:
            abort(404)

        sample = Session.query(Sample).get(id)
        if not sample:
            abort(404)

        for k, v in self.form_result.items():
            if k not in ('id',):
                setattr(sample, k, v)
        Session.commit()
        redirect(url(controller='sample', action='view', id=sample.id))


    def edit(self, id=None):
        if not id:
            abort(404)

        sample = Session.query(Sample).get(id)
        if not sample:
            abort(404)

        c.sample = sample
        sex_field = fl.sex_field(sample.sex)
        ethnicity_field = fl.ethnicity_field(sample.ethnicity)
        person_field = fl.person_field(sample.person_id)

        c.form = h.LiteralFormSelectPatch(
            value = {'name': c.sample.name,
                     'source': c.sample.source,
                     'sex': sex_field['value'],
                     'ethnicity': ethnicity_field['value'],
                     'person_id': unicode(person_field['value']),
                     'notes': c.sample.notes},
            option = {'sex': sex_field['options'],
                      'ethnicity': ethnicity_field['options'],
                      'person_id': person_field['options']}
        )

        return render('/sample/edit.html')

    def view(self, id=None):
        if not id:
            abort(404)

        sample = Session.query(Sample).get(id)
        if not sample:
            abort(404)

        c.sample = sample
        return render('/sample/view.html')

    @restrict('POST')
    def delete(self, id=None):
        if id is not None:
            sample = Session.query(Sample).get(id)
            if sample:
                # TODO: add flash message -- sample deleted
                # TODO: clear out any referring rows
                Session.delete(sample)
                Session.commit()
        redirect(url(controller='sample', action='list'))

    def list(self):
        # TODO: paginate
        samples = Session.query(Sample).order_by(Sample.name).all()
        c.samples = samples

        return render('/sample/list.html')

    def cnv_new(self):
        sample_field = fl.sample_field(blank=True, selected=request.params.get('sample_id', None))
        target_assay_field = fl.assay_field(blank=True, selected=request.params.get('assay_id', None))
        reference_assay_field = fl.assay_field(blank=True)
        author_field = fl.person_field()

        c.plate = None
        if request.params.get('plate_id', None):
            plate = Session.query(Plate).get(int(request.params.get('plate_id')))
            if plate:
                c.plate = plate

        c.form = h.LiteralFormSelectPatch(
            value = {'sample_id': sample_field['value'],
                     'target_assay_id': target_assay_field['value'],
                     'reference_assay_id': reference_assay_field['value'],
                     'author_id': author_field['value']},
            option = {'sample_id': sample_field['options'],
                      'target_assay_id': target_assay_field['options'],
                      'reference_assay_id': reference_assay_field['options'],
                      'author_id': author_field['options']}
        )

        return render('/sample/cnv/new.html')

    @restrict('POST')
    @validate(schema=SampleAssayCNVForm(), form='cnv_new')
    def cnv_create(self):
        cnv = AssaySampleCNV()

        # grrr
        for k, v in self.form_result.items():
            setattr(cnv, k, v)

        # messy
        cnv.target_assay = Session.query(Assay).get(self.form_result['target_assay_id'])
        cnv.sample = Session.query(Sample).get(self.form_result['sample_id'])
        if self.form_result['author_id']:
            cnv.reporter = Session.query(Person).get(self.form_result['author_id'])
        Session.add(cnv)
        Session.commit()

        redirect(url(controller='sample', action='cnv_saved', cnv_id=cnv.id, cnv=cnv.cnv))

    def cnv_saved(self):
        cnv_id = request.params.get('cnv_id', None)
        if cnv_id is None:
            abort(404)

        cnv = Session.query(AssaySampleCNV).get(int(cnv_id))
        if not cnv:
            abort(404)

        c.sample = cnv.sample
        c.assay = cnv.target_assay
        c.cnv = request.params.get('cnv', '?')
        return render('/sample/cnv/saved.html')

    def cnv_edit(self, id=None):
        if id is None:
            abort(404)

        cnv = Session.query(AssaySampleCNV).get(id)
        if not cnv:
            abort(404)

        sample_field = fl.sample_field(blank=True, selected=unicode(cnv.sample.id if cnv.sample else ''))
        target_assay_field = fl.assay_field(blank=True, selected=unicode(cnv.target_assay.id if cnv.target_assay else ''))
        reference_assay_field = fl.assay_field(blank=True, selected=unicode(cnv.reference_assay.id if cnv.reference_assay else ''))
        author_field = fl.person_field(selected=unicode(cnv.reporter.id if cnv.reporter else ''))
        c.plate = None
        c.form = h.LiteralFormSelectPatch(
            value = {'sample_id': sample_field['value'],
                     'target_assay_id': target_assay_field['value'],
                     'reference_assay_id': reference_assay_field['value'],
                     'author_id': author_field['value'],
                     'cnv': cnv.cnv,
                     'source_external_url': cnv.source_external_url,
                     'source_plate_id': cnv.plate.id if cnv.plate else None,
                     'notes': cnv.notes},
            option = {'sample_id': sample_field['options'],
                      'target_assay_id': target_assay_field['options'],
                      'reference_assay_id': reference_assay_field['options'],
                      'author_id': author_field['options']}
        )
        c.cnv = cnv

        return render('/sample/cnv/edit.html')

    @restrict('POST')
    @validate(schema=SampleAssayCNVForm(), form='edit')
    def cnv_save(self, id=None):
        if id is None:
            abort(404)

        cnv = Session.query(AssaySampleCNV).get(id)
        if not cnv:
            abort(404)

        # try manual overrides first
        for k, v in self.form_result.items():
            if k not in ('id',):
                setattr(cnv, k, v)
        Session.commit()

        redirect(url(controller='sample', action='cnv_saved', cnv_id=cnv.id, cnv=cnv.cnv))

    @restrict('POST')
    def cnv_delete(self, id=None):
        if id is None:
            abort(404)

        cnv = Session.query(AssaySampleCNV).get(id)
        if not cnv:
            abort(404)

        sample = cnv.sample
        Session.delete(cnv)
        Session.commit()

        redirect(url(controller='sample', action='view', id=sample.id))


