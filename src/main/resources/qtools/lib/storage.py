"""
Classes that abstract the selection and iteration of QLP files
from the volumes specified by the app configuration file.

Contains iterators for correctly named plates and wells and images
in a file system, as well as classes that map app-relative paths
to filesystem paths.
"""
import os, re, shutil

QLB_TIMESTAMP_FILE_RE = re.compile(r'\d+\-\d+\-\d+\-\d+\-\d+$')

def no_metadata_copytree(src, dst, symlinks=False, ignore=None):
    names = os.listdir(src)
    if ignore is not None:
        ignored_names = ignore(src, names)
    else:
        ignored_names = set()

    os.makedirs(dst)
    errors = []
    for name in names:
        if name in ignored_names:
            continue
        srcname = os.path.join(src, name)
        dstname = os.path.join(dst, name)
        try:
            if symlinks and os.path.islink(srcname):
                linkto = os.readlink(srcname)
                os.symlink(linkto, dstname)
            elif os.path.isdir(srcname):
                no_metadata_copytree(srcname, dstname, symlinks, ignore)
            else:
                shutil.copyfile(srcname, dstname)
        except (IOError, os.error) as why:
            errors.append((srcname, dstname, str(why)))
        except shutil.Error as err:
            errors.extend(err.args[0])

    if errors:
        raise shutil.Error(errors)


class QLBFileSource(object):
    """
    Abstracts file operations against a store of QLB files.
    
    TODO: this can be made an interface later, right now just go against the
    qlhyperv datastore.
    """
    def __init__(self, root):
        self.root = root

    def path_id(self, path):
        """
        Returns the path id, based off the root (and any other params if you subclass)
        """
        return os.path.relpath(path, self.root)

    def real_path(self, path):
        return os.path.join(self.root, path)

    def full_path(self, dirname, basename):
        return os.path.join(self.root, dirname, basename)


class QLStorageSource(object):
    """
    Sets up an abstraction layer to retrieve files from a local (or future:
    remote) filesystem.

    Constructed with a configuration.
    """
    def __init__(self, config):
        self.volume_dict = dict()
        volumes = config.get('qlb.fileroots', None)
        if volumes:
            for vol in volumes.split(','):
                location = config.get('qlb.fileroot.%s' % vol, None)
                if location:
                    self.volume_dict[vol] = QLBFileSource(location)

    def qlbwell_path(self, well):
        """
        Given a QLBWell, return the path to the QLB.  Requires the QLBWell to
        be part of a QLBPlate->Plate hierarchy with a known instrument.

        This kills the abstraction a bit but it's more direct; may belong
        in a different file?
        """
        if well and well.plate and well.file and well.plate.plate.box2:
            dirname = well.file.dirname
            basename = well.file.basename
            # could use box2_root abstraction here
            fileroot = well.plate.plate.box2.fileroot
            volume = self.volume_dict.get(fileroot, None)
            if volume:
                return volume.full_path(dirname, basename)
            else:
                raise ValueError("No qlb.fileroot configured for %s fileroot: %s" % (well.plate.plate.box2.name, fileroot))
        else:
            raise ValueError("Could not determine QLB path -- plate or DR unknown")

    def qlbplate_path(self, plate):
        """
        Given a QLBPlate, return the path to the QLP. Requires the QLBPlate to
        be part of a QLBPlate->Plate hierarchy with a known instrument.
        """
        if plate and plate.plate and plate.file and plate.plate.box2:
            dirname = plate.file.dirname
            basename = plate.file.basename
            # could use box2_root abstraction here
            fileroot = plate.plate.box2.fileroot
            volume = self.volume_dict.get(fileroot, None)
            if volume:
                return volume.full_path(dirname, basename)
            else:
                raise ValueError("No qlb.fileroot configured for %s fileroot: %s" % (plate.plate.box2.name, fileroot))
        else:
            raise ValueError("Could not determine QLP path -- plate or DR unknown")


    def plate_path(self, plate):
        """
        Given a Plate, return the path to the QLP.  Requires the Plate to have a
        QLBPlate associated with it, and a known instrument.
        """
        if plate and plate.qlbplate and plate.qlbplate.file and plate.box2:
            dirname = plate.qlbplate.file.dirname
            basename = plate.qlbplate.file.basename
            # could use box2_root abstraction here
            fileroot = plate.box2.fileroot
            volume = self.volume_dict.get(fileroot, None)
            if volume:
                return volume.full_path(dirname, basename)
            else:
                raise ValueError("No qlb.fileroot configured for %s fileroot: %s" % (plate.box2.name, fileroot))
        else:
            raise ValueError("Could not determine QLP path -- file or DR unknown")

    def plate_root(self, plate):
        if plate and plate.qlbplate and plate.qlbplate.file and plate.box2:
            # could use box2_root abstraction method here
            fileroot = plate.box2.fileroot
            volume = self.volume_dict.get(fileroot, None)
            if volume:
                return volume.root
            else:
                raise ValueError("No qlb.fileroot configured for %s fileroot: %s" % (plate.box2.name, fileroot))
        else:
            raise ValueError("Could not determine QLP path -- file or DR unknown")

    def box2_root(self, box2):
        if box2:
            fileroot = box2.fileroot
            volume = self.volume_dict.get(fileroot, None)
            if volume:
                return volume.root
            else:
                raise ValueError("No qlb.fileroot configured for %s fileroot %s" % (box2.name, fileroot))
        else:
            return ValueError("Could not determine Box2 path -- DR unknown")

    def box2_relative_path(self, box2, dirname, basename):
        if box2:
            fileroot = box2.fileroot
            volume = self.volume_dict.get(fileroot, None)
            if volume:
                return volume.full_path(os.path.join(box2.src_dir, dirname), basename)
            else:
                raise ValueError("No qlb.fileroot configured for %s fileroot: %s" % (box2.name, fileroot))
        else:
            raise ValueError("Could not determine relative path -- DR unknown")

    def path_id(self, volume, path):
        volume = self.volume_dict.get(volume, None)
        if not volume:
            raise ValueError("No qlb.fileroot configured for %s fileroot" % volume)
        else:
            return volume.path_id(path)

    def real_path(self, volume_name, path):
        volume = self.volume_dict.get(volume_name, None)
        if not volume:
            raise ValueError("No qlb.fileroot configured for %s fileroot" % volume_name)
        else:
            return volume.real_path(path)

    def full_path(self, volume_name, dirname, basename):
        volume = self.volume_dict.get(volume_name, None)
        if not volume:
            raise ValueError("No qlb.fileroot configured for %s fileroot" % volume_name)
        else:
            return volume.full_path(dirname, basename)

    def file_source(self, fileroot):
        """
        More for backwards compatibility with QLBFileSource

        full_path et al is same as self.file_source(volume).full_path(path)
        """
        # TODO throw exception instead?
        return self.volume_dict.get(fileroot, None)


class QLBPlateSource(QLStorageSource):
    """
    Yield the list of plate files that are correctly named (correlated
    with their parent folder) and QLPs.  Only look one level down.
    """
    def __init__(self, config, registered_drs):
        super(QLBPlateSource, self).__init__(config)
        self.root_dirs = []
        for dr in registered_drs:
            # CAREFUL -- if active flag set to false, don't look for plates
            if not dr.active:
                continue

            fileroot = dr.fileroot
            src_dir = dr.src_dir
            # avoid exception for now on ignore
            if fileroot in self.volume_dict:
                if os.path.exists(self.volume_dict[fileroot].real_path(src_dir)):
                    self.root_dirs.append((fileroot, src_dir))


    def volume_path_iter(self):
        # only look one level down for each src_dir
        folders = []
        for fileroot, src_dir in self.root_dirs:
            root_dir = self.volume_dict[fileroot].real_path(src_dir)
            for root, dirnames, files in os.walk(root_dir):
                for dir in dirnames:
                    folders.append((fileroot, os.path.join(root, dir)))
                break

        for fileroot, folder in folders:
            # get the correct QLP folder name
            match = QLB_TIMESTAMP_FILE_RE.search(folder)
            # potential problem: this may skip future rev,
            # pretty easy fix, though
            if match and match.start() > 0:
                base = os.path.basename(folder[:match.start()-1])
            else:
                base = os.path.basename(folder)
            qlp = '%s.qlp' % os.path.join(folder, base)
            if os.path.isfile(qlp):
                yield (fileroot, qlp)



class QLBImageSource(object):
    def __init__(self, root, isLocal=True):
        self.root = root
        self.isLocal = isLocal


    def process_subdir(self, dir_id):
        ## limit for the number of sub directories is 31998
        ## reserve 98 for extra sub dirs        

        if ( dir_id.isdigit() ):
            ## refactor to generalize this at some point!
            subdir = ''
            if( long(dir_id) > 31900 and long(dir_id) <= 63800):
                subdir = 'B'
            elif( long(dir_id) > 63800 and long(dir_id) <= 95700):
                subdir = 'C'
        
            #check directory exists only if this is a local dir
            if (self.isLocal):
                full_path = os.path.join(self.root, subdir )
                if not os.path.exists(full_path):
                    os.mkdir(full_path)

            processed_dir = os.path.join( subdir,  dir_id )      
        else:
            print 'Unexpected value in qtools.lib.storge, whats up?'
            print dir_id
            print dir_id.__class__
            print dir( dir_id )
            processed_dir = str( dir_id ) 

        return processed_dir

    def subdir_exists(self, dir_path):
        dir_path = self.process_subdir(dir_path)
        return os.path.exists(os.path.join(self.root, dir_path))

    def make_subdir(self, dir_path):
        dir_path = self.process_subdir(dir_path)

        full_path = os.path.join(self.root, dir_path)
        if not os.path.exists(full_path):
            os.mkdir(full_path)

    # TODO superclass that just has a root dir
    def get_path(self, path):
        path_parts = path.split(os.path.sep)
        path_parts[0] = self.process_subdir( path_parts[0] )
        return os.path.join(self.root, *path_parts)

class QLPReprocessedFileSource(object):
    """
    File source for reprocessed QLPs.
    """
    def __init__(self, root, reprocess_config):
        self.root = root
        self.rp_code = reprocess_config.code

    def full_path(self, analysis_group, dbplate):
        """
        Given the specified analysis group and original plate,
        return the address of the QLP that is part of the
        specified analysis group and reprocessed by this
        file source's reprocess configuration.

        If that doesn't make sense, it's because I'm dog tired. #btwd
        """
        return os.path.sep.join([self.root, "ag%s" % analysis_group.id,
                                 self.rp_code,
                                 dbplate.qlbplate.file.dirname,
                                 dbplate.qlbplate.file.basename])

class QSAlgorithmSource(object):
    """
    Identifies a source of QuantaSoft algorithms to use as
    reprocess targets.  Relies on configuration settings.
    """
    def __init__(self, config):
        self.source_root = config.get('qlb.quantasoft_source_root')
        self.sink_root = config.get('qlb.quantasoft_reprocess_sink')

    def algorithm_folder_iter(self):
        """
        Iterates over the list of available release candidates.
        """
        folders = []
        for root, dirnames, files in os.walk(self.source_root):
            if 'QuantaSoft.exe' in files:
                yield os.path.relpath(root, self.source_root)

    def source_path_exists(self, path):
        return os.path.exists(os.path.join(self.source_root, path))

    def add_reprocessor(self, src_folder, target_name):
        """
        Copy the specified algorithm source to the bank of
        reprocessors, under the specified target name.
        Throws problems (either IOError or shutil.Error)
        if there is a problem.

        :param src_folder: The folder (relative to source root) to copy.
        :param target_dir: The name of the folder to write in the reprocess folder.
        """
        full_src = os.path.join(self.source_root, src_folder)
        if not os.path.exists(full_src):
            raise IOError('Source does not exist: %s' % src_folder)
        target = os.path.join(self.sink_root, target_name)
        if os.path.exists(target):
            raise IOError('Destination folder already exists: %s' % target_name)

        no_metadata_copytree(full_src, target)
