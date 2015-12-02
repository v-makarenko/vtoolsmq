from pylons import request

__all__ = ['login_identity', 'is_logged_in', 'login_full_name', 'login_first_name', 'login_last_name', 'login_email']

def login_identity():
    return request.environ.get('repoze.who.identity', {})

def is_logged_in():
    return request.environ.get('repoze.who.identity') is not None

def login_full_name():
    return login_identity().get('repoze.who.displayName', '')

def login_first_name():
    return login_identity().get('repoze.who.givenName', '')

def login_last_name():
    return login_identity().get('repoze.who.sn', '')

def login_email():
    return login_identity().get('repoze.who.mail', '')