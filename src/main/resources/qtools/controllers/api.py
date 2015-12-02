import logging, json
from datetime import timedelta

from pylons import request, response, session, tmpl_context as c, url
from pylons.controllers.util import abort, redirect

from decorator import decorator
from qtools.lib.base import BaseController, render

from qtools.model import Session, Plate, QLBPlate, QLBWell, Box2

from sqlalchemy import and_, not_
from sqlalchemy.sql import func
from sqlalchemy.orm import joinedload_all

import formencode

log = logging.getLogger(__name__)

class PlateForm(formencode.Schema):
    allow_extra_fields = True
    filter_extra_fields = True

    include_empty_plates = formencode.validators.Bool(not_empty=False, if_missing=False)

class PlateDateForm(PlateForm):
    allow_extra_fields = True
    filter_extra_fields = True

    start_date = formencode.validators.DateConverter(not_empty=False, if_missing=None)
    end_date = formencode.validators.DateConverter(not_empty=False, if_missing=None)

def json_validate(schema=None, form=None, post_only=False, on_get=True):
    def wrapper(func, self, *args, **kwargs):
        request.content_type = 'application/json'
        return_dict = dict()
        if post_only:
            if request.method != 'POST':
                return_dict['code'] = 405
                return_dict['message'] = 'The request must be a POST'
                return json.dumps(return_dict)
    
        if on_get:
            params = request.params
        else:
            params = request.POST
    
        # ignore variabledecode for now

        if not schema:
            return_dict['code'] = 500
            return_dict['message'] = 'No form schema specified.'
            return json.dumps(return_dict)
    
        # I think formencode also works this way
        the_schema = None
        if isinstance(schema, formencode.Schema):
            the_schema = schema.__class__()
        else:
            try:
                if issubclass(schema, formencode.Schema):
                    the_schema = schema()
            except TypeError, e:
                pass
        
        if not the_schema:
            return_dict['code'] = 500
            return_dict['message'] = 'Invalid form schema specified.'
            return json.dumps(return_dict)

        try:
            form_result = the_schema.to_python(dict(params))
            self.form_result = form_result
        except formencode.Invalid, error:
            return_dict['code'] = 500
            return_dict['message'] = 'Invalid form arguments' % error.value
            return_dict.update(dict([(k, v.message) for k, v in error.error_dict.items()]))
            return json.dumps(return_dict)
        
        return func(self, *args, **kwargs)
    return decorator(wrapper)

# the methods that come out of here should form the definitive plate query API
def nonempty_qlbplates_query(filter_stmt):
    return Session.query(QLBPlate, func.count(QLBWell.id).label('well_count'))\
                  .join(QLBWell)\
                  .join(QLBPlate.plate)\
                  .join(Plate.box2)\
                  .filter(and_(QLBPlate.plate_id != None,
                               QLBWell.file_id != None,
                               QLBWell.file_id != -1))\
                  .filter(filter_stmt)\
                  .options(joinedload_all(QLBPlate.file))\
                  .group_by(QLBWell.plate_id)\
                  .having('well_count > 0')

def all_qlbplates_query(filter_stmt):
    return Session.query(QLBPlate)\
                  .join(QLBPlate.plate)\
                  .join(Plate.box2)\
                  .filter(QLBPlate.plate_id != None)\
                  .filter(filter_stmt)\
                  .options(joinedload_all(QLBPlate.file))


class ApiController(BaseController):

    def __execute_query(self, filter_args, options=None, order_by=None):
        if self.form_result['include_empty_plates']:
            # TODO limit, offset
            query = all_qlbplates_query(and_(*filter_args))
            if order_by:
                query = query.order_by(order_by)
                return query.all()
        else:
            query = nonempty_qlbplates_query(and_(*filter_args))
            if order_by:
                query = query.order_by(order_by)
                plate_counts = query.all()
                return [plate for plate, count in plate_counts]
    
    @json_validate(schema=PlateDateForm)
    def plate_addresses_by_date(self):
        # this could be a generic URL pattern -- process the universal parameters
        # to a filter query and then each controller pattern would just modify
        # the output
        start_date = self.form_result['start_date']
        end_date = self.form_result['end_date']
        args = []
        if start_date:
            args.append(QLBPlate.host_datetime >= start_date)
        if end_date:
            args.append(QLBPlate.host_datetime < end_date+timedelta(1))
        
        plates = self.__execute_query(args, order_by=QLBPlate.host_datetime)
        addresses = ['%s/%s' % (plate.file.dirname, plate.file.basename) for plate in plates]
        return json.dumps({'code': 200,
                           'results': addresses})




