import logging

from pylons import request, response, session, tmpl_context as c, url
from pylons.controllers.util import abort, redirect
from pylons.decorators import validate
from pylons.decorators.rest import restrict

from qtools.lib.base import BaseController, render
import qtools.lib.fields as fl
import qtools.lib.helpers as h
from qtools.lib.validators import IntKeyValidator
from qtools.model import Session, Person
from qtools.model.sequence import SequenceGroupTag

log = logging.getLogger(__name__)

import formencode
from sqlalchemy.exc import IntegrityError

class SequenceGroupTagForm(formencode.Schema):
    allow_extra_fields = True
    filter_extra_fields = True

    name = formencode.validators.String(not_empty=True, maxlength=50)
    notes = formencode.validators.String(not_empty=False, if_missing=None)
    owner_id = IntKeyValidator(Person, 'id', not_empty=False, if_missing=None)

class AssayGroupController(BaseController):

    def list(self):
        c.tags = Session.query(SequenceGroupTag).order_by(SequenceGroupTag.name).all()
        return render('/sequence/group_list.html')
    
    def new(self):
        response = self._new_base()
        return h.render_bootstrap_form(response)
    
    def _new_base(self):
        c.people = fl.person_field()
        return render('/sequence/group_new.html')

    @restrict('POST')
    @validate(schema=SequenceGroupTagForm, form='_new_base', error_formatters=h.tw_bootstrap_error_formatters)
    def create(self):
        model = self.__form_to_model(self.form_result)
        try:
            Session.commit()
            session['flash'] = 'Category saved.'
            session.save()
            return redirect(url(controller='assay_group', action='list'))
        except IntegrityError, e:
            Session.rollback()
            session['flash'] = 'There is already a category named %s.' % model.name
            session['flash_class'] = 'error'
            session.save()
            return redirect(url(controller='assay_group', action='new'))
    
    def edit(self, id=None):
        if not id:
            abort(404)
        
        tag = Session.query(SequenceGroupTag).get(int(id))
        c.tag = tag
        if not tag:
            abort(404)
        
        response = self._edit_base()
        return h.render_bootstrap_form(response, defaults=tag.__dict__)
    
    def _edit_base(self):
        c.people = fl.person_field()
        return render('/sequence/group_edit.html')
    
    @restrict('POST')
    @validate(schema=SequenceGroupTagForm, form='_edit_base', error_formatters=h.tw_bootstrap_error_formatters)
    def save(self, id=None):
        if not id:
            abort(404)
        
        model = Session.query(SequenceGroupTag).get(int(id))
        if not model:
            abort(404)
        
        model = self.__form_to_model(self.form_result, model=model)
        try:
            Session.commit()
            session['flash'] = 'Category saved.'
            session.save()
            return redirect(url(controller='assay_group', action='list'))
        except IntegrityError, e:
            Session.rollback()
            session['flash'] = 'There is already a category named %s.' % model.name
            session['flash_class'] = 'error'
            session.save()
            return redirect(url(controller='assay_group', action='edit', id=id))
    
    @restrict('POST')
    def delete(self, id=None):
        if id is None:
            abort(404)
        
        tag = Session.query(SequenceGroupTag).get(int(id))
        if not tag:
            abort(404)
        
        try:
            tag.sequence_groups = []
            Session.delete(tag)
            Session.commit()
        except Exception, e:
            Session.rollback()
            session['flash'] = 'Could not delete category.'
            session['flash_class'] = 'error'
            return redirect(url(controller='assay_group', action='edit', id=id))
        
        session['flash'] = 'Category deleted.'
        session.save()
        return redirect(url(controller='assay_group', action='list'))

    def __form_to_model(self, form, model=None):
        if not model:
            model = SequenceGroupTag()
            Session.add(model)
        
        model.name  = form['name']
        model.notes = form['notes']
        model.owner_id = form['owner_id']
        Session.merge(model)
        return model
