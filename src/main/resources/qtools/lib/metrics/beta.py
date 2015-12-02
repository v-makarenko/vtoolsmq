"""
Compute metrics and populates well metric and well
channel metric objects with information specific to
beta plate types, such as:

* Singleplex
* Duplex
* CNV
* RED
* Carryover

These metrics functions rely on standard plate layouts with
pre-agreed sample and target names.
"""
from qtools.lib.metrics import *
from qtools.lib.metrics.colorcal import SINGLEWELL_COLORCOMP_CALC, SINGLEWELL_CHANNEL_COLORCOMP_CALC
from qtools.lib.metrics.mixedplate import MIXED_PLATE_TYPE_CODES, compute_metric_foreach_mixed_qlwell, compute_metric_foreach_mixed_qlwell_channel
from collections import defaultdict


## qx200 stuff
dnr200_conc_dict = { 'NTC':(0,None),
                     '0.005 cpd': (5,None),
                     '0.010 cpd': (10,None),
                     '0.020 cpd': (20,None),
                     '0.039 cpd': (39,None),
                     '0.078 cpd': (78,None),
                     '0.156 cpd': (156,None),
                     '0.313 cpd': (313,None),
                     '0.625 cpd': (625,None),
                     '1.25 cpd': (1250,None),
                     '2.5 cpd': (2500,None),
                     '5 cpd': (5000,None)}


dplex200_conc_dict = { 'NTC/1cpd Ch2':(0,1000),
                        '0.125 cpd Ch1/1cpd Ch2':(125,1000),
                        '0.25 cpd Ch1/1cpd Ch2':(250, 1000),
                        '0.5 cpd Ch1/1cpd Ch2':(500, 1000),
                        '1 cpd Ch1/1cpd Ch2':(1000, 1000),
                        '2 cpd Ch1/1cpd Ch2':(2000, 1000)}

eg200_conc_dict = { 'NTC':(0,None), ##should this be 0 or none?
                    '0.5':(500,None)}

tq200_conc_dict = { 'NTC Ch1':(0,None),
                    'NTC Ch2':(None,0),
                    '0.5 Ch1':(500,None),
                    '0.5 Ch2':(None,500) }

# for the Beta test
singleplex_conc_dict = {'SA singleplex 1.0': (1000, None),
                        '0.5cpd':(500,None)}
duplex_conc_dict = {'NTC': (0, 1000),
					'S.a. 0.125': (125, 1000),
					'S.a. 0.25': (250, 1000),
					'S.a. 0.5': (500, 1000),
					'S.a. 1.02': (1020, 1000),
					'S.a. 2.0': (2000, 1000)}

staph2x10_conc_dict = {'S.a. NTC': (0, None),
	                   'S.a. NTC ': (0, None),
	                   'NTC': (0, None),
	                   'S.a. 0.008': (8, None),
	                   'S.a. 0.0016': (16, None), # TODO remove
	                   'S.a. 0.0156': (16, None),
	                   'S.a. 0.0031': (31, None), # TODO remove
	                   'S.a. 0.0312': (31, None),
	                   'S.a. 0.0063': (62, None), # TODO remove
	                   'S.a. 0.0625': (62, None),
	                   'S.a. 0.125': (125, None),
	                   'S.a. 0.25': (250, None),
	                   'S.a. 0.250': (250, None), # TODO remove
	                   'S.a. 0.5': (500, None),
	                   'S.a. 1.0': (1000, None),
	                   'S.a. 2.0': (2000, None),
	                   'S.a. 4.0': (4000, None),
	                   'S.a. 4.00': (4000, None),
	                   'S.a. 8.0': (8000, None)}

gdnr_conc_dict = {'S.a. NTC': (0, 0), # TODO remove
	              'S.a. NTC ': (0, 0), # TODO remove
	              'NTC': (0, 0),
	              'S.a. 0.008': (8, 8),
	              'S.a. 0.0016': (16, 16), # TODO remove
	              'S.a. 0.0156': (16, 16),
	              'S.a. 0.0031': (31, 31), # TODO remove
	              'S.a. 0.0312': (31, 31),
	              'S.a. 0.0063': (62, 62), # TODO remove
	              'S.a. 0.0625': (62, 62),
	              'S.a. 0.125': (125, 125),
	              'S.a. 0.25': (250, 250),
	              'S.a. 0.250': (250, 250), # TODO remove
	              'S.a. 0.5': (500, 500),
	              'S.a. 1.0': (1000, 1000),
	              'S.a. 2.0': (2000, 2000),
	              'S.a. 4.0': (4000, 4000),
	              'S.a. 4.00': (4000, 4000),
	              'S.a. 8.0': (8000, 8000)}

egdnr_conc_dict = {'NTC': (0, 0),
                   'RNaseP 0.004': (4, 4),
                   'RNaseP 0.008': (8, 8),
                   'RNaseP 0.016': (16, 16),
                   'RNaseP 0.032': (32, 32),
                   'RNaseP 0.0625': (63, 63),
                   'RNaseP 0.125': (125, 125),
                   'RNaseP 0.25': (250, 250),
                   'RNaseP 0.5': (500, 500),
                   'RNaseP 1.0': (1000, 0),
                   'RNaseP 2.0': (2000, 0),
                   'RNaseP 4.0': (4000, 0)}

#qx200_plate_types = ('dnr200','dplex200);

beta_plate_types = ('dnr200','dplex200', 'eg200', 'tq200', 'cnv200', 'cnv200e', 'av','bsplex','bdplex','bred','bdnr','bcarry','bdye2','bcnv','bfpfn','bdye','betaec','bcc','mfgco','mfgcc','gcnv','2x10','gdnr','fam350','egdnr','fm350l','scc','probeec','evaec')

# TODO: do we want to measure deviation of mutant?
# I think we can reuse this for red200...
red_conc_dict = {'NTC': (0, 0),
				 '0% Mutant, 1cpd WT': (0, None),
				 '0.01% Mutant, 1cpd WT': (0.1, None),
				 '0.05% Mutant, 1cpd WT': (0.5, None),
				 '0.1% Mutant, 1cpd WT': (1, None),
				 '0.5% Mutant, 1cpd WT': (5, None),
				 '1% Mutant, 1cpd WT': (10, None),
				 '0.01cpd Mutant, 0 WT': (10, None),
				 '0% Mutant, 2cpd WT': (0, None),
				 '0.01% Mutant, 2cpd WT': (0.2, None),
				 '0.05% Mutant, 2cpd WT': (1, None),
				 '0.1% Mutant, 2cpd WT': (2, None),
				 '0.5% Mutant, 2cpd WT': (10, None),
				 '1% Mutant, 2cpd WT': (20, None),
				 '0.02cpd Mutant, 0 WT': (20, None),
				 '0% Mutant, 2.5cpd WT': (0, None),
				 '0% Mutant, 2.5 cpd WT': (0, None),
				 '0.01% Mutant, 2.5cpd WT': (0.25, None),
				 '0.05% Mutant, 2.5cpd WT': (1.25, None),
				 '0.1% Mutant, 2.5cpd WT': (2.5, None),
				 '0.5% Mutant, 2.5cpd WT': (12.5, None),
				 '1% Mutant, 2.5cpd WT': (25, None),
				 '0.025 cpd Mutant, 0 WT': (25, None),
				 '0.025cpd Mutant, 0 WT': (25, None),
				 '0% Mutant, 5cpd WT': (0, None),
				 '0.01% Mutant, 5cpd WT': (0.5, None),
				 '0.05% Mutant, 5cpd WT': (2.5, None),
                 '0.2% Mutant, 5cpd WT': (10, None),
                 '0.02% Mutant, 5cpd WT': (1, None),
                 '0.002% Mutant, 5cpd WT': (.1, None),
				 '0.1% Mutant, 5cpd WT': (5, None),
				 '0.5% Mutant, 5cpd WT': (25, None),
				 '1% Mutant, 5cpd WT': (50, None),
				 '0.05cpd Mutant, 0 WT': (50, None)}

highdnr_conc_dict = {'Stealth': (None, None),
					 'SA DNR 0.001': (1, None),
					 'SA DNR 0.01': (10, None),
					 'SA DNR 0.1': (100, None),
					 'SA DNR 1.0': (1000, None),
					 'SA DNR 5': (5000, None)}

carryover_conc_dict = {'S.a. 1.5cpd': (1500, None),
                       'S.a. 1cpd': (1000, None),
                       'Staph': (1000, None),
                       'staph': (1000, None),
                       'stealth': (None, None),
                       'Stealth': (None, None)}

# not implimented now, need to get conc from claudia
cnv200_conc_dict = { 'NTC':  (None,None),
                   'CN1':  (None,None),
                   'CN2':  (None,None),
                   'CN3':  (None,None),
                   'CN4':  (None,None),
                   'CN5':  (None,None),
                   'CN6':  (None,None),
                   'CN11': (None,None),
                   'CN13': (None,None)}


cnv_cnv_dict = {'NA11994 CN1': 1,
				'NTC': None,
				'NA18507 CN2': 2,
				'NA19108 CN2': 2,
				'NA18502 CN3': 3,
				'NA18916 CN6': 6,
				'NA19221 CN4': 4,
				'NA19205 CN5': 5}

#plate well defs for qx200 validation
cnv200_dict = { 'NTC':  None,
                'CN1':  1,
                'CN2':  2,
                'CN3':  3,
                'CN4':  4,
                'CN5':  5,
                'CN6':  6,
                'CN11': 11,
                'CN13': 13,
                ' CN1':  1,
                ' CN2':  2,
                ' CN3':  3,
                ' CN4':  4,
                ' CN5':  5,
                ' CN6':  6,
                ' CN11': 11,
                ' CN13': 13}


## This dicts indicate wheather a signal is to be measured or not
## add well deffs to override default (fam/hex)
# qx200 settings
dnr200_nothreshold_dict = { 'NTC':(False,False),
                            '0.005 cpd':(False,False),
                            '0.010 cpd':(True,False),
                            '0.020 cpd':(True,False),
                            '0.039 cpd':(True,False),
                            '0.078 cpd':(True,False),
                            '0.156 cpd':(True,False),
                            '0.313 cpd':(True,False),
                            '0.625 cpd':(True,False),
                            '1.25 cpd':(True,False),
                            '2.5 cpd':(True,False),
                            '5 cpd':(True,False)}

dplex200_nothreshold_dict = {'NTC/1cpd Ch2': (False, True)}

eg200_nothreshold_dict = {  'NTC':(False,False),
                            '0.5':(True,False) }

tq200_nothreshold_dict = {  'NTC Ch1':(False,False),
                            'NTC Ch2':(False,False),
                            '0.5 Ch1':(True,False),
                            '0.5 Ch2':(False,True) }

# existing
singleplex_nothreshold_dict = {'SA singleplex 1.0': (True, False),
                               '0.5cpd': (True, False)}

duplex_nothreshold_dict = {'NTC': (False, True)}

gdnr_nothreshold_dict = {'S.a. NTC': (False, False),
                         'S.a. NTC ': (False, False),
	            		 'NTC': (False, False)}

egdnr_nothreshold_dict = {'NTC': (False, False),
                          'RNaseP 1.0': (True, False),
                          'RNaseP 2.0': (True, False),
                          'RNaseP 4.0': (True, False)}

staph2x10_nothreshold_dict = {'S.a. NTC': (False, False),
	            		      'S.a. NTC ': (False, False),
	            		      'NTC': (False, False),
	            		      'S.a. 0.008': (True, False),
	                          'S.a. 0.0016': (True, False), # TODO remove
	                          'S.a. 0.0156': (True, False),
	                          'S.a. 0.0031': (True, False), # TODO remove
	                          'S.a. 0.0312': (True, False),
	                          'S.a. 0.0063': (True, False), # TODO remove
	                          'S.a. 0.0625': (True, False),
	                          'S.a. 0.125': (True, False),
	                          'S.a. 0.25': (True, False),
	                          'S.a. 0.250': (True, False), # TODO remove
	                          'S.a. 0.5': (True, False),
	                          'S.a. 1.0': (True, False),
	                          'S.a. 2.0': (True, False),
	                          'S.a. 4.0': (True, False),
	                          'S.a. 4.00': (True, False),
	                          'S.a. 8.0': (True, False)}

carryover_nothreshold_dict = {'S.a. 1.5cpd': (True, False),
                              'S.a. 1cpd': (True, False),
                              'Staph': (True, False),
                              'staph': (True, False),
                              'stealth': (False, False),
                              'Stealth': (False, False)}

cnv_nothreshold_dict = {'NTC': (False, False)}

red_nothreshold_dict = {'NTC': (False, False),
				 '0% Mutant, 1cpd WT': (False, False),
				 '0.01% Mutant, 1cpd WT': (False, False), # check on this
				 '0.05% Mutant, 1cpd WT': (False, False), # check on this
				 '0.1% Mutant, 1cpd WT': (True, False),
				 '0.5% Mutant, 1cpd WT': (True, False),
				 '1% Mutant, 1cpd WT': (True, False),
				 '0.01cpd Mutant, 0 WT': (True, True),
				 '0% Mutant, 2cpd WT': (False, False),
				 '0.01% Mutant, 2cpd WT': (False, False), # check on this
				 '0.05% Mutant, 2cpd WT': (True, False),
				 '0.1% Mutant, 2cpd WT': (True, False),
				 '0.5% Mutant, 2cpd WT': (True, False),
				 '1% Mutant, 2cpd WT': (True, False),
				 '0.02cpd Mutant, 0 WT': (True, True),
				 '0% Mutant, 2.5cpd WT': (False, False),
				 '0% Mutant, 2.5 cpd WT': (False, False),
				 '0.01% Mutant, 2.5cpd WT': (False, False), # check on this
				 '0.05% Mutant, 2.5cpd WT': (True, False),
				 '0.1% Mutant, 2.5cpd WT': (True, False),
				 '0.5% Mutant, 2.5cpd WT': (True, False),
				 '1% Mutant, 2.5cpd WT': (True, False),
				 '0.025 cpd Mutant, 0 WT': (True, True),
				 '0.025cpd Mutant, 0 WT': (True, True),
				 '0.01% Mutant, 5cpd WT': (False, False), # check on this (and 5cpd VIC)
                 '0% Mutant, 5cpd WT': (False,False),
                 '0.05% Mutant, 5cpd WT': (True, False),
                 '0.2% Mutant, 5cpd WT': (True, False),
                 '0.02% Mutant, 5cpd WT': (True, False),
                 '0.002% Mutant, 5cpd WT': (True, False),
                 '0.1% Mutant, 5cpd WT': (True, False),
                 '0.5% Mutant, 5cpd WT': (True, False),
                 '1% Mutant, 5cpd WT': (True, False),
				 '0.05cpd Mutant, 0 WT': (True, True)}
 
fpfn_nothreshold_dict = {'NTC': (False, False),
						 'NA19205 7.5ng/uL undigested': (False, True),
						 'NA19205 3.3ng/uL undigested': (False, True),
						 'NA19205 50ng/uL digested': (False, False)}

dnr_nothreshold_dict = {'Stealth': (False, False),
						'SA DNR 0.001': (True, False),
						'SA DNR 0.01': (True, False),
						'SA DNR 0.1': (True, False),
						'SA DNR 1.0': (True, False),
						'SA DNR 5': (True, False)}

 # dye, event count just assume false

# TODO fill these in
fpfn_positive_wells = ('A02','A03','B01','A08','A09','B07','E02','E03','F01','E08','E09','F07')
fpfn_negative_wells = ('A01','B03','B06','A07','B09','B12','E01','F03','F06','E07','F09','F12')
fpfn_fp_measurement_wells = ('B03','B06','B09','B12','F03','F06','F09','F12')
fpfn_fn_measurement_wells = ('A03','A09','E03','E09')
red_threshold_wells = ('D01','D02','D03','D07','D08','D09','H01','H02','H03','H07','H08','H09')
red_fp_measurement_wells = ('A04','A05','A06','A10','A11','A12','E04','E05','E06','E10','E11','E12')

# going to key based off of plate type code-- may be a better way but these are standard
estimated_conc_funcs = {'bsplex': ExpectedConcentrationCalculator(
									well_channel_sample_name_lookup(singleplex_conc_dict)),
						'bdplex': ExpectedConcentrationCalculator(
									well_channel_sample_name_lookup(duplex_conc_dict)),
						'bred': ExpectedConcentrationCalculator(
									well_channel_sample_name_lookup(red_conc_dict)),
						'bdnr': ExpectedConcentrationCalculator(
									well_channel_sample_name_lookup(highdnr_conc_dict)),
						'bcarry': ExpectedConcentrationCalculator(
									well_channel_sample_name_lookup(carryover_conc_dict)),
						'mfgco': ExpectedConcentrationCalculator(
									well_channel_sample_name_lookup(carryover_conc_dict)),
						'2x10': ExpectedConcentrationCalculator(
									well_channel_sample_name_lookup(staph2x10_conc_dict)),
						'gdnr': ExpectedConcentrationCalculator(
									well_channel_sample_name_lookup(gdnr_conc_dict)),
						'egdnr': ExpectedConcentrationCalculator(
									well_channel_sample_name_lookup(egdnr_conc_dict)),
                        'dnr200': ExpectedConcentrationCalculator(
                                    well_channel_sample_name_lookup(dnr200_conc_dict)),
                        'dplex200': ExpectedConcentrationCalculator(
                                    well_channel_sample_name_lookup(dplex200_conc_dict)),
                        'eg200': ExpectedConcentrationCalculator(
                                    well_channel_sample_name_lookup(eg200_conc_dict)),
                        'tq200': ExpectedConcentrationCalculator(
                                    well_channel_sample_name_lookup(tq200_conc_dict)) }
                        

estimated_cnv_funcs = {'bcnv': ExpectedCNVCalculator(0,1,
								 well_sample_name_lookup(cnv_cnv_dict)),
                       'gcnv': ExpectedCNVCalculator(0,1,
								 well_sample_name_lookup(cnv_cnv_dict)),
                       'cnv200': ExpectedCNVCalculator(0,1,
                                 well_sample_name_lookup(cnv200_dict))}

false_positive_funcs = {'bfpfn': NTCSaturatedFalsePositiveCalculator(fpfn_positive_wells,
																	 fpfn_negative_wells,
																	 fpfn_fp_measurement_wells,
																	 (1,)),
						'bred': AverageSampleThresholdFalsePositiveCalculator(['1% Mutant, 1cpd WT','0.2% Mutant, 5cpd WT'],
																	   ['0% Mutant, 1cpd WT', '0% Mutant, 5cpd WT'],
																	   (0,)),
						'av': AverageSampleThresholdFalsePositiveCalculator(['1% Mutant, 1cpd WT'],
																	        ['0% Mutant, 1cpd WT'],
																	        (0,))}

false_negative_funcs = {'bfpfn': NTCSaturatedFalseNegativeCalculator(fpfn_positive_wells,
																	 fpfn_negative_wells,
																	 fpfn_fn_measurement_wells,
																	 (1,))}

expected_threshold_funcs = {'bsplex': ExpectedThresholdCalculator(
										well_channel_sample_name_lookup(singleplex_nothreshold_dict, default=True)),
							'bdplex': ExpectedThresholdCalculator(
										well_channel_sample_name_lookup(duplex_nothreshold_dict, default=True)),
							'2x10': ExpectedThresholdCalculator(
										well_channel_sample_name_lookup(staph2x10_nothreshold_dict, default=True)),
							'gdnr': ExpectedThresholdCalculator(
										well_channel_sample_name_lookup(gdnr_nothreshold_dict, default=True)),
							'egdnr': ExpectedThresholdCalculator(
										well_channel_sample_name_lookup(egdnr_nothreshold_dict, default=True)),
							'bcnv': ExpectedThresholdCalculator(
										well_channel_sample_name_lookup(cnv_nothreshold_dict, default=True)),
							'gcnv': ExpectedThresholdCalculator(
										well_channel_sample_name_lookup(cnv_nothreshold_dict, default=True)),
                            'cnv200': ExpectedThresholdCalculator(
                                        well_channel_sample_name_lookup(cnv_nothreshold_dict, default=True)),
                            'cnv200e': ExpectedThresholdCalculator(
                                        well_channel_sample_name_lookup(cnv_nothreshold_dict, default=True)),
							'bred': ExpectedThresholdCalculator(
										well_channel_sample_name_lookup(red_nothreshold_dict, default=True)),
							'bfpfn': ExpectedThresholdCalculator(
										well_channel_sample_name_lookup(fpfn_nothreshold_dict, default=True)),
							'bdnr': ExpectedThresholdCalculator(
										well_channel_sample_name_lookup(dnr_nothreshold_dict, default=True)),
							'bdye':   ExpectedThresholdCalculator(lambda well, channel: False),
							'bdye2':  ExpectedThresholdCalculator(lambda well, channel: False),
							'fam350': ExpectedThresholdCalculator(lambda well, channel: False),
							'fm350l': ExpectedThresholdCalculator(lambda well, channel: False),
							'betaec': ExpectedThresholdCalculator(lambda well, channel: False),
                            'probeec': ExpectedThresholdCalculator(lambda well, channel: False),
                            'evaec': ExpectedThresholdCalculator(lambda well, channel: False),
							'bcarry': CarryoverThresholdCalculator(),
							'mfgco':  CarryoverThresholdCalculator(),
							'bcc': ExpectedThresholdCalculator(lambda well, channel: False),
							'mfgcc': ExpectedThresholdCalculator(lambda well, channel: False),
                            'dnr200':ExpectedThresholdCalculator(
                                        well_channel_sample_name_lookup(dnr200_nothreshold_dict, default=True)),
                            'dplex200': ExpectedThresholdCalculator(
                                        well_channel_sample_name_lookup(dplex200_nothreshold_dict, default=True)),
                            'eg200':ExpectedThresholdCalculator(
                                        well_channel_sample_name_lookup(eg200_nothreshold_dict, default=True)),
                            'tq200': ExpectedThresholdCalculator(
                                        well_channel_sample_name_lookup(tq200_nothreshold_dict, default=True))}


class BlankLinkageCalculator(NullLinkageCalculator):
	def compute(self, qlwell, well_metric):
		well_metric.null_linkage = None

null_linkage_funcs = defaultdict(lambda: BlankLinkageCalculator(),
								 {'bdplex': NullLinkageCalculator(),
								  '2x10': NullLinkageCalculator(),
								  'bcnv': NullLinkageCalculator(),
								  'gcnv': NullLinkageCalculator(),
                                  'cnv200': NullLinkageCalculator()})

air_droplet_funcs = defaultdict(lambda: NOOP_WELL_METRIC_CALCULATOR,
                                {'bsplex': AirDropletsCalculator(('SA singleplex 1.0','0.5cpd'), 0),
                                 'betaec': AirDropletsCalculator(('Dye',), 1),
                                 'bcarry': AirDropletsCalculator(('S.a. 1cpd', 'staph', 'Staph'), 0),
                                 'mfgco': AirDropletsCalculator(('S.a. 1cpd', 'staph', 'Staph'), 0)})


class ColorCompPolydispersityCalculator(PolydispersityCalculator):
	"""
	Only compute for FAM HI/VIC HI
	"""
	def compute(self, qlwell, qlwell_channel, well_channel_metric):
		if (qlwell.sample_name in ('FAM 350nM', 'FAM HI') and qlwell_channel.channel_num == 0) or \
		   (qlwell.sample_name in ('VIC 350nM', 'VIC HI') and qlwell_channel.channel_num == 1):
			return super(ColorCompPolydispersityCalculator, self).compute(qlwell, qlwell_channel, well_channel_metric)
		else:
			well_channel_metric.polydispersity = None
		return well_channel_metric

polyd_funcs = defaultdict(lambda: NOOP_WELL_CHANNEL_METRIC_CALCULATOR,
                          {'betaec': DEFAULT_POLYD_CALC,
                           'probeec': DEFAULT_POLYD_CALC,
                           'evaec': DEFAULT_POLYD_CALC,
                           'bcarry': DEFAULT_POLYD_CALC,
                           'mfgco': DEFAULT_POLYD_CALC,
                           'bsplex': DEFAULT_POLYD_CALC,
                           '2x10': DEFAULT_POLYD_CALC,
                           'gdnr': DEFAULT_POLYD_CALC,
                           'bdplex': DEFAULT_POLYD_CALC,
                           'bcnv': DEFAULT_POLYD_CALC,
                           'gcnv': DEFAULT_POLYD_CALC,
                           'cnv200': DEFAULT_POLYD_CALC,
                           'bcc': ColorCompPolydispersityCalculator(),
                           'mfgcc': ColorCompPolydispersityCalculator()})

class ColorCompExtraclusterCalculator(ExtraclusterCalculator):
	"""
	Compute for FAM HI on FAM, FAM LO on FAM, VIC HI on VIC, VIC LO on VIC
	"""
	def compute(self, qlwell, qlwell_channel, well_channel_metric):
		if (qlwell.sample_name in ('FAM HI', 'FAM 350nM', 'FAM LO', 'FAM 40nM') and qlwell_channel.channel_num == 0) or \
		   (qlwell.sample_name in ('VIC HI', 'VIC 350nM', 'VIC LO', 'VIC 70nM') and qlwell_channel.channel_num == 1):
		    return super(ColorCompExtraclusterCalculator, self).compute(qlwell, qlwell_channel, well_channel_metric)
		return well_channel_metric

extrac_funcs = defaultdict(lambda: NOOP_WELL_CHANNEL_METRIC_CALCULATOR,
                           {'betaec': DEFAULT_EXTRAC_CALC,
                            'bcc': ColorCompExtraclusterCalculator(),
                            'mfgcc': ColorCompExtraclusterCalculator()})

class ColorCompGapRainCalculator(DyeGapRainMetricCalculator):
	"""
	Only compute air
	"""
	def compute(self, qlwell, qlwell_channel, well_channel_metric):
		from qtools.lib.nstats.peaks import gap_rain
		from pyqlb.nstats.peaks import cluster_1d
		if ((qlwell.sample_name in ('FAM 350nM', 'FAM 40nM', 'FAM HI', 'FAM LO') and qlwell_channel.channel_num == 0) or \
		    (qlwell.sample_name in ('VIC 350nM', 'VIC 70nM', 'VIC HI', 'VIC LO') and qlwell_channel.channel_num == 1)):
		    # also stipulate that amplitudes have to be under 1000

		    drops = gap_rain(qlwell, channel_num=qlwell_channel.channel_num, threshold=0)
		    rain, air = cluster_1d(drops, qlwell_channel.channel_num, 1000)
		    well_channel_metric.gap_rain_droplets = len(air)
		return well_channel_metric

class EventsGapRainCalculator(DyeGapRainMetricCalculator):
	"""
	compute willy nilly
	"""
	pass

gap_rain_funcs = defaultdict(lambda: NOOP_WELL_CHANNEL_METRIC_CALCULATOR,
                             {'betaec': EventsGapRainCalculator(),
                             'bcc': ColorCompGapRainCalculator(),
                             'mfgcc': ColorCompGapRainCalculator()})

def fill_beta_plate_metrics(qlplate, plate_metrics, plate_type_code=None):
    """
    Fills the metrics attributes for the specified plate with 

    Separated from the DB function to make this module reusable by
    processes not backed by a DB.

    :param qlplate: The QLPlate derived from the QLP file.
    :param plate_metrics: The object to populate with plate metric data.
    :param plate_type_code: The type code of the plate.

    :rtype: PlateMetrics
    :return: The PlateMetrics structure, populated with beta metrics.
    """

    fill_well_channel_metrics(qlplate, plate_metrics, plate_type_code, estimated_conc_funcs)
    fill_well_metrics(qlplate, plate_metrics, plate_type_code, estimated_cnv_funcs, default_func=CNVCalculator(0,1))

    # FP/FN calc does not make sense for mixed plates
    # wait, yes it does for FP (RED)
    fp_calc = false_positive_funcs.get(plate_type_code, None)
    if fp_calc:
        fp_calc.compute(qlplate, plate_metrics)

    fn_calc = false_negative_funcs.get(plate_type_code, None)
    if fn_calc:
        fn_calc.compute(qlplate, plate_metrics)

    fill_well_channel_metrics(qlplate, plate_metrics, plate_type_code, expected_threshold_funcs)
    fill_well_metrics(qlplate, plate_metrics, plate_type_code, null_linkage_funcs)
    fill_well_metrics(qlplate, plate_metrics, plate_type_code, air_droplet_funcs)
    fill_well_channel_metrics(qlplate, plate_metrics, plate_type_code, polyd_funcs)
    fill_well_channel_metrics(qlplate, plate_metrics, plate_type_code, gap_rain_funcs)
    fill_well_channel_metrics(qlplate, plate_metrics, plate_type_code, extrac_funcs)

    if plate_type_code == 'scc':
        compute_metric_foreach_qlwell_channel(qlplate, plate_metrics, SINGLEWELL_CHANNEL_COLORCOMP_CALC)
        compute_metric_foreach_qlwell( qlplate, plate_metrics, SINGLEWELL_COLORCOMP_CALC)
	
    return plate_metrics

def fill_well_metrics(qlplate, plate_metrics, plate_type_code, func_dict, default_func=None):
    if plate_type_code in MIXED_PLATE_TYPE_CODES:
        compute_metric_foreach_mixed_qlwell(qlplate, plate_metrics, func_dict)
    else:
        func = func_dict.get(plate_type_code, default_func)
        if func:
            compute_metric_foreach_qlwell(qlplate, plate_metrics, func)

    return plate_metrics

def fill_well_channel_metrics(qlplate, plate_metrics, plate_type_code, func_dict, default_func=None):
    if plate_type_code in MIXED_PLATE_TYPE_CODES:
        compute_metric_foreach_mixed_qlwell_channel(qlplate, plate_metrics, func_dict)
    else:
        func = func_dict.get(plate_type_code, default_func)
        if func:
            compute_metric_foreach_qlwell_channel(qlplate, plate_metrics, func)

    return plate_metrics
