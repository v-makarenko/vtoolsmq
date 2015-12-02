"""
manager.py

Manager in Dependency Injection pattern.  This is done to reasonable effect by
middleware.py, but invocation/setup requires a WSGI request.  For the parts of
QTools which may not be part of the WSGI request/response chain, there is
manager.py.
"""
import os
from paste.deploy import loadapp
from qtools.lib.collection import ImmutableAttrDict

config_manager_dict = dict()
PYLONS_CONTEXT_NAME = 'pylons_context'

class ComponentManager(ImmutableAttrDict):
    """
    Component manager, just returns a custom error message
    if there is a key miss.
    """
    def __getattribute__(self, key, default=None):
        if not key in super(ComponentManager, self).__dict__:
            raise AttributeError, "Component not registered on instantiation: %s" % key
        else:
            return super(ComponentManager, self).__getattribute__(key)

def get_manager(config_path):
    """
    Given a config path, construct the ComponentManager.
    """
    global config_manager_dict

    if config_path not in config_manager_dict:
        config_name = "config:%s" % config_path
        app = loadapp(config_name, relative_to=os.getcwd())
        if hasattr(app, 'config'):
            config = app.config
        # app from config is a filter
        elif hasattr(app, 'app'):
            config = app.app.config
        manager = create_manager(config)
        config_manager_dict[config_path] = manager
    
    return config_manager_dict[config_path]

def get_manager_from_pylonsapp_context():
    """
    Retrieve a component manager in a WSGI/Pylons app context.  Presumes
    the app is already running (thus, pylons.config is already accessible),
    so supplying a path is redundant at best, incorrect at worst.
    """
    global config_manager_dict, PYLONS_CONTEXT_NAME
    if PYLONS_CONTEXT_NAME not in config_manager_dict:
        from pylons import config
        manager = create_manager(config)
        config_manager_dict[PYLONS_CONTEXT_NAME] = manager
    return config_manager_dict[PYLONS_CONTEXT_NAME]

def create_manager(config):
    """
    Will create a component manager from the specified
    configuration by looking for keys starting with 'qtools.components.*'.
    The rest of the name will be the key in the manager, and the value
    will be the class specified by the value (which should be an absolute
    path to the class).

    Right now, values are intended to be classes only, though this could
    be refined to register_class, register_method and register_module,
    to swap in different functions and modules at runtime.
    """
    module_dict = dict()
    for k, v in config.items():
        if k.startswith('qtools.components.'):
            component_name = k.split('.')[-1]
            # assume here that paths fully qualified
            module_name = ('.').join(v.split('.')[:-1])
            class_name = v.split('.')[-1]
            # absolute import (level = 0)
            module = __import__(module_name, globals(), locals(), [class_name], 0)
            module_dict[component_name] = getattr(module, class_name)
            module_dict['pylons_config'] = config
    
    return ComponentManager(module_dict)
