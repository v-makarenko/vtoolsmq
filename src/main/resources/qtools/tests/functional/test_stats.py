from qtools.tests import *

class TestStatsController(TestController):

    def test_index(self):
        response = self.app.get(url(controller='stats', action='index'))
        # Test response...
