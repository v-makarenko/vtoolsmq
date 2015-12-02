"""
Date display helper functions.
"""
from datetime import datetime, timedelta, date
import time

__all__ = ['current_year','yesterday','now','today','tomorrow','workweeks_ago','weeks_ago_ymd',
           'ymd','hhmm','timestr','midnight', 'second_before_midnight', 'week_bounds', 'timestamp']

def current_year():
    return datetime.now().year

def yesterday(date):
    return date - timedelta(1)

def now():
    return datetime.now()

def today():
    return date.today()

def tomorrow(date):
    return date + timedelta(1)

def workweeks_ago(date):
    # get to beginning of week
    now = date.today()
    weekday = now.weekday()
    monday = now - timedelta(weekday)
    diff = monday - date
    if diff.total_seconds() == 0 or diff.days < 0:
        return 0
    else:
        return (diff.days / 7) + 1

def weeks_ago_ymd(weeks_ago=0, format='%Y%m%d'):
    today = date.today()
    week_start = today - timedelta(today.weekday())
    past_date = week_start - timedelta(7*weeks_ago)
    return past_date.strftime(format)

def ymd(date):
    if not date:
        return '?'
    return datetime.strftime(date, '%Y/%m/%d')
    
def hhmm(date):
    return datetime.strftime(date, '%H:%M')

def timestr(date):
    return datetime.strftime(date, '%Y/%m/%d %H:%M')

def midnight(today):
    """
    Return the midnight of the day.
    """
    return today.replace(hour=0, minute=0, second=0, microsecond=0)

def second_before_midnight(today):
    """
    Return the last second of the day. (that rounding doesn't budge)
    """
    return today.replace(hour=23, minute=59, second=59, microsecond=499999)

def week_bounds(week_diff=0):
    """
    Returns bounds for the week.  Aligns on Monday - Sunday.
    
    Will probably fail on a daylight savings time transition. TODO: fix that if
    this method is going to be used more generally than plate-running contests.
    
    Also: lookup to see if webhelpers has anything of the sort.  This should be
    a solved problem.
    
    week_bounds(0) returns the bounds for this week.
    week_bounds(-1) returns the bounds for last week.
    week_bounds(1) returns the bounds for next week.
    """
    now = datetime.now()
    # impervious to leap years, but vulnerable to daylight savings time and leap seconds.
    # TODO: make impervious to DST, leap seconds, through proper methods.
    
    delta = timedelta(days=now.weekday(), hours=now.hour, minutes=now.minute, seconds=now.second, microseconds=now.microsecond)
    week_start = now-delta
    delta = timedelta(days=6-now.weekday(), hours=23-now.hour, minutes=59-now.minute, seconds=59-now.second, microseconds=999999-now.microsecond)
    week_end = now+delta
    
    week_adjust = timedelta(days=7*week_diff)
    
    return (week_start+week_adjust, week_end+week_adjust)

def timestamp():
    return int(time.time())