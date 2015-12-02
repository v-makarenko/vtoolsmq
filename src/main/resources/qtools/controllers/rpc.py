import logging, operator, simplejson, re, pprint, StringIO

from pylons import request, response, session, tmpl_context as c, url, config
from pylons.decorators import validate
from pylons.decorators.rest import restrict
from pylons.controllers.util import abort, redirect

from qtools.lib.base import BaseController, render
# TODO fix, put in utils
from qtools.lib.collection import groupinto
from qtools.lib.platescan import scan_plates
from qtools.lib.platesetup import get_beta_project, generate_production_setups
from qtools.lib.storage import QLBImageSource, QLBPlateSource

import qtools.lib.helpers as h

from qtools.model import QLBFile, Session, QLBPlate, QLBWell, WellTag, Project, Plate, AnalysisGroup, ReprocessConfig, Box2, Person
from sqlalchemy import and_
from sqlalchemy.orm import joinedload_all
from datetime import datetime, timedelta

import formencode

log = logging.getLogger(__name__)

class RpcController(BaseController):
    """
    A controller that contains a list of callbacks, invokable over
    HTTP POSTs.
    """

    def __get_well_location_csv_by_tag_name(self, tag_name):
        response.content_type = 'text/csv'
        clog_tags = Session.query(WellTag).\
                   filter_by(name=tag_name).\
                   options(joinedload_all(WellTag.tag_wells, QLBWell.plate, QLBPlate.file, innerjoin=True),
                           joinedload_all(WellTag.tag_wells, QLBWell.file)).all()
        if not clog_tags:
            return ''
        else:
            clog_tag = clog_tags[0]
        wells = sorted(clog_tag.wells, key=operator.attrgetter('host_datetime'))
        lines = ["|".join(["%s/%s" % (well.plate.file.dirname, well.plate.file.basename),
                           well.well_name,
                           "%s/%s" % (well.file.dirname, well.file.basename)]) for well in wells]
        return "\n".join(lines)
    
    def get_clog_files(self):
        return self.__get_well_location_csv_by_tag_name(u'Clog')
    
    def get_noclog_files(self):
        return self.__get_well_location_csv_by_tag_name(u'NoClog Control')
    
    def get_tag_files(self):
        tag_name = request.params.get('tag')
        response.content_type = 'text/csv'
        return self.__get_well_location_csv_by_tag_name(unicode(tag_name))
    
    def beta_by_day(self, id=0):
        day = int(id)
        beta_project = get_beta_project()
        plates = Session.query(Plate).filter(and_(Plate.project_id == beta_project.id,
                                                  Plate.run_time > datetime.now()-timedelta(day+1),
                                                  Plate.run_time <= datetime.now()-timedelta(day))).\
                         options(joinedload_all(Plate.qlbplate, QLBPlate.file)).all()
        
        response.content_type = 'text/csv'
        lines = [','.join([p.qlbplate.file.dirname,p.qlbplate.file.basename]) for p in plates]
        return '\n'.join(sorted(lines))
    
    def fam_wells(self):
        response.content_type = 'text/csv'
        wells = Session.query(QLBWell).filter(and_(QLBWell.file_id != None,
                                                   QLBWell.plate_id != None,
                                                   QLBWell.host_datetime != None,
                                                   QLBWell.sample_name.in_(("F350","FAM 350 nM","350 nM FAM","Fam 350","FAM_HI","350nM FAM","FAM 350nM")),
                                                   QLBWell.event_count > 5000)).\
                                       options(joinedload_all(QLBWell.plate, QLBPlate.plate, Plate.box2, innerjoin=True)).all()
        
        wells = [well for well in wells if well.plate.plate.id not in (266, 217, 356, 195, 270, 279)]
        box_wells = groupinto(wells, lambda w: w.plate.plate.box2.name)
        output = []
        for box, well_list in sorted(box_wells):
            for well in sorted(well_list, key=lambda w: w.host_datetime):
                output.append(','.join((well.plate.file.dirname,well.plate.file.basename,well.well_name)))
        
        return "\n".join(output)
    
    def analysis_group_plates(self, id):
        response.content_type = 'text/csv'
        ag = Session.query(AnalysisGroup).get(id)
        if not ag:
            abort(404)
        
        plates = sorted(ag.plates, key=lambda p: p.qlbplate.file.dirname)
        return "\n".join([p.qlbplate.file.dirname for p in plates])
    
    def reprocess_config_params(self, id):
        # whatever
        response.content_type = 'application/json'
        rc = Session.query(ReprocessConfig).filter_by(code=id).one() # throws 500
        if not rc:
            abort(404)
        
        # currently the only flags to reprocessor
        rc_param_dict = {'peak_detection_minor': rc.peak_detection_minor,
                         'peak_quant_minor': rc.peak_quant_minor,
                         'vertical_streaks_enabled': rc.vertical_streaks_enabled,
                         'peak_separation': rc.peak_separation,
                         'cluster_mode': rc.cluster_mode}

        if rc.trigger_fixed_width is not None:
            # TODO fix typo?
            rc_param_dict['trigger_fixed_offset'] = float(rc.trigger_fixed_width)
        if rc.vic_min_amplitude is not None:
            rc_param_dict['min_amplitude'] = float(rc.vic_min_amplitude)

        return simplejson.dumps(rc_param_dict)
    
    # Restrict POST?
    def analysis_group_reprocessed(self):
        response.content_type = 'text/plain'
        analysis_group_id = request.params.get('ag_id', None)
        reprocess_config_code = request.params.get('rc_code', None)

        if not analysis_group_id or not reprocess_config_code:
            abort(404)
        
        ag = Session.query(AnalysisGroup).get(int(analysis_group_id))
        rc = Session.query(ReprocessConfig).filter_by(code=reprocess_config_code).one()
        if not ag or not rc:
            abort(404)
        
        # check to see if already exists
        if ag in rc.analysis_groups:
            return 'roger that'
        
        rc.analysis_groups.append(ag)
        Session.commit()
        return 'OK'
    
    # may want to make this a post because BACK totally creates more plates
    def prod_machine_active(self, id=None):
        """
        Multiple conditions:

        -- if a machine already exists, make sure it is active.
        -- if a machine does not yet exists (DR serial), create one.
        -- create carryover and colorcomp validation plates.  This may
           result in a lot of plates if you switch back and forth frequently,
           but that's OK-- they are easy to delete.
        """
        ok_str = re.compile(r'^\d{5}$')
        if id is None or not ok_str.match(id):
            abort(404)
        response.content_type = 'text/plain'
        
        # try to see if machine exists
        machine = Session.query(Box2).filter_by(code='p%s' % int(id)).first()
        if not machine:
            # create the machine
            machine = Box2(name=u'Prod %s' % id, code='p%s' % id, src_dir="DR %s" % id, fileroot='prod', active=True)
            Session.add(machine)
        machine.active = True
        Session.commit()

        # OK, now create validation plates
        #operator = Session.query(Person).filter_by(name_code='JohannesS').first() # TODO don't hard-code
        #carryover_plate, colorcomp_plate = generate_production_setups(machine, operator)
        ##Session.add(carryover_plate)
        #Session.add(colorcomp_plate)
        #Session.commit()
        return 'OK'
    
    def scan_plates(self, id=None):
        """
        Tell QTools to process the plates on the machine.
        """
        response.content_type = 'text/plain'
        if not h.wowo('process_plates'):
            abort(404)
        
        dr = Session.query(Box2).filter_by(code=id).first()
        if not dr:
            abort(404)
        
        source = QLBPlateSource(config, [dr])
        image_root = config['qlb.image_store']
        image_source = QLBImageSource(image_root)

        file_lists = scan_plates(source, image_source)
        sorted_file_lists = dict([(k, sorted(v)) for k, v in file_lists.items()])
        io = StringIO.StringIO()
        pprint.pprint(sorted_file_lists, io)
        return io.getvalue()







        
