"""
Methods to scan for QLPs in a source filesystem, and then construct
model objects based off those QLPs and QLBs, create thumbnails,
and compute metrics.  This is the main link between the QTools DB
and the underlying filesystem.

scan_plates() is the main method here-- everything else is basically
keyed off that.

Also useful: trigger_plate_rescan will indicate a plate is 'dirty',
so the subsequent call to scan_plates() will trigger a new look
at metrics computation.
"""
import os, errno, re, math
from datetime import datetime, timedelta
from collections import defaultdict

from pyqlb.nstats.well import well_channel_automatic_classification
from pyqlb.objects import QLWell

from qtools.constants.plot import *
from qtools.lib.metrics.db import dbplate_tree, process_plate, get_beta_plate_metrics
from qtools.lib.metrics.beta import beta_plate_types
from qtools.lib.mplot import plot_fam_peaks, plot_vic_peaks, plot_cluster_2d, render as plt_render, cleanup as plt_cleanup
from qtools.lib.plate import plate_from_qlp, apply_template_to_plate, apply_setup_to_plate, get_product_validation_plate
from qtools.lib.qlb_factory import get_plate, get_well

from qtools.model import Session, QLBFile, QLBPlate, QLBWell, QLBWellChannel, Plate, Box2

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import joinedload_all

def time_equals(t1, t2):
    return t1.year == t2.year \
           and t1.month == t2.month \
           and t1.day == t2.day \
           and t1.hour == t2.hour \
           and t1.minute == t2.minute \
           and t1.second == t2.second

all_drs = []
QLB_TIMESTAMP_RE = re.compile(r'\d+\-\d+\-\d+\-\d+\-\d+')

def run_id(path):
    """
    Get a unique identifier for the path to use as a unique
    key for the QLBFile table.  This is needed because
    MySQL's uniqueness indices have a width narrower than the
    name of the file (which would normally be a unique
    identifier).  This runs counter to QuantaSoft's file naming
    convention, where the unique string parts come toward the end
    (xxxxx_A05_RAW.qlb, xxxxxxx.qlp)

    The run id is:

    reader:time/filetype_well_filename

    Filename will sometimes be truncated in the index, but the
    unique identifying information of a file will come first.
    """
    match = QLB_TIMESTAMP_RE.search(path)

    global all_drs
    if not all_drs:
        boxes = Session.query(Box2).all()
        all_drs = dict([(b.src_dir, b.code) for b in boxes])
    
    if path.endswith('.qlp'):
        prefix = 'QLP'
    elif path.endswith('RAW.qlb'):
        prefix = path[-11:-8]
    else:
        prefix = ''
    
    box = '??'
   
    #determine DR code by idenifying the DR name in path. 
    filedir = path.split(os.sep)[0]
    for name, code in all_drs.items():
        if name == filedir:
            box = code
            break
    
    if match:
        timestamp = match.group(0)
        filename = path[match.end()+1:]
        return "%s:%s/%s_%s" % (box, timestamp, prefix, filename)
    else:
        return "%s:%s_%s" % (box, prefix, path)

def duplicate_run_id(path):
    path = run_id(path)
    now = datetime.strftime(datetime.now(),'%Y-%m-%d-%H-%M-%S')
    return "%s_%s" % (now, path)

def scan_plates(plate_source, image_source):
    """
    Scan for new/changed plates in the plate source.  Store database records in
    the database, and thumbnail images in locations specified by image_source.

    THIS IS THE METHOD YOU CALL TO LOOK FOR NEW PLATES.
    """
    count = 0

    file_lists = defaultdict(list)
    
        # get QLPs -- needs read status filter?
    mtime_dict = dict([("%s/%s" % (dirname, basename),
                       (id, mtime))
                       for id, dirname, basename, mtime
                       in Session.query(QLBFile.id, QLBFile.dirname, QLBFile.basename, QLBFile.mtime).\
                              filter(QLBFile.type == 'processed').\
                              all()])
    
    for volume, path in plate_source.volume_path_iter():
        count += 1
        path_id = plate_source.path_id(volume, path)
        file_source = plate_source.file_source(volume)
        __scan_plate(file_source, image_source, path_id, path, mtime_dict, file_lists)
    return file_lists

def scan_plate(plate_source, image_source, volume, path, plate_type=None):
    """
    Ugly abstraction to scan a single uploaded plate.
    """
    # TODO: refine this query to just check the path supplied
    mtime_dict = dict([("%s/%s" % (dirname, basename),
                       (id, mtime))
                       for id, dirname, basename, mtime
                       in Session.query(QLBFile.id, QLBFile.dirname, QLBFile.basename, QLBFile.mtime).\
                              filter(QLBFile.type == 'processed').\
                              all()])
    
    path_id = plate_source.path_id(volume, path)
    file_source = plate_source.file_source(volume)
    return __scan_plate(file_source, image_source, path_id, path, mtime_dict, plate_type=plate_type)

def __scan_plate(file_source, image_source, path_id, path, mtime_dict, plate_type=None, file_lists=None):
    """
    The method responsible for taking a QLP file on disk and creating
    thumbnails and adding/updating records in the database based off
    the contents of that file.

    This is a nasty abstraction, I apologize.

    TODO: make this more natural along add/update line, do not require use of
    mtime_dict or file_list (or return file_list as files touched)

    Returns the Plate object of the added/updated plate, or None if there was
    no touch/error.

    :param file_source: The source of the QLP files (QLStorageSource)
    :param image_source: The source/sink of thumbnails (QLStorageSource)
    :param path_id: The unique identifier of the plate file.  Computed by run_id()
    :param path: The actual file path of the QLP.
    :param mtime_dict: A mapping between plates and their last updated times.  This will
                       indicate whether or not a plate is 'dirty' with respect to the DB.
    :param plate_type: A plate type.  Supplying this will indicate that the special metrics
                       corresponding to that plate type should be computed during the scan.
    :param file_lists: A logging object used in the scan to record files that are missing,
                       poorly processed, etc.  Side-effected by this method.
    """
    if not file_lists:
        file_lists = defaultdict(list)
    
        # if the file is not being tracked, attempt to add it
        if not mtime_dict.has_key(path_id):
            print "Adding plate: %s" % path
            qlbfile, qlplate, valid_file = add_qlp_file_record(file_source, path)
            if not valid_file:
                print "Invalid file: %s" % path
                file_lists['invalid_plates'].append(path)
                return None
            elif path.endswith('HFE_Plate.qlp'):
                qlbfile.read_status = -7
                print "Ignoring HFE Plate: %s" % path
                Session.commit()
                return None
            elif qlbfile.version is 'Unknown':
                qlbfile.read_status = -8
                print "Ignoring plate run with unknown QS version: %s" % path
                Session.commit()
                return None
            
            if(qlbfile.version_tuple < (0,1,1,9)):
                # we don't recognize the QLP file version, ditch
                qlbfile.read_status = -2
                Session.commit()
                return None
                
            qlbplate, valid_plate = add_qlp_plate_record(qlplate, qlbfile)
            if not valid_plate:
                # invalid plate
                print "Could not read plate: %s" % path
                qlbfile.read_status = -20
                Session.commit()
                file_lists['unreadable_plates'].append(path)
                return None
                
            
            for well_name, proc_qlwell in sorted(qlplate.analyzed_wells.items()):
                
                # remove empty/blank wells generated by eng group
                if (well_name is None or well_name == ''):
                    del qlplate.analyzed_wells[well_name]
                    continue

                raw_qlwell = None
                # TODO: abstract?
                well_loc = "%s_%s_RAW.qlb" % (path[:-4], well_name)
                # process QLP only
                if not os.path.isfile(well_loc):
                    print "Could not find well file: %s" % well_loc
                    file_lists['missing_wells'].append(well_loc)
                    well_file = None
                    # proceed, as file may just not have been delivered
                    valid_file = True
                else:
                    well_file, raw_qlwell, valid_file = add_qlb_file_record(file_source, well_loc)
                
                if not valid_file:
                    print "Invalid well file: %s" % well_loc
                    file_lists['invalid_wells'].append(well_loc)
                    continue
                    
                qlbwell, valid_well = add_qlb_well_record(well_file, well_name, proc_qlwell, raw_qlwell)
                if valid_well:
                    qlbplate.wells.append(qlbwell)
            
            # bug 829: if there are invalid wells, do not process the plate;
            # wait for the well files to complete processing, get on next run
            #
            #
            if file_lists['invalid_wells']:
                print "Skipping plate processing (invalid well): %s" % path
                Session.rollback()
                return None # continue plate

            plate_meta = plate_from_qlp(qlbplate)
            Session.add(plate_meta)

            qlbplate.plate = plate_meta

            validation_test = get_product_validation_plate(qlplate, plate_meta)

            if not validation_test:
                if not apply_setup_to_plate(qlplate, plate_meta):
                    apply_template_to_plate(qlplate, plate_meta)
            
            # OK, try it now
            try:
                for well in qlbplate.wells:
                    if well.file_id != -1:
                        well.file.read_status = 1
                qlbplate.file.read_status = 1
                Session.commit()
                write_images_stats_for_plate(qlbplate, qlplate, image_source, override_plate_type=plate_type)
                Session.commit()
                qlbplate.plate.score = Plate.compute_score(qlbplate.plate)
                Session.commit()
                if validation_test:
                    validation_test.plate_id = qlbplate.plate.id
                    Session.add(validation_test)
                    Session.commit()
                file_lists['added_plates'].append(path)
                return plate_meta
            except Exception, e:
                print e
                print "Could not process new plate: %s" % path
                file_lists['unwritable_plates'].append(path)
                Session.rollback()
                
        elif time_equals(mtime_dict[path_id][1], datetime.fromtimestamp(os.stat(path).st_mtime)):
            return None
        else: 
            # strategy: reprocess the plate and update.
            qlbfile = Session.query(QLBFile).get(mtime_dict[path_id][0])
            if not qlbfile:
                print "No file for path: %s" % path
                return None
            elif path.endswith('HFE_Plate.qlp'):
                qlbfile.mtime = datetime.fromtimestamp(os.stat(path).st_mtime)
                Session.commit()
                return None
            
            qlbplates = Session.query(QLBPlate).filter_by(file_id=qlbfile.id).\
                                options(joinedload_all(QLBPlate.wells, QLBWell.channels)).all()
            if not qlbplates:
                print "No plate for read file: %s" % path
                return None
            
            qlbplate = qlbplates[0]
            if not qlbplate.plate_id:
                print "No plate for read file (plate deleted): %s" % path
                qlbfile.mtime = datetime.fromtimestamp(os.stat(path).st_mtime)
                Session.commit() 
                return None
            
            print "Updating plate %s/%s: %s" % (qlbplate.plate_id, qlbplate.id, path)
            qlplate = get_plate(path)
            updated = update_qlp_plate_record(qlbplate, qlplate)
            if not updated:
                print "Could not read updated file"
                Session.rollback()
                qlbplate.file.read_status = -30
                Session.commit()
                file_lists['unreadable_plates'].append(path)
                return None
            
            # this is basically the same as on add -- abstract?
            #
            # TODO (GitHub Issue 30): handle case where a previously analyzed well is switched to 'Not Used'
            for well_name, proc_qlwell in sorted(qlplate.analyzed_wells.items()):
                raw_qlwell = None
                
                # TODO: abstract?    
                well_loc = "%s_%s_RAW.qlb" % (path[:-4], well_name)
                qlbwells = [well for well in qlbplate.wells if well.well_name == well_name]
                if not qlbwells:
                    # add qlb file record
                    if not os.path.isfile(well_loc):
                        print "Could not find well file: %s" % well_loc
                        well_file = None
                        valid_file = True
                        file_lists['missing_wells'].append(well_loc)
                    else:
                        well_file, raw_qlwell, valid_file = add_qlb_file_record(file_source, well_loc)
                    
                    if not valid_file:
                        print "Invalid well file: %s" % well_loc
                        file_lists['invalid_wells'].append(well_loc)
                        continue
                    
                    qlbwell, valid_well = add_qlb_well_record(well_file, well_name, proc_qlwell, raw_qlwell)
                    if valid_well:
                        qlbplate.wells.append(qlbwell)
                    else:
                        file_lists['invalid_wells'].append(well_loc)
                        print "Could not add well %s: %s" % (well_name, well_loc)
                else:
                    qlbwell = qlbwells[0]

                    if not os.path.isfile(well_loc):
                        print "Could not find well file to update: %s" % well_loc
                        file_lists['missing_wells'].append(well_loc)
                        update_qlb_well_record(qlbwell, well_name, proc_qlwell, None)
                    else:
                        if qlbwell.file_id == -1:
                            well_file, raw_qlwell, valid_file = add_qlb_file_record(file_source, well_loc)
                            if valid_file:
                                qlbwell.file = well_file
                        update_qlb_well_record(qlbwell, well_name, proc_qlwell, raw_qlwell)
                
            # in lieu of updating plate meta (though it maybe should be done)
            qlbplate.plate.program_version = qlbplate.host_software
            
            try:
                for well in qlbplate.wells:
                    if well.file_id != -1 and well.file:
                        well.file.read_status = 1
                qlbplate.file.read_status = 1
                qlbfile.mtime = datetime.fromtimestamp(os.stat(path).st_mtime)
                Session.commit()
                # this is where updating the dirty bits would come in handy
                write_images_stats_for_plate(qlbplate, qlplate, image_source, overwrite=True, override_plate_type=plate_type)
                Session.commit()
                qlbplate.plate.score = Plate.compute_score(qlbplate.plate)
                Session.commit()
                file_lists['updated_plates'].append(path)
                return qlbplate.plate
            except Exception, e:
                print e
                print "Could not update plate %s/%s: %s" % (qlbplate.plate_id, qlbplate.id, path)
                file_lists['unwritable_plates'].append(path)
                Session.rollback()

VERSION_RE = re.compile(r'(\w+\.)+\w+')
def add_qlp_file_record(source, path):
    """
    Attempt to create a QLP file record.  Adds to the current
    SQLAlchemy Session object, but does not commit (will
    rollback, however, if there is a problem)
    
    Returns (record, valid) tuple
    """
    path_id = source.path_id(path)
    valid_file = True
    try:
        plate = get_plate(path)
        if plate.host_software is not None and plate.host_software:
            version = VERSION_RE.search(plate.host_software).group(0)
        else:
            plate.host_software = 'Unknown'
            version = 'Unknown'        

        file_metadata = dict(version=version,
                             type='processed',
                             run_id=run_id(path_id),
                             read_status=0,
                             mtime=datetime.fromtimestamp(os.stat(path).st_mtime),
                             runtime=datetime.strptime(plate.host_datetime, '%Y:%m:%d %H:%M:%S'),
                             dirname=os.path.dirname(path_id),
                             basename=os.path.basename(path_id))
        qlbfile = QLBFile(**file_metadata)
    except Exception, e:
        # do not add file if the text file is busy
        # (exists, but does not contain valid data)
        if hasattr(e, 'errno'):
            if e.errno in (errno.ETXTBSY, errno.EBUSY):
                print e
                valid_file = False
                plate = None
                qlbfile = None
                return (qlbfile, plate, valid_file)
        
        print e
        file_metadata = {'run_id': run_id(path_id),
                         'dirname': os.path.dirname(path_id),
                         'basename': os.path.basename(path_id),
                         'read_status': -10,
                         'type': 'unknown',
                         'version': '',
                         'mtime': datetime.fromtimestamp(os.stat(path).st_mtime)}
        qlbfile = QLBFile(**file_metadata)
        valid_file = False
        plate = None
    
    try:
        Session.add(qlbfile)
        return (qlbfile, plate, valid_file)
    except IntegrityError, e:
        Session.rollback()
        # arbitrary
        qlbfile.run_id = duplicate_run_id(path_id)
        qlbfile.read_status = -1
        return (qlbfile, plate, False)

def add_qlb_file_record(source, path):
    """
    Attempt to create a QLP file record.  Adds to the current
    SQLAlchemy Session object, but does not commit (will
    rollback, however, if there is a problem)
    
    Returns (record, valid) tuple
    """
    path_id = source.path_id(path)
    valid_file = True
    try:
        qlwell = get_well(path)
        
        ## catch custom qlbs that do not containt sw_versions or time stamps
        if ( qlwell.host_software is not None and len(qlwell.host_software) > 0):
            software_version = qlwell.host_software.split()[-1]
        else:
            software_version = 'Unknown'

        if (qlwell.host_datetime is not None ):
            runtime_stamp    = datetime.strptime(qlwell.host_datetime, '%Y:%m:%d %H:%M:%S')
        else:
            runtime_stamp    = '0000-00-00 00:00:01'

        file_metadata = dict(version=software_version,
                             type='raw',
                             run_id=run_id(path_id),
                             read_status=0,
                             mtime=datetime.fromtimestamp(os.stat(path).st_mtime),
                             runtime=runtime_stamp,
                             dirname=os.path.dirname(path_id),
                             basename=os.path.basename(path_id))
        qlbfile = QLBFile(**file_metadata)
    except Exception, e:
        # do not add file if the text file is busy
        # (exists, but does not contain valid data)
        if hasattr(e, 'errno'):
            if e.errno in (errno.ETXTBSY, errno.EBUSY):
                print e
                valid_file = False
                qlwell = None
                qlbfile = None
                return (qlbfile, qlwell, valid_file)
        
        print e
        file_metadata = {'run_id': run_id(path_id),
                         'dirname': os.path.dirname(path_id),
                         'basename': os.path.basename(path_id),
                         'read_status': -10,
                         'type': 'unknown',
                         'version': '',
                         'mtime': datetime.fromtimestamp(os.stat(path).st_mtime)}
        qlbfile = QLBFile(**file_metadata)
        valid_file = False
        qlwell = None
    
    try:
        Session.add(qlbfile)
        return (qlbfile, qlwell, valid_file)
    except IntegrityError, e:
        Session.rollback()
        # arbitrary
        qlbfile.run_id = duplicate_run_id(path_id)
        qlbfile.read_status = -1
        return (qlbfile, qlwell, False)


def add_qlp_plate_record(qlplate, qlbfile):
    """
    Create a QLBPlate object based off a new QLBFile.  Adds to
    the current SQLAlchemy Session object, but does not commit (will
    rollback, however, if there is a problem)
    """
    valid_plate = True
    plate = None
    
    try:
        plate = QLBPlate()
        set_qlp_plate_record_attrs(plate, qlplate)
        plate.file = qlbfile
        Session.add(plate)
    except Exception, e:
        print e
        Session.rollback()
        valid_plate = False
        
    return (plate, valid_plate)

def update_qlp_plate_record(dbplate, qlplate):
    """
    :param qlplate: The QLPlate object read from the file.
    :param dbplate: The QLBPlate record in the DB.
    """
    try:
        set_qlp_plate_record_attrs(dbplate, qlplate, update_time=False)
        return True
    except Exception, e:
        return False

def set_qlp_plate_record_attrs(plate, qlplate, update_time=True):
    """
    plate = QLBPlate db record
    qlplate = QLPlate object from factory
    update_time: whether to bump up the last modified time.
    """    
    # dangit
    plate.host_machine = qlplate.host_machine
    plate.host_software = qlplate.host_software
    plate.host_user = qlplate.host_user
    plate.equipment_make = qlplate.equipment_make
    plate.equipment_model = qlplate.equipment_model
    plate.equipment_serial = qlplate.equipment_serial
    plate.file_desc = qlplate.file_description
    plate.channel_map = ','.join(qlplate.channel_names)
    plate.system_version = qlplate.system_version
    if qlplate.is_fam_vic:
        plate.dyeset = QLBPlate.DYESET_FAM_VIC
    elif qlplate.is_fam_hex:
        plate.dyeset = QLBPlate.DYESET_FAM_HEX
    elif qlplate.is_eva_green:
        plate.dyeset = QLBPlate.DYESET_EVA
    else:
        plate.dyeset = QLBPlate.DYESET_UNKNOWN

    
    # cc matrix
    ## round to 4 dec places becasue tables only record that much...
    color_compensation_matrix = qlplate.color_compensation_matrix
    if color_compensation_matrix:
        # TODO figure out in which order they are stored
        if len(color_compensation_matrix) > 0:
            plate.color_compensation_matrix_11 = round( color_compensation_matrix[0], 4)
            # TODO: resolve flow rate/ccm problem here
        if len(color_compensation_matrix) > 1:
            plate.color_compensation_matrix_12 = round( color_compensation_matrix[1], 4)
        if len(color_compensation_matrix) > 3:
            plate.color_compensation_matrix_21 = round( color_compensation_matrix[2], 4)
            plate.color_compensation_matrix_22 = round( color_compensation_matrix[3], 4)
        
    if update_time:
        plate.host_datetime = qlplate.host_datetime

# TODO: well_file over well_path?  just use one?
def add_qlb_well_record(well_file, well_name, proc_qlwell, raw_qlwell):
    """
    well_file: QLBFile object, file record (can be null)
    well_name: name of well
    proc_qlwell: QLWell that came from the plate (contains quantdata)
    raw_qlwell: QLWell that came from the raw well (contains metadata) (can be null)
    """
    # read well metadata, then read the well.
    valid_well = True
    well = QLBWell()
    
    for idx, t in enumerate(proc_qlwell.channels):
        channel = QLBWellChannel(channel_num=idx)
        well.channels.append(channel)
    
    # If the well file is null but there is still associated metadata,
    # try to get the metadata.
    try:
        set_qlb_well_record_attrs(well, well_name, proc_qlwell, raw_qlwell)
        if well_file:
            well.file = well_file
        else:
            well.file_id = -1
    except Exception, e:
        print e
        well = None
        valid_well = False
    return (well, valid_well)

def update_qlb_well_record(dbwell, well_name, proc_qlwell, raw_qlwell):
    try:
        set_qlb_well_record_attrs(dbwell, well_name, proc_qlwell, raw_qlwell)
        return True
    except Exception, e:
        return False

def set_qlb_well_record_attrs(dbwell, well_name, proc_qlwell, raw_qlwell):
    """
    :param dbwell: The QLBWell database record to update.
    :param well_name: The name of the well (e.g., A05)
    :param proc_qlwell: The QLWell object (from factory) that came from the processed plate.
    :param raw_qlwell: The QLWell object (from factory) that came from the raw data. (can be null)
    """
    # reproduce old get_well_file_metadata inside here (in one pass)
    
    # assume certain params come from raw data, certain from setup/quant
    if proc_qlwell:
        dbwell.well_name = well_name
        dbwell.experiment_name = proc_qlwell.experiment_name
        dbwell.experiment_type = proc_qlwell.experiment_type
        dbwell.experiment_comment = proc_qlwell.experiment_comment
        dbwell.sample_name = proc_qlwell.sample_name
        dbwell.flow_rate = proc_qlwell.flow_rate
        dbwell.num_channels = len(proc_qlwell.channels)
        # keeping convention -- event_count = total events
        dbwell.event_count = proc_qlwell.statistics.event_count
        dbwell.setup_version = proc_qlwell.setup_version
        dbwell.system_version = proc_qlwell.system_version
        dbwell.raw_data = proc_qlwell.raw_data
        ## round to 4 places becasue mysql does not record more
        if proc_qlwell.color_compensation_matrix:
            ccm = proc_qlwell.color_compensation_matrix
            if len(ccm) > 0:
                dbwell.color_compensation_matrix_11 = round( ccm[0], 4)
            if len(ccm) > 1:
                dbwell.color_compensation_matrix_12 = round( ccm[1], 4)
            if len(ccm) > 3:
                dbwell.color_compensation_matrix_21 = round( ccm[2], 4)
                dbwell.color_compensation_matrix_22 = round( ccm[3], 4)

        #updates qlplate
        if proc_qlwell.is_fam_vic:
            dbwell.dyeset = QLBPlate.DYESET_FAM_VIC
        elif proc_qlwell.is_fam_hex:
            dbwell.dyeset = QLBPlate.DYESET_FAM_HEX
        elif proc_qlwell.is_eva_green:
            dbwell.dyeset = QLBPlate.DYESET_EVA
        else:
            dbwell.dyeset = QLBPlate.DYESET_UNKNOWN       
 
        # now populate channel
        for i, proc_chan in enumerate(proc_qlwell.channels):
            db_chan = dbwell.channels[i]
            db_chan.channel_num = i
            db_chan.type = proc_chan.type
            db_chan.target = proc_chan.target
            # ignore channel format version, that's QLP-specific
            # algorithm version is currently in wrong format in DB; TODO revisit
            stats = proc_chan.statistics

            # for continuation's sake-- should be able to replace these with plate metrics
            # going forward

            # also check if this obsoletes write_images_stats_for_plate
            if stats:
                db_chan.width_sigma = stats.width_gating_sigma
                db_chan.min_quality_gating = stats.min_quality_gate
                db_chan.min_quality_gating_conf = stats.min_quality_gate_conf
                db_chan.min_width_gating = stats.min_width_gate
                db_chan.min_width_gating_conf = stats.min_width_gate_conf
                db_chan.max_width_gating = stats.max_width_gate
                db_chan.max_width_gating_conf = stats.max_width_gate_conf
                db_chan.quantitation_threshold = stats.threshold
                db_chan.quantitation_threshold_conf = stats.threshold_conf
                # TODO handle manual threshold in DB, or add flag
                db_chan.concentration = stats.concentration
                # sic
                db_chan.conf_upper_bound = stats.concentration_upper_bound
                db_chan.conf_lower_bound = stats.concentration_lower_bound
                # ignore peak counts for now -- use metrics instead
    
    if raw_qlwell:
        daq = raw_qlwell.data_acquisition_params
        if daq:
            dbwell.sample_rate = daq.sample_rate
            dbwell.daq_version = daq.version
            dbwell.daq_input_range = daq.input_range
            dbwell.daq_output_range = daq.output_range
            dbwell.daq_sample_format = daq.sample_format
            dbwell.resolution_bits = daq.resolution_bits
        dbwell.host_machine = raw_qlwell.host_machine
        if raw_qlwell.host_datetime is not None:
            dbwell.host_datetime = datetime.strptime(raw_qlwell.host_datetime, '%Y:%m:%d %H:%M:%S')
        dbwell.host_software = raw_qlwell.host_software
        dbwell.host_user = raw_qlwell.host_user
        dbwell.system_version = raw_qlwell.system_version
        dbwell.channel_map = ','.join(raw_qlwell.channel_names)
        if raw_qlwell.user_params:
            for k, v in raw_qlwell.user_params.items():
                # avoid duplicates for DACQ
                if k not in ('daq_input_range','daq_output_range','daq_sample_format',
                             'daq_version','flow_rate','num_channels','resolution_bits',
                             'sample_rate'):
                    setattr(dbwell, k, v)
        
    # now check for infinity
    for k, v in dbwell.__dict__.items():
        if v == float('inf'):
            # override to a million to avoid DB choke
            setattr(dbwell, k, 1000000)
        elif type(v) == type(float(4)) and math.isnan(v):
            setattr(dbwell, k, None) # or 0?
    
    for c in dbwell.channels:
        for k, v in c.__dict__.items():
            if v == float('inf'):
                setattr(c, k, 1000000)
            elif type(v) == type(float(4)) and math.isnan(v):
                setattr(c, k, None) # or 0?

def write_images_stats_for_plate(dbplate, qlplate, image_source, overwrite=False, override_plate_type=None):
    """
    Write plate metrics to the database and thumbnails to local storage,
    as dictated by image_source.

    Metrics will be related to the supplied dbplate (Plate model)
    qlplate is a QLPlate object derived from reading the QLP file.
    """
    if image_source.subdir_exists(str(dbplate.id)):
        if not overwrite:
            return
    else:
        image_source.make_subdir(str(dbplate.id))
    
    max_amplitudes = (24000, 12000)
    show_only_gated = False # keep default behavior
    if qlplate:
        for well_name, qlwell in sorted(qlplate.analyzed_wells.items()):
            # TODO: common lib?
            if well_channel_automatic_classification(qlwell, 0):
                fig = plot_fam_peaks(qlwell.peaks,
                                     threshold=qlwell.channels[0].statistics.threshold,
                                     max_amplitude=max_amplitudes[0])
            else:
                fig = plot_fam_peaks(qlwell.peaks,
                                     threshold=qlwell.channels[0].statistics.threshold,
                                     threshold_color='red',
                                     max_amplitude=max_amplitudes[0],
                                     background_rgb=MANUAL_THRESHOLD_FAM_BGCOLOR)
            fig.savefig(image_source.get_path('%s/%s_%s.png' % (dbplate.id, well_name, 0)), format='png', dpi=72)
            plt_cleanup(fig)

            if well_channel_automatic_classification(qlwell, 1):
                fig = plot_vic_peaks(qlwell.peaks,
                                     threshold=qlwell.channels[1].statistics.threshold,
                                     max_amplitude=max_amplitudes[1])
            else:
                fig = plot_vic_peaks(qlwell.peaks,
                                     threshold=qlwell.channels[1].statistics.threshold,
                                     threshold_color='red',
                                     max_amplitude=max_amplitudes[1],
                                     background_rgb=MANUAL_THRESHOLD_VIC_BGCOLOR)
                
            fig.savefig(image_source.get_path('%s/%s_%s.png' % (dbplate.id, well_name, 1)), format='png', dpi=72)
            plt_cleanup(fig)

            if qlwell.clusters_defined:
                threshold_fallback = qlwell.clustering_method == QLWell.CLUSTERING_TYPE_THRESHOLD
                fig = plot_cluster_2d(qlwell.peaks,
                                      width=60,
                                      height=60,
                                      thresholds=[qlwell.channels[0].statistics.threshold,
                                                  qlwell.channels[1].statistics.threshold],
                                      boundaries=[0,0,12000,24000],
                                      show_axes=False,
                                      antialiased=True,
                                      unclassified_alpha=0.5,
                                      use_manual_clusters=not well_channel_automatic_classification(qlwell),
                                      highlight_thresholds=threshold_fallback)
                fig.savefig(image_source.get_path('%s/%s_2d.png' % (dbplate.id, well_name)), format='png', dpi=72)
                plt_cleanup(fig)
        
        pm = [pm for pm in dbplate.plate.metrics if pm.reprocess_config_id is None]
        for p in pm:
            Session.delete(p)

        plate = dbplate_tree(dbplate.plate.id)
        
        # override plate_type if supplied (another artifact of bad abstraction)
        if override_plate_type:
            plate.plate_type = override_plate_type

        # this relies on apply_template/apply_setup working correctly on plate addition
        # verify on DR 10005 plate that this works
        if plate.plate_type and plate.plate_type.code in beta_plate_types:
            plate_metrics = get_beta_plate_metrics(plate, qlplate)
        else:
            plate_metrics = process_plate(plate, qlplate)
        Session.add(plate_metrics)

def trigger_plate_rescan(plate):
    """
    Given a Plate object, trigger a cron rescan by setting
    the DB mtime back to prior to the actual OS modified time
    of the file.

    A parent function is responsible for committing this change
    to the DB.
    """
    if plate.qlbplate and plate.qlbplate.file:
        plate.qlbplate.file.mtime = plate.qlbplate.file.mtime - timedelta(0,60,0)
