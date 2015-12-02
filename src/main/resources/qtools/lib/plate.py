"""
Plate-level operations, usually concerning naming and metrics.
"""

from qtools.model import Session, QLBPlate, Plate, Project, Person, Box2, PlateTemplate, PlateSetup, PlateType
from qtools.model.reagents import ValidationTestLayout, ProductValidationPlate, ProductValidationPlateLotTest, ProductPart, ProductLot
import simplejson as json
import formencode
from datetime import datetime
from collections import defaultdict

from sqlalchemy import and_

def make_plate_name(plate, experiment_name=None):
    """
    Given a plate and assigned project, operator
    and experiment, generate a name that conforms
    to the QTools naming standard.

    Name will be project_operator_experiment.

    :param plate:
    :param experiment_name:
    :return:
    """
    # this is the hard way, before the relation is saved.
    if plate.project_id:
        project = Session.query(Project).get(plate.project_id)
        if project:
            if project.code:
                project_code = project.code
            else:
                project_code = project.name
        else:
            project_code = ''
    else:
        project_code = ''
    
    operator = Session.query(Person).get(plate.operator_id)
    if operator:
        user_code = operator.name_code
    else:
        user_code = ''
    
    
    fields = [project_code, user_code, experiment_name]
    return '_'.join([field for field in fields if field])


def plate_from_qlp(qlbplate):
    """
    Given a QLBPlate, find out what information we can automatically determine
    from the file name and location.
    """
    dirname = qlbplate.file.dirname
    basename = qlbplate.file.basename
    complete_name = basename[:-4] # -- .qlp
    
    # assign box 2
    boxes = Session.query(Box2).all()
    
    # TODO: rename as to not contain timestamp?
    # TODO-- this is probably bad (assumes parent directory like Box 2 Alpha 03)
    plate_name = qlbplate.file.dirname.split('/')[-1]
    plate = Plate(name=plate_name, program_version=qlbplate.host_software,
                  run_time=datetime.strptime(qlbplate.host_datetime, '%Y:%m:%d %H:%M:%S') if qlbplate.host_datetime else None)
    for b in boxes:
        if qlbplate.file.dirname.startswith(b.src_dir):
            plate.box2 = b
    
    return plate

def get_product_validation_plate(qlplate, dbplate):
    """
    Determine whether or not the plate run was part of a product
    validation.  If so, return a ProductValidationPlate object
    (with tests attached).  This object will need to be committed
    and attached to the dbplate.
    """
    # check the name
    dirname = dbplate.qlbplate.file.dirname
    basename = dbplate.qlbplate.file.basename
    complete_name = basename[:-4] # qlp

    product_parts = Session.query(ProductPart).order_by('name desc').all()

    name_parts = complete_name.split('__')
    tests = []
    spec = None
    for part in product_parts:
        if name_parts[0] == part.name:
            relevant_specs = [spec for spec in part.specs if spec.name == name_parts[1]]
            if not relevant_specs:
                continue

            spec = part.spec_for_date(dbplate.run_time)

            # ok, now get the spec layout and figure out which
            # lot numbers are in which wells
            layout = spec.test_template.layout

            lot_positive_controls = defaultdict(list)
            lot_negative_controls = defaultdict(list)
            lot_positive_tests = defaultdict(list)
            lot_negative_tests = defaultdict(list)
            for well_name, well in sorted(qlplate.analyzed_wells.items()):
                sample_name, test, pos = ValidationTestLayout.get_sample_characteristics(well.sample_name)
                if not sample_name:
                    continue

                if test:
                    if pos:
                        lot_positive_tests[sample_name].append(well_name)
                    else:
                        lot_negative_tests[sample_name].append(well_name)
                else:
                    if pos:
                        lot_positive_controls[sample_name].append(well_name)
                    else:
                        lot_negative_controls[sample_name].append(well_name)


            for lot in part.lot_numbers:
                for coll, test_flag, well_flag in ((lot_positive_controls, ProductValidationPlateLotTest.TEST_TYPE_CONTROL, ProductValidationPlateLotTest.WELL_TYPE_POSITIVE),
                                                   (lot_negative_controls, ProductValidationPlateLotTest.TEST_TYPE_CONTROL, ProductValidationPlateLotTest.WELL_TYPE_NEGATIVE),
                                                   (lot_positive_tests, ProductValidationPlateLotTest.TEST_TYPE_TEST, ProductValidationPlateLotTest.WELL_TYPE_POSITIVE),
                                                   (lot_negative_tests, ProductValidationPlateLotTest.TEST_TYPE_TEST, ProductValidationPlateLotTest.WELL_TYPE_NEGATIVE)):
                    if lot.number in coll.keys():
                        well_str = ','.join(sorted(coll[lot.number]))
                        tests.append(ProductValidationPlateLotTest(lot_id = lot.id,
                                                                   wells = well_str,
                                                                   test_type = test_flag,
                                                                   well_type = well_flag))
            break

    if len(tests) == 0 or spec is None:
        return None
    else:
        pvp = ProductValidationPlate(spec_id = spec.id)
        for t in tests:
            pvp.lot_tests.append(t)

        return pvp

def apply_template_to_plate(qlplate, dbplate):
    """
    Determine if a plate has an applicable template, either by
    explicit setting or by implicit naming.

    :param qlplate: The QLP file to read
    :param dbplate: The DB plate to update
    """
    # new-style: if plate file has plate_template_id in it,
    # just bind
    if qlplate.plate_template_id:
        template = Session.query(PlateTemplate).get(int(qlplate.plate_template_id))
        if template:
            inherit_template_attributes(dbplate, template)
            return True
    
    # otherwise, check the name
    dirname = dbplate.qlbplate.file.dirname
    basename = dbplate.qlbplate.file.basename
    complete_name = basename[:-4] # -- .qlp

    # duplicate prefixes are possible; use most recent
    templates = Session.query(PlateTemplate).order_by('prefix desc, id desc').all()
    
    for template in templates:
        if complete_name.startswith(template.prefix):
            inherit_template_attributes(dbplate, template)
            return True
    
    return False

def apply_setup_to_plate(qlplate, dbplate):
    """
    Determine if a plate has an applicable template, either by
    explicit setting or by implicit naming.

    :param qlplate: The QLP file to read
    :param dbplate: The DB plate to update
    """
    if qlplate.plate_setup_id:
        setup = Session.query(PlateSetup).get(int(qlplate.plate_setup_id))
        if setup:
            inherit_setup_attributes(dbplate, setup)
            return True
    
    dirname = dbplate.qlbplate.file.dirname
    basename = dbplate.qlbplate.file.basename
    complete_name = basename[:-4] # -- .qlp

    setups = Session.query(PlateSetup).order_by('prefix desc').all()

    for setup in setups:
        if complete_name.startswith(setup.prefix):
            inherit_setup_attributes(dbplate, setup)
            return True
    
    return False
    
def inherit_template_attributes(plate, template):
    plate.project_id = template.project_id
    plate.operator_id = template.operator_id
    plate.dg_oil = template.dg_oil
    plate.dr_oil = template.dr_oil
    plate.master_mix = template.master_mix
    plate.fluidics_routine = template.fluidics_routine
    plate.droplet_generation_method = template.droplet_generation_method
    plate.droplet_maker_id = template.droplet_maker_id
    plate.plate_type_id = template.plate_type_id
    plate.physical_plate_id = template.physical_plate_id
    plate.dg_used_id = template.dg_used_id

def inherit_setup_attributes(plate, setup):
    plate.project_id = setup.project_id
    plate.operator_id = setup.author_id
    plate.dg_oil = setup.dg_oil
    plate.dr_oil = setup.dr_oil
    plate.master_mix = setup.master_mix
    plate.droplet_generation_method = setup.droplet_generation_method
    plate.droplet_maker_id = setup.droplet_maker_id
    plate.thermal_cycler = setup.thermal_cycler_id
    plate.plate_setup_id = setup.id
    plate.chemistry_type = setup.chemistry_type
    plate.skin_type = setup.skin_type
    plate.plate_type_id = setup.plate_type_id
    setup.locked = True

    # apply consumables (TODO: specify batch)
    # TODO: make this accessor on plate.setup
    # ACKKK HACK HACK HACK
    setup_tree = json.loads(setup.setup)
    if isinstance(setup_tree, dict):
        consumables = setup_tree.get('consumable', [])
        plate_layout = setup_tree.get('plate_layout', None)
    else:
        consumables = []
        plate_layout = None
    if plate_layout:
        if len(plate_layout) > 3:
            plate_type = Session.query(PlateType).filter_by(code=plate_layout[3]).first()
            if plate_type:
                plate.plate_type_id = plate_type.id

    validator = formencode.validators.DateConverter(not_empty=False, if_missing=None)

    wells = dict([(well.well_name, well) for well in plate.qlbplate.wells])

    if consumables:
        for cnum, c in enumerate(consumables):
            # hack
            if type(c) == type(dict()):
                cwells = c['wells']
                batch = c['batch'] or None
                try:
                    date = validator._to_python(c['date'], {})
                except Exception, e:
                    date = None
                temp = int(c['temp']) if c.get('temp', None) else None
                dg = int(c.get('dg', None) or setup.droplet_generator_id)
                run = int(c.get('dg_run')) if c.get('dg_run', None) else None
                vacuum_time = float(c.get('dg_vacuum_time')) if c.get('dg_vacuum_time', None) else None

            else:
                cwells = c
                batch = None
                date = None
                temp = None
                dg = setup.droplet_generator_id
                run = None
                vacuum_time = None

            for chnum, well in enumerate(cwells):
                # todo: retrofit batch number
                if wells.get(well, None):
                    wells[well].consumable_chip_num = cnum+1
                    wells[well].consumable_channel_num = chnum+1
                    wells[well].consumable_batch = batch
                    wells[well].consumable_batch_date = date
                    wells[well].consumable_batch_temp = temp
                    wells[well].droplet_generator_id = dg
                    wells[well].dg_run_number = run
                    wells[well].dg_vacuum_time = vacuum_time
    elif setup.droplet_generator_id:
        for name, w in wells.items():
            w.droplet_generator_id = setup.droplet_generator_id


