import logging

from pylons import request, response, session, tmpl_context as c, url
from pylons.controllers.util import abort, redirect

from qtools.lib.base import BaseController, render
from qtools.lib.inspect import class_properties
from qtools.model import Session, WellMetric, WellChannelMetric

log = logging.getLogger(__name__)

class HelpController(BaseController):

    # TODO: put this in db or inspect?
    def __get_table_definitions(self, Klass):
        display_cols = []
        display_cols.extend([(col.doc, col.info.get('definition', ''), col.name)\
                              for col in Klass.__mapper__.columns if col.doc])

        for name, prop in class_properties(Klass):
            func = prop.fget
            doc = getattr(func, 'doc', None)
            info = getattr(func, 'info', dict())
            if doc:
                display_cols.append((doc, info.get('definition', ''), '(derived property)'))

        return display_cols

    def index(self):
        return render('/help/index.html')

    def well_metrics(self):
        c.well_metric_cols = sorted(self.__get_table_definitions(WellMetric))
        return render('/help/well_metrics.html')

    def well_channel_metrics(self):
        c.channel_metric_cols = sorted(self.__get_table_definitions(WellChannelMetric))
        return render('/help/channel_metrics.html')

