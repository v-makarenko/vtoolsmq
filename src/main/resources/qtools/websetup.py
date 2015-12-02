"""Setup the qtoolsqtools application"""
import logging

import pylons.test

from qtools.config.environment import load_environment
from qtools.model.meta import Session, Base

log = logging.getLogger(__name__)

def setup_app(command, conf, vars):
    """Place any commands to setup qtools here"""
    # Don't reload the app if it was loaded under the testing environment
    if not pylons.test.pylonsapp:
        load_environment(conf.global_conf, conf.local_conf)

    # Create the tables if they don't already exist
    # made irrelevant by sqlalchemy-migrate
    # Base.metadata.create_all(bind=Session.bind)
    
    # TODO: teardown on setup?
