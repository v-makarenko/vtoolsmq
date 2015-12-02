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
from qtools.model import  Session, Person, DGUsed 
from qtools.lib.inspect import class_properties
from qtools.lib.stringutils import militarize, camelize
from qtools.lib.validators import OneOfInt, UserNameSegment, PlateNameSegment, MetricPattern, IntKeyValidator, NullableStringBool, PlateUploadConverter, SaveNewIdFields

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

log = logging.getLogger(__name__)


class NewUserCreateForm(formencode.Schema):
    allow_extra_fields = True
    filter_extra_fields = True
    
    first_name = UserNameSegment(not_empty=True)
    last_name  = UserNameSegment(not_empty=True)
    name_code  = UserNameSegment(not_empty=True)
    

class UsersController(BaseController):

    def _index_base(self):
        return render('/users/index.html')

    def index(self):
        return render('/users/index.html')

    @RestrictedWowoActionProtector(has_permission('view-login'))
    def login(self):
        response.content_type = 'text/plain'
        return 'OK'
    

    @restrict('POST')
    @validate(schema=NewUserCreateForm(), form='_index_base', error_formatters=h.tw_bootstrap_error_formatters)
    def create_user(self, *args, **kwargs):
        new_user = Person()

        new_user.first_name = self.form_result['first_name']
        new_user.last_name = self.form_result['last_name']
        new_user.name_code = self.form_result['name_code']

        if not Session.query(Person).filter_by(name_code=new_user.name_code).first():
        	Session.add(new_user)
		Session.commit()
        	session['flash'] = 'New User %s %s Added.' % (new_user.first_name, new_user.last_name)
		fields = [new_user.first_name, new_user.last_name]
		c.new_user_name = ' '.join([field for field in fields if field])
        	return render('/users/added.html')
	else:
        	session['flash'] = 'A user %s %s with same Code Name Exists.' % (new_user.first_name, new_user.last_name)
        	return render('/users/index.html')


        c.new_user_id = new_user.id
	return render('/users/index.html')
        
