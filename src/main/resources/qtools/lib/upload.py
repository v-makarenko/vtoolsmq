"""
Helper methods for uploading QLP files from
a web form onto the filesystem.
"""
from pylons import config
from qtools.lib.storage import QLBImageSource, QLBPlateSource
from qtools.lib.platescan import scan_plate
from qtools.model import Session, Box2
import os, re, shutil

HOST_DATETIME_SPLIT_RE = re.compile(r'[\:\s\/]+')
PATHSEP_RE = re.compile(r'[\\/]+')

def upload_basename(path):
    return PATHSEP_RE.split(path)[-1]

def get_create_plate_box( plateobj ):
    """ 

    Returns a box2 object
    """
    serial = plateobj.equipment_serial

    # if not serial in plate just terminate...
    if not serial:
        return None

    # check for varous code permuations
    for code_ex in ['', 'p', 'f', 'd']:
        code = code_ex +  serial
        box2 = Session.query(Box2).filter_by(code=code).first()
        if box2:
            break
    
    # otherwise we check for box and create it if it is not there...

    if not box2:
        ### mostlikely a production box so set it to that:
        code = 'p' +  serial
        src_dir = "DR %s" % serial
        box2 = Box2(name=u'Prod %s' % serial, code=code, src_dir=src_dir, \
                      reader_type = Box2.READER_TYPE_WHOLE,\
                      fileroot=config['qlb.fileroot.register_fileroot'], active=True)
        Session.add(box2)
        box2.active = True

        local_plate_source = QLBPlateSource(config, [box2])
        dirname = local_plate_source.real_path(box2.fileroot, src_dir)
        try:
            if( not os.path.isdir( dirname) ):
                os.mkdir(dirname)
            Session.commit()
        except Exception, e:
            """Some error message?"""
            Session.rollback()
            return None

    return box2


def save_plate_from_upload_request(request_plateobj, upload_plate, box2, plate_type_obj=None):
    """
    UNSAFE METHOD.  ALSO, UGLY ABSTRACTION.

    Saves the plate from the upload folder.  Writes a directory to disk in the
    right place in order to do so.

    Returns a plateobj (Plate), which needs to be committed.

    :param request_plateobj: The enctype/multipart-form object on the request POST.
    :param upload_plate: The QLPlate object derived from the plateobj by the validator.
    :param box2: The DR to assign the plate to.
    :param plate_type_obj: The PlateType object to assign to the plate.
    """
    run_time_minute = upload_plate.host_datetime[:-3]
    filename = upload_basename(request_plateobj.filename)

    folder_name = filename.split('.')[0]
    folder_time = HOST_DATETIME_SPLIT_RE.sub('-', run_time_minute)
    folder = "%s/%s_%s" % (box2.src_dir, folder_name, folder_time)
    
    image_root = config['qlb.image_store']
    image_source = QLBImageSource(image_root)
    local_plate_source = QLBPlateSource(config, [box2])
    dirname = local_plate_source.real_path(box2.fileroot, folder)

    # probably need a directory creation service rather than relying
    # on permissions to work.
    #
    # THIS IS NOT A GOOD WAY TO DO THIS OUTSIDE THE LAB.
    # rethink this for customers-- probably include a predefined
    # location for all plates.
    if not os.path.exists(dirname):
        # this is subject to QLHyperV permissions.  Might not work.
        os.mkdir(dirname)
    # override in all cases
    
    # don't put this in try-catch; want to propagate errors to email first
    path = '%s/%s' % (dirname, filename)
    plate_file = open(path, 'wb')
    request_plateobj.file.seek(0)
    shutil.copyfileobj(request_plateobj.file, plate_file)
    request_plateobj.file.close()
    plate_file.close()
    plateobj = scan_plate(local_plate_source, image_source, box2.fileroot, path, plate_type=plate_type_obj)
    return plateobj
