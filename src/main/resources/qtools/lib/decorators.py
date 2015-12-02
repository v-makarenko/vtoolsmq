"""
Custom decorators.
"""
import warnings

from pylons import request, session, url
from pylons.controllers.util import redirect, abort
from pylons.decorators import PylonsFormEncodeState
from decorator import decorator

from qtools.controllers import populate_multiform_context
from qtools.lib.variabledecode import clean_variable_encode
from qtools.lib.wowo import wowo
from qtools.model import Session, Plate, QLBWell, QLBPlate

from sqlalchemy.orm import joinedload_all
from formencode import variabledecode, Invalid, htmlfill

def session_validate(variable, fallback=None):
    """
    Validates the presence of a variable in a user's session context.
    If not present, will redirect to the action specified as 'redirect'
    on the controller, or aborts 404.
    """
    def wrapper(func, self, *args, **kwargs):
        if isinstance(variable, basestring):
            variables = [variable]
        else:
            variables = variable
        missing = []
        for var in variables:
            if not var in session:
                missing.append(var)

        if missing:
            if not fallback:
                return abort(404)

            error_message = "Session timeout.  We are restarting at the beginning."
            session['flash'] = error_message
            session['flash_class'] = 'error'
            session.save()
            controller = request.environ['pylons.routes_dict']['controller']
            return redirect(url(controller=controller, action=fallback))

        return func(self, *args, **kwargs)

    return decorator(wrapper)

def session_validate_hierarchy(*chain, **topargs):
    """
    Validates the presence of the hierarchy of variables in a user's
    session context.  If not present, will redirect to the action specified
    as 'redirect' on the controller, or will abort 404.
    """
    def wrapper(func, self, *args, **kwargs):
        fallback = topargs.pop('fallback', None)
        toplevel = session
        missing = False
        for var in chain:
            if not var in toplevel:
                missing = True
                break
            toplevel = toplevel[var]

        if missing:
            if not fallback:
                return abort(404)

            error_message = "Session timeout.  We are restarting at the beginning."
            session['flash'] = error_message
            session['flash_class'] = 'error'
            session.save()
            controller = request.environ['pylons.routes_dict']['controller']
            return redirect(url(controller=controller, action=fallback))

        return func(self, *args, **kwargs)

    return decorator(wrapper)

# TODO FIXFIX (args[0] is wrong)
def session_validate_flow(variable, fallback=None):
    """
    Asserts that the variable is on the session flow dict.  The
    flow is interpreted from the routing.
    """
    def wrapper(func, self, *args, **kwargs):
        if isinstance(variable, basestring):
            variables = [variable]
        else:
            variables = variable
        missing = []

        flow = args[0] if len(args) > 0 else None
        if not flow:
            check = session
        else:
            check = session.get(flow, {})

        for var in variables:
            if not var in check:
                missing.append(var)

        if missing:
            if not fallback:
                return abort(404)

            error_message = "Session timeout.  We are restarting at the beginning."
            session['flash'] = error_message
            session['flash_class'] = 'error'
            session.save()
            controller = request.environ['pylons.routes_dict']['controller']
            return redirect(url(controller=controller, action=fallback, flow=flow))

        return func(self, *args, **kwargs)

    return decorator(wrapper)


def session_clear(variable):
    """
    Clears the variables on the session if set.
    """
    def wrapper(func, self, *args, **kwargs):
        if isinstance(variable, basestring):
            variables = [variable]
        else:
            variables = variable

        for var in variables:
            if var in session:
                del session[var]
        session.save()

        return func(self, *args, **kwargs)
    return decorator(wrapper)

def session_clear_startswith(prefix):
    """
    Clears session variables that start with the specified prefix.
    """
    def wrapper(func, self, *args, **kwargs):
        for var in session:
            if var.startswith(prefix):
                del session[var]
        session.save()
        return func(self, *args, **kwargs)
    return decorator(wrapper)

def multi_validate(schema=None, validators=None, form=None, variable_decode=False,
                   dict_char='.', list_char='-', post_only=True, state=None,
                   on_get=False, **htmlfill_kwargs):
    """
    Port of pylons.decorators.validate to do similar things when there are
    multiple field/form entries.
    """
    if state is None:
        state = PylonsFormEncodeState

    def wrapper(func, self, *args, **kwargs):
        """Decorator wrapper function"""
        request = self._py_object.request
        errors = {}

        # Skip the validation if on_get is False and its a GET
        if not on_get and request.environ['REQUEST_METHOD'] == 'GET':
            return func(self, *args, **kwargs)

        # If they want post args only, use just the post args
        if post_only:
            params = request.POST
        else:
            params = request.params

        params = params.mixed()
        if variable_decode:
            decoded = variabledecode.variable_decode(params, dict_char,
                                                     list_char)
        else:
            decoded = params

        if schema:
            try:
                self.form_result = schema.to_python(decoded, state)
            except Invalid, e:
                errors = e.unpack_errors(variable_decode, dict_char, list_char)
        if validators:
            if isinstance(validators, dict):
                if not hasattr(self, 'form_result'):
                    self.form_result = {}
                for field, validator in validators.iteritems():
                    try:
                        self.form_result[field] = \
                            validator.to_python(decoded.get(field), state)
                    except Invalid, error:
                        errors[field] = error

        if errors:
            request.environ['REQUEST_METHOD'] = 'GET'
            self._py_object.tmpl_context.form_errors = errors
            decoded_params = variabledecode.variable_decode(params, dict_char, list_char)
            populate_multiform_context(self, decoded_params)

            # If there's no form supplied, just continue with the current
            # function call.
            if not form:
                return func(self, *args, **kwargs)

            request.environ['pylons.routes_dict']['action'] = form
            response = self._dispatch_call()

            # If the form_content is an exception response, return it
            if hasattr(response, '_exception'):
                return response

            error_params = clean_variable_encode(variabledecode.variable_encode(errors, add_repetitions=False))

            htmlfill_kwargs2 = htmlfill_kwargs.copy()
            htmlfill_kwargs2.setdefault('encoding', request.charset)
            return htmlfill.render(response, defaults=params, errors=error_params,
                                   **htmlfill_kwargs2)
        return func(self, *args, **kwargs)
    return decorator(wrapper)


def block_contractor(func):
    """
    Blocks this function if wowo.contractor is True
    """
    def wrapper(self, *args, **kwargs):
        if wowo('contractor'):
            abort(403)
        else:
            return func.__call__(self, *args, **kwargs)
    return wrapper

def block_contractor_internal_plates(func):
    """
    Blocks this function if the id in the args is for
    a lab plate
    """
    def wrapper(self, *args, **kwargs):
        if wowo('contractor'):
            id = kwargs.get('id')
            if id is None:
                 abort(404,'Error: no plate id.')
            plate = Session.query(Plate).get(id)
            if not plate:
                abort(404,'Plate id error. got "%s"' % str(id))
            box2 = plate.box2
            if not box2.is_prod or plate.onsite:
                abort(403)
        return func.__call__(self, *args, **kwargs)
    return wrapper

def block_contractor_internal_wells(func):
    """
    Blocks this function if the id in the args
    is for a well in a lab plate
    """
    def wrapper(self, *args, **kwargs):
        if wowo('contractor'):
            id = kwargs.get('id')
            well = Session.query(QLBWell).filter(QLBWell.id == id)\
                          .options(joinedload_all(QLBWell.plate, QLBPlate.plate, Plate.box2, innerjoin=True)).first()
            if not well:
                abort(404)
            if not well.plate.plate.box2.is_prod or well.plate.plate.onsite:
                abort(403)
        return func(self, *args, **kwargs)
    return wrapper

def flash_if_form_errors(message="There were errors trying to save this form."):
    """
    If there are errors in the response, flash a message.  The flash
    typically gets rendered as a red box above the content.
    """
    def wrapper(func, self, *args, **kwargs):
        if getattr(self._py_object.tmpl_context, "form_errors", None):
            session['flash'] = message
            session['flash_class'] = 'error'

        return func(self, *args, **kwargs)
    return decorator(wrapper)

def help_at(uri):
    """
    Controller action decorator.

    Indicates where the help page for the view is, relative to
    the document root.

    :param uri: Relative URI of the help page.
    """
    def wrapper(func):
        def new_action(self, *args, **kwargs):
            from pylons import tmpl_context as c
            c.help_uri = uri
            return func.__call__(self, *args, **kwargs)

        new_action.__name__ = func.__name__
        new_action.__doc__ = func.__doc__
        new_action.__dict__.update(func.__dict__)
        return new_action

    return wrapper

# lifted from http://code.activestate.com/recipes/391367-deprecated/
def deprecated_action(func):
    """
    Renders a red flash (box above the content) that the page in
    question is deprecated and soon to be removed.
    """
    def newFunc(obj, *args, **kwargs):
        warnings.warn("Call to deprecated function %s" % func.__name__, category=DeprecationWarning)
        # not sure if this is the right way to do things
        routes_dict = dict(kwargs.get('environ', {}).get('pylons.routes_dict', {}))
        routes_dict.pop('controller', None)
        routes_dict.pop('action', None)

        context = kwargs.get('pylons', {})
        session = getattr(context, 'session', None)
        if session:
            session['flash'] = "This page is deprecated and will be removed soon.  If you are actively using it and do not wish to see it disappear, email the QTools admin."
            session['flash_class'] = 'error'
            session.save()
        return func(obj, **routes_dict)

    newFunc.__name__ = func.__name__
    newFunc.__doc__ = func.__doc__
    newFunc.__dict__.update(func.__dict__)
    return newFunc
