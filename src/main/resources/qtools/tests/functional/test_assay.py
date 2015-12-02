from qtools.tests import *

class TestAssayController(TestController):

    def test_index(self):
        response = self.app.get(url(controller='assay', action='list'))