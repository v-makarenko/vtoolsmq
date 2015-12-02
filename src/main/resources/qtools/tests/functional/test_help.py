from qtools.tests import *

class TestHelpController(TestController):

    def test_well_metrics(self):
        response = self.app.get(url(controller='help', action='well_metrics'))
