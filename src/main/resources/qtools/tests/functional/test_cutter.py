from qtools.tests import *

class TestCutterController(TestController):

    def test_index(self):
        response = self.app.get(url(controller='cutter', action='index'))
        # Test response...
