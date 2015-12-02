"""Pylons environment configuration"""
import os
from ConfigParser import SafeConfigParser

from mako.lookup import TemplateLookup
from pylons.configuration import PylonsConfig
from pylons.error import handle_mako_error
from sqlalchemy import engine_from_config

import pkg_resources

import qtools.lib.app_globals as app_globals
import qtools.lib.helpers
from qtools.config.routing import make_map
from qtools.model import init_model

def load_environment(global_conf, app_conf):
    """Configure the Pylons environment via the ``pylons.config``
    object
    """
    config = PylonsConfig()
    
    # Pylons paths
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

    # dynamic template paths
    template_paths = [os.path.join(root, path.strip()) for path in \
                        app_conf.get('template_paths', 'templates').split(',')]
    
    paths = dict(root=root,
                 controllers=os.path.join(root, 'controllers'),
                 static_files=os.path.join(root, 'public'),
                 templates=template_paths)

    # Initialize config with the basic options
    config.init_app(global_conf, app_conf, package='qtools', paths=paths)

    config['routes.map'] = make_map(config)
    config['pylons.app_globals'] = app_globals.Globals(config)
    config['pylons.h'] = qtools.lib.helpers
    
    # Setup cache object as early as possible
    import pylons
    pylons.cache._push_object(config['pylons.app_globals'].cache)
    

    # Create the Mako TemplateLookup, with the default auto-escaping
    config['pylons.app_globals'].mako_lookup = TemplateLookup(
        directories=paths['templates'],
        error_handler=handle_mako_error,
        module_directory=os.path.join(app_conf['cache_dir'], 'templates'),
        input_encoding='utf-8', default_filters=['escape'],
        imports=['from webhelpers.html import escape'])

    # Setup the SQLAlchemy database engine
    engine = engine_from_config(config, 'sqlalchemy.')
    
    init_model(engine)
    
    # for each table specif

    # CONFIGURATION OPTIONS HERE (note: all config options will override
    # any Pylons config options)

    #load qtools version from Setup.py
    config['version'] = pkg_resources.require("qtools")[0].version
    
    # load/overwrite instrument certifcaiton specs
    if ( 'certs.config_file' in config):
        
        certs_config = config['certs.config_file']
        parser = SafeConfigParser()

        ## keep cases as they are!   
        parser.optionxform = str 
        parser.read( certs_config )

        for item in parser.options('certspecs'):
            config[item] = parser.get('certspecs',item)

    return config
