import logging
import itertools
import datetime

from pylons import request, response, session, tmpl_context as c, url
from pylons.controllers.util import abort, redirect

from qtools.lib.base import BaseController, render
from qtools.lib.wowo import wowo
from qtools.lib.helpers import week_bounds, midnight, second_before_midnight

from qtools.model import Session, QLBPlate, QLBWell, Project, Person, Plate, Box2, Experiment

from sqlalchemy import and_
from sqlalchemy.sql import func
from sqlalchemy.orm import joinedload_all

log = logging.getLogger(__name__)


def plate_events_for_range(start, end):
    plate_query = QLBPlate.filter_by_host_datetime(Session.query(QLBPlate,
                                                                 func.sum(QLBWell.event_count).label('total_count')).
                                                           join(QLBWell).\
                                                           join(QLBPlate.plate).\
                                                           join(Plate.box2).\
                                                           filter(and_(QLBPlate.plate_id != None,
                                                                       QLBWell.file_id != None)),
                                                   start, end).group_by(QLBWell.plate_id)
    return plate_query.all()

def time_events(start, end):
    plate_query = QLBPlate.filter_by_host_datetime(Session.query(QLBPlate,
                                                                 func.sum(QLBWell.event_count).label('total_count')).
                                                           join(QLBWell).\
                                                           join(QLBPlate.plate).\
                                                           join(Plate.box2).\
                                                           filter(and_(QLBPlate.plate_id != None,
                                                                       QLBWell.file_id != None)),
                                                    start, end)
    
    if wowo('contractor'):
        plate_query = plate_query.filter(Box2.prod_query())
    return sum([total_count or 0 for plate, total_count in plate_query.all()])

def total_events():
    plate_query = Session.query(QLBPlate,
                                func.sum(QLBWell.event_count).label('total_count')).\
                                join(QLBWell).\
                                join(QLBPlate.plate).\
                                join(Plate.box2).\
                                filter(and_(QLBPlate.plate_id != None, QLBWell.file_id != None)).\
                                group_by(QLBWell.plate_id)
    if wowo('contractor'):
        plate_query = plate_query.filter(Box2.prod_query())
    return sum([total_count or 0 for plate, total_count in plate_query.all()])


def plate_runtimes_for_box_range(start, end):
    plate_query = QLBPlate.filter_by_host_datetime(Session.query(QLBPlate,
                                                                 func.min(QLBWell.host_datetime).label('start_time'),
                                                                 func.max(QLBWell.host_datetime).label('end_time')).
                                                           join(QLBWell).\
                                                           join(QLBPlate.plate).\
                                                           join(Plate.box2).\
                                                           filter(and_(QLBPlate.plate_id != None,
                                                                       QLBWell.file_id != None)),
                                                   start, end).group_by(QLBWell.plate_id).options(joinedload_all('plate.box2', innerjoin=True),
                                                                                                  joinedload_all('plate.operator'))
    if wowo('contractor'):
        plate_query = plate_query.filter(Box2.prod_query())
    runtimes = plate_query.all()
    # TODO: engineer quick fix for this
    return [runtime for runtime in runtimes if runtime.start_time and runtime.end_time]


def plate_runtimes_for_operator_range(start, end):
    plate_query = QLBPlate.filter_by_host_datetime(Session.query(QLBPlate,
                                                                 func.count(QLBWell).label('wells'),
                                                                 func.sum(func.if_(QLBWell.event_count >= 1000, 1, 0)).label('data_wells'),
                                                                 func.sum(QLBWell.event_count).label('data_well_events')).
                                                           join(QLBWell).\
                                                           join(QLBPlate.plate).\
                                                           join(Plate.box2).\
                                                           filter(and_(QLBPlate.plate_id != None,
                                                                       QLBWell.file_id != None)),
                                                   start, end).group_by(QLBWell.plate_id).options(joinedload_all('plate.box2', innerjoin=True),
                                                                                                  joinedload_all('plate.operator'))
    if wowo('contractor'):
        plate_query = plate_query.filter(Box2.prod_query())
    return plate_query.all()

def plate_runtimes_for_week_box(num_weeks=0):
    week_start, week_end = week_bounds(num_weeks)
    return plate_runtimes_for_box_range(week_start, week_end)

def plate_events_for_week(num_weeks=0):
    week_start, week_end = week_bounds(num_weeks)
    return plate_events_for_range(week_start, week_end)

def plate_runtimes_for_day_box(day):
    day_start = midnight(day)
    day_end = second_before_midnight(day)
    return plate_runtimes_for_box_range(day_start, day_end)
    
def plate_runtimes_for_week_operator(num_weeks=0):
    week_start, week_end = week_bounds(num_weeks)
    return plate_runtimes_for_operator_range(week_start, week_end)
    

class StatsController(BaseController):

    def index(self):
        
        events_by_week = []
        for i in range(5):
            weeks_ago = -1*i
            plates = plate_events_for_week(weeks_ago)
            droplet_sum = sum([num_events or 0 for plate, num_events in plates])
            week_begin, week_end = week_bounds(weeks_ago)
            events_by_week.append((week_begin, week_end, droplet_sum))
        
        c.events_by_week = events_by_week
        c.total_events = total_events()

        now = datetime.datetime.now()
        month_ago = now - datetime.timedelta(30)
        c.last_month_events = time_events(month_ago, now)
        
        return render('/stats/index.html')
            
        
    
    def boxes_by_week(self, weeks_ago=0):
        width = 700
        weeks_ago = -1*int(weeks_ago)
        
        plate_runtimes = sorted(plate_runtimes_for_week_box(weeks_ago), key=lambda tup: (tup[0].plate.box2.name, tup[1]))
        
        week_begin, week_end = week_bounds(weeks_ago)
        plate_runtime_dimensions = [(plate, int((width*round((start-week_begin).total_seconds())/(60*60*24*7))),
                                            max(1,int((width*round((end-start).total_seconds())/(60*60*24*7))))) for plate, start, end in plate_runtimes]
        c.run_histories = itertools.groupby(plate_runtime_dimensions, lambda tup: tup[0].plate.box2.name)
        
        c.days = [week_begin+(i*datetime.timedelta(1)) for i in range(7)]
        
        c.week = -1*weeks_ago
        c.first_day = week_begin
        return render('/stats/box2_week.html')
    
    def boxes_by_day(self, year, month, day):
        width = 696
        today = datetime.datetime(year=int(year), month=int(month), day=int(day))
        
        plate_runtimes = sorted(plate_runtimes_for_day_box(today), key=lambda tup: (tup[0].plate.box2.name, tup[1]))
        
        day_begin = midnight(today)
        day_end = second_before_midnight(today)
        plate_runtime_dimensions = [(plate, start, end, int((width*round((start-day_begin).total_seconds())/(60*60*24))),
                                            max(1,int((width*round((end-start).total_seconds())/(60*60*24))))) for plate, start, end in plate_runtimes]
        c.run_histories = [(machine, list(events)) for machine, events in itertools.groupby(plate_runtime_dimensions, lambda tup: tup[0].plate.box2.name)]
        
        c.today = today
        c.yesterday = today - datetime.timedelta(1)
        c.tomorrow = today + datetime.timedelta(1)
        c.weeks_ago = (datetime.datetime.now() - today).days/7
        return render('/stats/box2_day.html')
    
    def operators_by_week(self, weeks_ago=0):
        weeks_ago = -1*int(weeks_ago)
        plate_runtimes = sorted(plate_runtimes_for_week_operator(weeks_ago), key=lambda tup: tup[0].plate.operator.name_code if tup[0].plate.operator else '')
        
        c.run_profiles = sorted([(operator, list(plates)) \
                                 for operator, plates in itertools.groupby(
                                     plate_runtimes,
                                     lambda tup: tup[0].plate.operator if tup[0].plate.operator else ''
                                 )], key=lambda tup: sum([(plate.plate.score or 0) for plate, wells, data_wells, data_events in tup[1]]))
        unattributed_results = [results for operator, results in c.run_profiles if not operator]
        if len(unattributed_results) > 0:
            c.unattributed_results = unattributed_results[0]
        else:
            c.unattributed_results = []
        
        week_begin, week_end = week_bounds(weeks_ago)
        c.week = -1*weeks_ago
        c.first_day = week_begin
        return render('/stats/operator_week.html')
        c.first_day = we
    
        
