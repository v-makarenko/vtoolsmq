from qtools.model import now
from qtools.model.meta import Base

metadata = Base.metadata

from sqlalchemy import orm, Integer, String, Text, Date, Boolean, Numeric
from sqlalchemy.orm import backref
from sqlalchemy.schema import Table, Column, Sequence, ForeignKey

class ManufacturingPlateBatch(Base):
    __tablename__ = "mfg_plate_batch"
    __table_args__ = {"mysql_engine": 'InnoDB', 'mysql_charset': 'utf8'}

    DG_METHOD_CHIPSHOP = 1
    DG_METHOD_WEIDMANN_V5 = 105
    DG_METHOD_THINXXS_V2A = 201
    DG_METHOD_THINXXS_V2B = 202
    DG_METHOD_THINXXS_V2C = 203
    DG_METHOD_THINXXS_V2CD = 205

    TARGET_DROPLET_SIZE = 121
    TARGET_DROPLET_VARIANCE = 2

    id = Column(Integer, Sequence('mfg_plate_batch_id', optional=True), primary_key=True)
    name = Column(String(50), nullable=False, unique=True)
    creation_date = Column(Date, nullable=False)
    creator_id = Column(Integer, ForeignKey('person.id'), nullable=False)

    #### OBSOLETE FIELDS ####
    master_mix_lot = Column(String(50), nullable=True)
    fam_hi_dye_lot = Column(String(50), nullable=True)
    fam_lo_dye_lot = Column(String(50), nullable=True)
    vic_hi_dye_lot = Column(String(50), nullable=True)
    vic_lo_dye_lot = Column(String(50), nullable=True)
    #### END OBSOLETE FIELDS #####

    plate_type_id = Column(Integer, ForeignKey('plate_type.id'), nullable=False)
    default_dg_method = Column(Integer, nullable=False)
    notes = Column(Text, nullable=True)
    thermal_cycler_id = Column(Integer, ForeignKey('thermal_cycler.id'), nullable=True)

    # now a defunct column -- previously there was a distinction between internal & deployable
    # droplets in product batches
    shippable = Column(Boolean, nullable=True, default=False)
    
    plates = orm.relation('ManufacturingPlate', backref='batch', cascade='all, delete-orphan')
    plate_type = orm.relation('PlateType')
    creator = orm.relation('Person')
    thermal_cycler = orm.relation('ThermalCycler')

    fam_hi_size = Column(Numeric(precision=5, scale=2), nullable=True)
    vic_hi_size = Column(Numeric(precision=5, scale=2), nullable=True)
    hex_hi_size = Column(Numeric(precision=5, scale=2), nullable=True)

    def qc_plate_record(self, dyeset=None):
        qcs = self.qc_plate_records(dyeset=dyeset)
        if len(qcs) > 0:
            return qcs[0]
        return None

    def qc_plate_records(self, dyeset=None):
        if dyeset is None:
            qcs = [p for p in self.plates if p.qc_plate]
        else:
            qcs = [p for p in self.plates if p.qc_plate and p.plate and p.plate.qlbplate.dyeset == dyeset]

        return qcs

    @classmethod
    def dg_method_display_options(cls):
        return [(ManufacturingPlateBatch.DG_METHOD_CHIPSHOP, 'Chip Shop'),
                (ManufacturingPlateBatch.DG_METHOD_WEIDMANN_V5, 'Weidmann v5'),
                (ManufacturingPlateBatch.DG_METHOD_THINXXS_V2A, 'ThinXXS v2a'),
                (ManufacturingPlateBatch.DG_METHOD_THINXXS_V2B, 'ThinXXS v2b'),
                (ManufacturingPlateBatch.DG_METHOD_THINXXS_V2C, 'ThinXXS v2c'),
                (ManufacturingPlateBatch.DG_METHOD_THINXXS_V2CD, 'ThinXXS v2c Dimpled')]
    
    @property
    def default_dg_method_display(self):
        return dict(self.__class__.dg_method_display_options()).get(self.default_dg_method, '')

    @classmethod
    def min_droplet_size(cls):
        return cls.TARGET_DROPLET_SIZE - cls.TARGET_DROPLET_VARIANCE

    @classmethod
    def max_droplet_size(cls):
        return cls.TARGET_DROPLET_SIZE + cls.TARGET_DROPLET_VARIANCE

    def dye_correctly_sized(self, dye):
        """
        Return whether or not the batch has the correct size for the
        specified dye.  Valid dyes include FAM, VIC and HEX.
        """
        dyestr = dye.lower()
        dye_size = getattr(self, '%s_hi_size' % dyestr, None)
        if dye_size is None:
            return None
        elif dye_size < self.__class__.min_droplet_size() or dye_size > self.__class__.max_droplet_size():
            return False
        else:
            return True

    @property
    def all_correctly_sized(self):
        """
        Returns True if the droplets are correctly sized in the dyes that were
        tested.  It's possible that one dye set hasn't been sized yet-- this
        code takes the assumption (driven by CSFV) that not all dyes may be
        tested in a single batch.

        If no dye droplets have been sized, return None.
        """
        found_dye = False
        for dye in ('FAM', 'VIC', 'HEX'):
            bool_val = self.dye_correctly_sized(dye) # either False or None
            if bool_val == False:
                return False
            elif bool_val == True:
                found_dye = True
            # if none, continue
        # no dyes
        if found_dye:
            return True
        # no dyes present -- 
        else:
            return None



class ManufacturingPlate(Base):
    __tablename__ = "mfg_plate"
    __table_args__ = {"mysql_engine": 'InnoDB', 'mysql_charset': 'utf8'}

    id = Column(Integer, Sequence('mfg_plate_id', optional=True), primary_key=True)
    mfg_batch_id = Column(Integer, ForeignKey('mfg_plate_batch.id'), nullable=False)
    name = Column(String(50), nullable=False, unique=True)
    dg_method = Column(Integer, nullable=False)
    dg_notes = Column(Text, nullable=True)
    plate_notes = Column(Text, nullable=True)
    qc_plate = Column(Boolean, nullable=False, default=False)
    plate_id = Column(Integer, ForeignKey('plate.id'), nullable=True)
    secondary_plate_id = Column(Integer, ForeignKey('plate.id'), nullable=True)
    thermal_cycler_id = Column(Integer, ForeignKey('thermal_cycler.id'), nullable=True)
    plate = orm.relation('Plate', primaryjoin='ManufacturingPlate.plate_id == Plate.id')
    secondary_plate = orm.relation('Plate', primaryjoin='ManufacturingPlate.secondary_plate_id == Plate.id')

    @property
    def dg_method_display(self):
        return dict(ManufacturingPlateBatch.dg_method_display_options()).get(self.dg_method, '')
    
    @property
    def batch_qc_plate(self):
        if not self.plate:
            qc_plate_record = self.batch.qc_plate_record()
        else:
            qc_plate_record = self.batch.qc_plate_record(dyeset=self.plate.qlbplate.dyeset)

        if qc_plate_record and qc_plate_record.plate:
            return qc_plate_record.plate
        else:
            return None
