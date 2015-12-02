from qtools.tests import *

class TestGrooveController(TestController):

    def test_list(self):
        response = self.app.get(url(controller='groove', action='list'))
