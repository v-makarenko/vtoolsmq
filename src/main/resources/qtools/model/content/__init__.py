from qtools.model.meta import Base

from sqlalchemy import orm, Integer, String, Text, DateTime, Float, LargeBinary
from sqlalchemy.schema import Table, Column, Sequence, ForeignKey

from sqlalchemy.dialects.mysql.base import BIGINT as BigInt
from sqlalchemy.dialects.mysql.base import MEDIUMTEXT as MediumText

metadata = Base.metadata

class BGGeneInfo(Base):
    __tablename__ = "bg_gene_info"
    __table_args__ = {"mysql_engine": 'InnoDB', 'mysql_charset': 'utf8'}

    id = Column(Integer, Sequence('bg_gene_info_seq_id', optional=True), primary_key=True)
    species = Column(String(255), nullable=True)
    ensembl_gene = Column(String(128), unique=True, nullable=False)
    official_symbol = Column(String(45), nullable=True)
    official_name = Column(String(450), nullable=True)
    alias_symbol = Column(String(500), nullable=True)
    alias_name = Column(String(550), nullable=True)
    description = Column(Text, nullable=True)
    map_location = Column(String(50), nullable=True)
    gene_type = Column(String(30), nullable=True)
    entrez_gene_id = Column(BigInt(unsigned=True), nullable=True)
    gene_accession = Column(MediumText(), nullable=True)
    UniGene = Column(String(50), nullable=True)
    chromosome_location = Column(String(100), nullable=True)
    annotation_build = Column(String(100), nullable=True)

    designs = orm.relation('BGDesign', backref='gene_info', primaryjoin="BGGeneInfo.ensembl_gene==BGDesign.ENSG_ID")

class BGDesign(Base):
    __tablename__ = "bg_design"
    __table_args__ = {"mysql_engine": 'InnoDB', 'mysql_charset': 'utf8'}

    id = Column(Integer, Sequence('bg_design_seq_id', optional=True), primary_key=True)
    gene_info_id = Column(Integer, nullable=True) # using ENSG_ID to link -- leave blank for now
    qtools_assay_id = Column(Integer, ForeignKey('sequence_group.id'), nullable=True) # QTools assay reference
    bg_assay_id = Column(Integer, nullable=True) # BioGazelle assay reference
    project = Column(String(45), nullable=True)
    species = Column(String(255), nullable=True)
    application = Column(String(50), nullable=True)
    chemistry = Column(String(30), nullable=True)
    design_type = Column(String(50), nullable=True)
    assay_name = Column(String(100), nullable=False)
    ENSG_ID = Column(String(128), ForeignKey('bg_gene_info.ensembl_gene'), nullable=False)
    location = Column(String(69), nullable=True)
    forward = Column(String(45), nullable=True)
    reverse = Column(String(45), nullable=True)
    probe = Column(String(45), nullable=True) # this is an addition
    amplicon = Column(String(500), nullable=True)
    template = Column(String(60), nullable=True)
    amplicon_length = Column(Integer, nullable=True)
    gc_forward = Column(Float, nullable=True)
    gc_reverse = Column(Float, nullable=True)
    gc_amplicon = Column(Float, nullable=True)
    gc_probe = Column(Float, nullable=True)
    targeted_transcripts_count = Column(Integer, nullable=True)
    targeted_transcripts = Column(String(500), nullable=True)
    MIQE_start = Column(Integer, nullable=True)
    MIQE_end = Column(Integer, nullable=True)
    MIQE_location = Column(String(69), nullable=True)
    MIQE_context = Column(String(500), nullable=True)
    technology = Column(String(30), nullable=True)
    rs_id = Column(String(30), nullable=True)
    cosmic_id = Column(String(30), nullable=True)
    nucleotide_mutation = Column(String(100), nullable=True)
    amino_acid_change = Column(String(100), nullable=True)
    mutation_type = Column(String(30), nullable=True)
    splice_variants = Column(String(100), nullable=True)
    fluor = Column(String(30), nullable=True)
    quencher = Column(String(30), nullable=True)
    modifier_probe_seq = Column(String(150), nullable=True)
    restriction_enzyme = Column(String(30), nullable=True)
    anneal_temp = Column(Integer, nullable=True)
    extend_temp = Column(Integer, nullable=True)
    supermix_name = Column(String(100), nullable=True)
    supermix_part_number = Column(String(30), nullable=True)
    positive_ctrl_cell_line = Column(String(30), nullable=True)

    figures = orm.relation('BGFigures', backref='design')
    validations = orm.relation('BGAssayValidation', backref='design')

class BGFigures(Base):
    __tablename__ = "bg_figures"
    __table_args__ = {"mysql_engine": 'InnoDB', 'mysql_charset': 'utf8'}

    id = Column(Integer, Sequence('bg_figures_seq_id', optional=True), primary_key=True)
    design_id = Column(Integer, ForeignKey('bg_design.id')) # new construct
    project = Column(String(45), nullable=True)
    bg_assay_id = Column(Integer, nullable=True) # BioGazelle assay id
    assay_name = Column(String(100), nullable=True) # necessary if stored in design table?
    filename = Column(String(256), nullable=True) # if file referenced
    filetype = Column(String(45), nullable=True) # if file referenced
    filesize = Column(Integer, nullable=True) # if file referenced
    filecontent = Column(LargeBinary, nullable=True)
    caption = Text()

class BGAssayValidation(Base):
    __tablename__ = "bg_assay_validation"
    __table_args__ = {"mysql_engine": 'InnoDB', 'mysql_charset': 'utf8'}

    id = Column(Integer, Sequence('bg_assay_validation_seq_id', optional=True), primary_key=True)
    design_id = Column(Integer, ForeignKey('bg_design.id'))
    # necessary?
    project = Column(String(45), nullable=True)
    assay_name = Column(String(100), nullable=True)
    PCRcomposition = Column(String(50), nullable=True)
    PCRconditions = Column(String(50), nullable=True)
    PCRinstrument = Column(String(50), nullable=True)
    Sample = Column(String(50), nullable=True)
    approved = Column(Integer, nullable=True)
    NGS_on_target = Column(Integer, nullable=True)
    NGS_off_target = Column(Integer, nullable=True)
