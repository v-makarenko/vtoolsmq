import os
from urllib2 import URLError
from collections import defaultdict

from qtools.components.manager import create_manager
from qtools.model import Vendor, Buffer, Enzyme, VendorEnzyme, Box2, Project, Person, PlateTag, EquipmentSerialBox2, WellTag, Assay
from qtools.model import DropletGenerator, ThermalCycler, PlateType, Plate, PhysicalPlate, DRGroup, SystemVersion, DGUsed
from qtools.model.meta import Session
from qtools.model.sequence import SequenceGroup, Sequence, SequenceGroupComponent
from qtools.model.util import delete_plate_recursive

from . import QToolsCommand, WarnBeforeRunning

from qtools.lib.webservice.neb import read_neb_enzyme_price_list, read_neb_buffer_list, NEBEnzymeSource
from qtools.lib.webservice.ucsc import get_rebase_records

@WarnBeforeRunning("This will reset live database state by deleting plate tags.")
class ResetPlateTagsCommand(QToolsCommand):
    summary = "Resets the plate tags."
    usage = "paster --plugin=qtools reset-plate-tags [config]"
    
    def command(self):
        self.load_wsgi_app()
        
        Session.execute('DELETE from plate_tag_plate')
        Session.execute('DELETE from plate_tag')
        
        Session.commit()
        
        Session.add_all([PlateTag(name=u'Clog'),
                        PlateTag(name=u'Failure'),
                        PlateTag(name=u'Highlight')])
        
        Session.commit()

@WarnBeforeRunning("This will reset live database state by deleting well tags.")
class ResetWellTagsCommand(QToolsCommand):
    summary = "Resets the wall tags"
    usage = "paster --plugin=qtools reset-well-tags [config]"
    
    def command(self):
        self.load_wsgi_app()
        
        Session.execute('DELETE from well_tag_qlbwell')
        Session.execute('DELETE from well_tag')
        
        Session.commit()
        
        Session.add_all([WellTag(name=u'Clog'),
                         WellTag(name=u'NoClog Control'),
                         WellTag(name=u'Rain'),
                         WellTag(name=u'Negative Rain'),
                         WellTag(name=u'Bad Threshold'),
                         WellTag(name=u'Good Well')])
        
        Session.commit()
        
class UpdateLabCommand(QToolsCommand):
    """
    Updates the rosters and readers of the Pleasanton
    Lab.  Changing this file to add a reader or user
    and then running the update-lab command line is
    normally how I add them into the system.

    TODO: GitHub issue to make a starter version of
    this for a new installation.
    """
    summary = "Adds users if necessary."
    usage = "paster --plugin=qtools update-pleasanton-lab [config]"
    
    def command(self):
        self.load_wsgi_app()
        
        #self.update_box2s()
        self.update_dr_groups()
        self.update_dgs_used()
        self.update_droplet_generators()
        self.update_thermal_cyclers()
        self.update_people()
        self.update_plate_types()
        self.update_physical_plates()
        self.update_system_versions()
    

    def update_system_versions(self):
        """ Double check if values are inserted correctly if you re-enable this. mysql seesm to auto inc when id = 0....
        """
        #system_versions = [SystemVersion(id=-1 ,type=u'QX100',desc=u'Unknown Hardware version'),
        #                   SystemVersion(id=0  ,type=u'QX100',desc=u'QX100 - HW Rev A/B'),
        system_versions = [SystemVersion(id=1  ,type=u'QX100',  desc=u'QX100 - HW Rev A/B bigger detector cap differences'),
                           SystemVersion(id=2  ,type=u'QX100',  desc=u'QX100 - HW Rev C'),
                           SystemVersion(id=3  ,type=u'QX150',  desc=u'QX150 - HW Rev Z Upgrade'),
                           SystemVersion(id=4  ,type=u'QX200',  desc=u'QX200 - HW Rev Z'),
                           SystemVersion(id=5  ,type=u'QX201',  desc=u'QX200 - HW with BR built Detector'),
			   SystemVersion(id=6  ,type=u'QX150L', desc=u'QX150 - HW Rev Z Upgrade with LED'),
                           SystemVersion(id=7  ,type=u'QX201L', desc=u'QX201 - HW with BR built LED Detector'),
                           SystemVersion(id=200,type=u'QX200',  desc=u'QX200 - Pre-Beta HW')]
        for sv in system_versions:
            dbsv = Session.query(SystemVersion).filter_by(id=sv.id).first()
            if not dbsv:
                Session.add(sv)
            else:
                if (dbsv.type != sv.type):
                    dbsv.type = sv.type
                if( dbsv.desc != sv.desc):
                    dbsv.desc = sv.desc

        Session.commit()

    def update_plate_types(self):
        plate_types = [PlateType(name=u'CNV',code=u'bcnv'),
                       PlateType(name=u'Dye',code=u'bdye'),
                       PlateType(name=u'Singleplex',code=u'bsplex'),
                       PlateType(name=u'Duplex',code=u'bdplex'),
                       PlateType(name=u'FP/FN',code=u'bfpfn'),
                       PlateType(name=u'HighDNR',code=u'bdnr'),
                       PlateType(name=u'RED',code=u'bred'),
                       PlateType(name=u'Other',code=u'bapp'),
                       PlateType(name=u'Exception', code=u'bexp'),
                       PlateType(name=u'Dye v2',code=u'bdye2'),
                       PlateType(name=u'EventCount', code=u'betaec'),
                       PlateType(name=u'Carryover (ENG)', code=u'bcarry'),
                       PlateType(name=u'4-Well ColorComp (ENG)', code=u'bcc'),
                       PlateType(name=u'Cal Verification (CSFV)', code=u'fvtitr'),
                       PlateType(name=u'4-Well ColorComp (MFG)', code=u'mfgcc'),
                       PlateType(name=u'Dye Calibration', code=u'scc'),
                       PlateType(name=u'Fluidics Verification', code=u'mfgco'),
                       PlateType(name=u'FAM/VIC Titration (Groove)', code=u'gfv'),
                       PlateType(name=u'EvaGreen DNR (Staph/high BG)', code=u'2x10'),
                       PlateType(name=u'DG Pressure Volume', code=u'dgvol'),
                       PlateType(name=u'CNV (Groove)', code=u'gcnv'),
                       PlateType(name=u'EvaGreen DNR (Staph/no BG)', code=u'gdnr'),
                       PlateType(name=u'EvaGreen Assay DNA Load', code=u'gload'),
                       PlateType(name=u'EvaGreen DNR (RNaseP)', code=u'egdnr'),
                       PlateType(name=u'FAM350 no DNA', code=u'fam350'),
                       PlateType(name=u'FAM350 DNA Load', code=u'fm350l'),
                       PlateType(name=u'Auto Validation', code=u'av'),
                       PlateType(name=u'Qx200 DNR validation', code=u'dnr200'),
                       PlateType(name=u'Qx200 Duplex validation', code=u'dplex200'),
                       PlateType(name=u'Qx200 Broad Panel EG val', code=u'eg200'),
                       PlateType(name=u'Qx200 Broad Panel TQ val', code=u'tq200'),
                       PlateType(name=u'Qx200 CNV validation', code=u'cnv200'),
                       PlateType(name=u'Qx200 EvaGreen CNV val', code=u'cnv200e'),
                       PlateType(name=u'Probe EventCount', code=u'probeec'),
                       PlateType(name=u'Eva EventCount', code=u'evaec')
                ]
        
        for pt in plate_types:
            dpt = Session.query(PlateType).filter_by(code=pt.code).first()
            if not dpt:
                Session.add(pt)
            elif pt.name != dpt.name:
                dpt.name = pt.name
        Session.commit()

    def update_physical_plates(self):
        pps = [PhysicalPlate(name='Eppendorf twin.tec PCR plate 96'),
               PhysicalPlate(name='Bio-Rad Hard-Shell White/Clear'),
               PhysicalPlate(name='Bio-Rad Hard-Shell Red/Clear'),
               PhysicalPlate(name='Bio-Rad Hard-Shell Black/Clear'),
               PhysicalPlate(name='Bio-Rad Hard-Shell Yellow/Clear'),
               PhysicalPlate(name='Bio-Rad Hard-Shell Blue/Clear'),
               PhysicalPlate(name='Bio-Rad Hard-Shell Green/Clear')]

        for pp in pps:
            dbpp = Session.query(PhysicalPlate).filter_by(name=pp.name).first()
            if not dbpp:
                Session.add(pp)
        Session.commit()
    
    def update_box2s(self):
        # requires migration 24
        boxes = [Box2(name=u'Alpha 01',code=u'a01', os_name='QUANTAALPHA01', src_dir="Box 2 Alpha 01"),
                 Box2(name=u'Alpha 02',code=u'a02', os_name='QUANTAALPHA02', src_dir="Box 2 Alpha 02"),
                 Box2(name=u'Alpha 03',code=u'a03', os_name='QUANTAALPHA03', src_dir="Box 2 Alpha 03"),
                 Box2(name=u'Alpha 04',code=u'a04', os_name='QUANTAALPHA04', src_dir="Box 2 Alpha 04"),
                 Box2(name=u'Alpha 05',code=u'a05', os_name='QUANTAALPHA05', src_dir="Box 2 Alpha 05"),
                 Box2(name=u'Alpha 06',code=u'a06', os_name='QUANTAALPHA06', src_dir="Box 2 Alpha 06"),
                 Box2(name=u'Alpha 07',code=u'a07', os_name='QUANTAALPHA07', src_dir="Box 2 Alpha 07"),
                 Box2(name=u'Beta Bielas',code=u'b00', os_name='QUANTABETA00', src_dir="Box 2 Beta Bielas/Bielas Data"),
                 Box2(name=u'Beta 01',code=u'b01', os_name='QUANTABETA01', src_dir="DR Beta 01"),
                 Box2(name=u'Beta 02',code=u'b02', os_name='QUANTABETA02', src_dir="DR Beta 02"),
                 Box2(name=u'Beta 03',code=u'b03', os_name='QUANTABETA03', src_dir="DR Beta 03"),
                 Box2(name=u'Beta 04',code=u'b04', os_name='QUANTABETA04', src_dir="DR Beta 04"),
                 Box2(name=u'Beta 05',code=u'b05', os_name='QUANTABETA05', src_dir="DR Beta 05"),
                 Box2(name=u'Beta 06',code=u'b06', os_name='QUANTABETA06', src_dir="DR Beta 06"),
                 Box2(name=u'Beta 07',code=u'b07', os_name='QUANTABETA07', src_dir="DR Beta 07"),
                 Box2(name=u'Beta 08',code=u'b08', os_name='QUANTABETA08', src_dir="DR Beta 08"),
                 Box2(name=u'Beta 09',code=u'b09', os_name='QUANTABETA09', src_dir="DR Beta 09"),
                 Box2(name=u'Beta 10',code=u'b10', os_name='QUANTABETA10', src_dir="DR Beta 10"),
                 Box2(name=u'Beta 11',code=u'b11', os_name='QUANTABETA11', src_dir="DR Beta 11"),
                 Box2(name=u'Beta 12',code=u'b12', os_name='QUANTABETA12', src_dir="DR Beta 12"),
                 Box2(name=u'Beta Tewari',code=u'bt', src_dir="Box 2 Beta Tewari/Tewari Data"),
                 Box2(name=u'Beta Snyder',code=u'bs', src_dir="Box 2 Beta Snyder/Snyder data"),
                 Box2(name=u'Beta Roche',code=u'br', src_dir="Box 2 Beta Roche/Roche Data"),
                 Box2(name=u'Beta NMI',code=u'bn', src_dir="Box 2 Beta NMI/NMI Data"),
                 Box2(name=u'Beta Harvard',code=u'bh', src_dir='DR Harvard/Harvard Data'),
                 Box2(name=u'Beta Belgrader', code=u'bb', src_dir='DR Phil/Phil Data'),
                 Box2(name=u'RevZ Bielas', code=u'zb', src_dir='RevZ Bielas'),
                 Box2(name=u'ENG 001',code=u'e001', src_dir="DR ENG001"),
                 Box2(name=u'ENG 002',code=u'e002', src_dir="DR ENG002"),
                 Box2(name=u'ENG 003',code=u'e003', src_dir="DR ENG003"),
                 Box2(name=u'ENG 10017',code=u'e10017', src_dir="DR ENG 10017"),
                 Box2(name=u'GXD 10021',code=u'e10021', src_dir="DR GXD 10021"),
                 Box2(name=u'GXD 10027',code=u'e10027', src_dir="DR GXD 10027"),
                 Box2(name=u'ENG 10047',code=u'e10047', src_dir="DR ENG 10047"),
                 Box2(name=u'Prod 10001',code=u'p10001', src_dir="DR 10001", fileroot="prod"),
                 Box2(name=u'Prod 10002',code=u'p10002', src_dir="DR 10002", fileroot="prod"),
                 Box2(name=u'Prod 10003',code=u'p10003', src_dir="DR 10003", fileroot="prod"),
                 Box2(name=u'Prod 10004',code=u'p10004', src_dir="DR 10004", fileroot="prod"),
                 Box2(name=u'Prod 10005',code=u'p10005', src_dir="DR 10005", fileroot="prod"),
                 Box2(name=u'Prod 10006',code=u'p10006', src_dir="DR 10006", fileroot="prod"),
                 Box2(name=u'Prod 10007',code=u'p10007', src_dir="DR 10007", fileroot="prod"),
                 Box2(name=u'QuantaAwesome Sr.', code=u'qa1', src_dir="DR-DG-QC Integration"),
                 Box2(name=u'QuantaAwesome Jr.',code=u'qa2', src_dir='DR-DG-QC Integration2'),
                 Box2(name=u'RevC Alpha 002',code=u'c002', os_name='ALPHAC002', src_dir="DR Alpha C 002"),
                 Box2(name=u'RevC Alpha 003',code=u'c003', os_name='ALPHAC003', src_dir="DR Alpha C 003"),
                 Box2(name=u'RevC Beta 001',code=u'c101', os_name='BETAC001', src_dir="DR Beta C 001"),
                 Box2(name=u'RevC Beta 002',code=u'c102', os_name='BETAC002', src_dir="DR Beta C 002"),
                 Box2(name=u'RevC Beta 003',code=u'c103', os_name='BETAC003', src_dir="DR Beta C 003"),
                 Box2(name=u'RevC ENG 001',code=u'c201', os_name='ENGC001', src_dir="DR ENG C 001"),
                 Box2(name=u'RevC ENG 002',code=u'c202', os_name='ENGC002', src_dir="DR ENG C 002"),
                 Box2(name=u'RevZ Beta 001',code=u'z001', os_name='ENGZ001', src_dir="DR RevZ Beta 001"),
                 Box2(name=u'RevZ Beta 002',code=u'z002', os_name='ENGZ002', src_dir="DR RevZ Beta 002"),
                 Box2(name=u'RevZ Beta 003',code=u'z003', os_name='ENGZ003', src_dir="DR RevZ Beta 003"),
                 Box2(name=u'RevZ Beta 004',code=u'z004', os_name='ENGZ004', src_dir="DR RevZ Beta 004"),
                 Box2(name=u'RevZ Beta 005',code=u'z005', os_name='ENGZ005', src_dir="DR RevZ Beta 005"),
                 Box2(name=u'RevZ Beta 006',code=u'z006', os_name='ENGZ006', src_dir="DR RevZ Beta 006"),
                 Box2(name=u'RevZ Beta 011',code=u'z011', os_name='ENGZ011', src_dir="DR RevZ Beta 011"),
                 Box2(name=u'RevZ Beta 012',code=u'z012', os_name='ENGZ012', src_dir="DR RevZ Beta 012"),
                 Box2(name=u'RevZ Beta 013',code=u'z013', os_name='ENGZ013', src_dir="DR RevZ Beta 013"),
                 Box2(name=u'RevZ Beta 014',code=u'z014', os_name='ENGZ014', src_dir="DR RevZ Beta 014"),
                 Box2(name=u'Simulated 001',code=u's01', os_name='SIMUL001', src_dir="DR Simulated 001")]
        
        for box in boxes:
            dbox = Session.query(Box2).filter_by(code=box.code).first()
            if not dbox:
                Session.add(box)
            else:
                if dbox.name != box.name:
                    dbox.name = box.name
                if not hasattr(dbox, 'os_name') or dbox.os_name != box.os_name:
                    dbox.os_name = box.os_name
                if not hasattr(dbox, 'src_dir') or dbox.src_dir != box.src_dir:
                    dbox.src_dir = box.src_dir
            
        Session.commit()

    def update_dr_groups(self):
        dr_groups = [DRGroup(name='Apps DRs', active=True),
                     DRGroup(name='Groove DRs', active=True),
                     DRGroup(name='Golden DRs', active=True),
                     DRGroup(name='Rev Z DRs', active=True),
                     DRGroup(name='Custom DRs', active=True),
                     DRGroup(name='DNA 2.0', active=True),
                     DRGroup(name='Retired', active=False)]
        for group in dr_groups:
            drg = Session.query(DRGroup).filter_by(name=group.name).first()
            if not drg:
                Session.add(group)
        Session.commit()
    
    def update_droplet_generators(self):
        dgs = [DropletGenerator(name=u'DG #01'),
               DropletGenerator(name=u'DG #02'),
               DropletGenerator(name=u'DG #03'),
               DropletGenerator(name=u'DG #04'),
               DropletGenerator(name=u'DG #05'),
               DropletGenerator(name=u'DG #06'),
               DropletGenerator(name=u'DG #07'),
               DropletGenerator(name=u'DG #08'),
               DropletGenerator(name=u'DG #09'),
               DropletGenerator(name=u'DG #10'),
               DropletGenerator(name=u'DG #11'),
               DropletGenerator(name=u'DG #12'),
               DropletGenerator(name=u'DG #13'),
               DropletGenerator(name=u'DG #14'),
               DropletGenerator(name=u'DG #15'),
               DropletGenerator(name=u'DG #16'),
               DropletGenerator(name=u'DG #17'),
               DropletGenerator(id=101, name=u'Pilot #1'),
               DropletGenerator(id=102, name=u'Pilot #2'),
               DropletGenerator(id=103, name=u'Pilot #3'),
               DropletGenerator(id=104, name=u'Pilot #4'),
               DropletGenerator(id=105, name=u'Pilot #5'),
               DropletGenerator(id=201, name=u'Groove DG #1'),
               DropletGenerator(id=202, name=u'Groove DG #2'),
               DropletGenerator(id=203, name=u'Groove DG #3'),
               DropletGenerator(id=204, name=u'Groove DG #4')]
        
        for dg in dgs:
            db_dg = Session.query(DropletGenerator).filter_by(name=dg.name).first()
            if not db_dg:
                Session.add(dg)
        Session.commit()
    
    def update_dgs_used(self):
        dgu = [DGUsed(name=u'Unicorn'),
               DGUsed(name=u'Yeti'),
               DGUsed(name=u'Nessie')]
        
        for dgs in dgu:
            db_dgu = Session.query(DGUsed).filter_by(name=dgs.name).first()
            if not db_dgu:
                Session.add(dgs)
        Session.commit()

    def update_thermal_cyclers(self):
        tcs = [ThermalCycler(name=u'Eppendorf 1'),
               ThermalCycler(name=u'Eppendorf 2'),
               ThermalCycler(name=u'Eppendorf 3'),
               ThermalCycler(name=u'Eppendorf 4'),
               ThermalCycler(name=u'Eppendorf 5'),
               ThermalCycler(name=u'Eppendorf 6'),
               ThermalCycler(name=u'Bio-Rad T100 1'),
               ThermalCycler(name=u'Bio-Rad C1000 1'),
               ThermalCycler(name=u'Eppendorf 8')]
        
        for tc in tcs:
            db_tc = Session.query(ThermalCycler).filter_by(name=tc.name).first()
            if not db_tc:
                Session.add(tc)
        Session.commit()

    def update_people(self):
        people = [Person(first_name=u'Adam', last_name=u'Bemis', name_code=u'AdamB'),
                  Person(first_name=u'Adam', last_name=u'Lowe', name_code=u'AdamL'),
                  Person(first_name=u'Adam', last_name=u'McCoy', name_code=u'AdamM'),
                  Person(first_name=u'Amer', last_name=u'El-Hage', name_code=u'AmerE'),
                  Person(first_name=u'Amy', last_name=u'Hiddessen', name_code=u'AmyH'),
                  Person(first_name=u'Andi', last_name=u'Kleissner', name_code=u'AndiK'),
                  Person(first_name=u'Austin', last_name=u'So', name_code=u'AustinS'),
                  Person(first_name=u'Ben', last_name=u'Hindson', name_code=u'BenH'),
                  Person(first_name=u'Phil', last_name=u'Belgrader', name_code=u'PhilB'),
                  Person(first_name=u'Bill', last_name=u'Colston', name_code=u'BillC'),
                  Person(first_name=u'Bin', last_name=u'Zhang', name_code=u'BinZ'),
                  Person(first_name=u'Camille', last_name=u'Troup', name_code=u'CamilleT'),
                  Person(first_name=u'Cher', last_name=u'Zhang', name_code=u'CherZ'),
                  Person(first_name=u'Chris', last_name=u'Hindson', name_code=u'ChrisH'),
                  Person(first_name=u'Claudia', last_name=u'Litterst', name_code=u'ClaudiaL'),
                  Person(first_name=u'Crystal', last_name=u'Jain', name_code=u'CrystalJ'),
                  Person(first_name=u'Dave', last_name=u'Mukhopadhyay', name_code=u'DaveM'),
                  Person(first_name=u'Dave', last_name=u'Stumbo', name_code=u'DaveS'),
                  Person(first_name=u'David', last_name=u'Sally', name_code=u'DavidS'),
                  Person(first_name=u'Dawne', last_name=u'Shelton', name_code=u'DawneS'),
                  Person(first_name=u'Dean', last_name=u'Wittmann', name_code=u'DeanW'),
                  Person(first_name=u'Debkishore', last_name=u'Mitra', name_code=u'DebM'),
                  Person(first_name=u'Dianna', last_name=u'Maar', name_code=u'DiannaM'),
                  Person(first_name=u'Dimitri', last_name=u'Skvortsov', name_code=u'DSkvortsov'),
                  Person(first_name=u'Don', last_name=u'Masquelier', name_code=u'DonM'),
                  Person(first_name=u'Duc', last_name=u'Do', name_code=u'DucD'),
                  Person(first_name=u'Douglas', last_name=u'Greiner', name_code=u'DougG'),
                  Person(first_name=u'Eli', last_name=u'Hefner', name_code=u'EliH'),
                  Person(first_name=u'Elise', last_name=u'Bullock', name_code=u'EliseB'),
                  Person(first_name=u'Erin', last_name=u'Steenblock', name_code=u'ErinS'),
                  Person(first_name=u'Gayathri', last_name=u'Ramaswamy', name_code=u'GayathriR'),
                  Person(first_name=u'Geoff', last_name=u'McDermott', name_code=u'GeoffM'),
                  Person(first_name=u'George', last_name=u'Carman', name_code=u'GeorgeC'),
                  Person(first_name=u'George', last_name=u'Karlin-Neumann', name_code=u'GeorgeKN'),
                  Person(first_name=u'Irene', last_name=u'Castillo', name_code=u'IreneC'),
                  Person(first_name=u'Jack', last_name=u'Regan', name_code=u'JackR'),
                  Person(first_name=u'Jeff', last_name=u'Mellen', name_code=u'JeffM'),
                  Person(first_name=u'Jen', last_name=u'Berman', name_code=u'JenB'),
                  Person(first_name=u'Jeremy', last_name=u'Agresti', name_code=u'JeremyA'),
                  Person(first_name=u'Jerry', last_name=u'Hurst', name_code=u'JerryH'),
                  Person(first_name=u'Joh', last_name=u'Wong', name_code=u'JohW'),
                  Person(first_name=u'Johannes', last_name=u'Schrankenmueller', name_code=u'JohannesS'),
                  Person(first_name=u'John', last_name=u'Dzenitis', name_code=u'JohnD'),
                  Person(first_name=u'Jon', last_name=u'Petersen', name_code=u'JonP'),
                  Person(first_name=u'Joshua', last_name=u'Mopas', name_code=u'JoshuaM'),
                  Person(first_name=u'Kapil', last_name=u'Bajaj', name_code=u'KapilB'),
                  Person(first_name=u'Keith', last_name=u'Hamby', name_code=u'KeithH'),
                  Person(first_name=u'Kevin', last_name=u'Ness', name_code=u'KevinN'),
                  Person(first_name=u'Klint', last_name=u'Rose', name_code=u'KlintR'),
                  Person(first_name=u'Laura', last_name=u'Gilson', name_code=u'LauraG'),
                  Person(first_name=u'Leanne', last_name=u'Javier', name_code=u'LeanneJ'),
                  Person(first_name=u'Luc', last_name=u'Bousse', name_code=u'LucB'),
                  Person(first_name=u'Luz', last_name=u'Montesclaros', name_code=u'LuzM'),
                  Person(first_name=u'Maria', last_name=u'Dona', name_code=u'MariaD'),
                  Person(first_name=u'Mary', last_name=u'Ma', name_code=u'MaryM'),
                  Person(first_name=u'Mei', last_name=u'Ng', name_code=u'MeiN'),
                  Person(first_name=u'Mike', last_name=u'Hodel', name_code=u'MikeH'),
                  Person(first_name=u'Nestor', last_name=u'Castillo', name_code=u'NestorC'),
                  Person(first_name=u'Nia', last_name=u'Charrington', name_code=u'NiaC'),
                  Person(first_name=u'Nick', last_name=u'Erndt', name_code=u'NickE'),
                  Person(first_name=u'Nick', last_name=u'Heredia', name_code=u'NickH'),
                  Person(first_name=u'Niels', last_name=u'Klitgord', name_code=u'NielsK'),
                  Person(first_name=u'Pallavi', last_name=u'Shah', name_code=u'PallaviS'),
                  Person(first_name=u'Paul', last_name=u'Wyatt', name_code=u'PaulW'),
                  Person(first_name=u'Pingchen', last_name=u'Chen', name_code=u'PingchenC'),
                  Person(first_name=u'Raffi', last_name=u'Novosel', name_code=u'RaffiN'),
                  Person(first_name=u'Ryan', last_name=u'Koehler', name_code=u'RyanK'),
                  Person(first_name=u'Sam', last_name=u'Marrs', name_code=u'SamM'),
                  Person(first_name=u'Samantha', last_name=u'Cooper', name_code=u'SamanthaC'),
                  Person(first_name=u'Sean', last_name=u'Cater', name_code=u'SeanC'),
                  Person(first_name=u'Serge', last_name=u'Saxonov', name_code=u'SergeS'),
                  Person(first_name=u'Shawn', last_name=u'Hodges', name_code=u'ShawnH'),
                  Person(first_name=u'Sherman', last_name=u'Cheng', name_code=u'ShermanC'),
                  Person(first_name=u'Shenglong', last_name=u'Wang', name_code=u'ShenglongW'),
                  Person(first_name=u'Stefano', last_name=u'Schiaffino', name_code=u'StefanoS'),
                  Person(first_name=u'Steve', last_name=u'Romine', name_code=u'SteveR'),
                  Person(first_name=u'Steven', last_name=u'Vanbuskirk', name_code=u'StevenV'),
                  Person(first_name=u'Tesa', last_name=u'Abad', name_code=u'TesaA'),
                  Person(first_name=u'Tina', last_name=u'Legler', name_code=u'TinaL'),
                  Person(first_name=u'Tony', last_name=u'Makarewicz', name_code=u'TonyM'),
                  Person(first_name=u'Trey', last_name=u'Cauley', name_code=u'TreyC'),
                  Person(first_name=u'Tyler', last_name=u'Kitano', name_code=u'TylerK'),
                  Person(first_name=u'Vashishtha', last_name=u'Patil', name_code=u'VashishthaP'),
                  Person(first_name=u'Wei', last_name=u'Yang', name_code=u'WeiY'),
                  Person(first_name=u'Yann', last_name=u'Jouvenot', name_code=u'YannJ'),
                  Person(first_name=u'Yaqi', last_name=u'Wang', name_code=u'YaqiW')]
        
        for person in people:
            if not Session.query(Person).filter_by(name_code=person.name_code).first():
                Session.add(person)
        
        Session.commit()
  

class BetaSetupCommand(QToolsCommand):
    """
    TODO: figure whether this is necessary, or can be rolled into update-lab
    """
    summary = "Sets up structures needed for beta test"
    usage = "paster --plugin=qtools beta-setup [config]"

    def command(self):
        self.load_wsgi_app()

        projects = [Project(name=u'Beta Test',code=u'Beta'),
                    Project(name=u'Validation',code=u'Validation')]

        for project in projects:
            dp = Session.query(Project).filter_by(name=project.name).first()
            if not dp:
                Session.add(project)
            
        Session.commit()


class ExcludeBetaPlateCommand(QToolsCommand):
    summary = "Excludes a plate from QTools beta test."
    usage = "paster --plugin=qtools exclude-beta-plate [plate#] [config]"

    def command(self):
        app = self.load_wsgi_app()
        if len(self.args) > 1:
            plate_id = int(self.args[0])
        else:
            raise Exception, "Not enough arguments: %s" % self.__class__.usage
        
        plate = Session.query(Plate).get(plate_id)
        if not plate:
            raise Exception, "Could not find plate #: %s" % plate_id
        
        plate_type = Session.query(PlateType).filter_by(code=u'bexp').first()
        plate.plate_type = plate_type
        Session.commit()


@WarnBeforeRunning("This will delete a plate from the DB only.  If the underlying plate file is still accessible to QTools, it may be readded on the next cron pass.")
class DeletePlatesCommand(QToolsCommand):
    """
    Deletes plates with the specified IDs.  Keep in mind that
    QTools will rescan the file and re-add it to the database
    if the underlying QLP is still present in a place normally
    scanned by the cron job.
    """
    summary = "Deletes a plate and its associated files, including qlbfile entries."
    usage = "paster --plugin=qtools delete-plates [plates] [config]"

    def command(self):
        app = self.load_wsgi_app()
        
        # enforce at least one plate
        if len(self.args) < 2:
            raise ValueError, self.__class__.usage
    
        for i in range(0,len(self.args)-1):
            print "Deleting plate #%s" % self.args[i]
            delete_plate_recursive(int(self.args[i]))
            Session.commit()

@WarnBeforeRunning("This will reset live database state by deleting enzymes.")
class ResetNEBEnzymesWWWCommand(QToolsCommand):
    """
    Resets available NEB enzymes through their materials on the web.

    This process is two years old, to get both the available
    enzymes and their sequences, and the price.  It may not
    work.  In any case, we are migrating to a more standard
    restriction enzyme roster in the future, so we may not
    need to scan NEB's library for enzymes which are guaranteed
    to cut between gene copies.
    """
    summary = "Resets available NEB enzymes through materials on the web."
    usage = "paster --plugin=qtools reset-neb-enzymes-www [config]"

    def command(self):
        app = self.load_wsgi_app()

        print "Clearing NEB buffer tables..."
        # make this reversible...
        neb = Session.query(Vendor).filter_by(name='NEB').first()
        if neb:
            enzymes = neb.enzymes
            for enz in enzymes:
                Session.delete(enz)
            neb.enzymes = []

        Session.commit()

        # now go with the vendors (question: is it vendor enzyme or enzyme
        # in general subject to methylation)
        source = NEBEnzymeSource()
        if not neb:
            neb = Vendor(name="NEB", website="http://www.neb.com")
            Session.add(neb)
            Session.commit()

        try:
            for name, page_uri in source.iter_restriction_enzymes():
                print "Processing %s..." % name
                enz = Session.query(Enzyme).filter_by(name=name).first()
                if not enz:
                    enz = Enzyme(name=name)
                    Session.add(enz)
            
                details = source.enzyme_details(name, page_uri)
                if details:
                    enz.cutseq = details['sequence']
                    enz.methylation = details['methylation_sensitivity']

                    buf = Session.query(Buffer).filter_by(name=details['buffer']).first()
                    if not buf:
                        buf = Buffer(name=details['buffer'])
                        Session.add(buf)

                    ve = VendorEnzyme(enzyme=enz, vendor=neb, buffer=buf)
                    ve.unit_cost_1 = details.get('unit_cost_1', None)
                    ve.unit_cost_2 = details.get('unit_cost_2', None)
                    ve.unit_serial_1 = details.get('unit_serial_1', None)
                    ve.unit_serial_2 = details.get('unit_serial_2', None)
                    ve.vendor_serial = details.get('vendor_serial', None)
                    if ve.unit_cost_1 is not None:
                        Session.add(ve)
                # save per enzyme, interruption should be logged
                Session.commit()
        except IOError, e:
            Session.rollback()
            print "Could not communicate with NEB server"
        except URLError, e:
            Session.rollback()
            print "Error loading page from NEB server"


@WarnBeforeRunning("This will reset live database state by deleting enzymes, vendors and buffers.")
class ResetEnzymesCommand(QToolsCommand):
    """
    Resets the base enzymes tables to only include
    base vendors (NEB) and their buffers.  You will
    need to run the ResetNEBEnzymesWWWCommand to
    populate the tables with NEB enzymes.
    """
    summary = "Resets the enzymes table."
    usage = "paster --plugin=qtools reset-enzymes [config]"
    
    def command(self):
        app = self.load_wsgi_app()
        
        print "Clearing buffer tables..."
        Session.execute('DELETE from vendor_enzyme')
        Session.execute('DELETE from buffer')
        Session.execute('DELETE from vendor')
        Session.execute('DELETE from enzyme')
        
        Session.commit()

        self.setup_buffers()
        self.setup_vendors()

    
    def setup_buffers(self):
        Session.add_all([Buffer(name=u"NEBuffer 1"),
                         Buffer(name=u"NEBuffer 2"),
                         Buffer(name=u"NEBuffer 3"),
                         Buffer(name=u"NEBuffer 4"),
                         Buffer(name=u'NEBuffer DpnII'),
                         Buffer(name=u'NEBuffer EcoRI'),
                         Buffer(name=u'NEBuffer SspI')])
        
        Session.commit()
    
    def setup_vendors(self):
        NEB = Vendor(name=u'NEB')
        Session.add(NEB)
        Session.commit()
        
        Session.commit()

@WarnBeforeRunning("Be sure you have a CSV file compatible with Ryan's assay format, or you may get unexpected results.")
class BulkLoadAssayCommand(QToolsCommand):
    """
    Bulk load assays from a CSV file.  The assay sequences will
    be analyzed in the background for tM and SNPs after the
    data is loaded into the sequence tables.

    TODO: look for an example assay CSV file that this will load

    expecte csv fields:
    

    Relies on a little bit of standardization from Ryan's design
    programs.  Right now assumes Ryan is the owner.
    """
    summary = "Bulk loads assays from the specified file.  Mode can be 'cnv','gex','red','snp' or 'abs'"
    usage = "paster --plugin=qtools bulk-load-assays [file] [mode] [config]"

    def command(self):
        from qtools.constants.job import JOB_ID_PROCESS_ASSAY
        from qtools.messages.sequence import ProcessSequenceGroupMessage

        app = self.load_wsgi_app()
        mgr = create_manager(app.config)

        if len(self.args) < 3:
            raise ValueError, self.usage

        infile = open(self.args[-3], 'r')
        mode = self.args[-2].lower()

        #read in liens
        lines = [l for l in infile]
        infile.close()

        assay_line_dict = defaultdict(lambda: defaultdict(lambda: None))
        for line in lines:
            toks = self.__split_line(line)
            name = self.__assay_name(toks)
            if not name:
                continue
            comp = self.__assay_component(toks)
            seq = self.__assay_sequence(toks)
            assay_line_dict[name][comp] = seq

        Owner = Session.query(Person).filter_by(name_code=u'NielsK').first()

        for k, v in sorted(assay_line_dict.items()):
            sg = SequenceGroup(name=k,
                               owner_id=Owner.id,
                               gene=v['gene'],
                               kit_type = SequenceGroup.CHEMISTRY_TYPE_TAQMAN,
                               type = {'red': SequenceGroup.ASSAY_TYPE_RED,
                                       'cnv': SequenceGroup.ASSAY_TYPE_CNV,
                                       'snp': SequenceGroup.ASSAY_TYPE_SNP,
                                       'gex': SequenceGroup.ASSAY_TYPE_GEX,
                                       'abs': SequenceGroup.ASSAY_TYPE_ABS}[mode],
                               notes = mode + ' Content Project assay design. ' + \
                                       'Imported from %s' % os.path.basename(self.args[-3]),
                               status = v['status'],
                               analyzed = False)
            fps = Sequence(sequence=v['for'],
                           strand='+')
            rps = Sequence(sequence=v['rev'],
                           strand='+')
            if v['taq']:
                ps = Sequence(sequence=v['taq'],
                              strand='+')

            sg.forward_primers.append(SequenceGroupComponent(
                                        sequence=fps,
                                        role=SequenceGroupComponent.FORWARD_PRIMER,
                                        barcode_label='%s_FP1' % k[:12],
                                        primary=True,
                                        order=0))
            sg.reverse_primers.append(SequenceGroupComponent(
                                        sequence=rps,
                                        role=SequenceGroupComponent.REVERSE_PRIMER,
                                        barcode_label='%s_RP1' % k[:12],
                                        primary=True,
                                        order=0))
            if v['taq']:
                sg.probes.append(SequenceGroupComponent(
                                            sequence=ps,
                                            role=SequenceGroupComponent.PROBE,
                                            barcode_label='%s_P1FM' % k[:11],
                                            primary=True,
                                            order=0,
                                            dye=v['dye'],
                                            quencher='IABkFQ'))
            
            print "Committing %s..." % k
            Session.add(sg)
            Session.commit()
            job_queue = mgr.jobqueue()

            job = job_queue.add(JOB_ID_PROCESS_ASSAY, ProcessSequenceGroupMessage(sg.id))
            sg.pending_job_id = job.id
            Session.commit()

    def __split_line(self, line):
        return line.strip().split('\t')

    def __assay_name(self, toks):
        if '__' in toks[0]:
            return toks[0].split('__')[0]
        else:
            return None

    def __assay_component(self, toks):
        if '__' in toks[0]:
            return toks[0].split('__')[-1]
        else:
            return None

    def __assay_sequence(self, toks):
        return toks[1].upper()
