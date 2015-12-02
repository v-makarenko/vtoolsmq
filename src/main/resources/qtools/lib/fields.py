"""
Different fields used for presentation in QTools
form pages.
"""
from qtools.constants.plate import *
from qtools.lib.inspect import class_properties
from qtools.lib.platesetup import plate_layouts
from qtools.lib.wowo import wowo
from qtools.model import Session, Project, Assay, Person, Experiment, Box2
from qtools.model import Plate, LotNumber, PlateTag, WellTag, Sample, Enzyme, VendorEnzyme, ThermalCycler
from qtools.model import DropletGenerator, DGUsed, PlateType, PhysicalPlate, SystemVersion
from qtools.model.sequence import SequenceGroupTag, SequenceGroup
from qtools.model.sequence.util import sequence_group_with_amplicon_query, active_sequence_group_query
import operator, itertools

from sqlalchemy import and_, or_

LOT_NUMBER_TYPE_QLF11 = 1
LOT_NUMBER_TYPE_QLF21 = 2
LOT_NUMBER_TYPE_REAGENT = 3
LOT_NUMBER_TYPE_OLIGO = 4


def field_display_value(field):
    """
    Return the display value of the specified field.
    """
    return dict(field['options'])[field['value']]

def model_distinct_field(column, additional=None, selected=None, blank=''):
    """
    Creates a select-compatible dropdown based on the distinct values
    of the model in the DB.  Side effect is a DB query, so be careful.

    TODO: might be a good idea to separate the selection logic from the
    lookup logic here.

    :param column: The Model attribute to display
    :param additional: Additional values to have in the dropdown, if they
                       are not present in any DB records.
    :param selected: Which value should be selected.
    :param blank: The value to display if the backing value is null/blank.
    :return A dict with keys (value, options): the selected value and the option dict.
    """
    if not additional:
        additional = []
    # get model from attribute
    values = [tup[0] for tup in Session.query(column).distinct().all()]
    for val in additional:
        if val not in values:
            values.append(val)
    
    values.sort(key=lambda v: v.lower())
    
    field = {'value': (selected if selected in values else '') or '',
              'options': [('', blank)]+
                         [(v, v) for v in values]}
    return field

def model_kv_field(store_column, display_column, selected=None, blank=''):
    """
    Creates a select-compatible dropdown based on the distinct values of
    the model in the DB.  store_column refers to the stored value (value
    attribute in the HTML option) and display_column refers to the
    corresponding display in the select.

    Differs from model_distinct_field in that model_distinct field uses
    a single column as both the display value and the stored value.
    """
    keyvals = Session.query(store_column, display_column).all()
    keyvals.sort(key=lambda tup: tup[1].lower())

    field = {'value': (selected if selected in [k for k, v in keyvals] else '') or '',
             'options': [('', blank)]+
                        [(str(k), v) for k, v in keyvals]}
    return field


def enzyme_field(selected=None, blank=''):
    enzymes = Session.query(Enzyme).order_by('name').all()
    field = {'value': selected or '',
             'options': [('', blank)]+[(e.name, e.name) for e in enzymes]}
    return field

def instock_enzyme_field(selected=None, blank=''):
    enzymes = Session.query(VendorEnzyme, Enzyme.name)\
                     .join(Enzyme)\
                     .filter(VendorEnzyme.stock_units > 0)\
                     .group_by(VendorEnzyme.enzyme_id)\
                     .order_by(Enzyme.name).all()
    
    field = {'value': (selected if selected in [name for ve, name in enzymes] else '') or '',
             'options': [('', blank)]+
                        [(name, name) for ve, name in enzymes]}
    return field


def enzyme_select_field(selected=None):
    field = {'value': selected or '',
             'options': [('', 'In Stock'),
                         ('NEB', 'NEB (all)'),
                         ('NEB4', 'NEB 4-cutters'),
                         ('All4', 'All 4-cutters'),
                         ('Fermentas', 'Fermentas 4/5 Cutters')]
            }
    return field

def channel_field(blank=False, empty='--', selected=None):
    field = {'value': selected or '',
             'options': [(0, "FAM"),
                         (1, "VIC")]}
    if blank:
        field['options'].insert(0, ('', empty))
    return field


def assay_field(blank=False, include_empties=False, empty='--', selected=None):
    """
    Return a dict (value, options) field set for the assays field.
    """
    if include_empties:
        assay_q = Session.query(Assay).order_by(Assay.name)
    else:
        assay_q = Assay.populated_valid_query(Session).order_by(Assay.name)
    assays = assay_q.all()
    # TODO: this part can be refactored
    field = {'value': selected or '',
             'options': [(str(assay.id), assay.name) for assay in assays]}
    if blank:
        field['options'].insert(0, ('', empty))
    return field

# like assay_field, but uses assay names as both keys and values.
def assay_name_field(blank=False, include_empties=False, empty='', selected=None):
    if include_empties:
        assay_q = Session.query(Assay).order_by(Assay.name)
    else:
        assay_q = Assay.populated_valid_query(Session).order_by(Assay.name)
    assays = assay_q.all()
    # TODO: this part can be refactored
    field = {'value': selected or '',
             'options': [(str(assay.name), assay.name) for assay in assays]}
    if blank:
        field['options'].insert(0, ('', empty))
    return field

def sequence_group_field(blank=False, include_without_amplicons=False, empty='--', selected=None):
    """
    Return a dict (value, options) field set for the sequence group field.
    """
    if include_without_amplicons:
        query = active_sequence_group_query().order_by(SequenceGroup.name)
    else:
        query = sequence_group_with_amplicon_query().order_by(SequenceGroup.name)
    assays = query.all()
    field = {'value': selected or '',
             'options': [(str(assay.id), assay.name) for assay in assays]}
    if blank:
        field['options'].insert(0, ('', empty))
    return field

# like sequence_group_field, but uses assay names as both keys and values.
def sequence_group_name_field(blank=False, include_without_amplicons=False, empty='', selected=None):
    if include_without_amplicons:
        query = active_sequence_group_query().order_by(SequenceGroup.name)
    else:
        query = sequence_group_with_amplicon_query().order_by(SequenceGroup.name)
    assays = query.all()
    field = {'value': selected or '',
             'options': [(str(assay.name), assay.name) for assay in assays]}
    if blank:
        field['options'].insert(0, ('', empty))
    return field
    

def sample_field(blank=False, selected=None):
    """
    Return a dict (value, options) field set for the samples field.
    """
    sample_q = Session.query(Sample).order_by(Sample.name)
    samples = sample_q.all()
    field = {'value': selected or '',
            'options': [(sample.id, sample.name) for sample in samples]}
    if blank:
        field['options'].insert(0, ('', '--'))
    return field


def assay_dye_field(selected=None):
    field = {'value': selected or '',
             'options': [('','--'),
                         ('FAM','FAM'),
                         ('VIC','VIC'),
                         ('JOE','JOE'),
                         ('HEX','HEX'),
                         ('CFO','Cal Fluor Orange 560')]}
    return field

def assay_quencher_field(selected=None):
    field = {'value': selected or '',
             'options': [('','--'),
                         ('MGB','MGB'),
                         ('BHQ','BHQ'),
                         ('Eclipse','Eclipse'),
                         ('TAMRA','TAMRA'),
                         ('IABkFQ','IABkFQ'),
                         ('BHQ+','BHQplus')]}
    return field

CHROM_LIST = tuple([u'%s' % chr for chr in range(1,23)]) + ('X', 'Y', 'M')
def chromosome_field(selected=None, empty=''):
    field = {'value': selected or '',
             'options': [('', empty)]+
                        [(c, c) for c in CHROM_LIST]}
    return field

def project_field(selected=None, active_only=False, validation_only=False, empty='--'):
    if not wowo('contractor'):
        project_q = Session.query(Project).order_by(Project.name)
        if active_only:
            project_q = project_q.filter(Project.active == True)
        # should prob fix this...
        if validation_only:
            project_q = project_q.filter(or_(Project.name.like('%Beta%'),
                                             Project.name.like('%Validation%'),
                                             Project.name.like('%Alpha%')))
        projects = project_q.all()
    else:
        projects = []
    return {'value': selected or '',
            'options': [('',empty)]+[(project.id, project.name) for project in projects]}

def sequence_group_tag_field(selected=None, empty='--'):
    if not wowo('contractor'):
        tag_q = Session.query(SequenceGroupTag).order_by(SequenceGroupTag.name)
        tags = tag_q.all()
    else:
        tags = []
    return {'value': selected or '',
            'options': [('',empty)]+[(tag.id, tag.name) for tag in tags]}

def system_version_field(selected=None, empty='--'):
    system_version_q = Session.query(SystemVersion).order_by(SystemVersion.id)
    system_versions = system_version_q.all()
    return {'value': selected or '',
            'options': [('',empty)]+[(system_version.id, system_version.desc) for system_version in system_versions]}


def person_field(selected=None, active_only=True):
    person_q = Session.query(Person).order_by(Person.first_name)
    if active_only:
        person_q = person_q.filter_by(active=True)
    people = person_q.all()
    return {'value': selected or '',
            'options': [('','--')]+[(person.id, "%s %s" % (person.first_name, person.last_name)) for person in people]}

def experiment_field(selected=None):
    exp_q = Session.query(Experiment).order_by(Experiment.name)
    exps = exp_q.all()
    return {'value': selected or '',
            'options': [('','--')]+[(exp.id, exp.name) for exp in exps]}

def box2_field(selected=None, empty='--', prod_only=False, exclude_fluidics_modules=False,order_by='name',order_desc=False):

    if ( order_desc ):
        box_q = Session.query(Box2).order_by( getattr(Box2,order_by).desc() )
    else:
        box_q = Session.query(Box2).order_by( getattr(Box2,order_by) )

    if prod_only or wowo('contractor'):
        box_q = box_q.filter(Box2.prod_query())
    if exclude_fluidics_modules:
        box_q = box_q.filter(Box2.whole_readers_only_query())
    boxes = box_q.all()
    return {'value': selected or '',
            'options': [('',empty)]+
                       [(box.id, box.name) for box in boxes]}

def lab_reader_group_field(empty='--'):
    """
    Intended to be set in a manual environment.  Should be ported
    to a Bootstrap-type scheme like comparable_metric_field()
    """
    box_q = Session.query(Box2).order_by(Box2.name)
    lab_readers = box_q.filter(Box2.lab_query()).all()
    prod_readers = box_q.filter(Box2.prod_query()).all()

    # htmlfill-compatible.
    if not wowo('contractor'):
        return [('',empty),
                ([(box.id, box.name) for box in lab_readers], 'Lab'),
                ([(box.id, box.name) for box in prod_readers],'Production')]
    else:
        return [('',empty),
                ([(box.id, box.name) for box in prod_readers],'Production')]

def fluidics_module_field(selected=None, empty='--'):
    box_q = Session.query(Box2).filter(Box2.fluidics_modules_only_query())\
                               .order_by(Box2.name)
    boxes = box_q.all()
    
    return {'value': selected or '',
            'options': [('',empty)]+
                       [(box.id, box.name) for box in boxes]}

def plate_program_version_field(selected=None):
    plate_q = Session.query(Plate.program_version).distinct()
    versions = plate_q.all()
    return {'value': selected or '',
            'options': [('','--')]+[(v.program_version, v.program_version) for v in versions if len(v.program_version) > 0]}

def plate_type_field(selected=None):
    return {'value': selected or '',
            'options': [('', '--'),
                        (1, "Product Development"),
                        (2, "Quality Control"),
                        (3, "CNV"),
                        (4, "Rare Event"),
                        (5, "Other Life Science"),
                        (6, "Other Diagnostic")]}

def plate_tag_field(selected=None):
    plate_tag_q = Session.query(PlateTag).order_by(PlateTag.name)
    plate_tags = plate_tag_q.all()
    return {'value': selected or [],
            'options': [(pt.id, pt.name) for pt in plate_tags]}

def well_tag_field(selected=None):
    well_tag_q = Session.query(WellTag).order_by(WellTag.name)
    well_tags = well_tag_q.all()
    return {'value': selected or [],
            'options': [(wt.id, wt.name) for wt in well_tags]}

def beta_type_field(selected=None, empty='--'):
    pts = Session.query(PlateType).order_by('name').all()
    return {'value': selected or '',
            'options': [('', empty)]+[(pt.id, pt.name) for pt in pts]}

def plate_type_subset_field(subset, selected=None, empty='--'):
    pts = Session.query(PlateType).filter(PlateType.code.in_(subset)).order_by('name').all()
    return {'value': selected or '',
            'options': [('', empty)]+[(pt.id, pt.name) for pt in pts]}

def all_plate_types_field(selected=None, empty='--'):
    pts = Session.query(PlateType).order_by('name').all()
    return {'value': selected or '',
            'options': [('', empty)]+[(str(pt.id), pt.name) for pt in pts]}

def dg_used_field(selected=None):
    dgs = Session.query(DGUsed).order_by('name').all()
    return {'value': selected or '',
            'options': [('', '--')]+[(d.id, d.name) for d in dgs]}

def droplet_generator_field(selected=None):
    dgs = Session.query(DropletGenerator).order_by('name').all()
    return {'value': selected or '',
            'options': [('', '--')]+[(d.id, d.name) for d in dgs]}

def thermal_cycler_field(selected=None, empty='--'):
    cyclers = Session.query(ThermalCycler).order_by('name').all()
    return {'value': selected or '',
            'options': [('', empty)]+[(c.id, c.name) for c in cyclers]}

def droplet_generator_oil_field(selected=None, empty='Unknown'):
    return {'value': selected or '',
            'options': [('', empty),
                        (DG_OIL_QLF1_1, 'QLF 1.1'),
                        (DG_OIL_QLF1_3, 'QLF 1.3'),
                        (DG_OIL_QLF1_4, 'QLF 1.4'),
                        (DG_OIL_QLF3_0, 'QLF 3.0 (DNA Groove)'),
                        (DG_OIL_QLF3_1, 'QLF 3.1 (DNA Groove)'),
                        (DG_OIL_OTHER, 'Other')]}

def droplet_reader_oil_field(selected=None, empty='Unknown'):
    return {'value': selected or '',
            'options': [('', empty),
                        (DR_OIL_QLF2_1, 'QLF 2.1'),
                        (DR_OIL_QLF2_1_1, 'QLF 2.1.1'),
                        (DR_OIL_QLF2_2, 'QLF 2.2'),
                        (DR_OIL_QLF4_0, 'QLF 4.0 (DNA Groove)'),
                        (DR_OIL_OTHER, 'Other')]}
# default 2.1.1

def master_mix_field(selected=None, empty='Unknown'):
    return {'value': selected or '',
            'options': [('', empty),
                        (MMIX_0_1, 'QLMM 0.1'),
                        (MMIX_0_2, 'QLMM 0.2'),
                        (MMIX_1_0, 'QLMM 1.0'),
                        (MMIX_1_1, 'QLMM 1.1'),
                        (MMIX_1_2_HEX, 'QLMM 1.2 (HEX)'),
                        (MMIX_1STEP_RT, 'QL 1-step RT-PCR MM'),
                        (MMIX_GROOVE_0_2, 'DNA Groove MM 0.2'),
                        (MMIX_GROOVE_0_3, 'DNA Groove MM 0.3'),
                        (MMIX_GROOVE_0_5, 'EvaGreen MM 0.5'),
                        (MMIX_DDPCR_SUPERMIX, 'Droplet PCR Supermix'),
                        (MMIX_SKINLESS_TAQ_0_1, 'Skinless Taq MM 0.1'),
                        (MMIX_OTHER, 'Other')]}
# default 1.0

def fluidics_routine_field(selected=None, empty='Unknown'):
    return {'value': selected or '',
            'options': [('', empty),
                        (FLUIDICS_ROUTINE_1_2, '1.2'),
                        (FLUIDICS_ROUTINE_1_3, '1.3'),
                        (FLUIDICS_ROUTINE_1_4, '1.4'),
                        (FLUIDICS_ROUTINE_OTHER, 'Other')]}

# get rid of this
def gasket_field(selected=None):
    return {'value': selected or '',
            'options': [('','Unknown'),
                        (GASKET_ON, 'Gasket'),
                        (GASKET_OFF, 'No Gasket')]}

def droplet_generation_method_field(selected=None, empty='Unknown'):
    return {'value': selected or '',
            'options': [('', empty),
                        (DG_METHOD_THINXXS_V1, 'ThinXXS v1/DG'),
                        (DG_METHOD_THINXXS_V2A, 'ThinXXS v2a/DG'),
                        (DG_METHOD_THINXXS_V2B, 'ThinXXS v2b/DG'),
                        (DG_METHOD_THINXXS_V2C, 'ThinXXS v2c/DG'),
                        (DG_METHOD_THINXXS_V2C_DIMPLED, 'ThinXXS v2c Dimpled'),
                        (DG_METHOD_WEIDMANN_V3, 'Weidmann v3/DG'),
                        (DG_METHOD_WEIDMANN_V5, 'Weidmann v5/DG'),
                        (DG_METHOD_HARVARD_BULK, 'Harvard Pump/Chip Shop'),
                        (DG_METHOD_MENSOR_BULK, 'Mensor Pump/Chip Shop'),
                        (DG_METHOD_SYRINGE_BULK, 'Syringe/Chip Shop'),
                        (DG_METHOD_OTHER, 'Other')]}

# TODO this could be made generic
def qlf1_lot_number_field(selected=None):
    # TODO LotNumber enum instead? (this is arbitrary)
    lot_q = Session.query(LotNumber).filter(LotNumber.type == LOT_NUMBER_TYPE_QLF11)
    qlf1 = lot_q.all()
    return {'value': selected if selected in [q.id for q in qlf1] else '',
            'options': [('','--')]+[(q.id, q.name) for q in qlf1]}

def qlf2_lot_number_field(selected=None):
    # TODO LotNumber enum instead? (this is arbitrary)
    lot_q = Session.query(LotNumber).filter(LotNumber.type == LOT_NUMBER_TYPE_QLF21)
    qlf2 = lot_q.all()
    return {'value': selected if selected in [q.id for q in qlf2] else '',
            'options': [('','--')]+[(q.id, q.name) for q in qlf2]}

def reagent_lot_number_field(selected=None):
    # TODO LotNumber enum instead? (this is arbitrary)
    lot_q = Session.query(LotNumber).filter(LotNumber.type == LOT_NUMBER_TYPE_REAGENT)
    lots = lot_q.all()
    return {'value': selected if selected in [lot.id for lot in lots] else '',
            'options': [('','--')]+[(lot.id, lot.name) for lot in lots]}

def oligo_lot_number_field(selected=None):
    # TODO LotNumber enum instead? (this is arbitrary)
    lot_q = Session.query(LotNumber).filter(LotNumber.type == LOT_NUMBER_TYPE_OLIGO)
    lots = lot_q.all()
    return {'value': selected if selected in [lot.id for lot in lots] else '',
            'options': [('','--')]+[(lot.id, lot.name) for lot in lots]}

def physical_plate_field(selected=None, empty='--'):
    pps = Session.query(PhysicalPlate).filter_by(active=True).all()
    return {'value': selected if (selected and selected.isdigit() and int(selected) in [pp.id for pp in pps]) else '',
            'options': [('',empty)]+[(pp.id, pp.name) for pp in pps]}

def sex_field(selected=None, empty='--'):
    return {'value': selected or '',
            'options': [('', empty),
                        ('M', 'Male'),
                        ('F', 'Female'),
                        ('?', 'Unknown')]}

def ethnicity_field(selected=None, empty='--'):
    return {'value': selected or '',
            'options': [('', empty),
                        ('ASW','ASW (African-American)'),
                        ('CEU','CEU (Caucasian)'),
                        ('CHB','CHB (Han Chinese)'),
                        ('CHD','CHD (Chinese-American)'),
                        ('GIH','GIH (Indian-American)'),
                        ('JPT','JPT (Japanese)'),
                        ('LWK','LWK (Kenyan)'),
                        ('MXL','MXL (Mexican-American)'),
                        ('MKK','MKK (Masai)'),
                        ('TSI','TSI (Italian)'),
                        ('YRI','YRI (Yoruban)'),
                        ('?','Unknown')]}

def field_get(method, key, if_missing='', empty=''):
    return dict(method(empty=empty)['options']).get(key, if_missing)

def checkbox_field(checked=False):
    return {'value': [u'0', u'1' if checked else u'0'],
            'options': [(u'1','')]}

def tertiary_field(selected=None, empty=''):
    return {'value': 'yes' if selected else ('' if selected is None else 'no'),
            'options': [('', empty),
                        ('yes', 'Yes'),
                        ('no', 'No')]}

def make_identity_field(vals, empty='', empty_enabled=True):
    # returns a closure
    def _field(selected=None, empty=empty):
        spec = {'value': selected if selected in vals else '',
                'options': [(val, val) for val in vals]}
        if empty_enabled:
            spec['options'].insert(0,('', empty))
        return spec
    
    return _field

def make_enum_field(vals, empty='', empty_enabled=True, start=0):
    # returns a closure
    def _field(selected=None, empty=empty):
        spec = {'value': unicode(selected) if selected in range(start,start+len(vals)) else '',
                'options': [(start+i, val) for i, val in enumerate(vals)]}
        if empty_enabled:
            spec['options'].insert(0,('', empty))
        return spec
    return _field

def comparable_metric_field():
    """
    Intended to be set in a bootstrap environment (no value/options)
    """
    from qtools.model import WellMetric, WellChannelMetric

    well_compares = []
    for col in WellMetric.__mapper__.columns:
        if col.info.get('comparable'):
            well_compares.append(('well.%s' % col.name, col.doc))

    for name, prop in class_properties(WellMetric):
        func = prop.fget
        info = getattr(func, 'info', dict())
        if info.get('comparable'):
            well_compares.append(('well.%s' % name, func.doc))

    well_channel_compares = []
    for col in WellChannelMetric.__mapper__.columns:
        if col.info.get('comparable'):
            well_channel_compares.append(('channel.%s' % col.name, col.doc))

    for name, prop in class_properties(WellChannelMetric):
        func = prop.fget
        info = getattr(func, 'info', dict())
        if info.get('comparable'):
            well_channel_compares.append(('channel.%s' % name, func.doc))

    well_compares = sorted(well_compares, key=operator.itemgetter(1))
    well_channel_compares = sorted(well_channel_compares, key=operator.itemgetter(1))
    return [('Well Metrics', well_compares),('Channel Metrics', well_channel_compares)]

def comparable_metric_display(value):
    metric_fields = comparable_metric_field()
    metric_dict = dict(itertools.chain.from_iterable([field for title, field in metric_fields]))
    return metric_dict.get(value, '?')

def validation_template_field():
    layouts = dict(plate_layouts)
    return {'value': '',
            'options': [('%s:%s:%s' % (template, layout, plate_type), desc) \
                          for template, name, layout, plate_type, desc \
                            in sorted(layouts.values(), key=operator.itemgetter(4)) if desc]}

dr_door_type_field = make_enum_field(('Original','Slotted'))
dr_installed_field = make_identity_field(('Installed','Not Installed'))
dr_sensor_field = make_identity_field(('OK','Needs Repair'))
