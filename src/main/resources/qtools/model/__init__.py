"""The application's model objects"""
import os, re
from collections import defaultdict
from datetime import datetime

from sqlalchemy import schema, types, orm, and_, or_
from sqlalchemy.dialects.mysql.base import BIGINT as BigInt
from sqlalchemy.dialects.mysql.base import MSEnum, MSSet
from sqlalchemy.dialects.mysql.base import MEDIUMTEXT as MediumText
from sqlalchemy.ext.associationproxy import association_proxy
from sqlalchemy.orm import joinedload_all

from qtools.model.meta import Session, Base
from qtools.lib.bio import reverse_complement, SequenceGroup

# special case
metadata = Base.metadata

def init_model(engine, **kwargs):
    """Call me before using any of the tables or classes in the model"""
    Session.configure(bind=engine, autoflush=True, autocommit=False)

def prevent_real_flush(*args, **kwargs):
    print 'Attempted write to read-only DB connection.'
    return

def init_model_readonly(engine, **kwargs):
    Session.configure(bind=engine, autoflush=False, autocommit=False)
    Session.flush = prevent_real_flush

def property_attr_wrapper(bind_func='fget', **kwargs):
    """
    Creates a getter/setter property derived properties the same column attribute capability
    as mapped SQLAlchemy Columns.

    :param bind_func: Which function on the property to bind to (default: getter).
                      If there is no getter on the property, set to 'fset' or 'fdel'.
    """
    def wrapper(prop):
        func = getattr(prop, bind_func)
        for k, v in kwargs.items():
            # do not allow override
            if hasattr(func, k):
                raise ValueError, "Cannot override preexisting function attribute: %s" % k
            setattr(func, k, v)
        return prop
    return wrapper


def now():
	return datetime.now()
	

lot_number_plate_table = schema.Table('lot_number_plate', metadata,
    schema.Column('id', types.Integer, schema.Sequence('lot_number_plate_seq_id', optional=True), primary_key=True),
	schema.Column('plate_id', types.Integer, schema.ForeignKey('plate.id')),
	schema.Column('lot_number_id', types.Integer, schema.ForeignKey('lot_number.id')),
	mysql_engine='InnoDB',
	mysql_charset='utf8'
)

plate_tag_plate_table = schema.Table('plate_tag_plate', metadata,
    schema.Column('id', types.Integer, schema.Sequence('plate_tag_plate_seq_id', optional=True), primary_key=True),
    schema.Column('plate_id', types.Integer, schema.ForeignKey('plate.id')),
    schema.Column('plate_tag_id', types.Integer, schema.ForeignKey('plate_tag.id')),
    mysql_engine='InnoDB',
    mysql_charset='utf8'
)

assay_tag_assay_table = schema.Table('assay_tag_assay', metadata,
    schema.Column('id', types.Integer, schema.Sequence('assay_tag_assay_seq_id', optional=True), primary_key=True),
    schema.Column('assay_id', types.Integer, schema.ForeignKey('assay.id')),
    schema.Column('assay_tag_id', types.Integer, schema.ForeignKey('assay_tag.id')),
    mysql_engine='InnoDB',
    mysql_charset='utf8'
)

analysis_group_plate_table = schema.Table('analysis_group_plate', metadata,
    schema.Column('id', types.Integer, schema.Sequence('analysis_group_plate_seq_id', optional=True), primary_key=True),
    schema.Column('analysis_group_id', types.Integer, schema.ForeignKey('analysis_group.id')),
    schema.Column('plate_id', types.Integer, schema.ForeignKey('plate.id')),
    mysql_engine='InnoDB',
    mysql_charset='utf8'
)

analysis_group_reprocess_table = schema.Table('analysis_group_reprocess', metadata,
    schema.Column('id', types.Integer, schema.Sequence('analysis_group_reprocess_seq_id', optional=True), primary_key=True),
    schema.Column('analysis_group_id', types.Integer, schema.ForeignKey('analysis_group.id')),
    schema.Column('reprocess_config_id', types.Integer, schema.ForeignKey('reprocess_config.id')),
    mysql_engine='InnoDB',
    mysql_charset='utf8'
)

class AssayCacheMixin(object):
    """
    Declarative mixin for assay caches.
    """
    def cached(self, padding_pos5, padding_pos3):
        """
        Determine whether the cache object has records for the
        specified padding.
        """
        return padding_pos5 <= self.seq_padding_pos5 and padding_pos3 <= self.seq_padding_pos3

class PercentAttributeMixin(object):
    """
    Declarative mixin for computing the right values for percentages,
    when the underlying attribute is absolute.
    """
    def percent(self, val):
        if val is None:
            return None
        else:
            return val*100

class AssaySampleCNV(Base):
    __tablename__ = "assay_sample_cnv"
    __table_args__ = {"mysql_engine": 'InnoDB', 'mysql_charset': 'utf8'}
    
    id = schema.Column(types.Integer, schema.Sequence('assay_sample_cnv_id', optional=True), primary_key=True)
    sample_id = schema.Column(types.Integer, schema.ForeignKey('sample.id'), nullable=False)
    target_assay_id = schema.Column(types.Integer, schema.ForeignKey('assay.id'), nullable=False)
    reference_assay_id = schema.Column(types.Integer, schema.ForeignKey('assay.id'), nullable=True)
    cnv = schema.Column(types.Integer, nullable=False, default=1)
    source_plate_id = schema.Column(types.Integer, schema.ForeignKey('plate.id'), nullable=True)
    source_external_url = schema.Column(types.String(255), nullable=True)
    notes = schema.Column(types.UnicodeText(), nullable=True)
    author_id = schema.Column(types.Integer, schema.ForeignKey('person.id'), nullable=True)
    time_created = schema.Column(types.DateTime, default=now)

class AssayTag(Base):
    __tablename__ = "assay_tag"
    __table_args__ = {"mysql_engine": 'InnoDB', 'mysql_charset': 'utf8'}

    id = schema.Column(types.Integer, schema.Sequence('assay_tag_seq_id', optional=True), primary_key=True)
    name = schema.Column('name', types.Unicode(50), nullable=False)

class Assay(Base):
	__tablename__ = 'assay'
	__table_args__ = {'mysql_engine': 'InnoDB', 'mysql_charset': 'utf8'}
	TYPE_PRIMER = 'primer'
	TYPE_LOCATION = 'location'
	TYPE_SNP = 'snp'
	TYPE_INCOMPLETE = 'incomplete'
	
	id = schema.Column(types.Integer,
	                   schema.Sequence('assay_seq_id', optional=True), primary_key=True)
	name = schema.Column(types.Unicode(50), nullable=False, unique=True)
	gene = schema.Column(types.Unicode(50), nullable=True)
	owner_id = schema.Column(types.Integer, schema.ForeignKey('person.id'), nullable=True)
	primer_fwd = schema.Column(types.Unicode(50), nullable=True)
	primer_rev = schema.Column(types.Unicode(50), nullable=True)
	probe_pos = schema.Column(types.Integer, default=0)
	probe_seq = schema.Column(types.Unicode(100), nullable=True)
	dye = schema.Column(types.Unicode(10), nullable=True)
	quencher = schema.Column(types.Unicode(10), nullable=True)
	chromosome = schema.Column(types.Unicode(4), nullable=True)
	amplicon_width = schema.Column(types.Integer, default=0)
	snp_rsid = schema.Column(types.Unicode(50), nullable=True)
	# TODO: this probably should be a many-to-many (hg18 vs hg19 seq; multiple results for rsid)
	added = schema.Column(types.DateTime(), default=now)
	cached_sequences = orm.relation('HG19AssayCache', backref='assay', cascade='all, delete-orphan')
	sample_cnvs = orm.relation('AssaySampleCNV', backref='target_assay', primaryjoin=id == AssaySampleCNV.target_assay_id, cascade='all, delete-orphan')
	reference_cnvs = orm.relation('AssaySampleCNV', backref='reference_assay', primaryjoin=id == AssaySampleCNV.reference_assay_id, cascade='all, delete-orphan')
	enzyme_concentrations = orm.relation('EnzymeConcentration', backref='assay')
	
	forward_primer_tm = schema.Column(types.Numeric(precision=5, scale=2), nullable=True)
	reverse_primer_tm = schema.Column(types.Numeric(precision=5, scale=2), nullable=True)
	probe_tm = schema.Column(types.Numeric(precision=5, scale=2), nullable=True)
	forward_primer_dG = schema.Column(types.Numeric(precision=5, scale=2), nullable=True)
	reverse_primer_dG = schema.Column(types.Numeric(precision=5, scale=2), nullable=True)
	probe_dG = schema.Column(types.Numeric(precision=5, scale=2), nullable=True)
	secondary_structure = schema.Column(types.Boolean, nullable=True)
	notes = schema.Column(types.UnicodeText(), nullable=True)
	reference_source = schema.Column(types.String(255), nullable=True)
	optimal_anneal_temp = schema.Column(types.Numeric(precision=4, scale=1), nullable=True)
	rejected = schema.Column(types.Boolean, default=False, nullable=True)
	tags = orm.relation('AssayTag', secondary=assay_tag_assay_table)
	
	# TODO: make this type explicit?
	@property
	def assay_type(self):
	    if self.primer_fwd and self.primer_rev is not None:
	        return Assay.TYPE_PRIMER
	    elif self.probe_pos and self.chromosome and self.amplicon_width is not None:
	        return Assay.TYPE_LOCATION
	    elif self.snp_rsid and self.amplicon_width is not None:
	        return Assay.TYPE_SNP
	    else:
	        return Assay.TYPE_INCOMPLETE
	
	@property
	def assay_type_display(self):
	    return {Assay.TYPE_PRIMER: 'PCR Primer',
	            Assay.TYPE_LOCATION: 'PCR Probe Location',
	            Assay.TYPE_SNP: 'PCR SNP Target',
	            Assay.TYPE_INCOMPLETE: 'Unknown'}[self.assay_type]
	
	@classmethod
	def primer_query(cls, session):
	    return session.query(cls).filter(and_(cls.primer_fwd != None, cls.primer_rev != None))
	
	@classmethod
	def location_query(cls, session):
	    return session.query(cls).filter(and_(cls.primer_fwd == None, cls.chromosome != None, cls.probe_pos != None))
	
	@classmethod
	def snp_query(cls, session):
	    return session.query(cls).filter(and_(cls.snp_rsid != None, cls.amplicon_width != None))
	
	@classmethod
	def populated_valid_query(cls, session):
	    """
	    Include assays with some information.
	    """
	    return session.query(cls).filter(and_(or_(cls.primer_fwd != None, cls.chromosome != None, cls.snp_rsid != None), cls.rejected != True))

class Enzyme(Base):
    __tablename__ = "enzyme"
    __table_args__ = {'mysql_engine': 'InnoDB', 'mysql_charset': 'utf8'}
    
    name = schema.Column(types.Unicode(20), primary_key=True)
    cutseq = schema.Column(types.Unicode(50), nullable=True)
    methylation_sensitivity = schema.Column(types.String(50), nullable=True)
    vendor_specs = orm.relation('VendorEnzyme', backref='enzyme', cascade='all, delete-orphan')

class Vendor(Base):
    __tablename__ = "vendor"
    __table_args__ = {"mysql_engine": 'InnoDB', 'mysql_charset': 'utf8'}
    
    id = schema.Column(types.Integer,
                       schema.Sequence('vendor_seq_id', optional=True), primary_key=True)
    name = schema.Column(types.Unicode(50), nullable=False, unique=True)
    website = schema.Column(types.Unicode(50))
    enzymes = orm.relation('VendorEnzyme', backref='vendor')
    # TODO: add additional parameters.

class Buffer(Base):
    __tablename__ = "buffer"
    __table_args__ = {"mysql_engine": 'InnoDB', 'mysql_charset': 'utf8'}
    
    id = schema.Column(types.Integer,
                       schema.Sequence('buffer_seq_id', optional=True), primary_key=True)
    name = schema.Column(types.Unicode(50), nullable=False, unique=True)
    enzymes = orm.relation('VendorEnzyme', backref='buffer')
    # TODO: add additional parameters; add relation to vendor?

class VendorEnzyme(Base):
    __tablename__ = "vendor_enzyme"
    __table_args__ = {"mysql_engine": 'InnoDB', 'mysql_charset': 'utf8'}
    
    BIN_CHEAP_ENZYME     = 1
    BIN_MEDIUM_ENZYME    = 2
    BIN_EXPENSIVE_ENZYME = 3

    BIN_DISPLAY = {BIN_CHEAP_ENZYME: 'Low',
                   BIN_MEDIUM_ENZYME: 'Medium',
                   BIN_EXPENSIVE_ENZYME: 'High'}

    id = schema.Column(types.Integer,
                       schema.Sequence('vendor_enzyme_seq_id', optional=True), primary_key=True)
    enzyme_id = schema.Column(types.Unicode(20), schema.ForeignKey('enzyme.name'), nullable=False)
    vendor_id = schema.Column(types.Integer, schema.ForeignKey('vendor.id'), nullable=False)
    buffer_id = schema.Column(types.Integer, schema.ForeignKey('buffer.id'))
    unit_cost_1 = schema.Column(types.Numeric(precision=6, scale=2))
    unit_cost_2 = schema.Column(types.Numeric(precision=6, scale=2))
    stock_units = schema.Column(types.Integer, default=0)
    vendor_serial = schema.Column(types.Unicode(32), nullable=True)
    unit_serial_1 = schema.Column(types.Unicode(32), nullable=True)
    unit_serial_2 = schema.Column(types.Unicode(32), nullable=True)

    @property
    def unit_cost_bin(self):
        if self.unit_cost_1 < 10:
            return self.__class__.BIN_CHEAP_ENZYME
        elif self.unit_cost_1 < 50:
            return self.__class__.BIN_MEDIUM_ENZYME
        else:
            return self.__class__.BIN_EXPENSIVE_ENZYME
    
    @classmethod
    def unit_cost_bin_gettext(cls, bin):
        return cls.BIN_DISPLAY.get(bin, 'Unknown')
    
    @property
    def unit_cost_bin_display(self):
        return self.__class__.unit_cost_bin_text(self.unit_cost_bin)

class Box2(Base):
    __tablename__ = "box2"
    __table_args__ = {"mysql_engine": 'InnoDB', 'mysql_charset': 'utf8'}

    READER_TYPE_WHOLE = 0
    READER_TYPE_FLUIDICS_MODULE = 1
    READER_TYPE_DETECTOR_MODULE = 2   
 
    id = schema.Column(types.Integer, schema.Sequence('box2_seq_id', optional=True), primary_key=True)
    name = schema.Column(types.Unicode(20), nullable=False, unique=True)
    code = schema.Column(types.Unicode(20), nullable=False, unique=True)
    os_name = schema.Column(types.String(40))
    src_dir = schema.Column(types.String(255), nullable=True)
    status = schema.Column(types.Integer, nullable=True)
    status_comment = schema.Column(types.Unicode(140), nullable=True)
    active = schema.Column(types.Boolean, nullable=False, default=True)
    # real = schema.Column(types.Boolean, nullable=False, default=True) # TODO: also remove column after this propagates
    alt_name = schema.Column(types.Unicode(50), nullable=True)
    fileroot = schema.Column(types.String(50), nullable=False, default='main')
    reader_type = schema.Column(types.Integer, nullable=False, default=0)
    dr_group_id = schema.Column(types.Integer, schema.ForeignKey('dr_group.id'), nullable=True)
    reference = schema.Column(types.Boolean, default=False, nullable=False)
    plates = orm.relation('Plate', backref='box2')
    serials = orm.relation('EquipmentSerialBox2', backref='box2')
    logs = orm.relation('Box2Log', backref='box2')
    files = orm.relation('Box2File', backref='box2', primaryjoin='and_(Box2.id == Box2File.box2_id, Box2File.deleted != True)')

    @property
    def display_name(self):
        if self.alt_name:
            return "%s (%s)" % (self.name, self.alt_name)
        else:
            return self.name
    
    @property
    def is_prod(self):
        """
        For now...
        """
        return self.fileroot in ('prod','site6000')

    @staticmethod
    def prod_query():
        return Box2.fileroot.in_(('prod','site6000'))

    @staticmethod
    def reader_query():
        return and_(Box2.fileroot.in_(('prod','site6000')), Box2.reader_type == Box2.READER_TYPE_WHOLE)

    @staticmethod
    def lab_query():
        return and_(Box2.fileroot.in_(('main','archive')), Box2.reader_type == Box2.READER_TYPE_WHOLE)

    @staticmethod
    def fluidics_module_query():
        return and_(Box2.fileroot.in_(('prod','site6000')), Box2.reader_type == Box2.READER_TYPE_FLUIDICS_MODULE)

    @staticmethod
    def detector_module_query():
        return and_(Box2.fileroot.in_(('prod','site6000')), Box2.reader_type == Box2.READER_TYPE_DETECTOR_MODULE)

    @staticmethod
    def whole_readers_only_query():
        return Box2.reader_type == Box2.READER_TYPE_WHOLE

    @staticmethod
    def fluidics_modules_only_query():
        return Box2.reader_type == Box2.READER_TYPE_FLUIDICS_MODULE

    @staticmethod
    def detector_modules_only_query():
        return Box2.reader_type == Box2.READER_TYPE_DETECTOR_MODULE

class Box2File(Base):
    __tablename__  = "box2_file"
    __table_args__ = {"mysql_engine": "InnoDB", "mysql_charset": 'utf8'}

    id = schema.Column(types.Integer, schema.Sequence('box2_file_seq_id', optional=True), primary_key=True)
    box2_id = schema.Column(types.Integer, schema.ForeignKey('box2.id'), nullable=False)
    name = schema.Column(types.String(255), nullable=False)
    deleted = schema.Column(types.Boolean, default=False)
    path = schema.Column(types.String(255), nullable=False)
    updated = schema.Column(types.DateTime, nullable=False, default=now)
    size = schema.Column(types.Integer, nullable=True)
    mime_type = schema.Column(types.String(50), nullable=True)
    description = schema.Column(types.UnicodeText, nullable=True)

class DRGroup(Base):
    __tablename__  = "dr_group"
    __table_args__ = {"mysql_engine": "InnoDB", "mysql_charset": 'utf8'}

    id = schema.Column(types.Integer, schema.Sequence('dr_group_seq_id', optional=True), primary_key=True)
    name = schema.Column(types.String(255), nullable=False)
    active = schema.Column(types.Boolean, nullable=False, default=True)
    drs = orm.relation('Box2', backref='dr_group')


class EquipmentSerialBox2(Base):
    __tablename__ = "equipment_serial_box2"
    __table_args__ = {"mysql_engine": 'InnoDB', 'mysql_charset': 'utf8'}
    
    id = schema.Column(types.Integer, schema.Sequence('equipment_serial_box2_seq_id', optional=True), primary_key=True)
    box2_id = schema.Column(types.Integer, schema.ForeignKey('box2.id'), nullable=False)
    equipment_serial = schema.Column(types.String(40), nullable=False)

class Project(Base):
    __tablename__ = "project"
    __table_args__ = {"mysql_engine": 'InnoDB', 'mysql_charset': 'utf8'}
    
    id = schema.Column(types.Integer, schema.Sequence('project_seq_id', optional=True), primary_key=True)
    name = schema.Column(types.Unicode(100), nullable=False)
    code = schema.Column(types.Unicode(20), nullable=True)
    description = schema.Column(types.UnicodeText(), nullable=True)
    active = schema.Column(types.Boolean, default=True)
    plates = orm.relation('Plate', backref='project')
    plate_setups = orm.relation('PlateSetup', backref='project')

class Experiment(Base):
    __tablename__ = "experiment"
    __table_args__ = {"mysql_engine": 'InnoDB', 'mysql_charset': 'utf8'}
    
    id = schema.Column(types.Integer, schema.Sequence('experiment_seq_id', optional=True), primary_key=True)
    name = schema.Column(types.Unicode(100), nullable=False)
    code = schema.Column(types.Unicode(20), nullable=True)
    description = schema.Column(types.UnicodeText(), nullable=True)
    plates = orm.relation('Plate', backref='experiment')

WELL_NAME_RE = re.compile(r'[aAbBcCdDeEfFgGhH](\d\d)')
def __well_name_match(matchobj):
    """
    TODO: verify with nick that this may only be at the end of the sample/target name
    """
    well_num = int(matchobj.group(1))
    if well_num >= 0 and well_num <= 12:
        return ''
    else:
        return matchobj.group(0)

def excise_well_name(str):
    return re.sub(WELL_NAME_RE, __well_name_match, str)

class PlateSetup(Base):
    __tablename__ = "plate_setup"
    __table_args__ = {"mysql_engine": 'InnoDB', 'mysql_charset': 'utf8'}

    id = schema.Column(types.Integer, schema.Sequence('plate_setup_seq_id', optional=True), primary_key=True)
    prefix = schema.Column(types.String(72), nullable=True)
    name = schema.Column(types.String(40), nullable=False)
    setup = schema.Column(MediumText(), nullable=True)
    time_updated = schema.Column(types. DateTime(), nullable=True, default=now)
    locked = schema.Column(types.Boolean, default=False)
    completed = schema.Column(types.Boolean, nullable=True, default=False)
    project_id = schema.Column(types.Integer, schema.ForeignKey('project.id'), nullable=True)
    author_id = schema.Column(types.Integer, schema.ForeignKey('person.id'), nullable=True)
    dr_oil = schema.Column(types.Integer, nullable=True)
    dg_oil = schema.Column(types.Integer, nullable=True)
    master_mix = schema.Column(types.Integer, nullable=True)
    droplet_generation_method = schema.Column(types.Integer, nullable=True)
    droplet_generator_id = schema.Column(types.Integer, schema.ForeignKey('droplet_generator.id'), nullable=True)
    #dg_used_id = schema.Column(types.Integer, schema.ForeignKey('dg_used.id'), nullable=True)
    droplet_generation_time = schema.Column(types.DateTime(), nullable=True)
    thermal_cycler_id = schema.Column(types.Integer, schema.ForeignKey('thermal_cycler.id'), nullable=True)
    droplet_maker_id = schema.Column(types.Integer, schema.ForeignKey('person.id'), nullable=True)
    notes = schema.Column(types.UnicodeText(), nullable=True)
    skin_type = schema.Column(types.Integer, nullable=True)
    chemistry_type = schema.Column(types.Integer, nullable=True)
    donotrun = schema.Column(types.Boolean, nullable=True, default=False)
    plate_type_id = schema.Column(types.Integer, schema.ForeignKey('plate_type.id'), nullable=True)

    # TODO: should it be a single plate?  unless the consumables are still
    # tied to the individual plate (and not a batch)
    plates = orm.relation('Plate', backref='setup')
    plate_type = orm.relation('PlateType')

    @property
    def chemistry_type_display(self):
        return dict(Plate.chemistry_type_display_options()).get(self.chemistry_type, '')

    @property
    def skin_type_display(self):
        return dict(Plate.skin_type_display_options()).get(self.skin_type, '')


class Plate(Base):
    __tablename__ = "plate"
    __table_args__ = {"mysql_engine": 'InnoDB', 'mysql_charset': 'utf8'}

    CHEMISTRY_TYPE_TAQMAN = 1
    CHEMISTRY_TYPE_GREEN = 2

    SKIN_TYPE_SKINNED = 1
    SKIN_TYPE_SKINLESS = 2
    
    id = schema.Column(types.Integer, schema.Sequence('plate_seq_id', optional=True), primary_key=True)
    name = schema.Column(types.Unicode(255), nullable=False)
    type = schema.Column(types.Integer, nullable=False, default=0)
    plate_type_id = schema.Column(types.Integer, schema.ForeignKey('plate_type.id'), nullable=True)
    description = schema.Column(types.UnicodeText(), nullable=True)
    box2_id = schema.Column(types.Integer, schema.ForeignKey('box2.id'), nullable=True)
    operator_id = schema.Column(types.Integer, schema.ForeignKey('person.id'), nullable=True)
    run_time = schema.Column(types.DateTime(), nullable=True, default=now)
    project_id = schema.Column(types.Integer, schema.ForeignKey('project.id'), nullable=True)
    experiment_id = schema.Column(types.Integer, schema.ForeignKey('experiment.id'), nullable=True)
    score = schema.Column(types.Integer, nullable=True, default=0)
    lot_numbers = orm.relation('LotNumber', secondary=lot_number_plate_table)
    tags = orm.relation('PlateTag', secondary=plate_tag_plate_table)
    qlbplate = orm.relation('QLBPlate', backref='plate', uselist=False)
    dr_oil = schema.Column(types.Integer, nullable=True)
    dg_oil = schema.Column(types.Integer, nullable=True)
    master_mix = schema.Column(types.Integer, nullable=True)
    gasket = schema.Column(types.Integer, nullable=True)
    droplet_generation_method = schema.Column(types.Integer, nullable=True)
    droplet_maker_id = schema.Column(types.Integer, schema.ForeignKey('person.id'), nullable=True)
    fluidics_routine = schema.Column(types.Integer, nullable=True)
    mfg_exclude = schema.Column(types.Boolean, default=False)
    chemistry_type = schema.Column(types.Integer, nullable=True)
    skin_type = schema.Column(types.Integer, nullable=True)
    
    # convert these to enums?
    dg_used_id = schema.Column(types.Integer, schema.ForeignKey('dg_used.id'), nullable=True)
    droplet_generator = schema.Column(types.Integer, nullable=True, default=0)
    thermal_cycler = schema.Column(types.Integer, nullable=True, default=0)
    program_version = schema.Column(types.Unicode(20), nullable=True)
    plate_setup_id = schema.Column(types.Integer, schema.ForeignKey('plate_setup.id'), nullable=True)
    physical_plate_id = schema.Column(types.Integer, nullable=True)

    onsite = schema.Column(types.Boolean, default=False, nullable=True)
    dropship = schema.Column(types.Boolean, default=False, nullable=True)

    evidence_cnvs = orm.relation('AssaySampleCNV', backref='plate')
    enzyme_concentrations = orm.relation('EnzymeConcentration', backref='plate')
    metrics = orm.relation('PlateMetric', backref='plate',cascade='all, delete-orphan')
    analysis_groups = orm.relation('AnalysisGroup', secondary=analysis_group_plate_table)
    
    @classmethod
    def compute_score(cls, plate):
        """
        A plate's "score."  The formula is as follows:
        1 point for stealth/low event well (< 5000 events)
        2 points for normal quality well (5-15k events)
        3 points for high quality well (15k+ events)
        
        .5 points for well labeled with target and at least one sample
        4 points for distinct sample name
        4 points for distinct target name
        
        wrinkle: well name excised from sample/target names.
        """
        # Careful.  This property will trigger additional queries (it is lazily
        # loaded).  If you are showing multiple plates at a time, it may be
        # a good idea to eagerly load the underlying structure (including
        # wells, well channels)
        wells = [well for well in plate.qlbplate.wells if well.file_id and well.file_id != -1]
        score = 0
        score += sum([1 for well in wells if well.event_count < 5000])
        score += sum([2 for well in wells if well.event_count >= 5000 and well.event_count < 15000])
        score += sum([3 for well in wells if well.event_count >= 15000])
        
        event_score = score
        labeled_wells = len([well for well in wells if well.sample_name and len([chan for chan in well.channels if chan.target]) > 0])
        distinct_samples = set([excise_well_name(well.sample_name) for well in wells if well.sample_name])
        #raise Exception, distinct_samples
        distinct_channels = set([tuple([excise_well_name(chan.target) for chan in well.channels if chan.target]) for well in wells])
        score += 4*len(distinct_samples)
        score += 4*len([channel for channel in distinct_channels if channel])
        score += labeled_wells/2
        return score
    
    @property
    def plate_type_code(self):
        if self.plate_type_id:
            return self.plate_type.code
        else:
            return None

    @property
    def physical_plate_display(self):
        # loose FK
        if self.physical_plate_id is not None:
            pp = Session.query(PhysicalPlate).get(self.physical_plate_id)
            if not pp:
                return 'Unknown'
            else:
                return pp.name

    @property
    def is_auto_validation_plate(self):
        return self.plate_type_code == PlateType.AUTO_VALIDATION_CODE

    @property
    def mfg_record(self):
        from qtools.model.batchplate import ManufacturingPlate
        mfg_records = Session.query(ManufacturingPlate).filter(or_(ManufacturingPlate.plate_id==self.id,
                                                                   ManufacturingPlate.secondary_plate_id==self.id)).all()
        if mfg_records:
            return mfg_records[0]
        else:
            return None

    @property
    def is_mfg_qc_plate(self):
        mfg_record = self.mfg_record
        if mfg_record:
            return mfg_record.qc_plate
        else:
            return False

    
    def original_metrics(self, load_eager=True):
        """
        Returns the original plate metrics object (not reprocessed)

        If load_eager is True, will return the entire tree (PlateMetric->WellMetric->WellChannelMetric)
        """
        return self.metrics_for_reprocess_config_id(reprocess_config_id=None, load_eager=load_eager)

    def metrics_for_reprocess_config_id(self, reprocess_config_id=None, load_eager=True):
        """
        Returns the plate metrics that were computed using the specified reprocess configuration,
        which in turn specifies a signal processing version and set of input algorithms.

        If load_eager is True, this will return the entire Tree (PlateMetric->WellMetric->WellChannelMetric)
        """
        query = Session.query(PlateMetric).filter(and_(PlateMetric.plate_id == self.id,
                                                       PlateMetric.reprocess_config_id == reprocess_config_id))
        
        if load_eager:
            query = query.options(joinedload_all(PlateMetric.well_metrics, WellMetric.well_channel_metrics, innerjoin=True))
        
        return query.first()

    @classmethod
    def chemistry_type_display_options(cls):
        return [(Plate.CHEMISTRY_TYPE_TAQMAN, 'TaqMan'),
                (Plate.CHEMISTRY_TYPE_GREEN, 'EvaGreen')]

    @classmethod
    def skin_type_display_options(cls):
        return [(Plate.SKIN_TYPE_SKINNED, 'Skinned'),
                (Plate.SKIN_TYPE_SKINLESS, 'Skinless')]

    @property
    def chemistry_type_display(self):
        return dict(self.__class__.chemistry_type_display_options()).get(self.chemistry_type, '')

    @property
    def skin_type_display(self):
        return dict(self.__class__.skin_type_display_options()).get(self.skin_type, '')
    
class PhysicalPlate(Base):
    __tablename__ = "physical_plate"
    __table_args__ = {"mysql_engine": 'InnoDB', 'mysql_charset': 'utf8'}

    id = schema.Column(types.Integer, schema.Sequence('physical_plate_seq_id', optional=True), primary_key=True)
    name = schema.Column(types.String(100), nullable=False)
    active = schema.Column(types.Boolean, default=True)

class Person(Base):
    __tablename__ = "person"
    __table_args__ = {"mysql_engine": 'InnoDB', 'mysql_charset': 'utf8'}
    
    id = schema.Column(types.Integer, schema.Sequence('person_seq_id', optional=True), primary_key=True)
    first_name = schema.Column(types.Unicode(30), nullable=False)
    last_name = schema.Column(types.Unicode(30), nullable=False)
    name_code = schema.Column(types.Unicode(31), nullable=False, unique=True)
    email = schema.Column(types.Unicode(40), nullable=True)
    active = schema.Column(types.Boolean, default=True)
    plates = orm.relation('Plate', backref='operator', primaryjoin=id == Plate.operator_id)
    droplet_plates = orm.relation('Plate', backref='droplet_maker', primaryjoin=id == Plate.droplet_maker_id)
    assays = orm.relation('Assay', backref='owner')
    samples = orm.relation('Sample', backref='owner')
    assay_cnvs = orm.relation('AssaySampleCNV', backref='reporter')
    enzyme_concentrations = orm.relation('EnzymeConcentration', backref='reporter')
    plate_setups = orm.relation('PlateSetup', backref='author', primaryjoin=id == PlateSetup.author_id)
    droplet_plate_setups = orm.relation('PlateSetup', backref='droplet_maker', primaryjoin=id == PlateSetup.droplet_maker_id)
    dr_statuses = orm.relation('DRStatusLog', backref='reporter')
    dr_fixes = orm.relation('DRFixLog', backref='reporter')

    @property
    def full_name(self):
        return "%s %s" % (self.first_name, self.last_name)

class PlateTemplate(Base):
    __tablename__ = 'plate_template'
    __table_args__ = {"mysql_engine": 'InnoDB', 'mysql_charset': 'utf8'}
    
    id = schema.Column(types.Integer, schema.Sequence('plate_template_seq_id', optional=True), primary_key=True)
    prefix = schema.Column(types.String(72), unique=True, nullable=False)
    project_id = schema.Column(types.Integer, schema.ForeignKey('project.id'), nullable=True)
    operator_id = schema.Column(types.Integer, schema.ForeignKey('person.id'), nullable=True)
    dr_oil = schema.Column(types.Integer, nullable=True)
    dg_oil = schema.Column(types.Integer, nullable=True)
    master_mix = schema.Column(types.Integer, nullable=True)
    fluidics_routine = schema.Column(types.Integer, nullable=True)
    physical_plate_id = schema.Column(types.Integer, nullable=True)
    droplet_generation_method = schema.Column(types.Integer, nullable=True)
    droplet_maker_id = schema.Column(types.Integer, schema.ForeignKey('person.id'), nullable=True)
    plate_type_id = schema.Column(types.Integer, nullable=True)
    created_time = schema.Column(types.DateTime(), default=now)
    dg_used_id = schema.Column(types.Integer, schema.ForeignKey('dg_used.id'), nullable=True)


class PlateType(Base):
    __tablename__ = 'plate_type'
    __table_args__ = {"mysql_engine": 'InnoDB', 'mysql_charset': 'utf8'}

    AUTO_VALIDATION_CODE = "av"

    id = schema.Column(types.Integer, schema.Sequence('plate_type_seq_id', optional=True), primary_key=True)
    name = schema.Column(types.Unicode(30), unique=True, nullable=False)
    code = schema.Column(types.Unicode(8), unique=True, nullable=False)

    plates = orm.relation('Plate', backref='plate_type')


class PlateTag(Base):
    __tablename__ = "plate_tag"
    __table_args__ = {"mysql_engine": 'InnoDB', 'mysql_charset': 'utf8'}
    
    id = schema.Column(types.Integer, schema.Sequence('plate_tag_seq_id', optional=True), primary_key=True)
    name = schema.Column(types.Unicode(50), nullable=False)

class WellTag(Base):
    __tablename__ = "well_tag"
    __table_args__ = {"mysql_engine": 'InnoDB', 'mysql_charset': 'utf8'}
    
    id = schema.Column(types.Integer, schema.Sequence('well_tag_seq_id', optional=True), primary_key=True)
    name = schema.Column(types.Unicode(50), nullable=False)
    
    wells = association_proxy('tag_wells', 'well', creator=lambda w: QLBWellTag(well=w))

class Sample(Base):
    __tablename__ = "sample"
    __table_args__ = {"mysql_engine": 'InnoDB', 'mysql_charset': 'utf8'}
    
    id = schema.Column(types.Integer, schema.Sequence('sample_seq_id', optional=True), primary_key=True)
    name = schema.Column(types.Unicode(50), unique=True, nullable=False)
    source = schema.Column(types.Unicode(255), nullable=True)
    ethnicity = schema.Column(types.Unicode(50), nullable=True)
    sex = schema.Column(MSEnum('M','F','?'), nullable=True)
    notes = schema.Column(types.UnicodeText(), nullable=True)
    person_id = schema.Column(types.Integer, schema.ForeignKey('person.id'), nullable=True)
    time_created = schema.Column(types.DateTime(), default=now)
    
    assay_cnvs = orm.relation('AssaySampleCNV', backref='sample', cascade='all, delete-orphan')

class LotNumber(Base):
    __tablename__ = "lot_number"
    __table_args__ = {"mysql_engine": 'InnoDB', 'mysql_charset': 'utf8'}
    
    id = schema.Column(types.Integer, schema.Sequence('lot_number_seq_id', optional=True), primary_key=True)
    # TODO: make this enum instead?
    type = schema.Column(types.Integer, nullable=False, default=0)
    name = schema.Column(types.Unicode(50), nullable=False)
    

class HG19AssayCache(Base, AssayCacheMixin):
    __tablename__ = "hg19_assay_cache"
    __table_args__ = {"mysql_engine": 'InnoDB', 'mysql_charset': 'utf8'}
    
    id = schema.Column(types.Integer, schema.Sequence('hg19_assay_seq_id', optional=True), primary_key=True)
    assay_id = schema.Column(types.Integer, schema.ForeignKey('assay.id'), nullable=False)
    chromosome = schema.Column(types.String(4), nullable=False)
    start_pos = schema.Column(types.Integer, nullable=False)
    end_pos = schema.Column(types.Integer, nullable=False)
    seq_padding_pos5 = schema.Column(types.Integer, nullable=False, default=0)
    seq_padding_pos3 = schema.Column(types.Integer, nullable=False, default=0)
    positive_sequence = schema.Column(types.Text)
    negative_sequence = schema.Column(types.Text)
    amplicon_tm = schema.Column(types.Numeric(precision=5, scale=2), nullable=True)
    amplicon_dG = schema.Column(types.Numeric(precision=5, scale=2), nullable=True)
    added = schema.Column(types.DateTime(), default=now)
    snps = orm.relation('SNP131AssayCache', backref='sequence', cascade='all, delete-orphan')
    
    @property
    def positive_amplicon(self):
        return self.cached_seq(0, 0, '+')
    
    @property
    def negative_amplicon(self):
        return self.cached_seq(0, 0, '-')
    
    @property
    def amplicon_length(self):
        return (self.end_pos - self.start_pos) + 1
    
    def padding_pos5(self, length, strand='+'):
        return self.cached_seq(length, -self.amplicon_length, strand)
    
    def padding_pos3(self, length, strand='+'):
        return self.cached_seq(-self.amplicon_length, length, strand)
    
    def cached_seq(self, padding_pos5, padding_pos3, strand='+'):
        """
        Returns the cached sequence in the positive strand direction.
        
        @param padding_pos5  The amount of padding (left) in the 5' end
                             on the positive strand
        @param padding_pos3  The amount of padding (right) on the 3' end
                             on the positive strand
        """
        start_idx = self.seq_padding_pos5 - padding_pos5
        end_idx = -1*(self.seq_padding_pos3 - padding_pos3) or None # if 0, then None-- pass into idx
        
        if start_idx < 0:
            raise ValueError, "Have not yet cached sequence to -%sbp" % padding_pos5
        
        elif end_idx > 0:
            raise ValueError, "Have not yet cached sequence to +%sbp" % padding_pos3
        
        if self.negative_sequence:
            seq = reverse_complement(self.negative_sequence)
        else:
            seq = self.positive_sequence
        
        substr = seq[start_idx:end_idx]
        if strand == '+':
            return substr
        else:
            return reverse_complement(substr)

class SNP131AssayCache(Base):
    __tablename__ = "snp131_assay_cache"
    __table_args__ = {"mysql_engine": 'InnoDB', 'mysql_charset': 'utf8'}
    
    id = schema.Column(types.Integer, schema.Sequence('snp131_assay_seq_id', optional=True), primary_key=True)
    sequence_id = schema.Column(types.Integer, schema.ForeignKey('hg19_assay_cache.id'), nullable=False)
    bin = schema.Column(types.Integer)
    chrom = schema.Column(types.String(31))
    chromStart = schema.Column(types.Integer)
    chromEnd = schema.Column(types.Integer)
    name = schema.Column(types.String(15))
    score = schema.Column(types.SmallInteger)
    strand = schema.Column(MSEnum('+','-'))
    refNCBI = schema.Column(types.Text)
    refUCSC = schema.Column(types.Text)
    observed = schema.Column(types.String(255))
    molType = schema.Column(MSEnum('unknown','genomic','cDNA'))
    class_ = schema.Column(MSEnum('unknown','single','in-del','het','microsatellite','named','mixed','mnp','insertion','deletion'))
    valid = schema.Column(MSSet('unknown','by-cluster','by-frequency','by-submitter','by-2hit-2allele','by-hapmap','by-1000genomes'))
    avHet = schema.Column(types.Float)
    avHetSE = schema.Column(types.Float)
    func = schema.Column(MSSet("'unknown'","'coding-synon'","'intron'","'coding-synonymy-unknown'","'near-gene-3'","'near-gene-5'","'nonsense'",
                 "'missense'","'frameshift'","'cds-indel'","'untranslated-3'","'untranslated-5'","'splice-3'","'splice-5'"))
    locType = schema.Column(MSEnum('range','exact','between','rangeInsertion','rangeSubstitution','rangeDeletion'))
    weight = schema.Column(types.Integer)
    added = schema.Column(types.DateTime(), default=now)
    
    def equals(self, other):
        """
        not ==, which factors in id (which I did not want to
        override for SQLA purposes).  But tests basic
        mutation equivalence.
        """
        if not other or not isinstance(other, self.__class__):
            return False
        
        return self.chrom == other.chrom \
               and self.chromStart == other.chromStart \
               and self.chromEnd == other.chromEnd \
               and self.name == other.name \
               and self.class_ == other.class_
   
class SystemVersion(Base):
    __tablename__ = "system_version"
    __table_args__ = {"mysql_engine": 'InnoDB', 'mysql_charset': 'utf8'}

    id = schema.Column(types.Integer, schema.Sequence('system_version_seq_id', optional=True),primary_key=True)
    type = schema.Column(types.String(5), nullable=False)
    desc = schema.Column(types.String(100), nullable=False)

    #qlbplates = orm.relation('QLBPlate', backref='system_version')
    #qlbwells  = orm.relation('QLBWell', backref='system_version')

class QLBFile(Base):
    __tablename__ = "qlbfile"
    __table_args__ = {"mysql_engine": 'InnoDB', 'mysql_charset': 'utf8'}
    
    id = schema.Column(types.Integer, schema.Sequence('qlbfile_seq_id', optional=True), primary_key=True)
    run_id = schema.Column(types.String(255), nullable=False, unique=True)
    dirname = schema.Column(types.String(255), nullable=False)
    basename = schema.Column(types.String(255), nullable=False)
    type = schema.Column(MSEnum('processed','raw','template','unknown'),  nullable=False)
    version = schema.Column(types.String(30), nullable=True)
    mtime = schema.Column(types.DateTime(), nullable=False)
    runtime = schema.Column(types.DateTime(), nullable=True)
    read_status = schema.Column(types.Integer(), default=0)
    plate = orm.relation('QLBPlate', backref='file', uselist=False, cascade='all, delete-orphan')
    well = orm.relation('QLBWell', backref='file', uselist=False, cascade='all')
    
    @property
    def path(self):
        return os.path.join(self.dirname, self.basename)
    
    @property
    def version_tuple(self):
        real_version = self.version.split('_')[0]
        major = real_version.split('.')[0]
        # hack for 01.00
        if major == "01":
            return (0,0)
        else:
            # QuantaSoft has added a letter version because they are sadists
            parts = [part for part in real_version.split('.')]
            if not parts[-1].isdigit():
                char = parts[-1][-1]
                ver = parts[-1][:-1]
                subversion = 1+(ord(char)-ord('A'))
                return tuple([int(part) for part in parts[:-1]]+[int(ver), subversion])
            else:
                return tuple([int(part) for part in parts])


class QLBPlate(Base):
    __tablename__ = "qlbplate"
    __table_args__ = {"mysql_engine": 'InnoDB', 'mysql_charset': 'utf8'}

    DYESET_UNKNOWN = -1
    DYESET_FAM_VIC = 0
    DYESET_FAM_HEX = 1
    DYESET_EVA     = 2   
 
    ALGORITHM_MAP = defaultdict(lambda: '?', {
        'QuantaSoftBeta 0.1.2.0': '0.14',
        'QuantaSoftBeta 0.1.3.0': '0.20',
        'QuantaSoftBeta 0.1.3.1': '0.20',
        'QuantaSoftBeta 0.1.4.0': '0.22',
        'QuantaSoftBeta 0.1.4.1': '0.22',
        'QuantaSoftBeta 0.1.4.4': '0.24',
        'QuantaSoftBeta 0.1.4.5': '0.25',
        'QuantaSoftBeta 0.1.4.6': '0.25',
        'QuantaSoftBeta 0.1.4.7': '0.25',
        'QuantaSoftBeta 0.1.4.8': '0.25',
        'QuantaSoftBeta 0.1.4.9': '0.26',
        'QuantaSoftBeta 0.1.5.3': '0.27',
        'QuantaSoftBeta 0.1.5.5': '0.27',
        'QuantaSoft 0.1.8.6': '0.31',
        'QuantaSoft 0.1.8.10': '0.31',
        'QuantaSoft 0.1.8.12': '0.31',
        'QuantaSoft 0.1.8.15': '0.31',
        'QuantaSoft 0.2.0.1': '0.31',
        'QuantaSoft 0.2.0.2': '0.31',
        'QuantaSoft 0.2.0.4': '0.32',
        'QuantaSoft 0.2.0.5': '0.32',
        'QuantaSoft 0.2.0.6': '0.32',
        'QuantaSoft 0.2.0.7': '0.32',
        'QuantaSoft 0.2.0.8': '0.32',
        'QuantaSoft 0.2.0.9': '0.32',
        # try to make this the last hack
        'QuantaSoft 0.2.0.12': '0.3332',
        'QuantaSoft 0.2.0.15': '0.3332',
        'QuantaSoft 0.2.1.0': '0.3332',
        'QuantaSoft 0.2.1.1': '0.3332',
        'QuantaSoft 0.2.1.5': '0.3332',
        'QuantaSoft 0.2.1.6': '0.3332',
        'QuantaSoft 0.2.1.7': '0.3332',
        'QuantaSoft 0.2.2.0': '0.3433',
        'QuantaSoft 0.2.3.0': '0.3434',
        'QuantaSoft 0.2.4.0': '0.3434',
        'QuantaSoft 0.2.4.2': '0.3435',
        'QuantaSoft 0.2.5.0': '0.3436',
        'QuantaSoft 0.2.5.7': '0.3436',
        'QLPReprocessor 0.2.5.0': '0.3436'
        # TODO: add db column for peak, post analysis version (prob per well)
    })
    
    id = schema.Column(types.Integer, schema.Sequence('qlbplate_seq_id', optional=True), primary_key=True)
    file_id = schema.Column(types.Integer, schema.ForeignKey('qlbfile.id'), nullable=False)
    host_datetime = schema.Column(types.DateTime(), nullable=True)
    host_machine = schema.Column(types.String(40), nullable=True)
    host_software = schema.Column(types.String(40), nullable=True)
    host_user = schema.Column(types.String(40), nullable=True)
    color_compensation_matrix_11 = schema.Column(types.Numeric(precision=7, scale=4), nullable=True)
    color_compensation_matrix_12 = schema.Column(types.Numeric(precision=7, scale=4), nullable=True)
    color_compensation_matrix_21 = schema.Column(types.Numeric(precision=7, scale=4), nullable=True)
    color_compensation_matrix_22 = schema.Column(types.Numeric(precision=7, scale=4), nullable=True)
    equipment_make = schema.Column(types.String(40), nullable=True)
    equipment_model = schema.Column(types.String(40), nullable=True)
    equipment_serial = schema.Column(types.String(40), nullable=True)
    file_desc = schema.Column(types.String(255), nullable=True)
    channel_map = schema.Column(types.String(40), nullable=True)
    plate_id = schema.Column(types.Integer, schema.ForeignKey('plate.id'), nullable=True)
    dyeset = schema.Column(types.Integer, nullable=False, default=DYESET_FAM_VIC)
    system_version  = schema.Column(types.Integer, schema.ForeignKey('system_version.id'), nullable=True)   
    plate_holder_id = schema.Column(types.Integer, nullable=True) ## maybe add plateholder table???

    wells = orm.relation('QLBWell', backref='plate')
    algorithm_wells = orm.relation('AlgorithmWell', backref='plate')
    
    def algorithm_wells_by_version(self, major_version, minor_version):
        return [well for well in self.algorithm_wells if well.algorithm_major_version == major_version and well.algorithm_minor_version == minor_version]
    
    @classmethod
    def filter_by_host_datetime(cls, query, start_time, end_time):
        return query.filter(and_(cls.host_datetime >= start_time, cls.host_datetime <= end_time))
    
    @property
    def well_name_map(self):
        return dict([(well.well_name, well) for well in self.wells])

    @property
    def quantitation_algorithm(self):
        # TODO: defer to plate/store on read
        return self.__class__.ALGORITHM_MAP[self.host_software]
    
    @property
    def quantitation_algorithm_tuple(self):
        alg = self.quantitation_algorithm
        if alg != '?':
            return tuple([int(tok) for tok in alg.split('.')])
        else:
            # for now -- hack bugfix; fix in analyzing PyQLB
            return (0,0)
    

class QLBWell(Base):
    __tablename__ = "qlbwell"
    __table_args__ = {"mysql_engine": 'InnoDB', 'mysql_charset': 'utf8'}

    DYESET_UNKNOWN = -1
    DYESET_FAM_VIC = 0
    DYESET_FAM_HEX = 1
    DYESET_EVA     = 2

    id = schema.Column(types.Integer, schema.Sequence('qlbwell_seq_id', optional=True), primary_key=True)
    plate_id = schema.Column(types.Integer, schema.ForeignKey('qlbplate.id'), nullable=True)
    
    # NOTE: file_id not automatically backreffed
    file_id = schema.Column(types.Integer, schema.ForeignKey('qlbfile.id'), nullable=True)
    well_name = schema.Column(types.String(5), nullable=True)
    experiment_name = schema.Column(types.String(255), nullable=True)
    experiment_type = schema.Column(types.String(31), nullable=True)
    experiment_comment = schema.Column(types.String(255), nullable=True)
    sample_name = schema.Column(types.String(255), nullable=True)
    flow_rate = schema.Column(types.Float, nullable=True)
    num_channels = schema.Column(types.Integer, nullable=True)
    event_count = schema.Column(types.Integer, nullable=True)
    sample_rate = schema.Column(types.Float, nullable=True)
    setup_version = schema.Column(types.Integer, nullable=True)
    daq_version = schema.Column(types.Integer, nullable=True)
    daq_input_range = schema.Column(types.Float, nullable=True)
    daq_output_range = schema.Column(types.Float, nullable=True)
    daq_sample_format = schema.Column(types.Integer, nullable=True)
    resolution_bits = schema.Column(types.Integer, nullable=True)
    raw_data = schema.Column(types.Integer, nullable=True)
    color_compensation_matrix_11 = schema.Column(types.Numeric(precision=7, scale=4), nullable=True)
    color_compensation_matrix_12 = schema.Column(types.Numeric(precision=7, scale=4), nullable=True)
    color_compensation_matrix_21 = schema.Column(types.Numeric(precision=7, scale=4), nullable=True)
    color_compensation_matrix_22 = schema.Column(types.Numeric(precision=7, scale=4), nullable=True)
    host_machine = schema.Column(types.String(31), nullable=True)
    host_datetime = schema.Column(types.DateTime(), nullable=True)
    host_software = schema.Column(types.String(255), nullable=True)
    channel_map = schema.Column(types.String(31), nullable=True)
    host_user = schema.Column(types.String(31), nullable=True)
    CapillaryFlushVolume = schema.Column(types.Float, nullable=True)
    FastPickupRate = schema.Column(types.Float, nullable=True) #obsolete
    FastPickupVolume = schema.Column(types.Float, nullable=True) #obsolete
    system_version = schema.Column(types.Integer, schema.ForeignKey('system_version.id'), nullable=True)
    OilFocusRate = schema.Column(types.Float, nullable=True)
    OilFocusVolume = schema.Column(types.Float, nullable=True)
    P1FillRate = schema.Column(types.Float, nullable=True)
    P1MaxVolume = schema.Column(types.Float, nullable=True) #obsolete
    P1RinseRate = schema.Column(types.Float, nullable=True)
    P1RinseVolume = schema.Column(types.Float, nullable=True)
    P2FillRate = schema.Column(types.Float, nullable=True)
    P2MaxVolume = schema.Column(types.Float, nullable=True) #obsolete
    P2RinseRate = schema.Column(types.Float, nullable=True)
    P2RinseVolume = schema.Column(types.Float, nullable=True)
    PickupRate = schema.Column(types.Float, nullable=True)
    PickupVolume = schema.Column(types.Float, nullable=True)
    PreSolvationTime = schema.Column(types.Float, nullable=True) #obsolete
    PreSolvationVolume = schema.Column(types.Float, nullable=True) #obsolete
    SampleFocusRate = schema.Column(types.Float, nullable=True)
    SampleFocusVolume = schema.Column(types.Float, nullable=True)
    SingulatorFlushVolume = schema.Column(types.Float, nullable=True)
    SlowPickupRate = schema.Column(types.Float, nullable=True) #obsolete
    SlowPickupVolume = schema.Column(types.Float, nullable=True) #obsolete
    SolvationRate = schema.Column(types.Float, nullable=True) #obsolete
    SolvationVolume = schema.Column(types.Float, nullable=True) #obsolete
    TipHeight = schema.Column(types.Float, nullable=True)
    TipPrimeVolume = schema.Column(types.Float, nullable=True)
    V1 = schema.Column(types.Float, nullable=True)
    V2 = schema.Column(types.Float, nullable=True)
    V3 = schema.Column(types.Float, nullable=True)
    V4 = schema.Column(types.Float, nullable=True)
    V5 = schema.Column(types.Float, nullable=True)
    # v1.4 new columns
    CapillaryFlushRate = schema.Column(types.Float, nullable=True)
    DelayTime = schema.Column(types.Float, nullable=True)
    InitialPickupVolume = schema.Column(types.Float, nullable=True)
    PreWetVolume = schema.Column(types.Float, nullable=True)
    SampleFocusMultiplier = schema.Column(types.Float, nullable=True)
    SingulatorFlushRate = schema.Column(types.Float, nullable=True)
    TrailingAirVolume = schema.Column(types.Float, nullable=True)
    VersionNumber = schema.Column(types.String(31), nullable=True) # this may be more, remains to be seen
    WellSpargeVolume = schema.Column(types.Float, nullable=True)
    WellVolume = schema.Column(types.Float, nullable=True)

    consumable_batch = schema.Column(types.String(20), nullable=True)
    consumable_batch_date = schema.Column(types.Date, nullable=True)
    consumable_batch_temp = schema.Column(types.Integer, nullable=True)
    #consumable_batch_id = schema.Column(types.Integer, schema.ForeignKey('consumable_batch.id'), nullable=True)
    consumable_chip_num = schema.Column(types.Integer, nullable=True)
    consumable_channel_num = schema.Column(types.Integer, nullable=True)
    droplet_generator_id = schema.Column(types.Integer, schema.ForeignKey('droplet_generator.id'), nullable=True)
    dg_run_number = schema.Column(types.Integer, nullable=True)
    dg_vacuum_time = schema.Column(types.Float, nullable=True)

    dg_cartridge = schema.Column(types.String(35), nullable=True)
    supermix = schema.Column(types.String(35), nullable=True)
    dyeset = schema.Column(types.Integer, nullable=False, default=DYESET_FAM_VIC)
 
    channels = orm.relation('QLBWellChannel', backref='well', cascade='all, delete-orphan')
    algorithm_wells = orm.relation('AlgorithmWell', backref='well', cascade='all, delete-orphan')
    tags = association_proxy('well_tags', 'tag', creator=lambda t: QLBWellTag(well_tag=t))
    detailed_tags = orm.relation('QLBWellTag')
    well_metrics = orm.relation('WellMetric', backref='well')
    
    def algorithm_well_by_version(self, major_version, minor_version):
        wells = [well for well in self.algorithm_wells if well.algorithm_major_version == major_version and well.algorithm_minor_version == minor_version]
        if len(wells) > 0:
            return wells[0]
        else:
            return None

class QLBWellTag(Base):
    __tablename__ = "well_tag_qlbwell"
    __table_args__ = {"mysql_engine": 'InnoDB', 'mysql_charset': 'utf8'}

    id = schema.Column(types.Integer, schema.Sequence('well_tag_qlbwell_seq_id', optional=True), primary_key=True)
    well_id = schema.Column(types.Integer, schema.ForeignKey('qlbwell.id'))
    well_tag_id = schema.Column(types.Integer, schema.ForeignKey('well_tag.id'))
    tagger_id = schema.Column(types.Integer, schema.ForeignKey('person.id'), nullable=True)

    well = orm.relation('QLBWell', backref='well_tags')
    tag = orm.relation('WellTag', backref='tag_wells')
    
    def __init__(self, well=None, well_tag=None, tagger_id=None):
        if well:
            self.well_id = well.id
        if well_tag:
            self.well_tag_id = well_tag.id
        self.tagger_id = tagger_id

class QLBWellChannel(Base):
    __tablename__ = "qlbwell_channel"
    __table_args__ = {"mysql_engine": 'InnoDB', 'mysql_charset': 'utf8'}
    
    id = schema.Column(types.Integer, schema.Sequence('qlbwell_channel_seq_id', optional=True), primary_key=True)
    well_id = schema.Column(types.Integer, schema.ForeignKey('qlbwell.id'), nullable=False)
    channel_num = schema.Column(types.Integer, nullable=False)
    type = schema.Column(types.String(31), nullable=True)
    target = schema.Column(types.String(255), nullable=True)
    format_version = schema.Column(types.Integer, nullable=True)
    algorithm_version = schema.Column(types.Integer, nullable=True)
    width_sigma = schema.Column(types.Numeric(precision=3, scale=2), nullable=True)
    min_quality_gating = schema.Column(types.Float, nullable=True)
    min_quality_gating_conf = schema.Column(types.Float, nullable=True)
    min_width_gating = schema.Column(types.Float, nullable=True)
    min_width_gating_conf = schema.Column(types.Float, nullable=True)
    max_width_gating = schema.Column(types.Float, nullable=True)
    max_width_gating_conf = schema.Column(types.Float, nullable=True)
    quantitation_threshold = schema.Column(types.Float, nullable=True)
    quantitation_threshold_conf = schema.Column(types.Float, nullable=True)
    concentration = schema.Column(types.Float, nullable=True)
    conf_upper_bound = schema.Column(types.Float, nullable=True)
    conf_lower_bound = schema.Column(types.Float, nullable=True)
    positive_peaks = schema.Column(types.Integer, nullable=True, default=0)
    negative_peaks = schema.Column(types.Integer, nullable=True, default=0)
    peaks_count = schema.Column(types.Integer, nullable=True, default=0)
    rejected_peaks = schema.Column(types.Integer, nullable=True, default=0)
    sequence_group_id = schema.Column(types.Integer, schema.ForeignKey('sequence_group.id'), nullable=True)

    well_channel_metrics = orm.relation('WellChannelMetric', backref='well_channel')


class AlgorithmWell(Base):
    __tablename__ = "algwell"
    __table_args__ = {"mysql_engine": 'InnoDB', 'mysql_charset': 'utf8'}
    
    id = schema.Column(types.Integer, schema.Sequence('algwell_seq_id', optional=True), primary_key=True)
    plate_id = schema.Column(types.Integer, schema.ForeignKey('qlbplate.id'), nullable=True)
    well_id = schema.Column(types.Integer, schema.ForeignKey('qlbwell.id'), nullable=True)
    well_name = schema.Column(types.String(5), nullable=False)
    event_count = schema.Column(types.Integer, nullable=True)
    algorithm_major_version = schema.Column(types.Integer, default=0)
    algorithm_minor_version = schema.Column(types.Integer, default=21)
    
    channels = orm.relation('AlgorithmWellChannel', backref='well', cascade='all, delete-orphan')
    
    @property
    def experiment_type(self):
        return self.well.experiment_type
    
    @property
    def sample_name(self):
        return self.well.sample_name
    
    @property
    def csv_file_path(self):
        """
        Similar to qlbatch.batch_file_locations.  Concatenate to the root qlb file path
        to get the path to read.
        """
        return os.path.sep.join([self.well.file.dirname,
                                 "alg%s_%s_default" % (self.algorithm_major_version, self.algorithm_minor_version),
                                 self.well.file.basename.replace('.qlb','.csv')])
    
    @property
    def txt_file_path(self):
        """
        Similar to qlbatch.batch_file_locations.  Concatenate to the root qlb file path
        to get the path to read.
        """
        return os.path.sep.join([self.well.file.dirname,
                                 "alg%s_%s_default" % (self.algorithm_major_version, self.algorithm_minor_version),
                                 self.well.file.basename.replace('.qlb','.txt')])


class AlgorithmWellChannel(Base):
    __tablename__ = "algwell_channel"
    __table_args__ = {"mysql_engine": 'InnoDB', 'mysql_charset': 'utf8'}
    
    id = schema.Column(types.Integer, schema.Sequence('algwell_channel_seq_id', optional=True), primary_key=True)
    algwell_id = schema.Column(types.Integer, schema.ForeignKey('algwell.id'), nullable=False)
    channel_id = schema.Column(types.Integer, schema.ForeignKey('qlbwell_channel.id'), nullable=True)
    channel_num = schema.Column(types.Integer, nullable=False)
    width_sigma = schema.Column(types.Numeric(precision=3, scale=2), nullable=True)
    min_quality_gating = schema.Column(types.Float, nullable=True)
    min_width_gating = schema.Column(types.Float, nullable=True)
    max_width_gating = schema.Column(types.Float, nullable=True)
    quantitation_threshold = schema.Column(types.Float, nullable=True)
    concentration = schema.Column(types.Float, nullable=True)
    conf_upper_bound = schema.Column(types.Float, nullable=True)
    conf_lower_bound = schema.Column(types.Float, nullable=True)
    positive_peaks = schema.Column(types.Integer, nullable=True, default=0)
    negative_peaks = schema.Column(types.Integer, nullable=True, default=0)
    peaks_count = schema.Column(types.Integer, nullable=True, default=0)
    rejected_peaks = schema.Column(types.Integer, nullable=True, default=0)

class ConsumableMoldingStyle(Base):
    __tablename__ = "consumable_molding_style"
    __table_args__ = {"mysql_engine": 'InnoDB', 'mysql_charset': 'utf8'}

    id = schema.Column(types.Integer, schema.Sequence('consumable_molding_style_id', optional=True), primary_key=True)
    name = schema.Column(types.Unicode(50), nullable=False)
    description = schema.Column(types.Unicode(200), nullable=True)
    batches = orm.relation('ConsumableBatch', backref='consumable_molding_style')

class ConsumableBondingStyle(Base):
    __tablename__ = "consumable_bonding_style"
    __table_args__ = {"mysql_engine": 'InnoDB', 'mysql_charset': 'utf8'}

    id = schema.Column(types.Integer, schema.Sequence('consumable_bonding_style_id', optional=True), primary_key=True)
    name = schema.Column(types.Unicode(50), nullable=False)
    description = schema.Column(types.Unicode(200), nullable=True)
    batches = orm.relation('ConsumableBatch', backref='consumable_bonding_style')

class ConsumableBatch(Base):
    __tablename__ = "consumable_batch"
    __table_args__ = {"mysql_engine": 'InnoDB', 'mysql_charset': 'utf8'}

    id = schema.Column(types.Integer, schema.Sequence('consumable_batch_id', optional=True), primary_key=True)
    manufacturer = schema.Column(types.Unicode(50), nullable=False)
    consumable_molding_style_id = schema.Column(types.Integer, schema.ForeignKey('consumable_molding_style.id'), nullable=True)
    consumable_bonding_style_id = schema.Column(types.Integer, schema.ForeignKey('consumable_bonding_style.id'), nullable=True)
    insert = schema.Column(types.Unicode(20), nullable=False)
    bside = schema.Column(types.Unicode(50), nullable=True)
    lot_num = schema.Column(types.Unicode(50), nullable=False)
    manufacturing_date = schema.Column(types.DateTime(), nullable=False)
    added_date = schema.Column(types.DateTime(), nullable=True, default=now)

    # for now.
    batch_test = orm.relation('ConsumableBatchTest', backref='batch', uselist=False)
    fill_channels = orm.relation('ConsumableBatchFillChannel', backref='batch_test')

    def fill_channel(self, chip, channel):
        """
        May incur a DB call if the children are not eagerly loaded.
        """
        theone = [chan for chan in self.fill_channels if chan.chip_num == chip and chan.channel_num == channel]
        if len(theone) > 0:
            return theone[0]
        else:
            return None

class ConsumableBatchTest(Base):
    __tablename__ = "consumable_batch_test"
    __table_args__ = {"mysql_engine": 'InnoDB', 'mysql_charset': 'utf8'}

    id = schema.Column(types.Integer, schema.Sequence('consumable_batch_test_id', optional=True), primary_key=True)
    consumable_batch_id = schema.Column(types.Integer, schema.ForeignKey('consumable_batch.id'), nullable=False)
    pixel_calibration = schema.Column(types.Float, nullable=True)
    size_channels = orm.relation('ConsumableBatchSizeChannel', backref='batch_test')

    def size_channel(self, chip, channel):
        """
        May incur a DB call if the children are not eagerly loaded.
        """
        theone = [chan for chan in self.size_channels if chan.chip_num == chip and chan.channel_num == channel]
        if len(theone) > 0:
            return theone[0]
        else:
            return None

class ConsumableBatchSizeChannel(Base):
    __tablename__ = "consumable_batch_size_channel"
    __table_args__ = {"mysql_engine": 'InnoDB', 'mysql_charset': 'utf8'}

    id = schema.Column(types.Integer, schema.Sequence('consumable_batch_size_channel_id', optional=True), primary_key=True)
    consumable_batch_test_id = schema.Column(types.Integer, schema.ForeignKey('consumable_batch_test.id'), nullable=False)
    chip_num = schema.Column(types.Integer, nullable=False)
    channel_num = schema.Column(types.Integer, nullable=False)
    size_mean = schema.Column(types.Float, nullable=True)
    size_stdev = schema.Column(types.Float, nullable=True)
    droplet_count = schema.Column(types.Integer, nullable=True)

class ConsumableBatchFillChannel(Base):
    __tablename__ = "consumable_batch_fill_channel"
    __table_args__ = {"mysql_engine": 'InnoDB', 'mysql_charset': 'utf8'}

    id = schema.Column(types.Integer, schema.Sequence('consumable_batch_fill_channel_id', optional=True), primary_key=True)
    consumable_batch_id = schema.Column(types.Integer, schema.ForeignKey('consumable_batch.id'), nullable=False)
    chip_num = schema.Column(types.Integer, nullable=False)
    channel_num = schema.Column(types.Integer, nullable=False)
    fill_time = schema.Column(types.Float, nullable=True)


class DGUsed(Base):
    __tablename__ = "dg_used"
    __table_args__ = {"mysql_engine": 'InnoDB', 'mysql_charset': 'utf8'}

    id = schema.Column(types.Integer, schema.Sequence('dg_used_seq_id', optional=True), primary_key=True)
    name = schema.Column(types.Unicode(50), unique=True, nullable=False)

class DropletGenerator(Base):
    __tablename__ = "droplet_generator"
    __table_args__ = {"mysql_engine": 'InnoDB', 'mysql_charset': 'utf8'}

    id = schema.Column(types.Integer, schema.Sequence('droplet_generator_seq_id', optional=True), primary_key=True)
    name = schema.Column(types.Unicode(50), unique=True, nullable=False)

    plate_setups = orm.relation('PlateSetup', backref='droplet_generator')
    wells = orm.relation('QLBWell', backref='droplet_generator')
    runs = orm.relation('DropletGeneratorRun', backref='droplet_generator')

class DropletGeneratorRun(Base):
    __tablename__ = "dg_run"
    __table_args__ = {"mysql_engine": 'InnoDB', 'mysql_charset': 'utf8'}

    id = schema.Column(types.Integer, schema.Sequence('dg_run_id', optional=True), primary_key=True)
    droplet_generator_id = schema.Column(types.Integer, schema.ForeignKey('droplet_generator.id'), nullable=False)
    run_number = schema.Column(types.Integer, nullable=True)
    datetime = schema.Column(types.DateTime(), nullable=False)
    vacuum_time = schema.Column(types.Numeric(precision=5, scale=2), default=0)
    vacuum_pressure = schema.Column(types.Numeric(precision=5, scale=3), default=0)
    spike = schema.Column(types.Numeric(precision=7, scale=5), default=0)
    failed = schema.Column(types.Boolean, default=False)
    failure_reason = schema.Column(types.String(100), nullable=True)
    dirname = schema.Column(types.String(255), nullable=False)
    basename = schema.Column(types.String(255), nullable=False)

    wells = orm.relation('QLBWell', backref='dg_run',
                         primaryjoin=and_(droplet_generator_id==QLBWell.droplet_generator_id,
                                          run_number==QLBWell.dg_run_number),
                         foreign_keys=[QLBWell.droplet_generator_id, QLBWell.dg_run_number],
                         viewonly=True)

class ThermalCycler(Base):
    __tablename__ = "thermal_cycler"
    __table_args__ = {"mysql_engine": 'InnoDB', 'mysql_charset': 'utf8'}

    id = schema.Column(types.Integer, schema.Sequence('thermal_cycler_id', optional=True), primary_key=True)
    name = schema.Column(types.Unicode(50), unique=True, nullable=False)

    plate_setups = orm.relation('PlateSetup', backref='thermal_cycler')

class DropletGeneratorLog(Base):
    __tablename__ = "droplet_generator_log"
    __table_args__ = {"mysql_engine": 'InnoDB', 'mysql_charset': 'utf8'}

    id = schema.Column(types.Integer, schema.Sequence('droplet_generator_log_seq_id', optional=True), primary_key=True)
    droplet_generator_id = schema.Column(types.Integer, schema.ForeignKey('droplet_generator.id'), nullable=False)
    board = schema.Column(types.Unicode(50), nullable=False)
    pneumatic_circuit = schema.Column(types. Unicode(50), nullable=False)
    fluidics = schema.Column(types.Unicode(50), nullable=False)
    motor = schema.Column(types.Unicode(50), nullable=False)
    pressure_controller = schema.Column(types.Unicode(50), nullable=False)
    pump = schema.Column(types.Unicode(50), nullable=False)
    time_effective = schema.Column(types.DateTime(), nullable=False, default=now)

class DRStatusLog(Base):
    __tablename__ = "dr_status_log"
    __table_args__ = {"mysql_engine": 'InnoDB', 'mysql_charset': 'utf8'}

    id = schema.Column(types.Integer, schema.Sequence('dr_status_log_id', optional=True), primary_key=True)
    box2_id = schema.Column(types.Integer, schema.ForeignKey('box2.id'), nullable=False)
    status = schema.Column(types.Integer, nullable=False)
    status_comment = schema.Column(types.Unicode(140), nullable=True)
    time_effective = schema.Column(types.DateTime(), nullable=False, default=now)
    reporter_id = schema.Column(types.Integer, schema.ForeignKey('person.id'), nullable=True)


class DRFixLog(Base):
    __tablename__ = "dr_fix_log"
    __table_args__ = {"mysql_engine": 'InnoDB', 'mysql_charset': 'utf8'}

    id = schema.Column(types.Integer, schema.Sequence('dr_fix_log_id', optional=True), primary_key=True)
    box2_id = schema.Column(types.Integer, schema.ForeignKey('box2.id'), nullable=False)
    problem = schema.Column(types.UnicodeText(), nullable=True)
    root_cause = schema.Column(types.UnicodeText(), nullable=True)
    fix = schema.Column(types.UnicodeText(), nullable=True)
    time_effective = schema.Column(types.DateTime(), nullable=False, default=now)
    reporter_id = schema.Column(types.Integer, schema.ForeignKey('person.id'), nullable=True)


class Box2Log(Base):
    __tablename__ = "box2_log"
    __table_args__ = {"mysql_engine": 'InnoDB', 'mysql_charset': 'utf8'}

    id = schema.Column(types.Integer, schema.Sequence('box2_log_id', optional=True), primary_key=True)
    box2_id = schema.Column(types.Integer, schema.ForeignKey('box2.id'), nullable=False)
    box2_circuit_id = schema.Column(types.Integer, schema.ForeignKey('box2_circuit.id'), nullable=True)
    detector = schema.Column(types.Unicode(50), nullable=True, doc="Detector")
    singulator_type = schema.Column(types.Unicode(50), nullable=True, doc="Singulator Type")
    singulator_material = schema.Column(types.Unicode(50), nullable=True, doc="Singulator Material")
    capillary = schema.Column(types.Unicode(50), nullable=True, doc="Capillary")
    tip_lot_number = schema.Column(types.Unicode(50), nullable=True, doc="Tip Assembly #")
    tip_supplier = schema.Column(types.Unicode(50), nullable=True, doc="Tip Supplier")
    tip_material = schema.Column(types.Unicode(50), nullable=True, doc="Tip Material")
    tip_size = schema.Column(types.Unicode(10), nullable=True, doc="Tip Size")
    skin_on = schema.Column(types.Boolean, nullable=True, doc="Skin On?")
    routine_version = schema.Column(types.Unicode(50), nullable=True, doc="Routine Version")
    air_filter_location = schema.Column(types.Unicode(50), nullable=True, doc="Air Filter Location")
    door_type = schema.Column(types.Integer, nullable=True, default=0, doc="Door Type")
    peristaltic_tubing = schema.Column(types.Unicode(40), nullable=True, doc="Peristaltic Tubing")
    bottle_trough_hold_in_status = schema.Column(types.Unicode(50), nullable=True, doc="Bottle Trough Hold-In Status")
    plate_sensor_status = schema.Column(types.Unicode(50), nullable=True, doc="Plate Sensor Status")
    lid_sensor_status = schema.Column(types.Unicode(50), nullable=True, doc="Lid Sensor Status")
    firmware_version = schema.Column(types.Unicode(50), nullable=True, doc="Firmware Version")
    biochem_configuration = schema.Column(types.Unicode(50), nullable=True, doc="BioChem Configuration")
    quantasoft_version = schema.Column(types.Unicode(50), nullable=True, doc="QuantaSoft Version")
    waste_bottle_empty = schema.Column(types.Unicode(50), nullable=True, doc="Waste Bottle Empty Value")
    carrier_bottle_empty = schema.Column(types.Unicode(50), nullable=True, doc="Carrier Bottle Empty Value")
    waste_bottle_full = schema.Column(types.Unicode(50), nullable=True, doc="Waste Bottle Full Value")
    carrier_bottle_full = schema.Column(types.Unicode(50), nullable=True, doc="Carrier Bottle Full Value")
    firmware_mcu9 = schema.Column(types.Unicode(50), nullable=True, doc="MCU Firmware Version")
    firmware_dll130 = schema.Column(types.Unicode(50), nullable=True, doc="DLL Firmware Version")
    firmware_fpga16 = schema.Column(types.Unicode(50), nullable=True, doc="FPGA Firmware Version")
    firmware_fluidics = schema.Column(types.Unicode(50), nullable=True, doc="Fluidics Firmware Version")
    firmware_motor = schema.Column(types.Unicode(50), nullable=True, doc="Motor Firmware Version")
    reservoir_line = schema.Column(types.Unicode(50), nullable=True, doc="Reservoir Line")
    pickup_line = schema.Column(types.Unicode(50), nullable=True, doc="Pickup Line")
    waste_downspout = schema.Column(types.Unicode(50), nullable=True, doc="Waste Downspout")
    fluidics_circuit = schema.Column(types.Unicode(50), nullable=True, doc="Fluidics Circuit")
    time_effective = schema.Column(types.DateTime, nullable=False, default=now)

class Box2Circuit(Base):
    __tablename__ = "box2_circuit"
    __table_args__ = {"mysql_engine": 'InnoDB', 'mysql_charset': 'utf8'}

    id = schema.Column(types.Integer, schema.Sequence('box2_circuit_id', optional=True), primary_key=True)
    name = schema.Column(types.Unicode(50), unique=True, nullable=True)
    log_template_id = schema.Column(types.Integer, schema.ForeignKey('box2_log.id'), nullable=False)
    logs = orm.relation('Box2Log', backref='circuit', primaryjoin=id == Box2Log.box2_circuit_id)


class EnzymeConcentration(Base):
    __tablename__ = "enzyme_concentration"
    __table_args__ = {"mysql_engine": 'InnoDB', 'mysql_charset': 'utf8'}

    id = schema.Column(types.Integer, schema.Sequence('enzyme_concentration_seq_id', optional=True), primary_key=True)
    enzyme_id = schema.Column(types.Unicode(20), schema.ForeignKey('enzyme.name'), nullable=False)
    assay_id = schema.Column(types.Integer, schema.ForeignKey('assay.id'), nullable=False)
    minimum_conc = schema.Column(types.Numeric(precision=6, scale=4), nullable=True)
    maximum_conc = schema.Column(types.Numeric(precision=6, scale=4), nullable=True)
    author_id = schema.Column(types.Integer, schema.ForeignKey('person.id'), nullable=True)
    source_plate_id = schema.Column(types.Integer, schema.ForeignKey('plate.id'), nullable=True)
    notes = schema.Column(types.UnicodeText(), nullable=True)
    time_created = schema.Column(types.DateTime(), default=now, nullable=True)


class ReprocessConfig(Base):
    __tablename__ = "reprocess_config"
    __table_args__ = {"mysql_engine": 'InnoDB', 'mysql_charset': 'utf8'}

    CLUSTER_MODE_THRESHOLD = 0
    CLUSTER_MODE_CLUSTER   = 1

    id = schema.Column(types.Integer, schema.Sequence('reprocess_config_id', optional=True), primary_key=True)
    code = schema.Column(types.String(20), nullable=False)
    name = schema.Column(types.Unicode(50), nullable=False)
    peak_detection_major = schema.Column(types.Integer, nullable=False, default=0)
    peak_detection_minor = schema.Column(types.Integer, nullable=False, default=0)
    peak_quant_major = schema.Column(types.Integer, nullable=False, default=0)
    peak_quant_minor = schema.Column(types.Integer, nullable=False, default=0)
    trigger_sigma_multiplier = schema.Column(types.Numeric(precision=6, scale=2), nullable=True)
    trigger_fixed_width = schema.Column(types.Numeric(precision=6, scale=2), nullable=True)
    width_gating_sigma = schema.Column(types.Numeric(precision=6, scale=2), nullable=True)
    red_width_gating_sigma = schema.Column(types.Numeric(precision=6, scale=2), nullable=True)
    fam_min_amplitude = schema.Column(types.Numeric(precision=6, scale=2), nullable=True)
    vic_min_amplitude = schema.Column(types.Numeric(precision=6, scale=2), nullable=True)
    vertical_streaks_enabled = schema.Column(types.Boolean, nullable=True)
    peak_separation = schema.Column(types.Integer, nullable=True)
    active = schema.Column(types.Boolean, nullable=False, default=True)
    cluster_mode = schema.Column(types.Integer, nullable=False, default=CLUSTER_MODE_CLUSTER)
    original_folder = schema.Column(types.String(255), nullable=True)


    plate_metrics = orm.relation('PlateMetric', backref='reprocess_config', cascade='all, delete-orphan')
    analysis_groups = orm.relation('AnalysisGroup', secondary=analysis_group_reprocess_table)

class PlateMetric(Base):
    __tablename__ = "plate_metric"
    __table_args__ = {"mysql_engine": 'InnoDB', 'mysql_charset': 'utf8'}

    id = schema.Column(types.Integer, schema.Sequence('plate_metric_id', optional=True), primary_key=True)
    plate_id = schema.Column(types.Integer, schema.ForeignKey('plate.id'), nullable=False)
    reprocess_config_id = schema.Column(types.Integer, schema.ForeignKey('reprocess_config.id'), nullable=True)
    carryover_peaks = schema.Column(types.Integer, nullable=True, doc="Plate Carryover Peaks", info={'comparable': True})
    gated_contamination_peaks = schema.Column(types.Integer, nullable=True, doc="Plate Gated Contamination Peaks", info={'comparable': True})
    contamination_peaks = schema.Column(types.Integer, nullable=True, doc="Plate Contamination Peaks", info={'comparable': True})
    stealth_wells = schema.Column(types.Integer, nullable=True)
    software_pmt_gain_fam = schema.Column(types.Float, nullable=True)
    software_pmt_gain_vic = schema.Column(types.Float, nullable=False)

    well_metrics = orm.relation('WellMetric', backref='plate_metric', cascade='all, delete-orphan')

    @property
    def well_metric_name_dict(self):
        return dict([(wm.well_name, wm) for wm in self.well_metrics])

    @property
    def from_reprocessed(self):
        return self.reprocess_config_id is not None


class WellMetric(Base, PercentAttributeMixin):
    __tablename__ = "well_metric"
    __table_args__ = {"mysql_engine": 'InnoDB', 'mysql_charset': 'utf8'}

    id = schema.Column(types.Integer, schema.Sequence('well_metric_id', optional=True), primary_key=True)
    plate_metric_id = schema.Column(types.Integer, schema.ForeignKey('plate_metric.id'), nullable=False)
    well_id = schema.Column(types.Integer, schema.ForeignKey('qlbwell.id'), nullable=False)
    well_name = schema.Column(types.String(5), nullable=True)
    accepted_event_count = schema.Column(
        types.Integer, nullable=False, default=0,
        doc="Accepted Events",
        info={'comparable': True,
              'definition': """The number of events per well that are accepted, and figure toward
                               the concentration measured in that well."""})
    total_event_count = schema.Column(
        types.Integer, nullable=False, default=0,
        doc="Total Events",
        info={'comparable': True,
              'definition': """The number of events per well that were classified by the algorithm
                               as droplets.  These include width-gated and quality-gated droplets."""})
    width_mean = schema.Column(
        types.Float, nullable=True,
        doc="Width Mean",
        info={'comparable': True,
              'definition': """The mean width of all droplets, including width-gated droplets"""})
    width_variance = schema.Column(
        types.Float, nullable=True,
        doc="Width Stdev",
        info={'comparable': True,
              'definition': """The standard deviation of the width of all droplets, including
                               width-gated droplets"""})
    cnv = schema.Column(
        types.Float, nullable=True,
        doc="CNV",
        info={'comparable': True,
              'definition': """CNV of the well, if positives and negatives were determined in
                               both channels"""})
    cnv_lower_bound = schema.Column(
        types.Float, nullable=True,
        doc="CNV Lower CI Bound",
        info={'comparable': True})
    cnv_upper_bound = schema.Column(types.Float, nullable=True,
        doc="CNV Upper CI Bound",
        info={'comparable': True})
    inverse_cnv = schema.Column(types.Float, nullable=True,
        doc="CNV (VIC -> FAM)",
        info={'comparable': True})
    inverse_cnv_lower_bound = schema.Column(types.Float, nullable=True, doc="CNV VIC->FAM Lower CI Bound")
    inverse_cnv_upper_bound = schema.Column(types.Float, nullable=True, doc="CNV VIC->FAM Upper CI Bound")

    # This is yet determined by looking at the QLP value, rather it is normally assigned
    # when a plate is processed.
    expected_cnv = schema.Column(types.Float, nullable=True)

    rejected_peaks = schema.Column(
        types.Integer, nullable=True,
        doc="Rejected Peaks",
        info={'comparable': True,
              'definition': """The number of events above baseline that were not called as peaks by
                               the peak calling algorithm, because the algorithm could not reliably
                               determine a single-droplet width"""})
    vertical_streak_events = schema.Column(
        types.Integer, nullable=True,
        doc="Vertical Streak Events",
        info={'comparable': True,
              'definition': """The number of events gated out as part of QuantaSoft's vertical streak
                               elimination algorithm"""})

    # I don't even remember this anymore
    null_linkage = schema.Column(types.Float, nullable=True)

    balance_score = schema.Column(
        types.Float, nullable=True,
        doc="B-Score",
        info={'comparable': True,
              'definition': """A rough measurement of the bias toward or against positive-positive
                               droplets.  Only applicable if both channels have positives and
                               negatives.  Negative B-scores indicate too many negative-negative
                               droplets.  Positive B-scores indicate a bias against negative-negative
                               droplets."""})
    sum_baseline_mean = schema.Column(
        types.Float, nullable=True,
        doc="Sum Baseline Mean",
        info={'comparable': True,
              'definition': """Average combined baseline signal from FAM and VIC channels."""})
    sum_baseline_stdev = schema.Column(
        types.Float, nullable=True,
        doc="Sum Baseline Stdev",
        info={'comparable': True,
              'definition': """Standard deviation of the sum baseline signal from the FAM and VIC channels."""})
    cnv_rise_ratio = schema.Column(
        types.Float, nullable=True,
        doc="CNV 4Q/1Q Ratio",
        info={'comparable': True,
              'definition': """Observed CNV of the last quarter of accepted droplets (by event number) divided by the CNV
                               observed in the first quarter of droplets."""})
    carryover_peaks = schema.Column(
        types.Integer, nullable=True,
        doc="Well Carryover Peaks",
        info={'comparable': True,
              'definition': """Number of peaks considered carryover in this well.  This needs to be explicitly determined by
                               QTools, and will only be so done if this is a stealth well in a carryover plate."""})
    short_interval_count = schema.Column(
        types.Integer, nullable=True,
        doc="Well Narrow Droplet Spacing",
        info={'comparable': True,
              'definition': """Number of droplets that are less than a certain droplet width from the previous droplet.
                               Normally this interval is set at 2.75 normalized droplet widths."""})

    # the threshold in number of normalized droplet widths that was used for short_interval_count
    short_interval_threshold = schema.Column(types.Float, nullable=True)

    air_droplets = schema.Column(
        types.Integer, nullable=True,
        doc="Well 'Air' Droplets",
        info={'comparable': True,
              'definition': """Number of droplets considered air by QTools.  An air droplet is a low-fluorescence
                               droplet (< 500 RFU uncorrected, normally) that falls in between a
                               gap where there are no droplets of normal amplitude."""})

    # maximum amplitude for an air droplet in the air droplet count above
    air_droplets_threshold = schema.Column(types.Float, nullable=True)

    # TODO: should be comparable?
    min_amplitude_peaks = schema.Column(types.Integer, nullable=True)
    fragmentation_probability = schema.Column(types.Float, nullable=True)

    # QLWellChannelStatistics.CONC_CALC_MODE_CLUSTER if the CNV was determined by looking at the cluster calls from QTools,
    # QLWellChannelStatistics.CONC_CALC_MODE_THRESHOLD otherwise
    cnv_calc_mode = schema.Column(types.Integer, nullable=False, default=0)
    accepted_width_mean = schema.Column(
        types.Float, nullable=True,
        doc="Accepted Width Mean",
        info={'comparable': True,
              'definition': """The mean width of accepted droplets."""})
    accepted_width_stdev = schema.Column(
        types.Float, nullable=True,
        doc="Accepted Width Stdev",
        info={'comparable': True,
              'definition': """The standard deviation of the width accepted droplets."""})

    ## new cluster metrics
    diagonal_scatter  = schema.Column(
        types.Integer, nullable=True,
        doc="Diagonal Droplet Scatter",
        info={'comparable': True,
              'definition': """Number of droplets between the expected amplitude bounds 
                               of double negative and double postive clusters (ie on diagonal).
                               This metrics is only valid if wells with both double negative 
                               and positve droplets."""})
    diagonal_scatter_pct  = schema.Column(
        types.Integer, nullable=True,
        doc="Diagonal Droplet Scatter %",
        info={'comparable': True,
              'definition': """Percent of droplets between the expected amplitude bounds 
                               of double negative and double postive clusters (ie on diagonal).
                               Percent is calculated on the number of double pos + neg droplts.
                               This metrics is only valid if wells with both double negative 
                               and positve droplets."""})


    ## detrived metrics below
    well_channel_metrics = orm.relation('WellChannelMetric', backref='well_metric',  cascade='all, delete-orphan')

    @property
    def gated_out_event_count(self):
        return self.total_event_count - self.accepted_event_count
    
    @property_attr_wrapper(doc="Gated Out Events %",
                           info={'comparable': True,
                                 'definition': "Percentage of peaks gated out."}
    )
    @property
    def gated_out_event_pct(self):
        if self.total_event_count:
            return self.gated_out_event_count*100 / float(self.total_event_count)
        else:
            return 0
    
    @property_attr_wrapper(
        doc="Triggered Event Count",
        info={'definition': """Number of events above minimum amplitude.  Droplets below this
                               amplitude are considered air droplets."""}
    )
    @property
    def triggered_event_count(self):
        """
        total events - events below min amplitude.
        """
        if self.min_amplitude_peaks:
            return self.total_event_count - self.min_amplitude_peaks
        else:
            return self.total_event_count
    
    @property
    def total_peak_count(self):
        return self.total_event_count + (self.rejected_peaks or 0)

    @property
    def fragmentation_probability_pct(self):
        return self.percent(self.fragmentation_probability)

    
    @property_attr_wrapper(
        doc="Rejected Events %",
        info={'comparable': True,
              'definition': "Percentage of total peaks above baseline that were rejected"}
    )
    @property
    def rejected_peak_ratio(self):
        if self.total_peak_count:
            return float(self.rejected_peaks)*100/(self.total_peak_count+self.rejected_peaks)
        else:
            return 0
    
    @property_attr_wrapper(
        doc="Vertical Streak Events %",
        info={'comparable': True,
              'definition': "Percentage of events gated out as part of vertical streaks"}
    )
    @property
    def vertical_streak_ratio(self):
        """% Events Vertical Streak"""
        if self.vertical_streak_events is None:
            return None
        
        if self.triggered_event_count:
            return float(self.vertical_streak_events)*100/self.triggered_event_count
        else:
            return 0
    
    # TODO: rename to width_cv_ratio or _pct?
    @property_attr_wrapper(
        doc="Width CV%",
        info={'comparable': True,
              'definition': """Standard deviation the width of all droplets, as a percentage of
                               the mean width of all droplets."""}
    )
    @property
    def width_cv(self):
        if self.width_mean and self.width_variance is not None:
            return self.width_variance*100/self.width_mean
        else:
            return 0

    # TODO: rename to accepted_width_cv_ratio or _pct?
    @property_attr_wrapper(
        doc='Accepted Width CV%',
        info={'comparable': True,
              'definition': """Standard deviation of the width of all accepted events,
                               as a percentage of the mean width of accepted events."""}
    )
    @property
    def accepted_width_cv(self):
        if self.accepted_width_mean and self.accepted_width_stdev is not None:
            return self.accepted_width_stdev*100/self.accepted_width_mean
        else:
            return 0

    @property_attr_wrapper(
        doc="Below Min Amplitude %",
        info={'comparable': True,
              'definition': """Percentage of events that were gated out due to being
                               too low in amplitude to be considered an aqueous droplet."""}
    )
    @property
    def min_amplitude_ratio(self):
        if self.min_amplitude_peaks is None:
            return None
        
        if self.total_peak_count:
            return float(self.min_amplitude_peaks)*100/self.total_peak_count
        else:
            return 0
    
    @property_attr_wrapper(
        doc="Narrow Droplet Spacing %",
        info={'comparable': True,
              'definition': """Percentage of droplets that were considered close to
                               the following droplet."""}
    )
    @property
    def short_interval_count_ratio(self):
        if self.short_interval_count is None:
            return None
        
        if self.triggered_event_count > 2:
            return float(self.short_interval_count)*100/(self.triggered_event_count - 2)
        else:
            return 0

    @property_attr_wrapper(
        doc='Cluster Data Quality',
        info={'comparable': True,
              'definition': """Data quality/confidence as computed by the clustering
                               algorithm.  Normalized such that anything under 0.85
                               is considered unsuitable for definitive calling."""}
    )
    @property
    def cluster_conf(self):
        """
        Cluster conf is stored on the channel in the QLP but should be equal for both channels.
        Use this as a pass-thru, though with the caveat that this may incur a DB lookup if the
        channel records aren't eagerly loaded.
        """
        if len(self.well_channel_metrics) > 0:
            return self.well_channel_metrics[0].cluster_conf
        else:
            return None

    @property_attr_wrapper(
        doc='Detla High Width Mean',
        info={'comparable': True,
              'definition': """This State is only defined for single well color comp plates.
                               It is ment to give an indication of the alignment of channel readers.
                               It is the difference between the mean widths of ch0 positive
                               droplets and the mean widths of ch1 positve droplets"""}
    )
    @property
    def delta_widths(self):
        """
            This State is only defined for single well color comp plates
            It is the difference between the mean widths of ch0 positive
            droplets and the mean widths of ch1 positve droplets.        
        """
    
        if  hasattr( self, '_delta_widths'):
            return self._delta_widths
        else:
            if len(self.well_channel_metrics) < 2:
                return None
            elif (  self.well_channel_metrics[0].width_mean_hi is None \
               or self.well_channel_metrics[1].width_mean_hi is None ):
                return None

            self._delta_widths = self.well_channel_metrics[0].width_mean_hi \
                     - self.well_channel_metrics[1].width_mean_hi
            return self._delta_widths

    @delta_widths.setter
    def delta_widths(self, value):
        
        self._delta_widths = value


class WellChannelMetric(Base, PercentAttributeMixin):
    __tablename__ = "well_channel_metric"
    __table_args__ = {"mysql_engine": 'InnoDB', 'mysql_charset': 'utf8'}

    id = schema.Column(types.Integer, schema.Sequence('well_channel_metric_id', optional=True), primary_key=True)
    well_metric_id = schema.Column(types.Integer, schema.ForeignKey('well_metric.id'), nullable=False)
    well_channel_id = schema.Column(types.Integer, schema.ForeignKey('qlbwell_channel.id'), nullable=False)
    channel_num = schema.Column(types.Integer, nullable=False, default=0)
    min_quality_gating = schema.Column(types.Float, nullable=True)
    min_quality_gating_conf = schema.Column(types.Float, nullable=True)

    # these are a bit anachronistic as after 1.2.8 or so the width gates
    # vary by amplitude bin
    min_width_gate = schema.Column(types.Float, nullable=True)
    min_width_gate_conf = schema.Column(types.Float, nullable=True)
    max_width_gate = schema.Column(types.Float, nullable=True)
    max_width_gate_conf = schema.Column(types.Float, nullable=True)
    width_gating_sigma = schema.Column(types.Float, nullable=True)

    threshold = schema.Column(
        types.Float, nullable=True,
        doc="Threshold",
        info={'comparable': True,
              'definition': """Dividing line between positives and negatives as determined by
                               QuantaSoft's thresholding algorithm.  Computed independently
                               from clusters to enable dependent metrics (polydispersity,
                               rain, etc.).  Reflects the last saved state of the well, so
                               the threshold may be automatic or manually set."""})
    threshold_conf = schema.Column(
        types.Float, nullable=True,
        doc="Threshold Data Quality",
        info={'comparable': True,
              'definition': """Data quality as determined from the thresholding algorithm, or,
                               more accurately, the algorithm's confidence in placing the
                               threshold where it did, compared to possible alternatives."""})

    # This is a bit of a misnomer.  This is only set if QTools is manually thresholding a channel for some
    # reason.  The threshold stored in the QLP, be it manual or automatic, will appear in the 'threshold'
    # column.
    #
    # TODO (GitHub Issue #9): rename manual_threshold to qtools_assigned_threshold.
    #
    manual_threshold = schema.Column(types.Float, nullable=True)

    # whether an automatic threshold was expected -- set by plate loading logic,
    # rather than by QuantaSoft or the QLP
    auto_threshold_expected = schema.Column(types.Boolean, nullable=True, default=True)
    concentration = schema.Column(
        types.Float, nullable=True,
        doc="Concentration", info={'comparable': True,
                                   'definition': """Estimated copies per microliter of target."""})

    conc_lower_bound = schema.Column(types.Float, nullable=True, doc="Concentration CI Lower Bound", info={'comparable': True})
    conc_upper_bound = schema.Column(types.Float, nullable=True, doc="Concentration CI Upper Bound", info={'comparable': True})
    
    # what the expected concentration was-- set by plate loading logic in QTools,
    # not by QuantaSoft or the QLP
    expected_concentration = schema.Column(types.Float, nullable=True)
    positive_peaks = schema.Column(
        types.Integer, nullable=True,
        doc="Positive Peaks",
        info={'comparable': True,
              'definition': """Number of droplets called positive in this channel."""})
    negative_peaks = schema.Column(
        types.Integer, nullable=True,
        doc="Negative Peaks",
        info={'comparable': True,
              'definition': """Number of droplets called negative in this channel."""})

    # TODO move to WellMetric, really (like cluster mode)
    width_gated_peaks = schema.Column(
        types.Integer, nullable=True,
        doc="Width Gated Peaks",
        info={'comparable': True,
              'definition': """Number of peaks gated out due to width.  Should be the same for both channels in plates
                               run after 2010."""})
    quality_gated_peaks = schema.Column(
        types.Integer, nullable=True,
        doc="Quality Gated Peaks",
        info={'comparable': True,
              'definition': """Number of peaks gated out due to 'quality.'  As of QuantaSoft 1.3 and lower, this should
                               only happen in Rare Event mode, where a low-quality droplet is a droplet that is too
                               close to another droplet."""})
    
    # for false positive/false negative setting, see qtools.lib.metrics
    false_positive_peaks = schema.Column(
        types.Integer, nullable=True,
        doc="False Positive Peaks",
        info={'comparable': True,
              'definition': """Number of false positive droplets in this channel, as determined by QTools when the
                               well is part of a false positive/false negative layout.  Not set by QuantaSoft."""})
    false_negative_peaks = schema.Column(
        types.Integer, nullable=True,
        doc="False Negative Peaks",
        info={'comparable': True,
              'definition': """Number of false negatve droplets in this channel, as determined by QTools when the
                               well is part of a false positive/false negative layout.  Not set by QuantaSoft."""})

    # TODO: should be deprecated/removed -- carryover_peaks is on WellMetric
    carryover_peaks = schema.Column(types.Integer, nullable=True)

    total_events_amplitude_mean = schema.Column(
        types.Float, nullable=True,
        doc="Total Events Amplitude Mean",
        info={'comparable': True,
              'definition': """Mean amplitude of all droplets"""})
    total_events_amplitude_stdev = schema.Column(
        types.Float, nullable=True,
        doc="Total Events Amplitude Stdev",
        info={'comparable': True,
              'definition': """Standard deviation in amplitude of all droplets"""})

    amplitude_mean = schema.Column(
        types.Float, nullable=True,
        doc="Amplitude Mean",
        info={'comparable': True,
              'definition': """Mean amplitude of all accepted droplets"""})
    amplitude_stdev = schema.Column(
        types.Float, nullable=True,
        doc="Amplitude Stdev",
        info={'comparable': True,
              'definition': """Standard deviation in amplitude of all accepted droplets"""})
    positive_mean = schema.Column(
        types.Float, nullable=True,
        doc="Positive Amplitude Mean",
        info={'comparable': True,
              'definition': """Mean amplitude of all accepted, positive droplets."""})
    positive_stdev = schema.Column(
        types.Float, nullable=True,
        doc="Positive Amplitude Stdev",
        info={'comparable': True,
              'definition': """Standard deviation in amplitude of all accepted, positive droplets."""})
    negative_mean = schema.Column(types.Float, nullable=True, doc="Negative Mean Amplitude", info={'comparable': True})
    negative_stdev = schema.Column(types.Float, nullable=True, doc="Negative Amplitude Stdev", info={'comparable': True})
    positive_rain_peaks = schema.Column(types.Integer, nullable=True)
    middle_rain_peaks = schema.Column(types.Integer, nullable=True)
    negative_rain_peaks = schema.Column(types.Integer, nullable=True)
    decision_tree_flags = schema.Column(
        BigInt(unsigned=True), nullable=True, default=0,
        doc="Decision Tree",
        info={'comparable': True,
              'definition': """Integer value of the 64-bit decision tree flag set by QuantaSoft.  Used for debugging."""})
    s_value = schema.Column(
        types.Float, nullable=True,
        doc="S-Value",
        info={'comparable': True,
              'definition': """Where there are positives and negatives, the separability between positives and negatives.
                               Higher is better.  The difference in means divided by the sums of the standard deviations."""})
    rain_p_plus = schema.Column(types.Float, nullable=True)
    rain_p = schema.Column(types.Float, nullable=True)
    rain_p_minus = schema.Column(types.Float, nullable=True)
    positive_skew = schema.Column(
        types.Float, nullable=True,
        doc="Positive Skew",
        info={'comparable': True,
              'definition': """Distribution balance of positive amplitudes."""})
    positive_kurtosis = schema.Column(
        types.Float, nullable=True,
        doc="Positive Kurtosis",
        info={'comparable': True,
              'definition': """Distribution sharpness of positive amplitudes."""})
    nonpositive_skew = schema.Column(
        types.Float, nullable=True,
        doc="Non-Positive Skew",
        info={'comparable': True,
              'definition': """Distribution balance of negatives (with threshold) or all droplets (no threshold)"""})
    nonpositive_kurtosis = schema.Column(
        types.Float, nullable=True,
        doc="Non-Positive Kurtosis",
        info={'comparable': True,
              'definition': """Distribution sharpness of negatives (with threshold) or all droplets (no threshold)"""})
    concentration_rise_ratio = schema.Column(
        types.Float, nullable=True,
        doc="Concentration 4Q/1Q Ratio",
        info={'comparable': True,
              'definition': """The concentration computed by looking at the last quarter of droplets,
                               divided by the concentration computed by looking at the first quarter
                               of droplets (by event number).  This was used to determine whether
                               there is an increasing bias against negatives in signal processing as later-run
                               droplets, which were more tightly packed, crossed the detector."""})
    baseline_mean = schema.Column(
        types.Float, nullable=True,
        doc="Baseline Mean",
        info={'comparable': True,
              'definition': """Mean baseline noise in this channel."""})
    baseline_stdev = schema.Column(
        types.Float, nullable=True,
        doc="Baseline Stdev",
        info={'comparable': True,
              'definition': """Baseline/background noise standard deviation in this channel"""})

    polydispersity = schema.Column(types.Float, nullable=True)
    # forgot what this was for... different from air drops in well metric?
    gap_rain_droplets = schema.Column(types.Integer, nullable=True)
    extracluster = schema.Column(types.Float, nullable=True)
    revb_polydispersity = schema.Column(types.Float, nullable=True)
    revb_extracluster = schema.Column(types.Float, nullable=True)
    cluster_conf = schema.Column(
        types.Float, nullable=True,
        doc="Cluster Confidence",
        info={'comparable': False,
              'definition': """Data quality/confidence of automatic algorithm in
                               determining distinct positive and negative clusters."""})
    conc_calc_mode = schema.Column(
        types.Integer, nullable=False, default=0,
        doc="Concentration Mode",
        info={'comparable': True,
              'definition': """Whether the concentration was determined by thresholding
                               or by clustering."""})
    clusters_automatic = schema.Column(types.Boolean, nullable=True)
    ntc_positives = schema.Column(
        types.Integer, nullable=True,
        doc="NTC Contamination Count",
        info={'comparable': True,
              'definition': """Number of droplets above a certain threshold (5000 FAM,
                               3000 VIC) in an NTC well."""})

    ## new extra cluster based metrics
    s2d_value =  schema.Column(
        types.Float, nullable=True,
        doc="S2D value",
        info={'comparable': True,
              'definition': """The minimal number of standerd diviations between any 2 
                               pos/neg clusters for a specfic channel."""})

    high_flier_value = schema.Column(
        types.Integer, nullable=True,
        doc="High flier droplets",
        info={'comparable': True,
              'definition': """Number of droplets above theoretical feasible amplitude.
                               > (25000 Fam, 12500 VIC/HEX)"""})
    
    low_flier_value = schema.Column(
        types.Integer, nullable=True,
        doc="Low flier droplets",
        info={'comparable': True,
               'definition': """Number of droplets above expected limit of single/double 
                                clusters and below theoretical feasible amplitude limit
                                > (25000 Fam, 12500 VIC/HEX)."""})
    
    single_rain_value = schema.Column(
        types.Integer, nullable=True,
        doc="Single Rain droplets",
        info={'comparable': True,
              'definition': """Number of droplets between the expected amplitude bounds 
                               of double negative and single postive clusters. Amplitude projected onto the axis
                                defined by cluster centriods."""})

    single_rain_pct = schema.Column(
        types.Float, nullable=True,
        doc="Single Rain droplets %",
        info={'comparable': True,
              'definition': """Percent of droplets between the expected amplitude bounds 
                               of double negative and single postive clusters. Amplitude projected onto the axis
                                defined by cluster centriods.  Percent calcluated only on the number of
                               empty (double neg) + single droplets for a channel."""})

    double_rain_value = schema.Column(
        types.Integer, nullable=True,
        doc="Double rain droplets",
        info={'comparable': True,
              'definition': """Number of droplets between the expected amplitude bounds 
                               of single and double postive clusters. Amplitude projected onto the axis
                               defined by cluster centriods."""})
    
    double_rain_pct = schema.Column(
        types.Float, nullable=True,
        doc="Double rain droplet %",
        info={'comparable': True,
              'definition': """Percent of droplets between the expected amplitude bounds 
                               of single and double postive clusters. Amplitude projected onto the axis
                               defined by cluster centriods. Percent calcluated only on the number of
                               single + double droplets for a channel."""})

    width_mean_hi = schema.Column(
        types.Float, nullable=True,
        doc="Width Mean HI",
        info={'comparable': True,
              'definition': """With mean of HI droplets from single well color call in relevent channel (Blue HI 1, Green HI 2)
                               This metric is not set by Quantasoft."""})


    ## Below are 'derived metrics from data.....
    ### percent decorators ###
    property_attr_wrapper(
        doc="High flier %",
        info={'comparable': True,
              'definition': """Pecent of droplets above theoretical feasible amplitude.
                             > (25000 Fam, 12500 VIC/HEX). Percent calcluated on total number of
                            droplets."""})
    @property
    def high_flier_pct(self):
        if( self.high_flier_value is None or self.positive_peaks is None or self.negative_peaks is None):
            return None
        accepted_droplet_number = self.positive_peaks + self.negative_peaks

        if accepted_droplet_number < 1:
            return 0

        return self.percent(self.high_flier_value/(accepted_droplet_number))

    property_attr_wrapper(
        doc="Low flier %",
        info={'comparable': True,
              'definition': """Number of droplets above expected limit of single/double 
                               clusters and below theoretical feasible amplitude limit
                               (25000 Fam, 12500 VIC/HEX). calcluated on total number of
                               droplets."""})
    @property
    def low_flier_pct(self):

        if( self.low_flier_value is None or self.positive_peaks is None or self.negative_peaks is None):
            return None

        accepted_droplet_number = self.positive_peaks + self.negative_peaks
        
        if accepted_droplet_number < 1:
            return 0

        return self.percent(self.low_flier_value/(accepted_droplet_number))


    @property_attr_wrapper(
        doc="Rain: Positive %",
        info={'comparable': True,
              'definition': """Percentage of droplets brighter than 130% of the positive mean amplitude
                               (given a threshold present) or 30% brighter than total mean amplitude
                               if there is no threshold."""}
    )
    @property
    def rain_p_plus_pct(self):
        return self.percent(self.rain_p_plus)

    @property_attr_wrapper(
        doc="Rain: Middle %",
        info={'comparable': True,
              'definition': """Percentage of droplets dimmer than 70% of the positive mean amplitude,
                               and brighter than 130% of the negative mean amplitude.  Only
                               present/valid if a threshold is computed."""}
    )
    @property
    def rain_p_pct(self):
        return self.percent(self.rain_p)

    @property_attr_wrapper(
        doc="Rain: Negative/1-Cluster %",
        info={'comparable': True,
              'definition': """Percentage of droplets dimmer than 70% of the negative mean amplitude
                               (with a threshold present) or 30% dimmer than the total mean amplitude
                               if there is no threshold."""}
    )
    @property
    def rain_p_minus_pct(self):
        return self.percent(self.rain_p_minus)

    @property_attr_wrapper(
        doc="Polydispersity %",
        info={'comparable': True,
              'definition': """Percentage of total droplets that are smaller than the width gates and
                               dimmer than the main droplet populations, or larger than the width gates
                               and brighter than the main droplet populations.  This is the metric
                               used in manufacturing, which uses the widest width gates in the well
                               to establish consistent boundaries for what is a wrong-sized droplet (and
                               ensure metric backward-compatibility with QLPs generated by older versions
                               of QuantaSoft) The amplitude boundaries are the same as for positive
                               and negative rain."""}
    )
    @property
    def polydispersity_pct(self):
        return self.percent(self.polydispersity)

    @property_attr_wrapper(
        doc="Polydispersity % (binned measure)",
        info={'comparable': True,
              'definition': """Percentage of total droplets that are smaller than the width gates and
                               dimmer than the main droplet populations, or larger than the width gates
                               and brighter than the main droplet populations.  This metric takes
                               the variable width gates by amplitude sum into consideration."""}
    )
    @property
    def binned_polydispersity_pct(self):
        return self.percent(self.revb_polydispersity)

    @property_attr_wrapper(
        doc="Extracluster Droplet %",
        info={'comparable': True,
              'definition': """Percentage of total droplets that are outside the boundaries
                               defined by the width gates and a range of 30% around the mean
                               amplitude of the positive and negative clusters (or the single
                               cluster, should a threshold not be calculated).  The widest
                               width gates of the well are used in this calculation, to
                               allow comparison with older, non-amplitude binned QLPs."""}
    )
    @property
    def extracluster_pct(self):
        return self.percent(self.extracluster)

    @property_attr_wrapper(
        doc="Extracluster Droplet % (binned measure)",
        info={'comparable': True,
              'definition': """Percentage of total droplets that are outside boundaries defined
                               by the width gates and a range of 30% around the mean amplitude
                               of the droplet clusters.  This metric takes the variable width gates
                               by amplitude sum into consideration, should they be included in
                               the original plate file."""}
    )
    @property
    def binned_extracluster_pct(self):
        return self.percent(self.revb_extracluster)


    @property_attr_wrapper(
        doc="Cluster Mode",
        info={'definition': 'Whether clustering was done automatically or manually.'})
    @property
    def clusters_automatic_display(self):
        if self.clusters_automatic is None:
            return 'Unknown'
        elif self.clusters_automatic:
            return 'Automatic'
        else:
            return 'Manual'


    @property_attr_wrapper(doc="Non-Positive Amplitude Mean",
        info={'comparable': True,
              'definition': """The mean amplitude of all droplets, if positives and negatives are not
                               determined, or the mean amplitude of the negative droplets if a
                               threshold/clustering is determined."""})
    @property
    def nonpositive_mean(self):
        """
        Returns the mean of negatives or all data if no threshold was
        called.
        """
        if self.positive_peaks > 0:
            return self.negative_mean
        else:
            return self.amplitude_mean
    
    @property_attr_wrapper(doc="Non-Positive Amplitude Stdev", info={'comparable': True})
    @property
    def nonpositive_stdev(self):
        """
        Returns the variance of the negatives or all data if no threshold
        was called.
        """
        if self.positive_peaks > 0:
            return self.negative_stdev
        else:
            return self.amplitude_stdev
   
    @property_attr_wrapper(doc="Mean Pos/Neg Amplitude Ratio",
         info={'comparable': True,
               'definition': """
                             The mean amplitude of the positive droplets divided
                             by the mean amplitude of the negative droplets.
                             """}
    )
    @property
    def mean_pos_neg_ratio(self):
         """
         Return the mean positve to negative droplet amplitude ratio 
         (mean(pos)/mean(neg)) of the accepted droplets.
         """
         if self.positive_peaks is None or  self.negative_peaks is None:
            return None
         if self.negative_mean > 0:
             return self.positive_mean / self.negative_mean
         else:
             return 0

    @property_attr_wrapper(doc="Positive SNR (Mean/Stdev)",
        info={'comparable': True,
              'definition': """The mean of the positive amplitudes divided
                               by the standard deviation of the positive amplitudes."""}
    )
    @property
    def positive_snr(self):
        """
        Return the signal-to-noise ratio (mean/variance) of the
        positives.
        """
        if self.positive_peaks > 0 and self.positive_stdev != 0:
            return self.positive_mean / self.positive_stdev
        else:
            return None

    @property_attr_wrapper(doc="Non-Positive SNR (Mean/Stdev)",
        info={'comparable': True,
              'definition': """The mean of the negative amplitudes (if a threshold
                               is determined, otherwise all amplitudes) divided
                               by the standard deviation of the those amplitudes."""}
    )
    @property
    def nonpositive_snr(self):
        """
        Return the signal-to-noise ratio (mean/variance) of either
        the negatives (if a threshold were called) or all peaks
        (if not)
        """
        if self.nonpositive_stdev != 0:
            return self.nonpositive_mean/self.nonpositive_stdev
        else:
            return None

    @property_attr_wrapper(doc='Total Events Amplitude CV%',
        info={'comparable': True,
              'definition': """The standard deviation of the amplitudes of all
                               droplets divided by the mean of all amplitudes."""}
    )
    @property
    def total_events_amplitude_cv_pct(self):
        """
        total events amplitude stdev / total events amplitude mean
        """
        if self.total_events_amplitude_mean is not None:
        	if self.total_events_amplitude_mean != 0:
            	    return self.total_events_amplitude_stdev*100 / self.total_events_amplitude_mean
        else:
            return None

    @property_attr_wrapper(doc='Amplitude CV%',
        info={'comparable': True,
              'definition': """The standard deviation of the amplitudes of all
                               accepted droplets divided by the mean of all amplitudes."""}
    )
    @property
    def amplitude_cv_pct(self):
        """
        amplitude stdev / amplitude mean
        """
        if self.amplitude_mean != 0:
            return self.amplitude_stdev*100 / self.amplitude_mean
        else:
            return None

    @property_attr_wrapper(doc='Positive Amplitude CV%',
        info={'comparable': True,
              'definition': """The standard deviation of the positive amplitudes of all
                               accepted droplets divided by the mean of positive amplitudes."""}
    )
    @property
    def positive_amplitude_cv_pct(self):
        """
        Inverse of Positive SNR.  Positive amplitude standard deviation over
        positive amplitude mean.  Expressed as a percentage (value*100)
        """
        if self.positive_peaks > 0 and self.positive_mean != 0:
            return self.positive_stdev*100 / self.positive_mean
        else:
            return None

    @property_attr_wrapper(doc='Non-Positive Amplitude CV%', info={'comparable': True})
    @property
    def nonpositive_amplitude_cv_pct(self):
        """
        Inverse of Negative SNR.  Negative amplitude standard deviation over
        negative amplitude mean.  Expressed as a percentage (value*100)
        """
        if self.nonpositive_mean != 0:
            return self.nonpositive_stdev*100 / self.nonpositive_mean
        else:
            return None

    @property
    def min_width_gate_stdevs(self):
        if self.well_metric.width_variance:
            wm = self.well_metric.width_mean
            diff = wm - self.min_width_gate
            return diff/self.well_metric.width_variance
        else:
            return None

    @property
    def max_width_gate_stdevs(self):
        if self.well_metric.width_variance:
            wm = self.well_metric.width_mean
            diff = self.max_width_gate - wm
            return diff/self.well_metric.width_variance
        else:
            return None

class AnalysisGroup(Base):
    __tablename__ = "analysis_group"
    __table_args__ = {"mysql_engine": 'InnoDB', 'mysql_charset': 'utf8'}

    id = schema.Column(types.Integer, schema.Sequence('analysis_group_id', optional=True), primary_key=True)
    name = schema.Column(types.Unicode(50), nullable=False)
    active = schema.Column(types.Boolean, nullable=False, default=True)
    type_code = schema.Column(types.String(), nullable=True)
    plates = orm.relation('Plate', secondary=analysis_group_plate_table)
    reprocesses = orm.relation('ReprocessConfig', secondary=analysis_group_reprocess_table)

class MapCache(Base):
    __tablename__ = "map_cache"
    __table_args__ = {"mysql_engine": 'InnoDB', 'mysql_charset': 'utf8'}

    id = schema.Column(types.Integer, schema.Sequence('map_cache_seq_id', optional=True), primary_key=True)
    address = schema.Column(types.Unicode(255), nullable=False, unique=True)
    verified = schema.Column(types.Boolean, nullable=False, default=False)
    lat = schema.Column(types.Float, nullable=True)
    lon = schema.Column(types.Float, nullable=True)




assay_table = Assay.__table__
enzyme_table = Enzyme.__table__
vendor_table = Vendor.__table__
buffer_table = Buffer.__table__
vendor_enzyme_table = VendorEnzyme.__table__
box2_table = Box2.__table__
project_table = Project.__table__
experiment_table = Experiment.__table__
person_table = Person.__table__
plate_table = Plate.__table__
sample_table = Sample.__table__
lot_number_table = LotNumber.__table__
hg19_assay_table = HG19AssayCache.__table__
snp131_assay_table = SNP131AssayCache.__table__
qlbfile_table = QLBFile.__table__
qlbwell_table = QLBWell.__table__
