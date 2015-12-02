"""
These are methods and filters that were used as a part of the early
2011 beta test.  They still may have some utility, but they might
be better served in qtools.model somewhere.
"""

from sqlalchemy import and_
from sqlalchemy.orm import joinedload, joinedload_all
from datetime import datetime, timedelta
import numpy as np
import math
from collections import OrderedDict, defaultdict

from qtools.lib.collection import groupinto
from qtools.lib.nstats import percentile
from qtools.lib.qlb_factory import get_plate
from qtools.model import Session, Plate, PlateType, QLBPlate, QLBWell, QLBWellChannel, DropletGeneratorRun, DropletGenerator, Box2
from pyqlb.nstats import concentration_interval, cnv_interval
from pyqlb.nstats.peaks import fam_amplitudes, vic_amplitudes, peak_dtype, cluster_1d, fam_widths
from qtools.lib.nstats.peaks import accepted_peaks

def plate_query():

    # writing it this way because the .join seems to muck up
    # filter_by statements downstream
    box2s = [tup[0] for tup in Session.query(Box2.id).all()]

    query = Session.query(Plate).filter(Plate.box2_id.in_(box2s))
    return query

def plate_type_filter(plate_type, query=None):
    if not query:
        query = plate_query()
    
    query = query.filter_by(plate_type_id=plate_type.id)
    return query

def box2_filter(box2_id, query=None):
    if not query:
        query = plate_query()
    
    query = query.filter_by(box2_id=box2_id)
    return query

def day_filter(day, query=None):
    day_start = datetime(day.year, day.month, day.day, 0, 0, 0)
    day_end = day_start+timedelta(1)
    if not query:
        query = plate_query()
    
    query = query.filter(and_(Plate.run_time >= day_start, Plate.run_time < day_end))
    return query

def weeks_ago_filter(weeks_ago, query=None):
    now = datetime.now()
    week_start = now-timedelta(now.weekday(),now.hour*3600+now.minute*60+now.second, now.microsecond)
    if weeks_ago == 0:
        end_time = now
        start_time = week_start
    else:
        start_time = week_start-timedelta(weeks_ago*7)
        end_time = week_start-timedelta((weeks_ago-1)*7)
    
    if not query:
        query = plate_query()
    
    query = query.filter(and_(Plate.run_time >= start_time, Plate.run_time < end_time))
    return query

def since_filter(dt, query=None):
    if not query:
        query = plate_query()
    
    query = query.filter(Plate.run_time >= dt)
    return query

def setup_filter(query=None):
    if not query:
        query = plate_query()
    
    query = query.options(joinedload(Plate.setup, innerjoin=True))
    return query

def analyzed_well_query(plate_list, channels=False):

    if not plate_list:
        # is there an intentional empty?
        return Session.query(QLBWell).filter(QLBWell.id < 0)
    
    wells = Session.query(QLBWell).join(QLBPlate, Plate, Box2).\
                    filter(QLBWell.file_id != -1).\
                    filter(Plate.id.in_([p.id for p in plate_list]))
    
    if channels:
        wells = wells.options(joinedload_all(QLBWell.plate, QLBPlate.file, innerjoin=True),
                              joinedload_all(QLBWell.file, innerjoin=True),
                              joinedload_all(QLBWell.channels, innerjoin=True))
    else:
        wells = wells.options(joinedload_all(QLBWell.plate, QLBPlate.file, innerjoin=True),
                              joinedload_all(QLBWell.file, innerjoin=True))

    return wells

def analyzed_fam_channel_query(plate_list):
    return analyzed_channel_query(plate_list, 0)

def analyzed_vic_channel_query(plate_list):
    return analyzed_channel_query(plate_list, 1)

def analyzed_channel_query(plate_list, channel_num):

    if not plate_list:
        # intentional empty?
        return Session.query(QLBWellChannel).filter(QLBWellChannel.id < 0)
    
    query = Session.query(QLBWellChannel).join(QLBWell, QLBPlate, Plate, Box2).\
                   filter(QLBWellChannel.channel_num == channel_num).\
                   filter(QLBWell.file_id != -1).\
                   filter(Plate.id.in_([p.id for p in plate_list])).\
                   options(joinedload_all(QLBWellChannel.well, QLBWell.plate, QLBPlate.plate, innerjoin=True))
    
    return query

def eventcount_well_filter(query, threshold=0):
    return query.filter(QLBWell.event_count > threshold)

def no_stealth_ntc_filter(query):
    return query.filter(and_(QLBWell.sample_name != 'Stealth', QLBWell.sample_name != 'NTC'))

def sample_name_filter(well_list, sample_name):
    return [well for well in well_list if well.sample_name == sample_name]

def sample_name_channel_filter(well_channel_list, sample_name):
    return [channel for channel in well_channel_list if channel.well.sample_name == sample_name]

def sample_name_query_filter(sample_names, query):
    return query.filter(QLBWell.sample_name.in_(sample_names))

def defined_threshold_filter(query):
    return query.filter(QLBWellChannel.quantitation_threshold != 0)

def event_count_exclude_filter(query):
    """
    @deprecated
    Not up to date, plate specific
    """
    return query.filter(and_(QLBWell.sample_name != 'Stealth',
                             QLBWell.sample_name != '3nM FAM, 3nm VIC',
                             QLBWell.sample_name != '3 nM FAM, 0 nM VIC',
                             QLBWell.sample_name != '0 nM FAM, 3 nM VIC',
                             QLBWell.sample_name != '3 nM FAM, 10 nM VIC')) # this one's a tough call

def well_host_datetime_sort(query):
    return query.order_by(QLBWell.host_datetime)

def all_dye_plates(day):
    dye = Session.query(PlateType).filter_by(code='bdye').first()
    plates = day_filter(day, plate_type_filter(dye))
    return plates

def all_dnr_plates_day(day):
    dnr = Session.query(PlateType).filter_by(code='bdnr').first()
    plates = day_filter(day, plate_type_filter(dnr))
    return plates

def all_fpfn_plates_day(day):
    fpfn = Session.query(PlateType).filter_by(code='bfpfn').first()
    plates = day_filter(day, plate_type_filter(fpfn))
    return plates

def all_dye_plates_week(weeks_ago):
    dye = Session.query(PlateType).filter_by(code='bdye').first()
    plates = weeks_ago_filter(weeks_ago, plate_type_filter(dye))
    return plates

def all_dye_plates_since(dt):
    dye = Session.query(PlateType).filter_by(code='bdye').first()
    plates = since_filter(dt, plate_type_filter(dye))
    return plates

def all_dnr_plates_week(weeks_ago):
    dnr = Session.query(PlateType).filter_by(code='bdnr').first()
    plates = weeks_ago_filter(weeks_ago, plate_type_filter(dnr))
    return plates

def all_dnr_plates_since(dt):
    dnr = Session.query(PlateType).filter_by(code='bdnr').first()
    plates = since_filter(dt, plate_type_filter(dnr))
    return plates

def all_fpfn_plates_week(weeks_ago):
    fpfn = Session.query(PlateType).filter_by(code='bfpfn').first()
    plates = weeks_ago_filter(weeks_ago, plate_type_filter(fpfn))
    return plates

def all_fpfn_plates_since(dt):
    fpfn = Session.query(PlateType).filter_by(code='bfpfn').first()
    plates = since_filter(dt, plate_type_filter(fpfn))
    return plates

def all_dye_well_query(day):
    return analyzed_well_query(all_dye_plates(day).all())

def all_singleplex_plates_week(weeks_ago):
    splex = Session.query(PlateType).filter_by(code='bsplex').first()
    plates = weeks_ago_filter(weeks_ago, plate_type_filter(splex))
    return plates

def all_singleplex_plates_since(dt):
    splex = Session.query(PlateType).filter_by(code='bsplex').first()
    plates = since_filter(dt, plate_type_filter(splex))
    return plates

def all_duplex_plates_week(weeks_ago):
    dplex = Session.query(PlateType).filter_by(code='bdplex').first()
    plates = weeks_ago_filter(weeks_ago, plate_type_filter(dplex))
    return plates

def all_duplex_plates_since(dt):
    dplex = Session.query(PlateType).filter_by(code='bdplex').first()
    plates = since_filter(dt, plate_type_filter(dplex))
    return plates

def all_red_plates_week(weeks_ago):
    red = Session.query(PlateType).filter_by(code='bred').first()
    plates = weeks_ago_filter(weeks_ago, plate_type_filter(red))
    return plates

def all_red_plates_since(dt):
    red = Session.query(PlateType).filter_by(code='bred').first()
    plates = since_filter(dt, plate_type_filter(red))
    return plates

def all_cnv_plates_week(weeks_ago):
    cnv = Session.query(PlateType).filter_by(code='bcnv').first()
    plates = weeks_ago_filter(weeks_ago, plate_type_filter(cnv))
    return plates

def all_cnv_plates_since(dt):
    cnv = Session.query(PlateType).filter_by(code='bcnv').first()
    plates = since_filter(dt, plate_type_filter(cnv))
    return plates


def dye_by_bin(plate_objects, analyzed_wells, eventful_wells,
               analyzed_sample_names, eventful_sample_names, bin_func, channel='FAM'):
    """
    @deprecated -- use metrics
    """
    # assumes standard dye concentrations (see bin_plots)
    bins = set([bin_func(w) for w in analyzed_wells])
    bin_plots = dict([(bin, [[3,None],[10,None],[30,None],[100,None],[300,None],[500,None]]) for bin in bins])

    groups = []
    groups.extend([(sample_name, groupinto(sample_name_filter(analyzed_wells, sample_name), bin_func)) for sample_name in analyzed_sample_names])
    groups.extend([(sample_name, groupinto(sample_name_filter(eventful_wells, sample_name), bin_func)) for sample_name in eventful_sample_names])

    for i, (sample, group) in enumerate(groups):
        for bin, wells in group:
            amp_array = None
            for w in wells:
                qplate = plate_objects[(w.plate.file.dirname, w.plate.file.basename)]
                well = qplate.wells[w.well_name]
                if channel == 'VIC':
                    if amp_array is None:
                        amp_array = vic_amplitudes(well.peaks)
                    else:
                        amp_array = np.concatenate([amp_array, vic_amplitudes(well.peaks)])
                else:
                    if amp_array is None:
                        amp_array = fam_amplitudes(well.peaks)
                    else:
                        amp_array = np.concatenate([amp_array, fam_amplitudes(well.peaks)])
            if amp_array is not None:
                amp_mean = np.mean(amp_array)
                amp_sigma = np.std(amp_array)
                bin_plots[bin][i][1] = (amp_mean, amp_sigma)
    
    return bin_plots

def weekday_grouper(well):
    return well.plate.plate.run_time.weekday()

def date_grouper(well):
    return well.plate.plate.run_time.strftime('%m-%d')

def channel_weekday_grouper(channel):
    return channel.well.plate.plate.run_time.weekday()

def channel_date_grouper(channel):
    return channel.well.plate.plate.run_time.strftime('%m-%d')

def dye_by_box_time(storage, box2_id, weeks_ago=0, since=None):
    """
    @deprecated - use metrics
    """
    if since:
        plates = all_dye_plates_since(since)
        grouper = date_grouper
    else:
        plates = all_dye_plates_week(weeks_ago)
        grouper = weekday_grouper
    
    analyzed_wells = analyzed_well_query(box2_filter(box2_id, plates).all()).all()

    plate_objects = get_plate_objects(storage, analyzed_wells)
    eventful_wells = eventcount_well_filter(analyzed_well_query(box2_filter(box2_id, plates).all())).all()

    fam_analyzed_sample_names = ('3 nM FAM, 0 nM VIC',)
    fam_eventful_sample_names = ('10 nM FAM, 3nM VIC',
                             '30 nM FAM, 3nM VIC',
                             '100 nM FAM, 3nM VIC',
                             '300 nM FAM, 3nM VIC',
                             '500 nM FAM, 3nM VIC')
    fam_dye_data = dye_by_bin(plate_objects, analyzed_wells, eventful_wells,
                      fam_analyzed_sample_names, fam_eventful_sample_names,
                      grouper, 'FAM')
    
    vic_analyzed_sample_names = ('0 nM FAM, 3 nM VIC',)
    vic_eventful_sample_names = ('3 nM FAM, 10nM VIC',
                                 '3 nM FAM, 30nM VIC',
                                 '3 nM FAM, 100nM VIC',
                                 '3 nM FAM, 300nM VIC',
                                 '3 nM FAM, 500nM VIC')
    vic_dye_data = dye_by_bin(plate_objects, analyzed_wells, eventful_wells,
                      vic_analyzed_sample_names, vic_eventful_sample_names,
                      grouper, 'VIC')
    
    return (fam_dye_data, vic_dye_data)

# TODO not tested with storage refactor, but deprecated anyhow
def dye_by_date(storage, day):
    """
    @deprecated -- should be changed to use metrics and not plate files
    """
    # leave low-freq as zero event counts
    # boxes
    analyzed_wells = all_dye_well_query(day).all()

    plate_objects = get_plate_objects(storage, analyzed_wells)

    eventful_wells = eventcount_well_filter(all_dye_well_query(day)).all()
    fam_analyzed_sample_names = ('3 nM FAM, 0 nM VIC',)
    fam_eventful_sample_names = ('10 nM FAM, 3nM VIC',
                                 '30 nM FAM, 3nM VIC',
                                 '100 nM FAM, 3nM VIC',
                                 '300 nM FAM, 3nM VIC',
                                 '500 nM FAM, 3nM VIC')
    fam_dye_data = dye_by_bin(plate_objects, analyzed_wells, eventful_wells,
                              fam_analyzed_sample_names, fam_eventful_sample_names,
                              lambda w: w.plate.plate.box2.name, 'FAM')
    
    vic_analyzed_sample_names = ('0 nM FAM, 3 nM VIC',)
    vic_eventful_sample_names = ('3 nM FAM, 10nM VIC',
                                 '3 nM FAM, 30nM VIC',
                                 '3 nM FAM, 100nM VIC',
                                 '3 nM FAM, 300nM VIC',
                                 '3 nM FAM, 500nM VIC')
    
    vic_dye_data = dye_by_bin(plate_objects, analyzed_wells, eventful_wells,
                              vic_analyzed_sample_names, vic_eventful_sample_names,
                              lambda w: w.plate.plate.box2.name, 'VIC')
    
    return (fam_dye_data, vic_dye_data)


def dnr_by_date(storage, day):
    """
    @deprecated - use metrics
    """
    fam_channels = eventcount_well_filter(no_stealth_ntc_filter(analyzed_fam_channel_query(all_dnr_plates_day(day).all())), 100).all()
    plate_objects = get_plate_objects_from_channels(storage, fam_channels)
    
    sample_names = ('SA DNR 0.001', 'SA DNR 0.01', 'SA DNR 0.1', 'SA DNR 1.0', 'SA DNR 5')
    return dnr_by_bin(plate_objects, fam_channels, sample_names, lambda c: c.well.plate.plate.box2.name)

def dnr_by_box_time(storage, box2_id, weeks_ago=0, since=None):
    """
    @deprecated - use metrics
    """
    if since:
        plates = all_dnr_plates_since(since)
        grouper = channel_date_grouper
    else:
        plates = all_dnr_plates_week(weeks_ago)
        grouper = channel_weekday_grouper
    
    fam_channels = fam_channels = eventcount_well_filter(no_stealth_ntc_filter(analyzed_fam_channel_query(box2_filter(box2_id, plates).all())), 100).all()
    plate_objects = get_plate_objects_from_channels(storage, fam_channels)

    sample_names = ('SA DNR 0.001', 'SA DNR 0.01', 'SA DNR 0.1', 'SA DNR 1.0', 'SA DNR 5')
    return dnr_by_bin(plate_objects, fam_channels, sample_names, grouper)

def dnr_by_bin(plate_objects, fam_channels, sample_names, bin_func):
    """
    @deprecated - use metrics
    """
    bins = set([bin_func(c) for c in fam_channels])
    # TODO: do sample names here
    bin_plots = dict([(bin, [[0.001,None],[0.01,None],[0.1,None],[1,None],[5,None]]) for bin in bins])

    groups = []
    groups.extend([(sample_name, groupinto(sample_name_channel_filter(fam_channels, sample_name), bin_func)) for sample_name in sample_names])

    for i, (sample, group) in enumerate(groups):
        for bin, channels in group:
            conc_array = []
            for c in channels:
                qplate = plate_objects[(c.well.plate.file.dirname, c.well.plate.file.basename)]
                well = qplate.wells[c.well.well_name]
                # TODO: use dynamic threshold or keep 4000?
                pos, neg = cluster_1d(accepted_peaks(well), 0, 4000)
                conc, clow, chigh = concentration_interval(len(pos), len(neg), droplet_vol=well.droplet_volume)
                conc_array.append((max(conc,0.0001), max(clow,0.0001), max(chigh,0.0001)))
            
            if len(conc_array) > 0:
                conc_mean = np.mean([ca[0] for ca in conc_array])
                bin_plots[bin][i][1] = (conc_mean, conc_array)
    
    return bin_plots

def singleplex_by_dr(weeks_ago=0, since=None):
    """
    @deprecated - use metrics
    """
    if since:
        plates = all_singleplex_plates_since(since)
    else:
        plates = all_singleplex_plates_week(weeks_ago)

    fam_channels = eventcount_well_filter(
                     analyzed_fam_channel_query(
                       plates.all()
                     ), 1000).\
                     filter(and_(QLBWellChannel.quantitation_threshold_conf >= 0.85,
                                 QLBWell.consumable_chip_num != None)).all()
    return singleplex_by_bin(fam_channels, lambda c: c.well.plate.plate.box2.name)

def singleplex_by_bin(fam_channels, bin_func):
    channels = sorted(fam_channels, key=lambda c: (c.well.plate.plate.setup.id, c.well.consumable_chip_num, c.well.consumable_channel_num))
    groups = groupinto(channels, bin_func)
    plots = dict([(box2, []) for box2, data in groups])
    for i, (box2, well_channels) in enumerate(groups):
        conc_array = []
        for w in well_channels:
            #qplate = plate_objects[(w.well.plate.file.dirname, w.well.plate.file.basename)]
            #well = qplate.wells[w.well.well_name]
            #pos, neg = cluster_1d(well.peaks, 0, 4000)
            conc_array.append((w.well.id, (w.concentration, w.conf_lower_bound, w.conf_upper_bound)))
        
        plots[box2] = conc_array
    
    return plots

def duplex_by_dr(weeks_ago=0, since=None):
    if since:
        plates = all_duplex_plates_since(since)
    else:
        plates = all_duplex_plates_week(weeks_ago)
    
    fam_channels = eventcount_well_filter(
                     no_stealth_ntc_filter(
                     analyzed_fam_channel_query(
                       plates.all()
                     )), 1000).\
                     filter(and_(QLBWellChannel.quantitation_threshold_conf >= 0.85,
                                 QLBWell.consumable_chip_num != None)).all()
    
    sample_names = ('S.a. 0.125', 'S.a. 0.25', 'S.a. 0.5', 'S.a. 1.02', 'S.a. 2.0')
    return duplex_by_bin(fam_channels, sample_names, lambda c: c.well.plate.plate.box2.name)

def duplex_by_bin(fam_channels, sample_names, bin_func):
    channels = sorted(fam_channels, key=lambda c: (c.well.plate.plate.setup.id, c.well.consumable_chip_num, c.well.consumable_channel_num))
    bins = set([bin_func(c) for c in channels])
    bin_plots = dict([(bin, [[0.125, None],[0.25, None],[0.5, None],[1.02,None],[2,None]]) for bin in bins])

    groups = []
    groups.extend([(sample_name, groupinto(sample_name_channel_filter(channels, sample_name), bin_func)) for sample_name in sample_names])

    # this is just dnr with different coefficients -- can that be patternized?
    for i, (sample, group) in enumerate(groups):
        for bin, channels in group:
            conc_array = []
            for c in channels:
                conc, clow, chigh = max(c.concentration,0.0001), max(c.conf_lower_bound,0.0001), max(c.conf_upper_bound,0.0001)
                conc_array.append((conc, clow, chigh, c.well_id))
            
            if len(conc_array) > 0:
                conc_mean = np.mean([ca[0] for ca in conc_array])
                bin_plots[bin][i][1] = (conc_mean, conc_array)
    
    return bin_plots


def red_by_dr(weeks_ago=0, since=None):
    if since:
        plates = all_red_plates_since(since)
    else:
        plates = all_red_plates_week(weeks_ago)
    
    fam_channels = eventcount_well_filter(
                     analyzed_fam_channel_query(
                       plates.all()
                   ), 1000).all()
    
    sample_names = (('0% Mutant, 1cpd WT', (0, '1')),
                    ('0% Mutant, 2cpd WT', (0, '2')),
                    ('0% Mutant, 2.5cpd WT', (0, '2.5')),
                    ('0% Mutant, 5cpd WT', (0, '5')),
                    ('0.01% Mutant, 1cpd WT', (0.0001, '1')),
                    ('0.01% Mutant, 2cpd WT', (0.0002, '2')),
                    ('0.01% Mutant, 2.5cpd WT', (0.00025, '2.5')),
                    ('0.01% Mutant, 5cpd WT', (0.0005, '5')),
                    ('0.05% Mutant, 1cpd WT', (0.0005, '1')),
                    ('0.05% Mutant, 2cpd WT', (0.001, '2')),
                    ('0.05% Mutant, 2.5cpd WT', (0.00125, '2.5')),
                    ('0.05% Mutant, 5cpd WT', (0.0025, '5')),
                    ('0.1% Mutant, 1cpd WT', (0.001, '1')),
                    ('0.1% Mutant, 2cpd WT', (0.002, '2')),
                    ('0.1% Mutant, 2.5cpd WT', (0.0025, '2.5')),
                    ('0.1% Mutant, 5cpd WT', (0.005, '5')),
                    ('0.5% Mutant, 1cpd WT', (0.005, '1')),
                    ('0.5% Mutant, 2cpd WT', (0.01, '2')),
                    ('0.5% Mutant, 2.5cpd WT', (0.0125, '2.5')),
                    ('0.5% Mutant, 5cpd WT', (0.025, '5')),
                    ('1% Mutant, 1cpd WT', (0.01, '1')),
                    ('1% Mutant, 2cpd WT', (0.02, '2')),
                    ('1% Mutant, 2.5cpd WT', (0.025, '2.5')),
                    ('1% Mutant, 5cpd WT', (0.05, '5')),
                    ('0.01cpd Mutant, 0 WT', (0.01, '1.01')),
                    ('0.02cpd Mutant, 0 WT', (0.02, '2.01')),
                    ('0.025cpd Mutant, 0 WT', (0.025, '2.51')),
                    ('0.025 cpd Mutant, 0 WT', (0.025, '2.51')),
                    ('0.05cpd Mutant, 0 WT', (0.05, '5.01')))
    
    return red_by_bin(fam_channels, sample_names, lambda c: c.well.plate.plate.box2.name)

def red_by_bin(fam_channels, sample_names, bin_func):
    bins = set([bin_func(c) for c in fam_channels])
    bin_plots = dict([(bin, defaultdict(dict)) for bin in bins])

    sample_cpd_map = dict(sample_names)
    groups = []
    for sample_name, (sample_cpd, bg_cpd) in sample_names:
        channels = sample_name_channel_filter(fam_channels, sample_name)
        if channels:
            groups.append((sample_name, groupinto(channels, bin_func)))
    
    for i, (sample, group) in enumerate(groups):
        for bin, channels in group:
            pos_array = []
            for c in channels:
                pos_array.append((c.well.id, c.positive_peaks or 0))

            bin_plots[bin][sample_cpd_map[sample][0]][sample_cpd_map[sample][1]] = pos_array
    
    return bin_plots

def cnv_by_dr(weeks_ago=0, since=None):
    if since:
        plates = all_cnv_plates_since(since)
    else:
        plates = all_cnv_plates_week(weeks_ago)
    
    wells = eventcount_well_filter(
              analyzed_well_query(
                plates.all()
            ), 1000).all()
    sample_names = ('NA11994 CN1','NA18507 CN2', 'NA19108 CN2','NA18502 CN3', 'NA19221 CN4','NA19205 CN5','NA18916 CN6')
    return cnv_by_bin(wells, sample_names, lambda w: w.plate.plate.box2.name)

def cnv_by_bin(wells, sample_names, bin_func):
    bins = set([bin_func(w) for w in wells])
    bin_plots = dict([(bin, [[sample_name, []] for sample_name in sample_names]) for bin in bins])
    #raise Exception, bin_plots

    groups = []
    groups.extend([(sample_name, groupinto(sample_name_filter(wells, sample_name), bin_func)) for sample_name in sample_names])

    for i, (sample, group) in enumerate(groups):
        for bin, wells in group:
            cnv_array = []
            for w in wells:
                fam = w.channels[0]
                vic = w.channels[1]
                fam_pos = fam.positive_peaks
                fam_neg = fam.negative_peaks
                vic_pos = vic.positive_peaks
                vic_neg = vic.negative_peaks
                cnv, low, high = cnv_interval(fam_pos, fam_neg, vic_pos, vic_neg)
                if math.isnan(cnv):
                    cnv = 0
                if math.isnan(low):
                    low = 0
                if math.isnan(high):
                    high = 0

                cnv_array.append((w.id, (cnv, low, high)))
            
            bin_plots[bin][i][1] = cnv_array
        
    return bin_plots

def fpfn_by_date(storage, day):
    vic_channels = eventcount_well_filter(analyzed_vic_channel_query(all_fpfn_plates_day(day).all()), 1000).all()
    plate_objects = get_plate_objects_from_channels(storage, vic_channels)
    
    sample_names = ('NTC', 'NA19205 50ng/uL digested')
    return fpfn_by_bin(plate_objects, vic_channels, sample_names, lambda c: c.well.plate.plate.box2.name)

def fpfn_by_box_time(storage, box2_id, weeks_ago=0, since=None):
    if since:
        plates = all_fpfn_plates_since(since)
        grouper = channel_date_grouper
    else:
        plates = all_fpfn_plates_week(weeks_ago)
        grouper = channel_weekday_grouper
    
    vic_channels = eventcount_well_filter(analyzed_vic_channel_query(box2_filter(box2_id, plates).all()), 1000).all()
    plate_objects = get_plate_objects_from_channels(storage, vic_channels)

    sample_names = ('NTC', 'NA19205 50ng/uL digested')
    return fpfn_by_bin(plate_objects, vic_channels, sample_names, grouper)

fpfn_positive_well_names = ('A02','A03','B01','A08','A09','B07','E02','E03','F01','E08','E09','F01')
fpfn_negative_well_names = ('A01','B03','B06','A07','B09','B12','E01','F03','F06','E07','F09','F12')
fpfn_fp_well_names = ('B03','B06','B09','B12','F03','F06','F09','F12')
fpfn_fn_well_names = ('A03','A09','E03','E09')

def fpfn_by_bin(plate_objects, vic_channels, sample_names, bin_func):
    bins = set([bin_func(c) for c in vic_channels])
    bin_plots = dict([(bin, []) for bin in bins])

    bin_wells = defaultdict(list)
    # divide into plates
    for bin, group in groupinto(vic_channels, bin_func):
        # this is a wacky grouping, but for reuse in plate_objects (why did I not pick plate ids again?)
        plate_groups = groupinto(group, lambda c: (c.well.plate.file.dirname, c.well.plate.file.basename))
        for plate_id, channels in plate_groups:
            qplate = plate_objects[plate_id]
            positives = [c for c in channels if c.well.well_name in fpfn_positive_well_names]
            negatives = [c for c in channels if c.well.well_name in fpfn_negative_well_names]
            
            # compute a threshold which is 1/4 between the positive and negative means for the plate
            positive_means = []
            negative_means = []
            for p in positives:
                amps = vic_amplitudes(accepted_peaks(qplate.wells[p.well.well_name]))
                positive_means.append((len(amps), np.mean(amps)*len(amps)))
            
            if positive_means:
                positive_mean = sum([pm[1] for pm in positive_means])/sum([pm[0] for pm in positive_means])
            else:
                positive_mean = 32767
            
            for n in negatives:
                amps = vic_amplitudes(accepted_peaks(qplate.wells[n.well.well_name]))
                negative_means.append((len(amps), np.mean(amps)*len(amps)))
            
            if negative_means:
                negative_mean = sum([nm[1] for nm in negative_means])/sum([nm[0] for nm in negative_means])
            else:
                negative_mean = 0
            
            threshold = ((3*negative_mean)+positive_mean)/4

            fps = [c for c in channels if c.well.well_name in fpfn_fp_well_names]
            fns = [c for c in channels if c.well.well_name in fpfn_fn_well_names]

            fp_counts = []
            fn_counts = []

            for f in fps:
                pos, neg = cluster_1d(accepted_peaks(qplate.wells[f.well.well_name]), 1, threshold)
                fp_counts.append((f.well.id, len(pos),
                                  10000*(float(len(pos))/(float(len(pos))+float(len(neg)))),
                                  qplate.wells[f.well.well_name]))
            
            for f in fns:
                pos, neg = cluster_1d(accepted_peaks(qplate.wells[f.well.well_name]), 1, threshold)
                fn_counts.append((f.well.id, len(neg),
                                  10000*(float(len(neg))/(float(len(pos))+float(len(neg))))))
            
            bin_wells[bin].append((fp_counts, fn_counts, threshold))
    
    return bin_wells


def channel_events_by_time(weeks_ago=0, since=None):
    eventful_wells = get_channel_wells(weeks_ago=weeks_ago, since=since)
    return events_by_channel_dg(eventful_wells, lambda w: w.event_count)

def reader_events_by_time(weeks_ago=0, since=None):
    eventful_wells = get_channel_wells(weeks_ago=weeks_ago, since=since)
    return events_by_reader_dg(eventful_wells, lambda w: w.event_count)

def channel_widths_by_time(storage, weeks_ago=0, since=None):
    eventful_wells = get_channel_wells(weeks_ago=weeks_ago, since=since)
    plate_objects = get_plate_objects(storage, eventful_wells)

    def well_mean_sigma_closure(well):
        qplate = plate_objects[(well.plate.file.dirname, well.plate.file.basename)]
        if not qplate:
            return None
        
        well = qplate.wells[well.well_name]
        widths = fam_widths(well.peaks)
        mean = np.mean(widths)
        stddev = np.std(widths)
        return (mean, mean-stddev, mean+stddev)
    
    return events_by_channel_dg(eventful_wells, well_mean_sigma_closure)

def reader_widths_by_time(storage, weeks_ago=0, since=None):
    eventful_wells = get_channel_wells(weeks_ago=weeks_ago, since=since)
    plate_objects = get_plate_objects(storage, eventful_wells)

    def well_mean_sigma_closure(well):
        qplate = plate_objects[(well.plate.file.dirname, well.plate.file.basename)]
        if not qplate:
            return None
        
        well = qplate.wells[well.well_name]
        widths = fam_widths(well.peaks)
        mean = np.mean(widths)
        stddev = np.std(widths)
        return (mean, mean-stddev, mean+stddev)
    
    return events_by_reader_dg(eventful_wells, well_mean_sigma_closure)

def events_by_channel_dg(wells, quant_func):
    well_order = [((well.plate.plate.setup.id*12.0+well.consumable_chip_num)/12.0, well) for idx, well in enumerate(wells)] # assume sorted by host_datetime incoming
    bin_func = lambda tup: tup[1].consumable_channel_num
    dg_func = lambda tup: tup[1].droplet_generator_id

    groups = groupinto(well_order, bin_func)
    channel_groups = []
    for channel_num, group in groups:
        channel_groups.append((channel_num, [(dg_id, [(idx, quant_func(w)) for idx, w in wells]) for dg_id, wells in groupinto(group, dg_func)]))
    
    return channel_groups

def events_by_reader_dg(wells, quant_func):
    well_order = [((well.plate.plate.setup.id*96.0+well.consumable_chip_num*12.0+well.consumable_channel_num)/96.0, well) for idx, well in enumerate(wells)] # assume sorted by host_datetime incoming
    bin_func = lambda tup: tup[1].plate.plate.box2_id
    dg_func = lambda tup: tup[1].droplet_generator_id

    groups = groupinto(well_order, bin_func)
    reader_groups = []
    for reader_num, group in groups:
        reader_groups.append((reader_num, [(dg_id, [(idx, quant_func(w)) for idx, w in wells]) for dg_id, wells in groupinto(group, dg_func)]))
    
    return reader_groups


def get_plate_objects(storage, qlbwells):
    plates = set([w.plate for w in qlbwells])
    return dict([((p.file.dirname, p.file.basename), get_plate(storage.qlbplate_path(p))) for p in plates])

def get_plate_objects_from_channels(storage, qlbwell_channels):
    plates = set([c.well.plate for c in qlbwell_channels])
    return dict([((p.file.dirname, p.file.basename), get_plate(storage.qlbplate_path(p))) for p in plates])

def get_channel_wells(weeks_ago=0, since=None):
    if since:
        plates = since_filter(since)
    else:
        plates = weeks_ago_filter(weeks_ago)
    
    return well_host_datetime_sort(
                       eventcount_well_filter(
                         event_count_exclude_filter(
                           analyzed_well_query(
                             setup_filter(plates).all()
                           )
                         )
                       )
                     ).filter(and_(QLBWell.consumable_chip_num != None, QLBWell.droplet_generator_id != None)).all()

fam_dq_sample_names = ('SA singleplex 1.0',
                         '0.01% Mutant, 1cpd WT',
                         '0.01% Mutant, 2cpd WT',
                         '0.01% Mutant, 2.5cpd WT',
                         '0.01% Mutant, 5cpd WT',
                         '0.05% Mutant, 1cpd WT',
                         '0.05% Mutant, 2cpd WT',
                         '0.05% Mutant, 2.5cpd WT',
                         '0.05% Mutant, 5cpd WT',
                         '0.1% Mutant, 1cpd WT',
                         '0.1% Mutant, 2cpd WT',
                         '0.1% Mutant, 2.5cpd WT',
                         '0.1% Mutant, 5cpd WT',
                         '0.5% Mutant, 1cpd WT',
                         '0.5% Mutant, 2cpd WT',
                         '0.5% Mutant, 2.5cpd WT',
                         '0.5% Mutant, 5cpd WT',
                         '1% Mutant, 1cpd WT',
                         '1% Mutant, 2cpd WT',
                         '1% Mutant, 2.5cpd WT',
                         '1% Mutant, 5cpd WT',
                         '0.01cpd Mutant, 0 WT',
                         '0.02cpd Mutant, 0 WT',
                         '0.025cpd Mutant, 0 WT',
                         '0.025 cpd Mutant, 0 WT',
                         '0.05cpd Mutant, 0 WT',
                         'SA DNR 0.001',
                         'SA DNR 0.01',
                         'SA DNR 0.1',
                         'SA DNR 1.0',
                         'S.a. 1.5cpd',
                         'S.a. 1cpd')
    
famvic_dq_sample_names = ('S.a. 0.125',
                            'S.a. 0.25',
                            'S.a. 0.5',
                            'S.a. 1.02',
                            'S.a. 2.0',
                            'NA11994 CN1',
                            'NA18507 CN2',
                            'NA19108 CN2',
                            'NA18502 CN3',
                            'NA18916 CN6',
                            'NA19221 CN4',
                            'NA19205 CN5')
    
vic_dq_sample_names = []

def get_quality_wells(weeks_ago=0, channels=False):
    exclude_quality_names = ('3nM FAM, 3nM VIC','3 nM FAM, 0 nM VIC','Stealth','0 nM FAM, 3 nM VIC')

    # exclude beta apps plates (not sure what they are, not labeled systematically)
    beta_app_setup = Session.query(PlateType).filter_by(code='bapp').first()
    wells = analyzed_well_query(
              setup_filter(weeks_ago_filter(weeks_ago)).all(), channels=channels
            ).filter(Plate.plate_type_id != beta_app_setup.id).\
              options(joinedload_all(QLBWell.plate, QLBPlate.plate, Plate.plate_type, innerjoin=True),
                      joinedload_all(QLBWell.plate, QLBPlate.plate, Plate.box2, innerjoin=True)).all()
    
    return [w for w in wells if w.sample_name not in exclude_quality_names]

# TODO make more generic (LOD in general by attribute, 95% pct)
def get_red_lod(weeks_ago=0, since=None):
    if since:
        plates = since_filter(since)
    else:
        plates = weeks_ago_filter(weeks_ago)
    
    wells = sample_name_query_filter(
               ('0% Mutant, 1cpd WT','0% Mutant, 2cpd WT','0% Mutant, 2.5cpd WT','0% Mutant, 2.5 cpd WT','0% Mutant, 5cpd WT'),
               analyzed_well_query(
                 setup_filter(plates).all(), channels=True
               )
            ).all()
    
    fam = [well.channels[0] for well in wells]
    return percentile(fam, 0.95, lambda f: f.positive_peaks)

def get_dg_runs(dg_id):
    start_date = datetime(2011, 3, 21, 0, 0)
    return Session.query(DropletGeneratorRun).filter(and_(DropletGeneratorRun.droplet_generator_id==dg_id,
                                                          DropletGeneratorRun.datetime >= start_date)).\
                                              order_by(DropletGeneratorRun.datetime)

def get_good_dg_runs(dg_id):
    query = get_dg_runs(dg_id)
    return query.filter(DropletGeneratorRun.failed == False).all()

def get_bad_dg_runs(dg_id):
    query = get_dg_runs(dg_id)
    return query.filter(DropletGeneratorRun.failed == True).all()
