from . import QToolsCommand, WarnBeforeRunning, DoNotRun
import re
from qtools.lib.plate import *
from qtools.lib.platescan import scan_plates, trigger_plate_rescan
from qtools.lib.platesetup import generate_daily_setups, generate_custom_setup
from qtools.lib.storage import QLBImageSource, QLBPlateSource, QLStorageSource
from qtools.lib.qlb_factory import get_plate
from qtools.lib.dropletgen import DGLogSource, read_dg_log
from qtools.model import Session, QLBPlate, QLBWellChannel, Plate, PlateTemplate, PlateSetup, DropletGenerator, DropletGeneratorRun, Box2
from qtools.model.sequence import SequenceGroup

from sqlalchemy import desc, and_, func
from sqlalchemy.orm import joinedload_all

QLB_TIMESTAMP_RE = re.compile(r'\d+\-\d+\-\d+\-\d+\-\d+')

class UpdatePlatesCommand(QToolsCommand):
    """
    The main command used by a cron job to look
    for new plates in the plate source and process
    those plates.
    """
    summary = "Looks for changes to plates."
    usage = "paster --plugin=qtools update-plates [config]"
    
    def command(self):
        app = self.load_wsgi_app()

        # TODO use better filter for production instrument
        drs = Session.query(Box2).filter(Box2.fileroot != 'archive').order_by(Box2.name)
        source = QLBPlateSource(app.config, drs)
        
        image_root = app.config['qlb.image_store']
        image_source = QLBImageSource(image_root)
        
        scan_plates(source, image_source)


@WarnBeforeRunning("You probably don't want to do this.  Read the docs before running.")
class LinkQLBPlatesCommand(QToolsCommand):
    """
    This should not need to be run.  Should only be run if
    a QLBPlate object lacks an appropriate corresponding
    Plate record.

    This was used wayyyy early when scanning for plates
    via update-plates did not produce a Plate record,
    but this should not happen now.
    """
    summary = "Detects metadata-compatible plates from QLP folder names."
    usage = "paster --plugin=qtools link-qlb-plates"
    
    def command(self):
        self.load_wsgi_app()
        
        unknown_plates = Session.query(QLBPlate).filter(QLBPlate.plate == None)
        for qlbplate in unknown_plates:
            try:
                plate = plate_from_qlp(qlbplate)
                Session.add(plate)
                qlbplate.plate = plate
                Session.commit()
            except Exception:
                Session.rollback()

class LinkPlateSetupCommand(QToolsCommand):
    """
    Manually links a loaded plate ID (corresponding to an
    ID you see in /plate/view/XXX) to a plate setup ID (containing
    information about consumables, layout, operator, etc.)

    PlateSetups were used more in the original QX100 beta test,
    when we tracked consumables alongside plates.
    """
    summary = "Links plates to setups."
    usage = "paster --plugin-qtools link-plate-setup [plate id] [plate setup id]"
    min_args = 2

    def command(self):
        self.load_wsgi_app()

        plate_id = self.args[0]
        plate_setup_id = self.args[1]
        plate = Session.query(Plate).get(plate_id)
        plate_setup = Session.query(PlateSetup).get(plate_setup_id)
        if plate and plate_setup:
            inherit_setup_attributes(plate, plate_setup)
            trigger_plate_rescan(plate) # in case metrics need recalc
            Session.commit()
            print "Plate linked."
        else:
            print "Plate or setup not found (%s, %s)" % (plate_id, plate_setup_id)

class LinkPlateTemplateCommand(QToolsCommand):
    """
    Manually links a loaded plate ID (corresponding to an
    ID you see in /plate/view/XXX) to a plate template ID
    (containing the information stored when you specify
    metadata when naming a plate).  This should be
    detected automatically if a user uses the plate name,
    but if you need to reconcile this, use this command.
    """
    summary = "Links plates to plate templates."
    usage = "paster --plugin-qtools link-plate-template [plate id] [plate template id]"
    min_args = 2
    
    def command(self):
        self.load_wsgi_app()
        
        # TODO: this might be better with keywords
        plate_id = self.args[0]
        plate_template_id = self.args[1]
        plate = Session.query(Plate).get(plate_id)
        plate_template = Session.query(PlateTemplate).get(plate_template_id)
        if plate and plate_template:
            inherit_template_attributes(plate, plate_template)
            trigger_plate_rescan(plate) # in case metrics need recalc
            Session.commit()
            print "Plate linked."
        else:
            print "Plate or template not found: (%s,%s)" % (plate_id, plate_template_id)

# TODO: eliminate as part of scrubbing PlateSetup in favor of templates
class AddBetaSetupsCommand(QToolsCommand):
    summary = "Generates the new list of beta plates to run today."
    usage = "paster --plugin=qtools add-beta-setups"

    def command(self):
        self.load_wsgi_app()
        if len(self.args) > 1:
            day_of_week_override = int(self.args[0])
        else:
            day_of_week_override = None
        
        if len(self.args) > 2:
            weekdays_ahead = int(self.args[1])
        else:
            weekdays_ahead = 1
        
        setups = generate_daily_setups(weekdays_ahead=weekdays_ahead, day_of_week_override=day_of_week_override)
        Session.add_all(setups)
        Session.commit()

# TODO: eliminate as part of scrubbing PlateSetup in favor of templates
class AddCustomBetaSetupCommand(QToolsCommand):
    summary = "Custom specify a beta plate to run."
    usage = "paster --plugin=qtools add-beta-custom"

    def command(self):
        self.load_wsgi_app()
        setup = generate_custom_setup(*self.args[:-1])
        Session.add(setup)
        Session.commit()

@DoNotRun("Plate scores are already computed for each plate.")
class BackfillPlateScoresCommand(QToolsCommand):
    """
    Used to backfill blank 'plate scores' when we were
    having weekly droplet contest.  A plate score is
    high if it is annotated and varied in its
    annotation, as you're getting more bits of
    information.
    """
    summary = "Backfills scores for plates."
    usage = "paster --plugin=qtools backfill-plate-scores"
    
    def command(self):
        self.load_wsgi_app()
        
        qlbplates = Session.query(QLBPlate).\
                         filter(and_(QLBPlate.file_id != None, QLBPlate.plate_id != None)).\
                         order_by(desc(QLBPlate.id)).\
                         options(joinedload_all(QLBPlate.plate, innerjoin=True))
        
        for qlbplate in qlbplates:
            qlbplate.plate.score = Plate.compute_score(qlbplate.plate)
            print "%s: %s points" % (qlbplate.plate.id, qlbplate.plate.score)
            Session.commit()

@DoNotRun("Dyesets should have been computed/are computed for each plate.")
class BackfillDyesetCommand(QToolsCommand):
    """
    Used to backfill the dyeset attribute on the
    QLBPlate (qlbplate) table.  Should not need
    to be run again going forward, as the dyesets
    are added when a plate is added.
    """
    summary = "Backfills dyesets for plates."
    usage = "paster --plugin=qtools backfill-dyesets [config]"

    def command(self):
        app = self.load_wsgi_app()
        min_id = 0
        if len(self.args) > 1:
            min_id = self.args[0]
        storage = QLStorageSource(app.config)

        qlbplates = Session.query(QLBPlate).filter(QLBPlate.id > min_id).order_by('id').all()
        for qlbplate in qlbplates:
            try:
                path = storage.qlbplate_path(qlbplate)
            except Exception:
                print "Could not find plate: %s (%s)" % (qlbplate.plate.name if qlbplate.plate else 'Name unknown', qlbplate.id)
                continue
            try:
                qlplate = get_plate(path)
            except Exception:
                print "Could not read plate: %s (%s)" % (qlbplate.plate.name if qlbplate.plate else 'Name Unknown', qlbplate.id)
                continue

            if qlplate.is_fam_vic:
                qlbplate.dyeset = QLBPlate.DYESET_FAM_VIC
            elif qlplate.is_fam_hex:
                qlbplate.dyeset = QLBPlate.DYESET_FAM_HEX
            elif qlplate.is_eva_green:
                qlbplate.dyeset = QLBPlate.DYESET_EVA
            else:
                qlbplate.dyeset = QLBPlate.DYESET_UNKNOWN

            print "Assigned dye %s - %s (%s)" % (qlbplate.dyeset, qlbplate.plate.name if qlbplate.plate else 'Name Unknown', qlbplate.id)
            Session.commit()

class BackfillChannelSequenceGroupCommand(QToolsCommand):
    """
    This one may still be useful.  Given all the assay names
    we've run, find the well channels which match those
    targets (exactly), and assign the sequence group id of
    that well channel to the sequence group id of the assay.

    Trend tools do LIKE searches to pick out wells run with
    a certain assay, which given the poor track record in the
    lab of correctly naming plates may ultimately be more
    robust.  But this can still be used should one decide
    to do more with the assay->channel relation.
    """
    summary = 'backfills sequence_group_ids based on targets.'
    usage = 'paster --plugin=qtools backfill-channel-sequence-groups'

    def command(self):
        self.load_wsgi_app()

        sequence_groups = Session.query(SequenceGroup).all()
        for sg in sequence_groups:
            try:
                print "Backfilling channels for %s" % sg.name

                channels = Session.query(QLBWellChannel).filter_by(target=sg.name)
                for c in channels:
                    c.sequence_group_id = sg.id

                Session.commit()
            except Exception:
                import sys, traceback
                traceback.print_exc(file=sys.stdout)
                Session.rollback()
                continue

@WarnBeforeRunning("Droplet generator logs are not normally saved anymore.  This may not do much.")
class ReadDropletGeneratorLogsCommand(QToolsCommand):
    """
    We're no longer normally syncing logs from the
    droplet generators, so this should be deprecated.

    But, read the droplet generator logs and analyze
    for certain variables.
    """
    summary = "Reads droplet generator logs (deprecated)."
    usage = "paster --plugin=qtools process-dg-logs"
    
    def command(self):
        app = self.load_wsgi_app()
        root = app.config['qlb.dg_root']
        top_folders = app.config['qlb.top_dg_folders']
        source = DGLogSource(root, top_folders)

        min_file_dict = dict(Session.query(DropletGeneratorRun.dirname,
                                      func.max(DropletGeneratorRun.basename).label('last_file')).\
                                group_by(DropletGeneratorRun.dirname).all())
        
        min_file_prefix = '2011-03-21'

        dgs = Session.query(DropletGenerator).all()
        dg_ids = [dg.id for dg in dgs]

        for dirname, basename in source.path_iter(min_file_name=min_file_prefix, min_file_dict=min_file_dict):
            print dirname, basename
            dg_run = read_dg_log(source.full_path(dirname, basename))
            if not dg_run:
                continue
            dg_run.dirname = dirname
            dg_run.basename = basename
            if dg_run.droplet_generator_id in dg_ids:
                Session.add(dg_run)
                Session.commit()
