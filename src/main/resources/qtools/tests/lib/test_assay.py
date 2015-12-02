from qtools.tests import SimpleAssayDatabaseTest
from qtools.lib.assay import *
from qtools.model import Enzyme

class TestAssayLib(SimpleAssayDatabaseTest):

	def test_cached_assay_cut_by_enzyme(self):
		cutter = Enzyme(name='MseI', cutseq='TTAA')
		cuts = cached_assay_cut_by_enzyme(self.quest_smn2, cutter)
		assert cuts == 1

		# this doesn't cut at all
		no_cutter = Enzyme(name='FakI', cutseq='CTTG')
		cuts = cached_assay_cut_by_enzyme(self.quest_smn2, no_cutter)
		assert cuts == False

		# this cutsite is screwed on both sequences due to SNP
		snp_cutter = Enzyme(name='FakII', cutseq='TCAG')
		cuts = cached_assay_cut_by_enzyme(self.quest_smn2, snp_cutter)
		assert cuts == False

		# this cutsite is screwed on only one sequence due to SNP
		snp_cutter2 = Enzyme(name='FakIII', cutseq='CCCT')
		cuts = cached_assay_cut_by_enzyme(self.quest_smn2, snp_cutter2)
		assert cuts == False