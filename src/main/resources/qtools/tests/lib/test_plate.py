from unittest import TestCase
from qtools.lib.plate import plate_from_qlp, apply_template_to_plate
from qtools.lib.qlb_objects import ExperimentMetadataQLPlate
from qtools.model import Session, PlateTemplate, Box2, QLBFile, QLBPlate
from qtools.tests import SimpleEnvironmentDatabaseTest
from datetime import datetime, timedelta

class TestNamePlate(SimpleEnvironmentDatabaseTest):
    def setUp(self):
        super(TestNamePlate, self).setUp()
        self.nameVariant = QLBFile(dirname='Box 2 Alpha 03/TestProject_TestU_Test 2_2011_01_19_09_36',
                                   run_id='nameVariant',
                                   basename='TestProject_TestU_Test 2.qlp',
                                   type='processed',
                                   read_status=1,
                                   mtime=datetime.now()-timedelta(0,0,3))
        
        self.unknownName = QLBFile(dirname='Box 2 Alpha 03/Unknown_TestU_Test_2011_01_19_09_36',
                                   run_id='unknownName',
                                   basename='Unknown_TestU_Test 2.qlp',
                                   type='processed',
                                   read_status=1,
                                   mtime=datetime.now()-timedelta(0,0,5))
        
        self.plateTemplate = PlateTemplate(prefix='TestProject_TestU_Test',
                                           project_id=self.testProject.id,
                                           operator_id=self.testUser.id,
                                           dg_oil = 1,
                                           dr_oil = 2,
                                           master_mix = 10,
                                           fluidics_routine = 12,
                                           droplet_generation_method = 4)
        
        self.shortTemplate = PlateTemplate(prefix='TestProject_TestU',
                                           project_id=self.testProject.id,
                                           operator_id=self.testUser.id,
                                           dg_oil = 2,
                                           dr_oil = 3,
                                           master_mix = 2,
                                           fluidics_routine = 13,
                                           droplet_generation_method = 3)
                                          
        self.host_machine = Session.query(Box2).filter_by(src_dir='Box 2 Alpha 03').one()
        self.qlbPlate = QLBPlate(file=self.readQLP, host_machine=self.host_machine.os_name)
        self.plateVariant = QLBPlate(file=self.nameVariant, host_machine=self.host_machine.os_name)
        self.unknownPlate = QLBPlate(file=self.unknownName, host_machine=self.host_machine.os_name)
            
        Session.add_all([self.plateTemplate, self.nameVariant, self.unknownName, self.qlbPlate, self.plateVariant, self.unknownPlate, self.shortTemplate])
        Session.commit()
    
    def test_plate_from_qlp(self):
        plate = plate_from_qlp(self.qlbPlate)
        # TODO: maybe this should be automatic?
        plate.qlbplate = self.qlbPlate

        apply_template_to_plate(ExperimentMetadataQLPlate(), plate)
        assert plate.project_id == self.testProject.id
        assert plate.operator_id == self.testUser.id
        assert plate.dg_oil == 1
        assert plate.dr_oil == 2
        assert plate.master_mix == 10
        assert plate.fluidics_routine == 12
        assert plate.droplet_generation_method == 4
        assert plate.droplet_maker_id is None
        assert plate.box2_id == self.host_machine.id
        
        plate2 = plate_from_qlp(self.plateVariant)
        plate2.qlbplate = self.plateVariant
        apply_template_to_plate(ExperimentMetadataQLPlate(), plate2)
        assert plate2.project_id == self.testProject.id
        assert plate2.operator_id == self.testUser.id
        assert plate2.dg_oil == 1
        assert plate2.dr_oil == 2
        assert plate2.master_mix == 10
        assert plate2.fluidics_routine == 12
        assert plate2.droplet_generation_method == 4
        assert plate2.droplet_maker_id is None
        assert plate.box2_id == self.host_machine.id
        
        plate3 = plate_from_qlp(self.unknownPlate)
        plate3.qlbplate = self.unknownPlate
        apply_template_to_plate(ExperimentMetadataQLPlate(), plate3)
        assert plate3.project_id is None
        assert plate3.operator_id is None
        assert plate3.dg_oil is None
        assert plate3.dr_oil is None
        assert plate3.master_mix is None
        assert plate3.fluidics_routine is None
        assert plate3.droplet_generation_method is None
        assert plate3.droplet_maker_id is None
        assert plate3.box2_id == self.host_machine.id

        # plate-based only
        plate3b = plate_from_qlp(self.unknownPlate)
        plate3b.qlbplate = self.unknownPlate
        apply_template_to_plate(ExperimentMetadataQLPlate(plate_template_id=self.plateTemplate.id), plate3b)
        assert plate3b.project_id == self.testProject.id
        assert plate3b.operator_id == self.testUser.id
    
    def tearDown(self):
        Session.rollback() # catches pending changes
        Session.delete(self.plateTemplate)
        Session.delete(self.shortTemplate)
        Session.delete(self.qlbPlate)
        Session.delete(self.plateVariant)
        Session.delete(self.unknownPlate)
        Session.delete(self.nameVariant)
        Session.delete(self.unknownName)
        Session.commit()
        
        super(TestNamePlate, self).tearDown()
        
