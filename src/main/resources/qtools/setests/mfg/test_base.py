from qtools.setests import SeleniumContextTest, CSS
from unittest import TestSuite

class BaseUITest(SeleniumContextTest):

    def test_list(self):
        self.driver.get(self.url(controller='plate', action='list'))
        top_bar_lis = CSS(self.driver, 'ul.nav > li')
        assert len(top_bar_lis) == 4
        plates, readers, qc, csv = top_bar_lis
        assert plates.text == 'Plates'
        assert readers.text == 'Readers'
        assert qc.text == 'QC Batches'
        assert csv.text == 'Page as CSV'