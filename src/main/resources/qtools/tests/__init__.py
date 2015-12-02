"""Pylons application test package

This package assumes the Pylons environment is already loaded, such as
when this script is imported from the `nosetests --with-pylons=test.ini`
command.

This module initializes the application via ``websetup`` (`paster
setup-app`) and provides the base testing objects.
"""
from unittest import TestCase

from paste.deploy import loadapp
from paste.script.appinstall import SetupCommand
from pylons import url
from routes.util import URLGenerator
from webtest import TestApp
from datetime import datetime, timedelta

import pylons.test

__all__ = ['environ', 'url', 'TestController']

# Invoke websetup with the current config file
SetupCommand('setup-app').run([pylons.test.pylonsapp.config['__file__']])

environ = {}

class TestController(TestCase):
    def __init__(self, *args, **kwargs):
        wsgiapp = pylons.test.pylonsapp
        config = wsgiapp.config
        self.app = TestApp(wsgiapp)
        url._push_object(URLGenerator(config['routes.map'], environ))
        TestCase.__init__(self, *args, **kwargs)
    

class DatabaseTest(TestCase):
    def __init__(self, *args, **kwargs):
        wsgiapp = pylons.test.pylonsapp
        config = wsgiapp.config
        self.app = TestApp(wsgiapp)
        TestCase.__init__(self, *args, **kwargs)
    

class SimpleEnvironmentDatabaseTest(DatabaseTest):
    def setUp(self):
        from qtools.model import Person, Project, Session, QLBFile
        # just set up a few things as necessary
        self.testUser = Person(first_name=u'Test', last_name=u'User', name_code=u'TestU')
        self.testProject = Project(name=u'TestProject')
        
        # TODO: make a test folder with a real set of files
        self.readQLP = QLBFile(dirname='Box 2 Alpha 03/TestProject_TestU_Test_2011_01_19_09_36',
                               run_id='readQLP',
                               basename='TestProject_TestU_Test.qlp',
                               type='processed',
                               read_status=1,
                               mtime=datetime.now()-timedelta(0,0,1))
        
        self.unreadQLP = QLBFile(dirname='Box 2 Alpha 03/TestProject_TestU_Test_2011_01_19_09_37',
                                 run_id='unreadQLP',
                                 basename='TestProject_TestU_Test.qlp',
                                 type='processed',
                                 read_status=0,
                                 mtime=datetime.now())
        
        # note: make sure this survives an error
        Session.add_all([self.testUser, self.testProject, self.readQLP, self.unreadQLP])
        Session.commit()
    
    def tearDown(self):
        from qtools.model import Session
        Session.delete(self.testUser)
        Session.delete(self.testProject)
        Session.delete(self.readQLP)
        Session.delete(self.unreadQLP)
        Session.commit()

class SimpleAssayDatabaseTest(DatabaseTest):
    def setUp(self):
        from qtools.model import Session, Assay, HG19AssayCache, SNP131AssayCache

        self.quest_smn2 = Assay(name='Quest_SMN2',
                                gene='SMN2',
                                primer_fwd='ATAGCTATTTTTTTTAACTTCCTTTATTTTCC',
                                primer_rev='TGAGCACCTTCCTTCTTTTTGA',
                                probe_seq='TTTTGTCTAAAACCC')
        
        seq1 = HG19AssayCache(chromosome='5',
                              start_pos=70247730,
                              end_pos=70247803,
                              positive_sequence='ATAGCTATTTTTTTTAACTTCCTTTATTTTCCTTACAGGGTTTCAGACAAAATCAAAAAGAAGGAAGGTGCTCA',
                              negative_sequence='TGAGCACCTTCCTTCTTTTTGATTTTGTCTGAAACCCTGTAAGGAAAATAAAGGAAGTTAAAAAAAATAGCTAT',
                              seq_padding_pos5=0,
                              seq_padding_pos3=0)
                    
        seq2 = HG19AssayCache(chromosome='5',
                              start_pos=69372310,
                              end_pos=69372383,
                              positive_sequence='ATAGCTATTTTTTTTAACTTCCTTTATTTTCCTTACAGGGTTTTAGACAAAATCAAAAAGAAGGAAGGTGCTCA',
                              negative_sequence='TGAGCACCTTCCTTCTTTTTGATTTTGTCTAAAACCCTGTAAGGAAAATAAAGGAAGTTAAAAAAAATAGCTAT',
                              seq_padding_pos5=0,
                              seq_padding_pos3=0)
                    
        snp11 = SNP131AssayCache(bin=1120,
                                 chrom='chr5',
                                 chromStart=70247767,
                                 chromEnd=70247768,
                                 name='rs77969175',
                                 score=0,
                                 strand='-',
                                 refNCBI='G',
                                 refUCSC='G',
                                 observed='A/C',
                                 molType='genomic',
                                 class_='single',
                                 valid='unknown',
                                 avHet=0,
                                 avHetSE=0,
                                 func='missense',
                                 locType='exact',
                                 weight=1)
        
        snp12 = SNP131AssayCache(bin=1120,
                                 chrom='chr5',
                                 chromStart=70247768,
                                 chromEnd=70247769,
                                 name='rs76163360',
                                 score=0,
                                 strand='-',
                                 refNCBI='G',
                                 refUCSC='G',
                                 observed='A/C',
                                 molType='genomic',
                                 class_='single',
                                 valid='unknown',
                                 avHet=0,
                                 avHetSE=0,
                                 func='missense',
                                 locType='exact',
                                 weight=1)
        
        snp13 = SNP131AssayCache(bin=1120,
                                 chrom='chr5',
                                 chromStart=70247772,
                                 chromEnd=70247773,
                                 name='rs4916',
                                 score=0,
                                 strand='+',
                                 refNCBI='C',
                                 refUCSC='C',
                                 observed='C/T',
                                 molType='genomic',
                                 class_='single',
                                 valid='by-cluster,by-frequency',
                                 avHet=0.5,
                                 avHetSE=0,
                                 func='coding-synon',
                                 locType='exact',
                                 weight=2)
        
        seq1.snps.append(snp11)
        seq1.snps.append(snp12)
        seq1.snps.append(snp13)
        self.quest_smn2.cached_sequences.append(seq1)

        snp21 = SNP131AssayCache(bin=1114,
                                 chrom='chr5',
                                 chromStart=69372352,
                                 chromEnd=69372353,
                                 name='rs4916',
                                 score=0,
                                 strand='+',
                                 refNCBI='T',
                                 refUCSC='T',
                                 observed='C/T',
                                 molType='genomic',
                                 class_='single',
                                 valid='by-cluster,by-frequency',
                                 avHet=0.5,
                                 avHetSE=0,
                                 func='coding-synon,intron',
                                 locType='exact',
                                 weight=2)
        seq2.snps.append(snp21)
        self.quest_smn2.cached_sequences.append(seq2)

