"""The base Controller API

Provides the BaseController class for subclassing.
"""
from pylons.controllers import WSGIController
from pylons import request, response
from pylons.templating import render_mako as render

from qtools.lib.response import tables_to_csv
from qtools.model.meta import Session

class BaseController(WSGIController):

    def __call__(self, environ, start_response):
        """Invoke the Controller"""
        # WSGIController.__call__ dispatches to the Controller method
        # the request is routed to. This routing information is
        # available in environ['pylons.routes_dict']
        try:
            return WSGIController.__call__(self, environ, start_response)
        finally:
            Session.remove()

    def __after__(self, *args, **kwargs):
    	if request.params.get('output', None) in ('csv', 'CSV'):
            csv = tables_to_csv(response.body)
            response.content_type = "text/csv"
            if ( 'id' in kwargs.keys() ):
                filename = kwargs['id']
            else:
                filename = 'unknown'
            response.headers['Content-disposition'] = 'attachment; filename=%s.csv' % filename
            response.body = csv
            return csv


