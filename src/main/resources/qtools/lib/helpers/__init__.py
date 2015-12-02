"""Helper functions

Consists of functions to typically be used within templates, but also
available to Controllers. This module is available to templates as 'h'.
"""
# Import helpers as desired, or define your own, ie:
#from webhelpers.html.tags import checkbox, password
from webhelpers.date import time_ago_in_words
from webhelpers.html.tags import *
from webhelpers.html.builder import HTML
from webhelpers.paginate import Page
from webhelpers.html import literal
from webhelpers.number import format_number
from formbuild import Form
from textwrap import wrap
from urllib import quote, unquote
from datetime import datetime, timedelta, date
from pylons import config, url
from itertools import groupby
from formencode import htmlfill
import locale, math, re

import qtools.lib.fields as fl

from qtools.lib.bio import *
from qtools.lib.wowo import wowo

from qtools.lib.helpers.auth import *
from qtools.lib.helpers.date import *
from qtools.lib.helpers.download import *
from qtools.lib.helpers.form import *
from qtools.lib.helpers.html import *
from qtools.lib.helpers.images import *
from qtools.lib.helpers.links import *
from qtools.lib.helpers.numeric import *
from qtools.lib.helpers.text import *
from qtools.lib.helpers.tw_bootstrap import *


# TODO phase these out
def gc_display(seq):
    return HTML.tag("span", "%s%% GC" % sig0(gc_content(seq)*100), class_="secondary_info")

def dg_display(assay, section):
    if getattr(assay, '%s_dG' % section, None) is not None:
        return literal("<span class=\"secondary_info\">&Delta;G %s</span>" % sig2(getattr(assay, '%s_dG' % section)))
    else:
        return ''

def tm_display(assay, section):
    if getattr(assay, '%s_tm' % section, None) is not None:
        return literal("<span class=\"secondary_info\">%s&deg; tM</span>" % sig1(getattr(assay, '%s_tm' % section)))
# TODO end phasing these out


