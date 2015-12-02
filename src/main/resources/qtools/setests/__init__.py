from unittest import TestCase
from pylons import url as uri
import pylons.test, sys, logging, urlparse

from paste.deploy import loadapp
from paste.script.appinstall import SetupCommand
from routes.util import URLGenerator
from webtest import TestApp

import os, inspect, nose, re, logging

DB_URL_RE = re.compile(r'([^\:]+)\:\/\/([^\:]+)\:([^\@]+)\@([^\/]+)\/([^\s]+)')

environ = {}

if not pylons.test.pylonsapp:
    logging.error("Cannot run tests: need to specify config file")

# if this isn't set up right, let it fail in order for nose to display the error
SetupCommand('setup-app').run([pylons.test.pylonsapp.config['__file__']])

try:
    from selenium.webdriver.remote.remote_connection import LOGGER
    LOGGER.setLevel(logging.INFO)
except ImportError, e:
    print "These tests are likely going to fail as Selenium had an import error..."

def CSS(source, selector):
    return source.find_elements_by_css_selector(selector)

class SeleniumContextTest(TestCase):
    """
    A Selenium test that correctly operates within a QTools context.

    Whether or not a subclass of this test runs depends on whether it
    is in a directory specified by the 'nose.selenium.test_paths' variable
    in the active Pylons configuration.

    It will also trigger Firefox as the webdriver to check the front-end
    test on setUp.
    """
    @property
    def __reldir(self):
        parentPath = os.path.dirname(inspect.getfile(SeleniumContextTest))
        localPath = os.path.dirname(inspect.getfile(self.__class__))
        return os.path.relpath(localPath, parentPath)

    @property
    def db_props(self):
        theprops = {'dialect': None,
                    'user': None,
                    'host': None,
                    'database': None}
        if not self.app:
            return theprops
        else:
            db_url = self.app.app.config.get('sqlalchemy.url')
            db_group = DB_URL_RE.match(db_url)
            if not db_group:
                return theprops
            dialect, user, password, host, database = db_group.groups()
            theprops.update(dialect=dialect,
                            user=user,
                            host=host,
                            database=database)
            return theprops

    @staticmethod
    def requires_db_property_equal(*db_args, **db_kwargs):
        """
        Class method decorator for running tests iff the
        DB configuration matches the supplied arguments.
        For example, if you want the test to run only if
        the DB host is localhost, call this decorator with
        the arguments (host='localhost').

        Valid arguments: dialect, user, host, database
        """
        def class_wrapper(func):
            def wrapper(self, *args, **kwargs):
                for prop, val in db_kwargs.items():
                    # OK to chuck a ValueError if the argument is invalid
                    if self.db_props[prop] != val:
                        raise nose.exc.SkipTest('DB %s required to be %s to run test' % (prop, val))

                return func(self, *args, **kwargs)
            wrapper.__name__ = func.__name__
            wrapper.__dict__ = func.__dict__
            return wrapper
        return class_wrapper

    @staticmethod
    def requires_db_property_startswith(*db_args, **db_kwargs):
        """
        Class method decorator for running tests iff the
        DB configuration matches the supplied arguments.
        For example, if you want the test to run only if
        the DB host is like qtools, call this decorator with
        the arguments (host='qtools').  This means the test
        will run if the host is qtools.global.bio-rad.com,
        or just qtools.
        """
        def class_wrapper(func):
            def wrapper(self, *args, **kwargs):
                for prop, val in db_kwargs.items():
                    # OK to chuck a ValueError if the argument is invalid
                    if not self.db_props[prop].startswith(val):
                        raise nose.exc.SkipTest('DB %s required to be like %s to run test' % (prop, val))

                return func(self, *args, **kwargs)
            wrapper.__name__ = func.__name__
            wrapper.__dict__ = func.__dict__
            return wrapper
        return class_wrapper

    def __init__(self, *args, **kwargs):
        wsgiapp = pylons.test.pylonsapp
        config = wsgiapp.config
        self.app = TestApp(wsgiapp)
        uri._push_object(URLGenerator(config['routes.map'], environ))

        self.driver_type = config.get('selenium.default_driver', 'Firefox')

        # TODO: use env to get SELENIUM_TARGET?
        self.server = config.get('selenium.default_server', 'http://127.0.0.1:5000')

        reldir = self.__reldir
        reltest_dirs = config.get('nose.selenium.test_paths', '').split(',')
        if reldir != '.' and reldir not in reltest_dirs:
            raise nose.exc.SkipTest('%s not in directory specified in nose.selenium.testdirs for given config' % self.__class__.__name__)
        super(SeleniumContextTest, self).__init__(*args, **kwargs)

    def urlpath(self, path):
        return urlparse.urljoin(self.server, path)

    def url(self, *args, **kwargs):
        return urlparse.urljoin(self.server, uri(*args, **kwargs))

    def setUp(self):
        from selenium import webdriver
        self.driver = getattr(webdriver, self.driver_type)()

    def tearDown(self):
        self.driver.quit()

