from qtools.tests import *

class TestExternalController(TestController):

    def test_index(self):
        response = self.app.get(url(controller='external', action='index'))
        # Test response...
