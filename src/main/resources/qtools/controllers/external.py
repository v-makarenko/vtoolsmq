import logging

from pylons import request, response, session, tmpl_context as c, url
from pylons.controllers.util import abort, redirect

from qtools.lib.base import BaseController, render

log = logging.getLogger(__name__)

class ExternalController(BaseController):

    def index(self):
    	c.logged_in = False
        return render('/external/login.html')
    
    def support(self):
    	c.logged_in = False
    	return render('/external/support.html')
    
    def assay(self):
    	c.logged_in = True
    	return render('/external/assay.html')
    
    def validation(self):
    	c.logged_in = True
    	return render('/external/validation.html')
