from qtools.constants.plate import *
from qtools.model import Session, PlateSetup, Project, Person, PlateType
from datetime import datetime, timedelta
import simplejson as json

consumable_layouts = {
	    'inverted': [['A01','B01','C01','D01','E01','F01','G01','H01'],
			['H02','G02','F02','E02','D02','C02','B02','A02'],
			['A03','B03','C03','D03','E03','F03','G03','H03'],
			['H04','G04','F04','E04','D04','C04','B04','A04'],
			['A05','B05','C05','D05','E05','F05','G05','H05'],
			['H06','G06','F06','E06','D06','C06','B06','A06'],
			['A07','B07','C07','D07','E07','F07','G07','H07'],
			['H08','G08','F08','E08','D08','C08','B08','A08'],
			['A09','B09','C09','D09','E09','F09','G09','H09'],
			['H10','G10','F10','E10','D10','C10','B10','A10'],
			['A11','B11','C11','D11','E11','F11','G11','H11'],
			['H12','G12','F12','E12','D12','C12','B12','A12']],
	   
		'standard': [['A01','B01','C01','D01','E01','F01','G01','H01'],
	        ['A02','B02','C02','D02','E02','F02','G02','H02'],
	        ['A03','B03','C03','D03','E03','F03','G03','H03'],
	        ['A04','B04','C04','D04','E04','F04','G04','H04'],
	        ['A05','B05','C05','D05','E05','F05','G05','H05'],
	        ['A06','B06','C06','D06','E06','F06','G06','H06'],
	        ['A07','B07','C07','D07','E07','F07','G07','H07'],
	        ['A08','B08','C08','D08','E08','F08','G08','H08'],
	        ['A09','B09','C09','D09','E09','F09','G09','H09'],
	        ['A10','B10','C10','D10','E10','F10','G10','H10'],
	        ['A11','B11','C11','D11','E11','F11','G11','H11'],
	        ['A12','B12','C12','D12','E12','F12','G12','H12']],
	    
	    'half': [['A01','B01','C01','D01','E01','F01','G01','H01'],
	        ['A02','B02','C02','D02','E02','F02','G02','H02'],
	        ['A03','B03','C03','D03','E03','F03','G03','H03'],
	        ['A04','B04','C04','D04','E04','F04','G04','H04'],
	        ['A05','B05','C05','D05','E05','F05','G05','H05'],
	        ['A06','B06','C06','D06','E06','F06','G06','H06']],
	    
	    'right': [['A07','B07','C07','D07','E07','F07','G07','H07'],
	        ['A08','B08','C08','D08','E08','F08','G08','H08'],
	        ['A09','B09','C09','D09','E09','F09','G09','H09'],
	        ['A10','B10','C10','D10','E10','F10','G10','H10'],
	        ['A11','B11','C11','D11','E11','F11','G11','H11'],
	        ['A12','B12','C12','D12','E12','F12','G12','H12']],
	    
	    'beta5A': [['A01','B01','C01','D01','A02','B02','C02','D02'],
	               ['A03','B03','C03','D03','A04','B04','C04','D04'],
	               ['A05','B05','C05','D05','A06','B06','C06','D06']],
	    
	    'beta5R': [['D01','C01','B01','A01','D02','C02','B02','A02'],
	               ['D03','C03','B03','A03','D04','C04','B04','A04'],
	               ['D05','C05','B05','A05','D06','C06','B06','A06']]
}

execution_orders = {
	'q1': ['Beta1','Beta2','Beta3','Beta4'],
	'q2': ['Beta2','Beta3','Beta4','Beta1'],
    'q3': ['Beta3','Beta4','Beta1','Beta2'],
    'q4': ['Beta4','Beta1','Beta2','Beta3'],
    'q5': ['Beta5','Beta6','Beta7','Beta8'],
    'q6': ['Beta6','Beta7','Beta8','Beta5'],
    'q7': ['Beta7','Beta8','Beta5','Beta6'],
    'q8': ['Beta8','Beta5','Beta6','Beta7'],
    'h1': ['Beta1','Beta2'],
    'h2': ['Beta2','Beta1'],
    'h3': ['Beta3','Beta4'],
    'h4': ['Beta4','Beta3'],
    'h5': ['Beta5','Beta6'],
    'h6': ['Beta6','Beta5'],
    'h7': ['Beta7','Beta8'],
    'h8': ['Beta8','Beta7'],
    'mb1': ['Beta3','Beta4','Beta8','Beta3'],
    'mb2': ['Beta4',"Beta8",'Beta3','Beta4'],
    'mb3': ['Beta8','Beta3','Beta4','Beta8'],
    'eb1': ['ENG002','','ENG003',''],
    'eb2': ['ENG003','','ENG002',''],
    'ebh1': ['ENG002','ENG003'],
    'ebh2': ['ENG003','ENG002'],
    '8e': ['ENG002','ENG003','ENG002','ENG003','ENG002','ENG003','ENG002','ENG003'],
    '8o': ['ENG003','ENG002','ENG003','ENG002','ENG003','ENG002','ENG003','ENG002']
}

# c = columns (4), h = halves, q = quartiles
# note: half on dye plate A-F... going to be filled later?
# follow-up to original note: yes
# these may have orthogonal consumable layouts (or these might be made to be orthogonal to consumable layouts)
# Note, %s in plate name if filled in by a letter code (A-...), and must match the rest of plate qlt file in qlts folder.
# format:
#     'plate name' : ('replacemnt name', "??dupliat type", "layout style", "plate type",( display name")
plate_layouts = {
    'DNA_load_undig': ('DNA_load_undig_%s.qlt', 'Duplex',  LAYOUT_STYLE_QUADRANT, 'dplex200', 'QV DNA load (undigested) Quadrant Plates'),
    'DNA_load_dig': ('DNA_load_dig_%s.qlt', 'Duplex',  LAYOUT_STYLE_QUADRANT, 'dplex200',     'QV DNA load (digested) Quadrant Plates'),
    'DNR_cDNA': ('DNR_cDNA_%s.qlt', 'DNR', LAYOUT_STYLE_HORIZHALF, 'dnr200', 'QV cDNA DNR Half Plates' ),
    'DNR_cDNA_duplex': ('DNR_cDNA_duplex_%s.qlt', 'Duplex', LAYOUT_STYLE_HORIZHALF, 'dplex200', 'QV duplex cDNA DNR Half Plates' ),
    'DNR_IL-1': ('DNR_IL-1_%s.qlt', 'DNR', LAYOUT_STYLE_HORIZHALF, 'dnr200', 'QV DNR IL-1 Half Plates'),
    'Duplex_HSV_B2M': ('Duplex_HSV_B2M_%s.qlt', 'Duplex', LAYOUT_STYLE_QUADRANT, 'dplex200', 'QV Duplex HSV B2M Quadrant Plates'),
    'BP_EG' : ('BP_EG_%s.qlt', 'Singleplex', LAYOUT_STYLE_VERTHALF, 'eg200', 'QV Evagreen Broad Panel'),
    'BP_TQ' : ('BP_TQ_%s.qlt', 'Singleplex', LAYOUT_STYLE_VERTHALF, 'tq200', 'QV TaqMan Broad Panel'),
    'CNV_myc': ('CNV_myc_%s.qlt', 'CNV', LAYOUT_STYLE_QUADRANT, 'cnv200', 'QV CNV myc Quadrent Plates'),
    'CNV_myc_EG': ('CNV_myc_EG_%s.qlt', 'CNV', LAYOUT_STYLE_VERTHALF, 'cnv200e', 'QV Evagreen CNV myc-hbb Half Plates'),
    'RED_GAPDH': ('RED_GAPDH_%s.qlt', 'RED', LAYOUT_STYLE_THIRD, 'bred', 'QV RED GAPDH Third Plates'),
    'RED_1cpd': ('RED_1cpd_%s.qlt', 'RED', LAYOUT_STYLE_QUADRANT, 'bred', 'QV RED 1cpd Quadrant Plates'),
    'RED_5cpd': ('RED_5cpd_%s.qlt', 'RED',  LAYOUT_STYLE_QUADRANT, 'bred', 'QV RED 5cpd Quadrant Plates'),
    'RSD_B2M': ('RSD_B2M_%s.qlt', 'RED', LAYOUT_STYLE_THIRD, 'bred', 'QV RSD B2M Third Plates'),
    'RSD_B2M_quarter_plates': ('RSD_B2M_quarter_plates_%s.qlt', 'RED', LAYOUT_STYLE_QUADRANT, 'bred', 'QV RSD B2M Quadrant PLates'),
    'Uniformity_FGFR2': ('Uniformity_FGFR2.qlt', 'Singleplex', LAYOUT_STYLE_WHOLEPLATE, 'bsplex', 'QV Uniformity FGFR2 Full Plate'),
    'sa_singleplex': ('sa_singleplex_%s.qlt', 'Singleplex', LAYOUT_STYLE_QUADRANT, 'bsplex', 'Singleplex Quadrant'), # will be uniform
    'sa_singleplex_A': ('sa_singleplex_A.qlt','Singleplex', LAYOUT_STYLE_SINGLE, 'bsplex', ''),
    'singleplex_full': ('singleplex.qlt', 'Singleplex', LAYOUT_STYLE_WHOLEPLATE, 'bsplex', 'Singleplex Full Plate'),
    'sa_duplex': ('sa_duplex_%s.qlt', 'Duplex', LAYOUT_STYLE_QUADRANT, 'bdplex', 'Duplex Quadrant'),
    'sa_duplex_A': ('sa_duplex_A.qlt', 'Duplex', LAYOUT_STYLE_SINGLE, 'bdplex', ''),
    'duplex_full': ('duplex.qlt', 'Duplex', LAYOUT_STYLE_WHOLEPLATE, 'bdplex', 'Duplex Full Plate'),
    'cnv_demo': ('cnv_demo_%s.qlt', 'CNV', LAYOUT_STYLE_CNV, 'bcnv', 'CNV Quadrant'),
    'cnv_demo_A': ('cnv_demo_A.qlt', 'CNV', LAYOUT_STYLE_SINGLE, 'bcnv', ''),
    'cnv_full': ('cnv.qlt', 'CNV', LAYOUT_STYLE_WHOLEPLATE, 'bcnv', 'CNV Full Plate'),
    'red_demo': ('red_demo_%s.qlt', 'RED', LAYOUT_STYLE_QUADRANT, 'bred', 'RED 1cpd Quadrant'),
    'red_demo_A': ('red_demo_A.qlt', 'RED', LAYOUT_STYLE_SINGLE, 'bred', ''),
    'red_demo5': ('red_demo5_%s.qlt', 'RED5cpd', LAYOUT_STYLE_QUADRANT, 'bred', 'RED 5cpd Quadrant'),
    'red_demo2': ('red_demo2_%s.qlt', 'RED2cpd', LAYOUT_STYLE_QUADRANT, 'bred', 'RED 2cpd Quadrant'),
    'red_full': ('red.qlt', 'RED', LAYOUT_STYLE_WHOLEPLATE, 'bred', 'RED Full Plate'),
    'fpfn': ('fpfn_%s.qlt', 'FPFN CO', LAYOUT_STYLE_QUADRANT, 'bfpfn', 'FP/FN/CO Quadrant'),
    'fpfn_A': ('fpfn_A.qlt', 'FPFN CO', LAYOUT_STYLE_SINGLE, 'bfpfn', ''),
    'fpfn_half': ('fpfnh_%s.qlt', 'FPFN', LAYOUT_STYLE_VERTHALF, 'bfpfn', 'FP/FN/CO Half Plate'),
    'fpfn_full': ('fpfn.qlt', 'FPFN CO', LAYOUT_STYLE_WHOLEPLATE, 'bfpfn', 'FP/FN/CO Full Plate'),
    'high_dnr': ('sa_singleplex_high_dnr_%s.qlt', 'HighDNR', LAYOUT_STYLE_QUADRANT, 'bdnr', 'HighDNR Quadrant'),
    'high_dnr_A': ('sa_singleplex_high_dnr_A.qlt', 'HighDNR', LAYOUT_STYLE_SINGLE, 'bdnr', ''),
    'dnr_full': ('dnr_full.qlt', 'HighDNR', LAYOUT_STYLE_WHOLEPLATE, 'bdnr', 'HighDNR Full Plate'),
    'dye': ('dye_%s.qlt', 'Dye', LAYOUT_STYLE_HORIZHALF, 'bdye', 'FAM/VIC Dye Half Plate'),
    'dye_5': ('dye_%s.qlt', 'Dye', LAYOUT_STYLE_HORIZHALF, 'bdye', ''),
    'hexdye': ('hexdye_%s.qlt', 'Dye', LAYOUT_STYLE_QUADRANT, 'bdye2', 'FAM/VIC/HEX Dye Quadrant'),
    'nohexdye': ('nohexdye_%s.qlt', 'Dye', LAYOUT_STYLE_QUADRANT, 'bdye2', ''),
    'events': ('event_%s.qlt', 'Events', LAYOUT_STYLE_VERTHALF, 'betaec', 'Event Count Half Plate'),
    'carryover': ('carryover_%s.qlt', 'Carryover', LAYOUT_STYLE_HORIZHALF, 'bcarry', ''),
    'carryover_full': ('carryover.qlt', 'Carryover', LAYOUT_STYLE_WHOLEPLATE, 'bcarry', ''),
    'mfg_carryover': ('carryover_%s.qlt', 'Carryover', LAYOUT_STYLE_HORIZHALF, 'mfgco', 'Carryover Half Plate'),
    'mfg_carryover_full': ('carryover.qlt', 'Carryover', LAYOUT_STYLE_WHOLEPLATE, 'mfgco', 'Carryover Full Plate'),
    'colorcomp': ('colorcomp_%s.qlt','ColorComp',LAYOUT_STYLE_COLORCOMP,'bcc', ''),
    'mfg_colorcomp': ('colorcomp_%s.qlt','ColorComp',LAYOUT_STYLE_COLORCOMP,'mfgcc', ''),
    'prod': ('carryover.qlt', 'ProdTest', LAYOUT_STYLE_SINGLE, 'bcarry', ''),
    'prodevents': ('events.qlt', 'Events', LAYOUT_STYLE_SINGLE, 'betaec', ''),
    'famvic_full': ('famvic_titration.qlt', 'FAM-VIC-Titration', LAYOUT_STYLE_WHOLEPLATE, 'fvtitr', ''),
    'singleplex_half': ('singleplex_half_%s.qlt', 'Singleplex', LAYOUT_STYLE_VERTHALF, 'bsplex', 'Singleplex Half Plate'),
    'duplex_half': ('duplex_half_%s.qlt', 'Duplex', LAYOUT_STYLE_VERTHALF, 'bdplex', 'Duplex Half Plate'),
    'cnv_half': ('cnv_half_%s.qlt', 'CNV', LAYOUT_STYLE_VERTHALF, 'bcnv', 'CNV Half Plate'),
    'red_half': ('red_half_%s.qlt', 'RED', LAYOUT_STYLE_VERTHALF, 'bred', 'RED 1cpd Half Plate'),
    'events_half': ('event_half_%s.qlt', 'Events', LAYOUT_STYLE_VERTHALF, 'betaec', 'Event Count Half Plate'),
    'fvbatch': ('fvbatch.qlt', 'FAM/VIC', LAYOUT_STYLE_SINGLE, 'fvtitr', 'FAM HI/VIC HI Plate'),
    'gfv': ('gfv.qlt', 'FAM/VIC', LAYOUT_STYLE_WHOLEPLATE, 'gfv', 'Groove FAM/VIC Titration'),
    '2x10': ('staph2x10.qlt', 'StaphDilution', LAYOUT_STYLE_WHOLEPLATE, '2x10', 'Groove Staph Titration'),
    'dgvol': ('dgvol.qlt','DGDropletVol', LAYOUT_STYLE_WHOLEPLATE, 'dgvol', 'Groove Droplet Volume'),
    'gcnv': ('gcnv_%s.qlt', 'CNV', LAYOUT_STYLE_VERTHALF, 'gcnv', 'Groove CNV'),
    'gdnr': ('gdnr.qlt', 'SingleplexDNR', LAYOUT_STYLE_WHOLEPLATE, 'gdnr', 'Groove Taq HighDNR'),
    'gload': ('gload.qlt', 'EGLoad', LAYOUT_STYLE_WHOLEPLATE, 'gload', 'Groove Taq Load'),
    'egdnr': ('egdnr.qlt', 'EGDNR', LAYOUT_STYLE_WHOLEPLATE, 'egdnr', 'Groove EvaGreen HighDNR'),
    'fam350': ('fam350.qlt', 'FAM350', LAYOUT_STYLE_WHOLEPLATE, 'fam350', 'Groove Dye Titration'),
    'fm350l': ('fm350l.qlt', 'FAM350Load', LAYOUT_STYLE_WHOLEPLATE, 'fm350l', 'Groove Dye Load'),
    'av': ('quadplate_%s.qlt','HamiltonPlate', LAYOUT_STYLE_QUADPLEX,'av', 'Auto QuadPlex'),
}

def progress(**kwargs):
	prog = dict(droplets_generated=False,
	            thermal_cycled=False,
	            num_readers=1,
	            reader_1=False,
	            reader_2=False,
	            reader_3=False,
	            reader_4=False,
	            reader_5=False,
	            reader_6=False,
	            reader_7=False,
	            reader_8=False)
	prog.update(kwargs)
	return prog

def get_beta_project():
	return Session.query(Project).filter_by(name='Beta Test').first()

def get_validation_project():
	return Session.query(Project).filter_by(name='Validation').first()

def make_setup_name(setup):
    # this is the hard way, before the relation is saved.
    if setup.project_id:
        project = Session.query(Project).get(setup.project_id)
        if project:
            if project.code:
                project_code = project.code
            else:
                project_code = project.name
        else:
            project_code = ''
    else:
        project_code = ''
    
    if setup.author_id:
    	author = Session.query(Person).get(setup.author_id)
        user_code = author.name_code
    else:
        user_code = ''

    fields = [project_code, user_code, setup.name]
    return '_'.join([field for field in fields if field])

def get_daily_plans(date, day_of_week_override=None):
	if day_of_week_override is None:
		day_of_week = date.weekday()
	else:
		day_of_week = day_of_week_override

	# TODO fix this
	plans = [# Monday
	         [dict(consumable='standard', plate_layout='sa_singleplex', execution_order='eb1', name='Singleplex'),
	          dict(consumable='standard', plate_layout='carryover', execution_order='eb2', name='FPFN'),
	          dict(consumable='standard', plate_layout='high_dnr', execution_order='eb1', name='HighDNR'),
	          dict(consumable='standard', plate_layout='hexdye', execution_order='eb2', name='Dye')],

			 # Tuesday
	         [dict(consumable='standard', plate_layout='sa_duplex', execution_order='eb2', name='Duplex'),
	          dict(consumable='standard', plate_layout='carryover', execution_order='eb1', name='FPFN'),
	          dict(consumable='standard', plate_layout='high_dnr', execution_order='eb2', name='HighDNR'),
	          dict(consumable='standard', plate_layout='hexdye', execution_order='eb1', name='Dye')],
	         
	         # Wednesday
	         [dict(consumable='standard', plate_layout='cnv_demo', execution_order='eb1', name='CNV'),
	          dict(consumable='standard', plate_layout='carryover', execution_order='eb2', name='FPFN'),
	          dict(consumable='standard', plate_layout='high_dnr', execution_order='eb1', name='HighDNR'),
	          dict(consumable='standard', plate_layout='hexdye', execution_order='eb2', name='Dye')],

	         # Thursday
	         [dict(consumable='standard', plate_layout='red_demo', execution_order='eb2', name='RED'),
	          dict(consumable='standard', plate_layout='red_demo5', execution_order='eb1', name='RED5cpd'),
	          dict(consumable='standard', plate_layout='carryover', execution_order='eb2', name='FPFN'),
	          dict(consumable='standard', plate_layout='high_dnr', execution_order='eb1', name='HighDNR'),
	          dict(consumable='standard', plate_layout='hexdye', execution_order='eb2', name='Dye')],

	         # Friday
	         [dict(consumable='standard', plate_layout='carryover', execution_order='eb1', name='FPFN'),
	          dict(consumable='standard', plate_layout='high_dnr', execution_order='eb2', name='HighDNR'),
	          dict(consumable='standard', plate_layout='hexdye', execution_order='eb1', name='Dye')]]
	
	return plans[day_of_week]


def weekdays_ahead_date(days):
	date = datetime.now()
	
	# figure out next weekday
	if date.weekday() in (5,6):
		date += timedelta(7-date.weekday(), 0, 0)
		days -= 1 # I think this is the right behavior
	
	for i in range(days):
		date += timedelta(1, 0, 0)
		if date.weekday() == 5:
			date += timedelta(2, 0, 0)
	
	return date

def make_default_setup(date, plan, project=None):
	if not project:
		project = get_validation_project()
	plan_name = plan.get('name', None) or plate_layouts[plan['plate_layout']][1]
	plate_setup = PlateSetup(project_id=project.id, name=plan_name)
	plate_setup.locked = False
	plate_setup.completed = False

	if type(plan['execution_order']) == type([]):
		execution_order = plan['execution_order']
	else:
		execution_order = execution_orders[plan['execution_order']]
	# TODO add status steps
	setup = dict(consumable=consumable_layouts[plan['consumable']],
	           	 execution_order=execution_order,
	           	 plate_layout=plate_layouts[plan['plate_layout']],
	           	 progress=progress(num_readers=len(execution_order)))
	
	plate_setup.time_updated = datetime.now()
	plate_setup.author_id = plan['operator'].id
	plate_setup.setup = json.dumps(setup)
	plate_setup.dr_oil = 22
	plate_setup.dg_oil = 14
	plate_setup.master_mix = 12
	plate_setup.droplet_generation_method = 201
	plate_setup.thermal_cycler_id = plan.get('thermal_cycler', None)
	plate_setup.prefix = make_setup_name(plate_setup)
	return plate_setup

# TODO set default dr oil, dg oil, master mix
def generate_production_setups(dr, operator, weekdays_ahead=0, day_of_week_override=None):
	date_str = weekdays_ahead_date(weekdays_ahead).strftime('%m-%d')
	project = get_validation_project()

	carryover_plate_setup = PlateSetup(project_id=project.id,
	                                   name="%s_Carryover%s" % (date_str, dr.code[1:]),
	                                   locked=False,
	                                   completed=False,
	                                   time_updated=datetime.now(),
	                                   author_id=operator.id,
	                                   dr_oil=22,
	                                   dg_oil=14,
	                                   master_mix=12,
	                                   droplet_generation_method=201)
	carryover_plate_setup.setup = json.dumps(
		dict(consumable=consumable_layouts['standard'],
	         plate_layout=plate_layouts['prod'],
	         execution_order=[dr.name],
	         progress=progress(num_readers=1))
	)
	carryover_plate_setup.prefix = make_setup_name(carryover_plate_setup)

	colorcomp_plate_setup = PlateSetup(project_id=project.id,
	                                   name="%s_ColorComp%s" % (date_str, dr.code[1:]),
	                                   locked=False,
	                                   completed=False,
	                                   time_updated=datetime.now(),
	                                   author_id=operator.id,
	                                   dr_oil=22,
	                                   dg_oil=14,
	                                   master_mix=12,
	                                   droplet_generation_method=201)
	colorcomp_plate_setup.setup = json.dumps(
		dict(consumable=consumable_layouts['half'],
	         plate_layout=plate_layouts['colorcomp'],
	         execution_order=[dr.name, dr.name, dr.name, dr.name, dr.name, dr.name, dr.name, dr.name],
	         progress=progress(num_readers=8))
	)
	colorcomp_plate_setup.prefix = make_setup_name(colorcomp_plate_setup)
	return carryover_plate_setup, colorcomp_plate_setup
	




def generate_daily_setups(weekdays_ahead=1, day_of_week_override=None):
	date = weekdays_ahead_date(weekdays_ahead)
	plans = get_daily_plans(date, day_of_week_override=day_of_week_override)

	setups = []
	for plan in plans:
		setups.append(make_default_setup(date, plan))
	
	return setups

# TODO: replace with regex
def generate_custom_setup(*args):
	print len(args)
	name = args[0]
	consumable = args[1]
	plate_layout = args[2]
	username = args[3]
	project_name = args[4]
	execution_order = []
	idx = 5

	operator = Session.query(Person).filter_by(name_code=username).first()
	project = Session.query(Project).filter_by(code=project_name).first()
	if not operator:
		raise ValueError, "No known user: %s" % username
	if not project:
		raise ValueError, "No known project: %s" % project_name
	
	prefix_map = {'b': 'Beta ',
	              'e': 'ENG00',
	              'p': 'Pilot 100',
	              'c': 'RevC Alpha 0',
	              'd': 'RevC Beta 0'}

	# THIS IS SLIGHTLY LESS TERRIBLE CODE NOW
	for x in range(5,13):
		section_name = chr(ord('a')+(x-5))
		print section_name
		if args[x].startswith(section_name):
			prefix = args[x][1]
			machine_name = prefix_map[prefix]
			execution_order.append('%s%s' % (machine_name, args[x][2:]) if args[x][2:] != '0' else '')
			idx = idx + 1
		else:
			break
	
	date = weekdays_ahead_date(int(args[idx]))
	plan = dict(consumable=consumable, plate_layout=plate_layout, execution_order=execution_order, name=name, operator=operator)
	setup = make_default_setup(date, plan, project=project)
	return setup

