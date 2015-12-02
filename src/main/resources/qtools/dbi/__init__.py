"""
This is a file that is used to allow access to QTools
model objects without all the rest of QTools (see setup.py)

In theory, qtools-lite should work like this:

from qtools.dbi import init_session_from_url

engine = init_session_from_url('mysql://qtools:password@localhost/qtools')
# use SQLAlchemy engine/sessionmaker to use QTools DB
# in an ORM-like way
"""
import ConfigParser

from qtools.model import Session, init_model, init_model_readonly
from sqlalchemy import engine_from_config, create_engine

def get_engine_from_config(config_path):
    """
    Get a reference to the SQLAlchemy DB engine from the
    config file.  The config should have sqlalchemy parameters
    in the [DEFAULT] section.
    """
    config = ConfigParser.ConfigParser()
    with open(config_path) as infile:
        config.readfp(infile)
    
    engine = engine_from_config(config.defaults(), prefix='sqlalchemy.')
    return engine

def init_session_from_config(config_path):
    """
    Init the environment, including binding qtools.model.Session,
    using the specified config file.  The config should have sqlalchemy
    parameters in the [DEFAULT] section.
    """
    engine = get_engine_from_config(config_path)
    init_model(engine)
    return engine # for optional daisychain

def init_session_readonly_from_config(config_path):
    """
    Init the environment, including binding qtools.model.Session,
    using the specified config file.  The config should have sqlalchemy
    parameters in the [DEFAULT] section.  The Session will be a
    read-only session.
    """
    engine = get_engine_from_config(config_path)
    init_model_readonly(engine)
    return engine # for optional daisychain

def init_session_from_url(url):
    """
    Init the environment, including binding qtools.model.Session,
    using the specified connection URL.
    """
    engine = create_engine(url)
    init_model(engine)
    return engine

def init_session_readonly_from_url(url):
    """
    Init the environment, including binding qtools.model.Session,
    using the specified connection URL.  The Session will be a
    read-only session.
    """
    engine = create_engine(url)
    init_model_readonly(engine)
    return engine
