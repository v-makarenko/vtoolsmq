from qtools.tests import *

class TestProductController(TestController):

    def test_index(self):
        response = self.app.get(url(controller='product', action='index'))
        # Test response...
