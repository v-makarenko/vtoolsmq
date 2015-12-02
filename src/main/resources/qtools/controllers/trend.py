import logging, json, time, math
from datetime import datetime, timedelta

from pylons import request, response, session, tmpl_context as c, url
from pylons.controllers.util import abort, redirect
from pylons.decorators import validate
from pylons.decorators.rest import restrict

import qtools.lib.fields as fl
import qtools.lib.helpers as h

from qtools.lib.base import BaseController, render
from qtools.lib.collection import groupinto
from qtools.lib.decorators import help_at
from qtools.lib.inspect import class_properties
from qtools.lib.validators import MetricPattern, OneOfInt, FormattedDateConverter, IntKeyValidator

from qtools.model import Session, WellChannelMetric, WellMetric, PlateMetric, Plate, QLBWell, QLBWellChannel, Box2,  PlateType, SystemVersion

# TODO: should be a mixin, separated from PVSI
from qtools.model.reagents import ProductValidationSpecItem

log = logging.getLogger(__name__)

from sqlalchemy import func

import formencode
from formencode.variabledecode import NestedVariables

SAMPLE_NTC = 'NTC'
SAMPLE_STEALTH = 'Stealth'
SAMPLE_FAM_HI = 'FAM HI'
SAMPLE_FAM_LO = 'FAM LO'
SAMPLE_VIC_HI = 'VIC HI'
SAMPLE_VIC_LO = 'VIC LO'
SAMPLE_CC_FAMVIC = 'FAM/VIC'
SAMPLE_CC_FAMHEX = 'FAM/HEX'
SAMPLE_CODS = 'S.a. 1cpd'

ASSAY_STAPH = 'QL_S_aureus'
ASSAY_EGFR = 'EGFR L858R WT'
ASSAY_RPP = 'QL_RPP30_1'
ASSAY_MRG = 'MRGPRX1 CNV'

READER_PRODUCTION = 'prod'
READER_GROOVE = 'groove'
READER_LAB = 'lab'
READER_GOLDEN_DR = 'golden'
READER_FLUIDICS_MODULES = 'fluidics'
READER_DETECTOR_MODULES = 'detector'
READER_QX100 = 'qx100'
READER_QX150 = 'qx150'
READER_QX200 = 'qx200'

EXCLUDE_OUTLIER = 'outlier'
EXCLUDE_LOW_EVENTS = 'low'
EXCLUDE_NO_CALL = 'nocall'

# TODO: break this logic out into separate groups?
def sample_category_field(selected=None):
    field = {'value': selected or '',
             'options': [('','All'),
                         (SAMPLE_NTC, 'NTC'),
                         (SAMPLE_STEALTH, 'Stealth'),
                         (SAMPLE_FAM_HI, 'FAM HI'),
                         (SAMPLE_FAM_LO, 'FAM LO'),
                         (SAMPLE_VIC_HI, 'VIC HI'),
                         (SAMPLE_VIC_LO, 'VIC LO'),
                         (SAMPLE_CC_FAMVIC, 'FAM/VIC Single-Well ColorCal'),
                         (SAMPLE_CC_FAMHEX, 'FAM/HEX Single-Well ColorCal'),
                         (SAMPLE_CODS, '1cpd Staph or Dye Equivalent')]}
    return field

def assay_category_field(selected=None):
    field = {'value': selected or '',
             'options': [('', 'All'),
                         (ASSAY_STAPH, 'S. aureus'),
                         (ASSAY_EGFR, 'EGFR WT'),
                         (ASSAY_RPP, 'RPP30'),
                         (ASSAY_MRG, 'MRGPRX1')]}
    return field

def reader_category_field(selected=None):
    field = {'value': selected or '',
             'options': [('','All'),
                         (READER_PRODUCTION, 'Production Readers'),
                         #(READER_GROOVE, 'Groove Readers'),
                         (READER_LAB, 'Lab Readers'),
                         (READER_GOLDEN_DR, 'Golden DR'),
                         (READER_FLUIDICS_MODULES, 'Fluidics Modules'),
                         (READER_DETECTOR_MODULES, 'Detector Modules'),
                         (READER_QX100, 'QX100 Readers'),
                         (READER_QX150, 'QX150 Readers'),
                         (READER_QX200, 'QX200 Readers')
                         ]}
    return field

def exclusion_field(selected=None):
    field = {'value': selected or '',
             'options': [('None', 'None'),
                         (EXCLUDE_LOW_EVENTS, 'Exclude Wells < 1000 Events'),
                         (EXCLUDE_NO_CALL, 'Exclude No Calls')]}
    return field

def col_from_form_results(form_result):
    """
    Return which entity column the user wants to query.
    """
    if form_result['metric'][0] == 'channel':
        return getattr(WellChannelMetric, form_result['metric'][1])
    elif form_result['metric'][0] == 'well':
        return getattr(WellMetric, form_result['metric'][1])
    else:
        return None

# todo: move this out into query filters?
def build_base_query(form_result):
    """
    Builds the base SQLAlchemy query object needed to execute a
    trend query, from the values in the form submitted.

    The return from the query will take the form (desired stat/object,
    time, object id, [object display information]).  The ID could be
    the ID of the plate or well, depending on whether the user desired
    to group results by plate, or view well IDs independently.

    :param form_result: self.form_result, computed by Pylons.
    :return: A 3-tuple (query, joined_entities, return_objects)

             The ``query`` is the SQLAlchemy query that can be executed.

             ``joined_entities`` are the list of entity class (e.g., Plate)
             that have been joined to the query already.  Use this
             to determine downstream whether additional joins are necessary.

             ``return_objects`` is a boolean about whether to expect that the
            primary (first) return value of the query is going to be a
            SQLAlchemy object, as opposed to a column value.  This will be
            true if the desired statistic from the form values is not a
            native column in the database, but a derived model column.
            (TODO: I bet SQLAlchemy has a better way of doing this..)
    """
    joined_entities = []
    return_objects = False
    col = col_from_form_results(form_result)

    # desired metric is a per-channel metric
    if form_result['metric'][0] == 'channel':
        # metric is a virtual property, not a DB column -- query will need to return objects
        # group-by will need to be done downstream in logic
        if isinstance(col, property):
            base_q = Session.query(WellChannelMetric, Plate.run_time, Plate.id, Plate.name, WellMetric.well_name)
            base_q = base_q.join(WellMetric).join(PlateMetric).join(Plate)
            joined_entities.extend([WellChannelMetric, WellMetric, PlateMetric, Plate])
            return_objects = True
        # average metric by plate; metric is a db column; you can use db group by function
        elif form_result['group_by_plate']:
            base_q = Session.query(func.avg(col), Plate.run_time, Plate.id, Plate.name)
            base_q = base_q.join(WellMetric).join(PlateMetric).join(Plate)
            joined_entities.extend([WellChannelMetric, WellMetric, PlateMetric, Plate])
        # metric is a db column, per-well OK
        else:
            base_q = Session.query(col, Plate.run_time, WellMetric.well_id, Plate.name, WellMetric.well_name)
            base_q = base_q.join(WellMetric).join(PlateMetric).join(Plate)
            joined_entities.extend([WellChannelMetric, WellMetric, PlateMetric, Plate])
        # filter by channel if specified
        if form_result['channel_num'] is not None:
            base_q = base_q.filter(WellChannelMetric.channel_num == form_result['channel_num'])
    # desired metric is a per-well metric
    elif form_result['metric'][0] == 'well':
        # metric is a virtual property, not a DB column -- query will need to return objects
        # group-by will need to be done downstream in logic
        if isinstance(col, property):
            base_q = Session.query(WellMetric, Plate.run_time, Plate.id, Plate.name, WellMetric.well_name)
            base_q = base_q.join(PlateMetric).join(Plate)
            joined_entities.extend([WellMetric, PlateMetric, Plate])
            return_objects = True
        # average metric by plate; metric is a db column; you can use db group by function
        elif form_result['group_by_plate']:
            base_q = Session.query(func.avg(col), Plate.run_time, Plate.id, Plate.name)
            base_q = base_q.join(PlateMetric).join(Plate)
            joined_entities.extend([WellMetric, PlateMetric, Plate])
        # metric is a db-column, per-well OK
        else:
            base_q = Session.query(col, Plate.run_time, WellMetric.well_id, Plate.name, WellMetric.well_name)
            base_q = base_q.join(PlateMetric).join(Plate)
            joined_entities.extend([WellMetric, PlateMetric, Plate])

    # specify the right (non-reprocessed) plate metric id
    if PlateMetric not in joined_entities:
        base_q = base_q.join(PlateMetric)
        joined_entities.append(PlateMetric)
    base_q = base_q.filter(PlateMetric.reprocess_config_id == None)

    # filter by date
    if form_result['start_date'] or form_result['end_date']:
        if Plate not in joined_entities:
            base_q = base_q.join(Plate)
            joined_entities.append(Plate)

        if form_result['start_date']:
            base_q = base_q.filter(Plate.run_time > form_result['start_date'])
        if form_result['end_date']:
            base_q = base_q.filter(Plate.run_time < form_result['end_date'])

    return base_q, joined_entities, return_objects

def build_exclude_query(query, exclusions, joined_entities):
    """
    Exclude certain well types from aggregate or individual metrics.

    :param query: The existing query to further filter.
    :param exclusions: List of well types to exclude.
    :param joined_entities: The list of already joined entities.  This method
                            may add an additional join to the query.
    :return: Side-effects query.
    """
    if EXCLUDE_LOW_EVENTS in exclusions:
        if WellMetric not in joined_entities:
            query = query.join(WellMetric).filter(WellMetric.accepted_event_count > 1000)

    if EXCLUDE_NO_CALL in exclusions:
        # assume a channel has been selected
        if WellChannelMetric not in joined_entities:
            query = query.join(WellChannelMetric)
        query = query.filter(WellChannelMetric.concentration > 0)

    return query

def build_category_query(form_result):
    """
    Return a query to analyze wells in a certain category by a specified metric.

    All filtering instructions should be on form values in the form_result object,
    which Pylons creates from the request.

    The query, when executed, will return a tuple per record, of the form:
    (stat or record, run time, object ID, plate name, [well name])  For queries
    against derived attributes on the entity model (properties of the model not
    stored in a DB Column), the first member of the tuple will be a model object.
    If this is the case, the second return value of this function will be True.

    :param form_result:
    :return: (query, postprocess_objects):
             ``query`` is the query to execute.
             ``postprocess_objects``: A boolean indicating whether the first
             member of a query row is expected to be a model object.
    """
    cat_q, joined_entities, postprocess_objects = build_base_query(form_result)
    if form_result['reader_category']:
        if Plate not in joined_entities:
            cat_q = cat_q.join(Plate)
            joined_entities.append(Plate)
        cat_q = cat_q.join(Box2)
        joined_entities.append(Box2)

    if form_result['reader_category']:
        cat_q = add_reader_category_filter(cat_q, form_result['reader_category'], joined_entities)
    if form_result['sample_category']:
        cat_q = add_sample_category_filter(cat_q, form_result['sample_category'], joined_entities)
    if form_result['assay_category']:
        cat_q = add_assay_category_filter(cat_q, form_result['assay_category'], joined_entities)

    cat_q = build_exclude_query(cat_q, form_result, joined_entities)
    return cat_q, postprocess_objects

def build_reader_query(form_result):
    """
    Return a query to analyze wells/plates by reader only.

    See :func:`build_category_query` for an explanation of return values.
    """
    cat_q, joined_entities, postprocess_objects = build_base_query(form_result)
    box2_id = form_result['reader']
    if Plate not in joined_entities:
        cat_q = cat_q.join(Plate)
        joined_entities.append(Plate)
    cat_q = cat_q.join(Box2)
    joined_entities.append(Box2)

    cat_q = cat_q.filter(Box2.id == box2_id)

    cat_q = build_exclude_query(cat_q, form_result, joined_entities)
    return cat_q, postprocess_objects

def build_search_query(form_result):
    cat_q, joined_entities, postprocess_objects = build_base_query(form_result)
    if form_result['plate_name']:
        cat_q = add_plate_like_filter(cat_q, form_result['plate_name'], joined_entities)
    if form_result['sample_name']:
        cat_q = add_sample_like_filter(cat_q, form_result['sample_name'], joined_entities)
    if form_result['assay_name']:
        cat_q = add_assay_like_filter(cat_q, form_result['assay_name'], joined_entities)

    cat_q = build_exclude_query(cat_q, form_result, joined_entities)
    return cat_q, postprocess_objects

def add_reader_category_filter(query, category, joined_entities):
    """
    Modifies query to filter by reader type.

    :param query: The query to further filter.
    :param category: The category type.
    :param joined_entities: Which entities have already been joined in the query.
                            Reader filters may require additional joins.  This
                            list will be modified if an additional join is made.
    :return: query (side-effected)
    """
    if Box2 not in joined_entities:
        query = query.join(Box2)

    if category == READER_PRODUCTION:
        query = query.filter(Box2.prod_query()).filter(Box2.reference != True)
    #elif category == READER_GROOVE:
    #    query = query.filteR(Box2.code.in_())
    elif category == READER_LAB:
        query = query.filter(Box2.lab_query())
    elif category == READER_GOLDEN_DR:
        query = query.filter(Box2.reference == True)
    elif category == READER_FLUIDICS_MODULES:
        query = query.filter(Box2.fluidics_module_query())
    elif category == READER_DETECTOR_MODULES:
        query = query.filter(Box2.detector_module_query())
    elif category == READER_QX100:
        query = query.filter(SystemVersion.type == 'QX100')
    elif category == READER_QX150:
        query = query.filter(SystemVersion.type == 'QX150')
    elif category == READER_QX200:
        query = query.filter(SystemVersion.type == 'QX200')
    return query

def add_sample_category_filter(query, category, joined_entities):
    """
    Modifies query to filter by sample type.

    :param query: The query to further filter.
    :param category: The category type.
    :param joined_entities: Which entities have already been joined in the query.
                            Sample filters may require additional joins.  This
                            list will be modified if an additional join is made.
    :return: query (side-effected)
    """
    if QLBWell not in joined_entities:
        query = query.join(QLBWell)
        joined_entities.append(QLBWell)
    if category == SAMPLE_NTC:
        return query.filter(QLBWell.sample_name.like('NTC%'))
    else:
        return query.filter(QLBWell.sample_name == category)

def add_assay_category_filter(query, category, joined_entities):
    """
    Modifies query to filter by assay type.

    :param query: The query to further filter.
    :param category: The category type.
    :param joined_entities: Which entities have already been joined in the query.
                            Assay filters may require additional joins.  This
                            list will be modified if an additional join is made.
    :return: query (side-effected)
    """
    if WellChannelMetric not in joined_entities:
        query = query.join(WellChannelMetric)
        joined_entities.append(WellChannelMetric)
    if QLBWellChannel not in joined_entities:
        query = query.join((QLBWellChannel, WellChannelMetric.well_channel_id == QLBWellChannel.id))
        joined_entities.append(QLBWellChannel)

    if category == ASSAY_RPP:
        return query.filter(QLBWellChannel.target.in_(('RPP30','QL_RPP30_1','QLRPP30_#1','QLRPP30','QL_RPP30','RPP30_1')))
    elif category == ASSAY_STAPH:
        return query.filter(QLBWellChannel.target.in_(('Sa822','QL_S_aureus','s. aureus','S.Aureus','SA','Sa 1 cpd','S_aureus_822')))
    else:
        return query.filter(QLBWellChannel.target == category)

def add_sample_like_filter(query, sample_name, joined_entities):
    """
    Modifies query to filter by sample LIKE.
    :param query: The query to modify
    :param category: The sample name to query against.
    :param joined_entities: Which entities have already been joined in the query.
    :return: query (side-effected)
    """
    if not sample_name:
        return query

    if QLBWell not in joined_entities:
        query = query.join(QLBWell)
        joined_entities.append(QLBWell)
    return query.filter(QLBWell.sample_name.like("%%%s%%" % sample_name))

def add_plate_like_filter(query, plate_name, joined_entities):
    """
    Modifies query to filter by plate name
    :param query: The query to modify
    :param plate_name: The plate name to query against
    :param joined_entities: Which entities have already been joined in the query
    :return: query (side-effected)
    """
    if not plate_name:
        return query

    if Plate not in joined_entities:
        query = query.join(Plate)
        joined_entities.append(Plate)

    return query.filter(Plate.name.like("%%%s%%" % plate_name))

def add_assay_like_filter(query, assay_name, joined_entities):
    """
    Modifies query to filter by assay LIKE
    :param query: The query to modify
    :param assay_name: The assay name to query against.
    :param joined_entities: Which entities have already been joined in the query.
    :return: query (side-effected)
    """
    if not assay_name:
        return query

    if WellChannelMetric not in joined_entities:
        query = query.join(WellChannelMetric)
        joined_entities.append(WellChannelMetric)
    if QLBWellChannel not in joined_entities:
        query = query.join((QLBWellChannel, WellChannelMetric.well_channel_id == QLBWellChannel.id))
        joined_entities.append(QLBWellChannel)

    return query.filter(QLBWellChannel.target.like("%%%s%%" % assay_name))

def execute_built_query(base_q, group_by_plate, objects_expected=False, derived_metric=None):
    """
    Executes the query built by one of the build_*_query functions.  The result
    will be a 4-tuple: [statistic, timepoint, object id, object display string]

    :param base_q: The query to execute.
    :param group_by_plate: Whether to group the results by plate.
    :param objects_expected: Whether the first member of the result set is expected to be a model object.
    :param derived_metric: If the metric is a property derived from database columns, the name of this property.
    :return: A result set of (stat, run_time, object id, identifying information)
    """
    if group_by_plate and not objects_expected:
        base_q = base_q.group_by(Plate.id).order_by(Plate.run_time)
    else:
        base_q = base_q.order_by(Plate.run_time, WellMetric.well_name)

    records = base_q.all()

    if group_by_plate and objects_expected:
        records = [(obj, dt, id, plate_name) for obj, dt, id, plate_name, well_name in records]
    elif not group_by_plate:
        records = [(obj, dt, id, "%s - %s" % (plate_name, well_name)) for obj, dt, id, plate_name, well_name in records]

    if objects_expected:
        import numpy as np
        # have to decorate & unwind groups if property derived
        # TODO: could there be a nicer way to define virtual props in SQLAlchemy
        records = [(getattr(obj, derived_metric), dt, id, name) for obj, dt, id, name in records]
        if group_by_plate:
            grouped_records = groupinto(records, lambda tup: tup[2])
            records = [(np.mean([r[0] for r in recs if r[0] is not None]), recs[0][1], group_id, recs[0][3]) for group_id, recs in grouped_records]
            records = [(avg, dt, id, name) for avg, dt, id, name in records if not math.isnan(avg)]
    
    return records




def create_exclude_function(form_result):
    """
    From the form, create a function that filters out statistics,
    most likely from showing up in the chart.
    """
    op = form_result['outlier_operator']
    threshold = form_result['outlier_value']
    if op and threshold is not None:
        # TODO: take logic from value_passes and make it more general
        if op == ProductValidationSpecItem.EQUAL:
            include_func = lambda v: v != form_result['outlier_value']
        elif op == ProductValidationSpecItem.LESS_THAN:
            include_func = lambda v: v >= form_result['outlier_value']
        elif op == ProductValidationSpecItem.GREATER_THAN:
            include_func = lambda v: v <= form_result['outlier_value']
    else:
        include_func = lambda v: True

    return include_func



class QueryForm(formencode.Schema):
    allow_extra_fields = True
    filter_extra_fields = True

    metric = MetricPattern(not_empty=True)
    channel_num = OneOfInt((0,1), not_empty=False, if_missing=None)
    start_date = FormattedDateConverter(date_format='%m/%d/%Y', not_empty=False, if_missing=None)
    end_date = FormattedDateConverter(date_format='%m/%d/%Y', not_empty=False, if_missing=None)
    group_by_plate = formencode.validators.Bool(not_empty=False, if_missing=False)
    outlier_operator = formencode.validators.OneOf(dict(ProductValidationSpecItem.compare_operator_field()['options']).keys(), not_empty=False, if_missing=None)
    outlier_value = formencode.validators.Number(not_empty=False, if_missing=None)

class CategoryQueryForm(QueryForm):
    pre_validators = [NestedVariables()]

    reader_category = formencode.validators.OneOf(dict(reader_category_field()['options']).keys(), not_empty=False, if_missing=None)
    sample_category = formencode.validators.OneOf(dict(sample_category_field()['options']).keys(), not_empty=False, if_missing=None)
    assay_category = formencode.validators.OneOf(dict(assay_category_field()['options']).keys(), not_empty=False, if_missing=None)
    exclude = formencode.ForEach(formencode.validators.OneOf(dict(exclusion_field()['options']).keys()), if_missing=None)

class ReaderQueryForm(QueryForm):
    pre_validators = [NestedVariables()]

    reader = IntKeyValidator(Box2, 'id', not_empty=True)
    exclude = formencode.ForEach(formencode.validators.OneOf(dict(exclusion_field()['options']).keys()), if_misisng=None)

class SearchQueryForm(QueryForm):
    pre_validators = [NestedVariables()]

    plate_name = formencode.validators.String(not_empty=False, if_missing=None)
    sample_name = formencode.validators.String(not_empty=False, if_missing=None)
    assay_name = formencode.validators.String(not_empty=False, if_missing=None)

class TrendController(BaseController):

    def _query_setup_context(self):
        c.metric_field = fl.comparable_metric_field()
        c.channel_field = fl.channel_field(blank=True, empty='--')
        c.default_start_date = datetime.now() - timedelta(90)
        c.outlier_operator_field = dict(ProductValidationSpecItem.compare_operator_field())
        c.outlier_operator_field['options'] = [(op, disp) for op, disp in c.outlier_operator_field['options']\
                                                  if op in (ProductValidationSpecItem.EQUAL,\
                                                            ProductValidationSpecItem.LESS_THAN,
                                                            ProductValidationSpecItem.GREATER_THAN)]

    def _category_query_setup_context(self):
        self._query_setup_context()
        c.sample_category_field = sample_category_field()
        c.assay_category_field = assay_category_field()
        c.reader_category_field = reader_category_field()
        c.exclusion_field = exclusion_field()

    def _category_query_base(self):
        self._category_query_setup_context()
        c.tab = 'category'
        return render('/trend/category.html')

    def _reader_query_base(self):
        self._query_setup_context()
        c.tab = 'reader'
        c.reader_field = fl.box2_field(exclude_fluidics_modules=True)
        c.exclusion_field = exclusion_field()
        return render('/trend/reader.html')

    def _search_query_base(self):
        self._query_setup_context()
        c.tab = 'search'
        c.exclusion_field = exclusion_field()
        return render('/trend/search.html')

    @help_at('features/trends.html')
    def category(self, *args, **kwargs):
        response = self._category_query_base()
        defaults = dict(request.params)
        if not request.params.get('start_date'):
            defaults['start_date'] = c.default_start_date.strftime('%m/%d/%Y')
        return h.render_bootstrap_form(response, defaults=defaults)

    @help_at('features/trends.html')
    def reader(self, *args, **kwargs):
        response = self._reader_query_base()
        defaults = dict(request.params)
        if not request.params.get('start_date'):
            defaults['start_date'] = c.default_start_date.strftime('%m/%d/%Y')
        return h.render_bootstrap_form(response, defaults=defaults)

    @help_at('features/trends.html')
    def search(self, *args, **kwargs):
        response = self._search_query_base()
        defaults = dict(request.params)
        if not request.params.get('start_date'):
            defaults['start_date'] = c.default_start_date.strftime('%m/%d/%Y')
        return h.render_bootstrap_form(response, defaults=defaults)

    def _process_and_display_trends(self, query, objects_expected):
        from qtools.lib.nstats import moving_average_by_interval
        from numpy import histogram
        import numpy as np

        group_by_plate = self.form_result['group_by_plate']
        if objects_expected:
            results = execute_built_query(query, group_by_plate, True, self.form_result['metric'][1])
        else:
            results = execute_built_query(query, group_by_plate, False)

        epoch_results = [(float(stat), time.mktime(dt.timetuple()), id, name) for stat, dt, id, name in results if stat is not None]

        exclude_func = create_exclude_function(self.form_result)
        filtered_results = [tup for tup in epoch_results if exclude_func(tup[0])]

        c.yaxis_title = fl.comparable_metric_display(MetricPattern.from_python(self.form_result['metric']))
        c.mean_value = 'N/A'
        c.std_value  = 'N/A'
        c.metric_name = fl.comparable_metric_display(MetricPattern.from_python(self.form_result['metric']))
        c.table_data =[]

        if group_by_plate:
            moving_average = 10
            epoch_url_results = [(stat, stamp*1000, url(controller='plate', action='view', id=id), name) for stat, stamp, id, name in filtered_results]
        else:
            moving_average = 50
            epoch_url_results = [(stat, stamp*1000, url(controller='well', action='view', id=id), name) for stat, stamp, id, name in filtered_results]

        if epoch_url_results:
            c.stats = {}
            stats, time_points, urls, names = zip(*epoch_url_results)
            c.stats = h.literal(json.dumps(zip(time_points, stats)))

            c.table_data = zip( names, stats, time_points )
            #update if we can.
            c.mean_value = str( np.mean( stats ) )
            c.std_value  = str( np.std( stats ) )
            
            INTERVAL = 24*60*60*1000
            ma = moving_average_by_interval(stats, time_points, INTERVAL, 10)
            c.moving_avg = h.literal(json.dumps(ma))
            c.urls = h.literal(json.dumps(urls))
            c.names = h.literal(json.dumps(names))

            # get histogram of points by day
            #raise Exception, len(ma)
            density, edges = histogram(time_points, bins=len(ma), range=(ma[0][0], ma[-1][0]))
            c.densities = h.literal(json.dumps(zip([m[0] for m in ma], [int(d) for d in density])))
            c.max_density_axis = 3*max(density)
        else:
            c.stats = {}
            c.moving_avg = {}
            c.urls = {}
            c.names = {}
            c.densities = {}
            c.max_density_axis = 3

        return render('/trend/results.html')

    @help_at('features/trends.html')
    @restrict('POST')
    @validate(schema=CategoryQueryForm(), form='_category_query_base', error_formatters=h.tw_bootstrap_error_formatters)
    def category_trend(self, *args, **kwargs):
        query, objects_expected = build_category_query(self.form_result)
        c.back_url = url(controller='trend', action='category')
        response = self._process_and_display_trends(query, objects_expected)
        return h.render_bootstrap_form(response, defaults=CategoryQueryForm.from_python(self.form_result))


    @help_at('features/trends.html')
    @restrict('POST')
    @validate(schema=ReaderQueryForm(), form='_reader_query_base', error_formatters=h.tw_bootstrap_error_formatters)
    def reader_trend(self, *args, **kwargs):
        query, objects_expected = build_reader_query(self.form_result)
        c.back_url = url(controller='trend', action='reader')
        response = self._process_and_display_trends(query, objects_expected)
        return h.render_bootstrap_form(response, defaults=ReaderQueryForm.from_python(self.form_result))

    @help_at('features/trends.html')
    @restrict('POST')
    @validate(schema=SearchQueryForm(), form='_search_query_base', error_formatters=h.tw_bootstrap_error_formatters)
    def search_trend(self, *args, **kwargs):
        query, objects_expected = build_search_query(self.form_result)
        c.back_url = url(controller='trend', action='search')
        response = self._process_and_display_trends(query, objects_expected)
        return h.render_bootstrap_form(response, defaults=SearchQueryForm.from_python(self.form_result))
