from pyqlb.nstats.peaks import cluster_1d
from pyqlb.nstats.well import well_channel_automatic_classification, accepted_peaks
from pyqlb.objects import QLWell

from qtools.lib.metrics import WellChannelMetricCalculator, DEFAULT_NTC_POSITIVE_CALCULATOR
from qtools.lib.metrics.db import *
from qtools.lib.storage import QLBImageSource, QLStorageSource, QLPReprocessedFileSource
from qtools.lib.qlb_factory import get_plate
from qtools.model import AnalysisGroup, Plate, ReprocessConfig, Box2, PlateMetric
from qtools.model.meta import Session

from sqlalchemy.orm import joinedload

from . import QToolsCommand, WarnBeforeRunning

class ComputeBetaAnalysisGroupMetricsCommand(QToolsCommand):
    """
    This is the workhorse command of algorithm reprocessing.
    Given the ID of an analysis group, and an optional reprocess config
    code (e.g., 'qs129'), compute the plate metrics for the group.

    Take into consideration the plate types and layouts, should the
    plate have a particular plate type.
    """
    summary = "Computes beta plate metrics for an entire analysis group."
    usage = "paster --plugin=qtools compute-beta-analysis-group-metrics [analysis group id] [config]"

    def command(self):
        app = self.load_wsgi_app()

        # enforce config.ini
        if len(self.args) < 2:
            raise ValueError, self.__class__.usage

        analysis_group_id = int(self.args[0])
        if len(self.args) == 3:
            reprocess_config = Session.query(ReprocessConfig).filter_by(code=self.args[1]).one()
            reprocess_config_id = reprocess_config.id
        else:
            reprocess_config = None
            reprocess_config_id = None

        analysis_group = Session.query(AnalysisGroup).get(analysis_group_id)
        if not analysis_group:
            raise ValueError, "No analysis group for id %s" % analysis_group_id

        plates = analysis_group.plates
        # todo: add in reprocess config id
        for plate in plates:
            pm = [pm for pm in plate.metrics if pm.reprocess_config_id == reprocess_config_id]
            # should only be of length 1, but just to be safe
            for p in pm:
                Session.delete(p)

        # TODO: how to make this whole operation transactional
        Session.commit()

        # this is a little tricky in the ORM world.  only get the
        # ids of the analysis_group plates, so that you can load the plate
        # and all the necessary children
        plate_ids = [plate.id for plate in plates]

        if reprocess_config_id is None:
            storage = QLStorageSource(app.config)

            for id in plate_ids:
                dbplate = dbplate_tree(id)
                plate_path = storage.plate_path(dbplate)
                print "Reading/updating metrics for %s" % plate_path
                qlplate = get_plate(plate_path)
                if not qlplate:
                    print "Could not read plate: %s" % plate_path
                    continue

                plate_metrics = get_beta_plate_metrics(dbplate, qlplate)
                Session.add(plate_metrics)
                del qlplate
        else:
            data_root = app.config['qlb.reprocess_root']
            file_source = QLPReprocessedFileSource(data_root, reprocess_config)

            for id in plate_ids:
                dbplate = dbplate_tree(id)
                # TODO: right abstraction?
                plate_path = file_source.full_path(analysis_group, dbplate)

                print "Reading/updating metrics for %s" % plate_path
                qlplate = get_plate(plate_path)
                if not qlplate:
                    print "Could not read plate: %s" % plate_path
                    continue

                plate_metrics = get_beta_plate_metrics(dbplate, qlplate, reprocess_config)
                Session.add(plate_metrics)
                del qlplate


        Session.commit()



class AddAnalysisGroupCommand(QToolsCommand):
    summary = "Adds an analysis group with the specific name"
    usage = "paster --plugin=qtools add-analysis-group [name] [config]"
    
    def command(self):
        app = self.load_wsgi_app()

        # enforce name.ini
        if len(self.args) < 2:
            raise ValueError, self.__class__.usage
        
        name = self.args[0]

        ag = AnalysisGroup(name=name)
        Session.add(ag)
        Session.commit()
        print "Created analysis group %s with id=%s" % (ag.name, ag.id)

class AddAnalysisGroupPlateCommand(QToolsCommand):
    summary = "Adds a plate to an analysis group"
    usage = "paster --plugin=qtools add-analysis-plate [plate id] [group id] [config]"

    def command(self):
        app = self.load_wsgi_app()

        # enforce name.ini
        if len(self.args) < 3:
            raise ValueError, self.__class__.usage
        
        plate_id = int(self.args[0])
        ag_id = int(self.args[1])

        plate = Session.query(Plate).get(plate_id)
        if not plate:
            raise ValueError, "Invalid plate id: %s" % plate_id
        
        ag = Session.query(AnalysisGroup).get(ag_id)
        if not ag:
            raise ValueError, "Invalid analysis group id: %s" % ag_id
        
        ag.plates.append(plate)
        Session.commit()

class AddAnalysisGroupPlatesCommand(QToolsCommand):
    summary = "Add a bunch of plates to an analysis group"
    usage = "paster --plugin=qtools add-analysis-plates [group id] [plate_id]+ [config]"

    def command(self):
        app = self.load_wsgi_app()
        
        # enforce at least one plate
        if len(self.args) < 3:
            raise ValueError, self.__class__.usage
    
        group_id = int(self.args[0])
        ag = Session.query(AnalysisGroup).get(group_id)
        if not ag:
            raise ValueError, "Invalid analysis group id: %s" % group_id
        
        for i in range(1,len(self.args)-1):
            plate_id = int(self.args[i])
            plate = Session.query(Plate).get(plate_id)
            if not plate:
                print "Could not find plate with id %s" % plate_id
                continue
            ag.plates.append(plate)
        
        Session.commit()

class BackfillPlateMetricsCommand(QToolsCommand):
    summary = "Backfills beta plate metrics for a plate id."
    usage = "paster --plugin=qtools backfill-plate-metrics [plate id] [config]"

    def command(self):
        app = self.load_wsgi_app()

        # enforce config.ini
        if len(self.args) < 2:
            raise ValueError, self.__class__.usage
        
        plate_id = int(self.args[0])

        plate = dbplate_tree(plate_id)
        if not plate:
            raise ValueError, "Invalid plate id: %s" % plate_id
        
        storage = QLStorageSource(app.config)

        # for now, no reprocessing.
        plate_path = storage.plate_path(plate)
                                        
        qlplate = get_plate(plate_path)
        if not qlplate:
            raise ValueError, "Could not read plate: %s" % plate_path
        
        try:
            plate_metrics = plate.metrics[0]
            self.process_plate( qlplate, plate_metrics)
        except Exception, e:
            import sys, traceback
            traceback.print_exc(file=sys.stdout)
            Session.rollback()
            return
        Session.commit()
    
    def process_plate(self, qlplate, plate_metric):
        """
        Override me!
        """
        pass




@WarnBeforeRunning("This will iterate over all plate metric records, which can be a time-consuming operation.")
class BackfillAllPlateMetricCommand(QToolsCommand):
    """
    Parent command to a backfill plate metric operation.  Subclasses should
    override the process_plate method.
    """
    summary = "Iterate over all plates with plate metrics stored and populate a value."

    def command(self):
        app = self.load_wsgi_app()
        storage = QLStorageSource(app.config)

         # enforce config.ini
        if len(self.args) > 1:
            plate_id = int(self.args[0])
        else:
            plate_id = 1 ## default start....

        plate_metrics = Session.query(PlateMetric).filter(PlateMetric.plate_id >= plate_id)\
                               .options(joinedload(PlateMetric.plate, innerjoin=True))\
                               .options(joinedload(PlateMetric.reprocess_config))

        # TODO come up with version that takes care of reprocessed plates as well
        # (by iterating through analysis groups, most likely)
        for pm in plate_metrics:
            if pm.from_reprocessed:
                continue

            plate = dbplate_tree(pm.plate_id)
            try:
                plate_path = storage.plate_path(plate)
            except Exception:
                print "Could not read plate: %s" % pm.plate_id
                continue

            try:
                qlplate = get_plate(plate_path)
            except Exception:
                print  "Could not read plate: %s" % plate_path
                continue

            if not qlplate:
                print "Could not read plate: %s" % plate_path
                continue
            else:
                print "Processing %s: %s..." % (pm.plate_id, plate_path)

            self.process_plate(qlplate, pm)

    def process_plate(self, qlplate, plate_metric):
        """
        Override me!
        """
        pass

class BackfillNTCPositivesCommand(BackfillAllPlateMetricCommand):
    """
    Backfills NTC positive in the WellChannelMetric table.
    """
    summary = "Add the NTC positive metric to all original plate metrics"
    usage = "paster --plugin=qtools backfill-ntc-positives [config]"

    def process_plate(self, qlplate, plate_metric):
        well_dict = plate_metric.well_metric_name_dict
        # TODO move this into a metrics lib instead?
        for name, qlwell in qlplate.analyzed_wells.items():
            well_metric = well_dict[name]
            for qwc, wcm in zip(qlwell.channels, well_metric.well_channel_metrics):
                DEFAULT_NTC_POSITIVE_CALCULATOR.compute(qlwell, qwc, wcm)
        Session.commit()

     
class BackfillNewDropletClusterMetricsCommand(BackfillAllPlateMetricCommand):
    """
    Backfills New Cluster Metrics in all plates
    """
    summary = "Adds the new cluster metrics to all the original plate metrics"
    usage = "paster --plugin=qtools backfill-new-droplet-cluster-metircs [config]"


    def process_plate(self, qlplate, plate_metric):
        from qtools.lib.metrics import NEW_DROPLET_CLUSTER_METRICS_CALCULATOR, compute_metric_foreach_qlwell_channel
        from qtools.lib.metrics import NEW_DROPLET_CLUSTER_WELL_METRICS_CALCULATOR, compute_metric_foreach_qlwell

        compute_metric_foreach_qlwell_channel(qlplate, plate_metric, NEW_DROPLET_CLUSTER_METRICS_CALCULATOR)
        compute_metric_foreach_qlwell( qlplate, plate_metric, NEW_DROPLET_CLUSTER_WELL_METRICS_CALCULATOR)

        Session.commit()


class BackfillPlateExtraclusterMetric(QToolsCommand):
    summary = "Backfills extracluster metrics for plate ids"
    usage = "paster --plugin=qtools backfill-plate-extracluster [config]"

    def command(self):
        app = self.load_wsgi_app()
        storage = QLStorageSource(app.config)

        if len(self.args) < 2:
            print self.__class__.usage
            return

        for i in range(0,len(self.args)-1):
            plate_id = int(self.args[i])
            plate = dbplate_tree(plate_id)
            try:
                plate_path = storage.plate_path(plate)
            except Exception, e:
                print "Could not read plate: %s" % plate_id
                continue

            qlplate = get_plate(plate_path)
            if not qlplate:
                raise ValueError, "Could not read plate: %s" % plate_path
            else:
                print "Processing %s" % plate_path

            try:
                from qtools.lib.metrics import DEFAULT_EXTRAC_CALC, compute_metric_foreach_qlwell_channel
                plate_metrics = plate.metrics[0]
                compute_metric_foreach_qlwell_channel(qlplate, plate_metrics, DEFAULT_EXTRAC_CALC)
            except:
                import sys, traceback
                traceback.print_exc(file=sys.stdout)
                Session.rollback()
                return
        Session.commit()

# re-write to inherit from plate...
class BackfillPlateNewDropletClusterMetricsCommand(BackfillPlateMetricsCommand):
    summary = "Backfills extracluster metrics for plate ids"
    usage = "paster --plugin=qtools backfill-plate-NewDropletClusterMetrics <plate-ids> [config]"

    def process_plate(self, qlplate, plate_metric):
        from qtools.lib.metrics import NEW_DROPLET_CLUSTER_METRICS_CALCULATOR, compute_metric_foreach_qlwell_channel
        from qtools.lib.metrics import NEW_DROPLET_CLUSTER_WELL_METRICS_CALCULATOR, compute_metric_foreach_qlwell

        compute_metric_foreach_qlwell_channel(qlplate, plate_metric, NEW_DROPLET_CLUSTER_METRICS_CALCULATOR)
        compute_metric_foreach_qlwell( qlplate, plate_metric, NEW_DROPLET_CLUSTER_WELL_METRICS_CALCULATOR)

class BackfillPlateAllMetricsCommand(BackfillPlateMetricsCommand):
    summary = "Updates all metrics for plate ids"
    usage = "paster --plugin=qtools update-plate-AllMetrics <plate-ids> [config]"

    def process_plate(self, qlplate, plate_metric):

        dbplate = dbplate_tree(plate_metric.plate_id)
        plate_metrics = get_beta_plate_metrics(dbplate, qlplate)
        Session.add(plate_metrics)



class BackfillInverseCNV(QToolsCommand):
    summary = "Backfills extracluster metrics for plate ids"
    usage = "paster --plugin=qtools backfill-inverse-cnv [config]"

    def command(self):
        app = self.load_wsgi_app()
        storage = QLStorageSource(app.config)

        if len(self.args) < 2:
            print self.__class__.usage
            return

        for i in range(0,len(self.args)-1):
            plate_id = int(self.args[i])
            plate = dbplate_tree(plate_id)
            try:
                plate_path = storage.plate_path(plate)
            except Exception, e:
                print "Could not read plate: %s" % plate_id
                continue

            qlplate = get_plate(plate_path)
            if not qlplate:
                raise ValueError, "Could not read plate: %s" % plate_path
            else:
                print "Processing %s" % plate_path

            try:
                from qtools.lib.metrics import DEFAULT_CNV_CALC, compute_metric_foreach_qlwell
                plate_metrics = plate.metrics[0]
                compute_metric_foreach_qlwell(qlplate, plate_metrics, DEFAULT_CNV_CALC)
            except Exception, e:
                import sys, traceback
                traceback.print_exc(file=sys.stdout)
                Session.rollback()
                return
        Session.commit()


class BackfillAnalysisGroupCommand(QToolsCommand):
    """
    Common class for populating a new metric for an analysis group.
    Includes functionality to populate for an analysis group and
    reprocess config.
    """
    def command(self):
        app = self.load_wsgi_app()

        # TODO: abstract into analysis group/reprocess config extraction code?
        analysis_group_id = int(self.args[0])
        if len(self.args) == 3:
            reprocess_config = Session.query(ReprocessConfig).filter_by(code=self.args[1]).one()
            reprocess_config_id = reprocess_config.id
        else:
            reprocess_config = None
            reprocess_config_id = None

        analysis_group = Session.query(AnalysisGroup).get(analysis_group_id)
        if not analysis_group:
            raise ValueError, "No analysis group for id %s" % analysis_group_id

        self.process_plates(app, analysis_group, reprocess_config)

    def process_plates(self, app, analysis_group, reprocess_config):
        storage = QLStorageSource(app.config)
        plates = analysis_group.plates
        for plate in plates:
            pms = [pm for pm in plate.metrics if pm.reprocess_config_id == reprocess_config.id]
            if not pms:
                print "Cannot find analysis group for plate %s" % plate.id
            else:
                pm = pms[0]
            dbplate = dbplate_tree(plate.id)

            if reprocess_config:
                data_root = app.config['qlb.reprocess_root']
                storage = QLPReprocessedFileSource(data_root, reprocess_config)
            else:
                storage = QLStorageSource(app.config)
            
            try:
                if reprocess_config:
                    plate_path = storage.full_path(analysis_group, dbplate)
                else:
                    plate_path = storage.plate_path(dbplate)
            except Exception, e:
                print "Could not read plate: %s" % plate.id
                continue
            
            qlplate = get_plate(plate_path)
            if not qlplate:
                raise ValueError, "Could not read plate: %s" % plate_path
            else:
                print "Processing %s" % plate_path
            
            try:
                self.backfill_plate(qlplate, pm)
                Session.commit()
            except Exception, e:
                print "Could not process plate %s" % dbplate.id
                import sys, traceback
                traceback.print_exc(file=sys.stdout)
                Session.rollback()
                continue

    def backfill_plate(self, qlplate, plate_metric):
        """
        Given a QLPlate object and a PlateMetric record, populate
        the DB metric object with values gleaned from reading the QLPlate object.
        """
        pass

class ClusterConfCalculator(WellChannelMetricCalculator):
    def compute(self, qlwell, qlwell_channel, well_channel_metric):
        well_channel_metric.cluster_conf = qlwell_channel.statistics.cluster_conf
        return well_channel_metric

CLUSTER_CONF_CALCULATOR = ClusterConfCalculator()

class BackfillAnalysisGroupClusterConf(BackfillAnalysisGroupCommand):
    summary = "Backfills cluster confidences for the specified analysis group."
    usage = "paster --plugin=qtools backfill-analysis-group-cluster-conf [ag id] (reprocess config code) [config]"

    def backfill_plate(self, qlplate, plate_metric):
        from qtools.lib.metrics import compute_metric_foreach_qlwell_channel
        compute_metric_foreach_qlwell_channel(qlplate, plate_metric, CLUSTER_CONF_CALCULATOR)


class BackfillAnalysisGroupNewDropletClusterMetricsCommand(BackfillAnalysisGroupCommand):
    summary = "Backfills cluster confidences for the specified analysis group."
    usage = "paster --plugin=qtools backfill-analysis-group-new_droplet_cluster_metrics [ag id] (reprocess config code) [config]"

    def backfill_plate(self, qlplate, plate_metric):
        from qtools.lib.metrics import NEW_DROPLET_CLUSTER_METRICS_CALCULATOR, compute_metric_foreach_qlwell_channel
        from qtools.lib.metrics import NEW_DROPLET_CLUSTER_WELL_METRICS_CALCULATOR, compute_metric_foreach_qlwell

        compute_metric_foreach_qlwell_channel(qlplate, plate_metric, NEW_DROPLET_CLUSTER_METRICS_CALCULATOR)
        compute_metric_foreach_qlwell( qlplate, plate_metric, NEW_DROPLET_CLUSTER_WELL_METRICS_CALCULATOR)


@WarnBeforeRunning("Be sure you are running this command on the instance where your thumbnails are stored.")
class BackfillAnalysisGroupClustersCommand(QToolsCommand):
    summary = "Generates 2D cluster graphics for an entire analysis group"
    usage = "paster --plugin=qtools backfill-analysis-group-cluster-gfx [analysis_group_id] [reprocess config id] [config]"

    def command(self):
        from qtools.lib.mplot import plot_cluster_2d, cleanup as plt_cleanup
        app = self.load_wsgi_app()

        image_root = app.config['qlb.image_store']
        image_source = QLBImageSource(image_root)

        # enforce config.ini
        if len(self.args) < 2:
            raise ValueError, self.__class_.usage

        analysis_group_id = int(self.args[0])
        if len(self.args) == 3:
            reprocess_config = Session.query(ReprocessConfig).filter_by(code=self.args[1]).one()
            reprocess_config_id = reprocess_config.id
        else:
            reprocess_config = None
            reprocess_config_id = None

        if reprocess_config:
            data_root = app.config['qlb.reprocess_root']
            storage = QLPReprocessedFileSource(data_root, reprocess_config)
        else:
            storage = QLStorageSource(app.config)

        analysis_group = Session.query(AnalysisGroup).get(analysis_group_id)
        if not analysis_group:
            raise ValueError, "No analysis group for id %s" % analysis_group_id

        plates = analysis_group.plates
        for plate in plates:
            # TODO: UGH THIS CODE INVARIANT SUCKS (should merge QLReprocessedFile/QLStorageSources)
            if reprocess_config:
                plate_path = storage.full_path(analysis_group, plate)
            else:
                plate_path = storage.plate_path(plate)
            print "Reading %s" % plate_path
            qlplate = get_plate(plate_path)
            if not qlplate:
                print "Could not read plate: %s" % plate.name
                continue
            print "Generating thumbnails for %s" % plate.name
            for name, qlwell in sorted(qlplate.analyzed_wells.items()):
                # TODO abstract into utility image generation function (thumbnail.py?)

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
                image_path = image_source.get_path('%s/%s_2d.png' % (plate.qlbplate.id, name))
                print image_path
                fig.savefig(image_path, format='png', dpi=72)
                plt_cleanup(fig)
