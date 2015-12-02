from qtools.lib.webservice.neb import *
from unittest import TestCase

class TestNEBEnzymeSource(TestCase):
	def setUp(self):
		self.source = NEBEnzymeSource()

	def test_iter_res(self):
		pages = []
		for name, page_uri in self.source.iter_restriction_enzymes():
			pages.append((name, page_uri))
		assert len(pages) > 0
		assert len([name for name, page in pages if '-HF' in name]) == 0
		assert len([name for name, page in pages if 'RE-Mix' in name]) == 0

	def test_enzyme_details(self):
		AatII = self.source.enzyme_details('AatII', 'productR0117.asp')
		assert AatII['sequence'] == 'GACGTC'
		assert AatII['buffer'] == 'NEBuffer 4'
		assert AatII['methylation_sensitivity'] == 'CpG'
		assert AatII['vendor_serial'] == 'R0117'

	
