import os, sys

from paste.script.command import Command, BadCommand
from paste.deploy import loadapp

class QToolsCommand(Command):
    """
    The base class for any QTools command line executable that
    is run through Paste, which requires an app environment/
    context to run.  The purpose of the base class is to
    provide the functionality to correctly "load the app,"
    meaning to correctly set the Pylons context, and hook
    SQLAlchemy to a database.
    """
    group_name = "qtools"
    parser = Command.standard_parser(verbose=False)

    @property
    def config_path(self):
        """
        Get the path of the config file from the supplied arguments
        to Paste.
        """
        if len(self.args) == 0 or (self.min_args and len(self.args) == self.min_args):
            path = 'development.ini'
        else:
            path = self.args[-1]
        return path

    
    def load_wsgi_app(self):
        """
        Load the application context from the config specified
        by arguments into Paste.
        """
        if not os.path.isfile(self.config_path):
            raise BadCommand('%sError: CONFIG_FILE not found at: .%s%s\n'
                             'Please specify a CONFIG_FILE' % \
                             (self.parser.get_usage(), os.path.sep,
                              self.config_path))
        
        config_name = 'config:%s' % self.config_path
        here_dir = os.getcwd()

        wsgiapp = loadapp(config_name, relative_to=here_dir)
        
        return wsgiapp


class WarnBeforeRunning(object):
    """
    Decorator class that prints a warning before running the command.
    """
    def __init__(self, msg):
        self.msg = msg

    def __call__(self, klass):
        cmd_method = klass.command
        decorator = self
        def wrapped(self, *args, **kwargs):
            print "\n==========================="
            print "WARNING: %s" % decorator.msg
            print "===========================\n"
            answer = raw_input("Would you like to continue this operation? (y/N): ")
            if answer.lower() != 'y':
                sys.exit(0)
            return cmd_method.__call__(self, *args, **kwargs)
        klass.command = wrapped
        return klass

class DoNotRun(object):
    """
    Decorator class that prevents running the command for a good reason.
    """
    def __init__(self, msg):
        self.msg = msg

    def __call__(self, klass):
        cmd_method = klass.command
        decorator = self
        def wrapped(self, *args, **kwargs):
            print "\n==========================="
            print "ABORT: %s" % decorator.msg
            print "===========================\n"
            sys.exit(0)
        klass.command = wrapped
        return klass