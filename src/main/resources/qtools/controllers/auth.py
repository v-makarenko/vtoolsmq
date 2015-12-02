import logging

from pylons import request, response, session, tmpl_context as c, url
from pylons.controllers.util import abort, redirect

from qtools.lib.base import BaseController, render
from repoze.what.plugins.pylonshq import ActionProtector
from repoze.what.predicates import not_anonymous, is_anonymous
import qtools.lib.helpers as h

log = logging.getLogger(__name__)

def already_logged_in(action):
    session['flash'] = 'You have already logged in.'
    session.save()
    return redirect(url(controller='auth', action='logged_in'))

class AuthController(BaseController):

    def _login_base(self):
        response = render('/auth/login.html')
        return response

    @ActionProtector(is_anonymous(), already_logged_in)
    def login(self):
        response = self._login_base()
        defaults = {'came_from': request.params.get('came_from', url(controller='auth', action='logged_in'))}
        return h.render_bootstrap_form(response, defaults=defaults)

    @ActionProtector(not_anonymous())
    def logged_in(self):
        return render('/auth/logged_in.html')

    def logged_out(self):
        return render('/auth/logged_out.html')
