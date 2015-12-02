"""
Cookie helper methods and constants.
"""
from pylons import request, response

__all__ = ['ACTIVE_ANALYSIS_GROUP_ID','get','set_session','set_persistent','clear']

ACTIVE_ANALYSIS_GROUP_ID = 'analysis_group_id'
QTOOLS_COOKIE_PREFIX = 'qtools_%s'

def get(key, default=None, as_type=str):
    val = request.cookies.get(QTOOLS_COOKIE_PREFIX % key, None)
    if val is None:
        return default
    else:
        return as_type(val)

def set_session(key, val):
    response.set_cookie(QTOOLS_COOKIE_PREFIX % key, str(val))

def set_persistent(key, val, max_age=None, expires=None):
    response.set_cookie(QTOOLS_COOKIE_PREFIX % key, str(val), max_age=max_age, expires=expires)

def clear(key):
    response.delete_cookie(QTOOLS_COOKIE_PREFIX % key)