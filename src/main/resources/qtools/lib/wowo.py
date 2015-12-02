"""
Wowo stands for wire on-wire off.  This refers to the
selective enabling and disabling of features based off
a config file.
"""
from pylons import config

def wowo(key):
    """
    Return whether or not the feature with the specified
    name is 'wired on'.  The settings are stored in the
    app configuration file.
    """
    portions = key.split('.')
    for i in range(len(portions)):
        if not config.get('.'.join(['wowo']+portions[0:i+1]), None):
            return False
    val = config.get('wowo.%s' % key)
    if not bool(val):
        return False
    if val.capitalize() in ['False','No','Off','F','N']:
        return False
    return True