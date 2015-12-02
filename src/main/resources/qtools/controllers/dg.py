import logging, operator

from pylons import request, response, session, tmpl_context as c, url
from pylons.controllers.util import abort, redirect

from qtools.lib.collection import groupinto
from qtools.lib.base import BaseController, render
from qtools.model import DropletGeneratorRun, DropletGenerator, Session, QLBWell, WellMetric, PlateMetric, QLBPlate, Plate

from sqlalchemy import and_
from sqlalchemy.orm import joinedload_all

log = logging.getLogger(__name__)

class DgController(BaseController):

    def __set_dg_context(self, dg_id, run_id):
        c.dg_run = Session.query(DropletGeneratorRun).filter(
                                    and_(DropletGeneratorRun.droplet_generator_id == dg_id,
                                         DropletGeneratorRun.run_number == run_id))\
                           .options(joinedload_all(DropletGeneratorRun.droplet_generator, innerjoin=True)).first()
        if not c.dg_run:
            abort(404)
    
    def __well_metric_query(self, dg_id, run_id, reprocess_config_id=None):
        # OK for now since
        wells = Session.query(WellMetric,
                              QLBWell.id,
                              QLBWell.sample_name,
                              Plate.id,
                              Plate.name)\
                       .join(QLBWell)\
                       .join(PlateMetric)\
                       .join(QLBPlate)\
                       .join(Plate)\
                       .filter(and_(QLBWell.droplet_generator_id == dg_id,
                                    QLBWell.dg_run_number == run_id,
                                    PlateMetric.reprocess_config_id == reprocess_config_id))
        return wells.all()
    
    def runs(self, id=None):
        c.dg = Session.query(DropletGenerator).get(int(id))
        if not c.dg:
            abort(404)
        
        reprocess_config_id = request.params.get('rp_id', None)
        if reprocess_config_id:
            reprocess_config_id = int(reprocess_config_id)
        
        runs = Session.query(DropletGeneratorRun).filter(
                    and_(DropletGeneratorRun.droplet_generator_id == c.dg.id,
                         DropletGeneratorRun.run_number != None)).all()
        
        run_dict = dict([(run.run_number, run) for run in runs])

        wells = Session.query(WellMetric,
                              QLBWell.id,
                              QLBWell.sample_name,
                              QLBWell.dg_run_number,
                              QLBWell.consumable_channel_num)\
                       .join(QLBWell)\
                       .join(PlateMetric)\
                       .filter(and_(QLBWell.droplet_generator_id == id,
                                    QLBWell.dg_run_number != None,
                                    PlateMetric.reprocess_config_id == reprocess_config_id))\
                       .order_by(QLBWell.dg_run_number, QLBWell.consumable_channel_num).all()
        
        sorted_runs = sorted(groupinto(wells, lambda tup: (tup[3])), key=operator.itemgetter(0))
        c.runs = [(run_id, run_dict[run_id], sorted(info, key=operator.itemgetter(4))) for run_id, info in sorted_runs if run_dict.get(run_id, None)]
        #raise Exception, c.runs
        return render('/product/dg/runs.html')
             
    def run(self, dg_id=None, run_id=None):
        reprocess_config_id = request.params.get('rp_id', None)
        if reprocess_config_id:
            reprocess_config_id = int(reprocess_config_id)
        well_metrics = self.__well_metric_query(dg_id, run_id, reprocess_config_id)
        # may need to handle overlapping analysis group case here.







