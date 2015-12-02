"""
Helper functions to display numerical values.
"""
import math, locale

locale.setlocale(locale.LC_NUMERIC, '')

__all__ = ['sig0','sig1','sig2','sig3', 'format_currency','commafy','isnan']

def sig0(value):
    if isinstance(value, basestring):
        return value
    if isinstance(value, float) and math.isnan(value):
        return "NaN"
    elif isinstance(value, float) and math.isinf(value):
        return "Infinity"
    #return "%d" % (round(value or 0))
    return "%f" % (value or 0)

def sig1(value):
    if isinstance(value, basestring):
        return value
    if isinstance(value, float) and math.isnan(value):
        return "NaN"
    elif isinstance(value, float) and math.isinf(value):
        return "Infinity"
    #return "%.1f" % (value or 0)
    return "%f" % (value or 0) 

def sig2(value):
    if isinstance(value, basestring):
        return value
    if isinstance(value, float) and math.isnan(value):
        return "NaN"
    elif isinstance(value, float) and math.isinf(value):
        return "Infinity"
    #return "%.2f" % (value or 0)
    return "%f" % (value or 0)

def sig3(value):
    if isinstance(value, basestring):
        return value
    if isinstance(value, float) and math.isnan(value):
        return "NaN"
    elif isinstance(value, float) and math.isinf(value):
        return "Infinity"
    #return "%.3f" % (value or 0)
    return "%f" % (value or 0)

# TODO test
def sig_step(value, steps, start=0):
    if isinstance(value, basestring):
        return value
    if isinstance(value, float) and math.isnan(value):
        return "NaN"
    elif isinstance(value, float) and math.isinf(value):
        return "Infinity"
    for idx, step in enumerate(steps):
        if value > step:
            sig = start+idx
            if sig == 0:
                return int(round(value))
            else:
                return ("%%.%sf" % sig) % value
    return value

def format_currency(value):
    return "$%.2f" % value

def commafy(val):
    return locale.format('%d', val, True)

def isnan(val):
    return math.isnan(val)
