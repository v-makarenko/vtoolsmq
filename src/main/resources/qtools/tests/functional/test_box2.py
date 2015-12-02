from qtools.tests import *

class TestBox2Controller(TestController):

    def test_index(self):
        response = self.app.get(url(controller='box2', action='index'))
        # Test response...
