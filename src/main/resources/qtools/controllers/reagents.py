import logging, operator
from itertools import chain
from collections import defaultdict

from pylons import request, response, session, tmpl_context as c, url
from pylons.controllers.util import abort, redirect
from pylons.decorators import validate
from pylons.decorators.rest import restrict

from pyqlb.writers import QLTWriter

from repoze.what.predicates import has_permission

from qtools.lib.auth import WowoActionProtector

from qtools.lib.base import BaseController, render
from qtools.lib.collection import groupinto
from qtools.lib.decorators import multi_validate
import qtools.lib.fields as fl
import qtools.lib.helpers as h
from qtools.lib.qlb_objects import singlecolor_label_funcs
from qtools.lib.metrics.db import dbplate_metrics_tree
from qtools.lib.validators import OneOfInt, FormattedDateConverter, MetricPattern, CapitalLetter, IntKeyValidator, SanitizedString

from qtools.model import Session, Plate
from qtools.model.reagents import *
from qtools.model.reagents.templates import make_qlplate_for_layout

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import joinedload_all

import formencode
from formencode.variabledecode import NestedVariables
from webhelpers import paginate

log = logging.getLogger(__name__)

# only do this in development -- change to RestrictedWowoActionProtector when
# things are ready to go
AuthProtector = WowoActionProtector

################################################################################
# Constants
################################################################################
DATE_MANUFACTURED_FORMAT = '%m/%d/%Y'


################################################################################
# Controller-Specific Fields
################################################################################
def product_line_type_field(selected=None):
    return {'value': selected or '',
            'options': ProductLine.type_display_options()}

def product_line_field(selected=None):
    return {'value': selected or '',
            'options': [('','All')]+Session.query(ProductLine.id, ProductLine.name).order_by(ProductLine.name).all()}

def template_type_field(selected=None):
    return {'value': selected or '',
            'options': ValidationTestTemplate.all_display_options()}

def lot_number_field(product_part, selected=None):
    return {'value': selected or '',
            'options': sorted([(lot.id, lot.number) for lot in product_part.lot_numbers], key=operator.itemgetter(1))}


################################################################################
# Validation Forms
################################################################################
class ProductLineForm(formencode.Schema):
    allow_extra_fields = True
    filter_extra_fields = True

    type = OneOfInt(dict(ProductLine.type_display_options()).keys())
    name = formencode.validators.String(not_empty=True)

class ProductPartForm(formencode.Schema):
    allow_extra_fields = True
    filter_extra_fields = True

    name = formencode.validators.String(not_empty=True)
    rev = CapitalLetter(not_empty=True, if_missing='A')

class ProductLotItem(formencode.Schema):
    allow_extra_fields = True
    filter_extra_fields = True

    number = formencode.validators.String(not_empty=True)
    date_manufactured = FormattedDateConverter(date_format=DATE_MANUFACTURED_FORMAT, not_empty=False)

class ProductLotForm(ProductLotItem):
    """
    Expanded -- with notes.
    """
    notes = formencode.validators.String(not_empty=False)

class ProductLotsForm(formencode.Schema):
    allow_extra_fields = True
    filter_extra_fields = True
    pre_validators = [NestedVariables()]

    lots = formencode.ForEach(ProductLotItem(), not_empty=True, if_missing=formencode.NoDefault)

class ProductSpecItem(formencode.Schema):
    allow_extra_fields = True
    filter_extra_fields = True

    metric = MetricPattern(not_empty=True)
    operator = formencode.validators.OneOf(dict(ProductValidationSpecItem.compare_operator_field()['options']).keys(), not_empty=True)
    channel_num = OneOfInt((0,1), not_empty=False, if_missing=None)
    value1 = formencode.validators.Number(not_empty=False, if_missing=None)
    value2 = formencode.validators.Number(not_empty=False, if_missing=None)


class ProductSpecForm(formencode.Schema):
    allow_extra_fields = True
    filter_extra_fields = True
    pre_validators = [NestedVariables()]

    name = SanitizedString(not_empty=True)
    negative_items = formencode.ForEach(ProductSpecItem(), not_empty=False)
    positive_items = formencode.ForEach(ProductSpecItem(), not_empty=False)
    test_template_id = IntKeyValidator(ValidationTestTemplate, 'id')
    notes = SanitizedString(not_empty=False, if_missing=None)

class TemplateLotItem(formencode.Schema):
    allow_extra_fields = True
    filter_extra_fields = True

    lot_number = IntKeyValidator(ProductLot, 'id', not_empty=True)

class MakeTemplateForm(formencode.Schema):
    allow_extra_fields = True
    filter_extra_fields = True
    pre_validators = [NestedVariables()]

    controls = formencode.ForEach(TemplateLotItem(), not_empty=True, if_missing=formencode.NoDefault)
    tests = formencode.ForEach(TemplateLotItem(), not_empty=True, if_missing=formencode.NoDefault)
    name = formencode.validators.MaxLength(30, not_empty=False, if_missing=None)

class PlateFilterForm(formencode.Schema):
    allow_extra_fields = True
    filter_extra_fields = True

    product_line_id = IntKeyValidator(ProductLine, 'id', not_empty=False, if_missing=None)


################################################################################
# Actions
################################################################################
class ReagentsController(BaseController):

    def lines(self):
        product_lines = Session.query(ProductLine).order_by('type, name')
        c.product_groups = sorted(groupinto(product_lines, lambda pl: pl.type_display))
        return render('/reagents/lines.html')

    def __setup_line_fields(self):
        c.type = product_line_type_field()

    def _line_new_base(self):
        self.__setup_line_fields()
        c.title = "Create Product Line"
        c.submit_action = url(controller='reagents', action='line_create')
        c.call_to_action = "Create Line"
        c.record_exists = False
        c.allow_delete = False
        response = render('/reagents/line_edit.html')
        return response

    @AuthProtector(has_permission('product-edit'))
    def line_new(self):
        response = self._line_new_base()
        return h.render_bootstrap_form(response)

    def _line_edit_base(self, line_id):
        self.__setup_line_fields()
        c.title = "Edit Product Line"
        c.line_id = line_id
        c.submit_action = url(controller='reagents', action='line_save', id=line_id)
        c.call_to_action = 'Save Product Line'
        c.record_exists = True
        c.allow_delete = False
        response = render('/reagents/line_edit.html')
        return response

    @AuthProtector(has_permission('product-edit'))
    def line_edit(self, id=None):
        line = Session.query(ProductLine).get(id)
        if not line:
            abort(404)

        c.line = line
        response = self._line_edit_base(id)
        return h.render_bootstrap_form(response, defaults=line.__dict__)


    def __update_product_line(self, record=None):
        if not record:
            record = ProductLine(type=self.form_result['type'],
                                 name=self.form_result['name'])
        else:
            record.type = self.form_result['type']
            record.name = self.form_result['name']

        # this try/catch may not be necessary, but I might add uniqueness constraint
        try:
            Session.add(record)
            Session.commit()
        except IntegrityError, e:
            Session.rollback()
            raise e

    @AuthProtector(has_permission('product-edit'))
    @restrict('POST')
    @validate(schema=ProductLineForm(), form='_line_new_base', error_formatters=h.tw_bootstrap_error_formatters)
    def line_create(self):
        try:
            self.__update_product_line()
        except IntegrityError:
            response = self._line_new_base()
            defaults = ProductLineForm().from_python(self.form_result)
            return h.render_bootstrap_form(response,
                defaults=defaults,
                errors={'name': 'A product line already exists with this name.'},
                error_formatters=h.tw_bootstrap_error_formatters)

        session['flash'] = 'Product line created.'
        session.save()
        return redirect(url(controller='reagents', action='lines'))

    @AuthProtector(has_permission('product-edit'))
    @restrict('POST')
    @validate(schema=ProductLineForm(), form='_line_edit_base', error_formatters=h.tw_bootstrap_error_formatters)
    def line_save(self, id=None):
        line = Session.query(ProductLine).get(id)
        if not line:
            abort(404)
        try:
            self.__update_product_line(record=line)
        except IntegrityError:
            response = self._line_edit_base(id)
            defaults = ProductLineForm().from_python(self.form_result)
            return h.render_bootstrap_form(response,
                defaults=defaults,
                errors={'name': 'A product line already exists with this name.'},
                error_formatters=h.tw_bootstrap_error_formatters)
        session['flash'] = 'Product line saved.'
        session.save()
        return redirect(url(controller='reagents', action='lines'))

    def parts(self, id=None):
        line = Session.query(ProductLine).filter_by(id=id)\
        .options(joinedload_all(ProductLine.part_numbers, ProductPart.specs, ProductPart.lot_numbers)).first()
        if not line:
            abort(404)

        c.line = line
        c.part_numbers = sorted(line.part_numbers, key=operator.attrgetter('name'))
        return render('/reagents/parts.html')

    def _part_new_base(self, id=None):
        c.title = "Create Part Number"
        c.line_id = id
        c.submit_action = url(controller='reagents', action='part_create', id=id)
        c.call_to_action = "Create Part Number"
        c.record_exists = False
        c.allow_delete = False
        response = render('/reagents/part_edit.html')
        return response


    @AuthProtector(has_permission('product-edit'))
    def part_new(self, id=None):
        c.line = Session.query(ProductLine).get(id)
        if not c.line:
            abort(404)

        response = self._part_new_base(id)
        return h.render_bootstrap_form(response)

    def _part_edit_base(self, id=None):
        part = Session.query(ProductPart).get(id)
        if not part:
            abort(404)

        c.part = part
        c.title = "Edit Part Number"
        c.submit_action = url(controller='reagents', action='part_save', id=id)
        c.call_to_action = 'Save Part Number'
        c.record_exists = True
        c.allow_delete = False
        response = render('/reagents/part_edit.html')
        return response

    @AuthProtector(has_permission('product-edit'))
    def part_edit(self, id=None):
        response = self._part_edit_base(id)
        return h.render_bootstrap_form(response, defaults=c.part.__dict__)

    def __update_product_part(self, line=None, record=None):
        if line and not record:
            record = ProductPart(name=self.form_result['name'],
                                 rev=self.form_result['rev'])
            line.part_numbers.append(record)
        else:
            record.name = self.form_result['name']
            record.rev = self.form_result['rev']

        # this try/catch may not be necessary, but I might add uniqueness constraint
        try:
            Session.add(record)
            Session.commit()
        except IntegrityError, e:
            Session.rollback()
            raise e

    @AuthProtector(has_permission('product-edit'))
    @restrict('POST')
    @validate(schema=ProductPartForm(), form='_part_new_base', error_formatters=h.tw_bootstrap_error_formatters)
    def part_create(self, id=None):
        c.line = Session.query(ProductLine).get(id)
        if not c.line:
            abort(404)
        try:
            self.__update_product_part(line=c.line)
        except IntegrityError:
            response = self._part_new_base()
            defaults = ProductPartForm().from_python(self.form_result)
            return h.render_bootstrap_form(response,
                defaults=defaults,
                errors={'name': 'A part number with this name already exists.'},
                error_formatters=h.tw_bootstrap_error_formatters)

        session['flash'] = 'Part number created.'
        session.save()
        return redirect(url(controller='reagents', action='parts', id=c.line.id))

    @AuthProtector(has_permission('product-edit'))
    @restrict('POST')
    @validate(schema=ProductPartForm(), form='_part_edit_base', error_formatters=h.tw_bootstrap_error_formatters)
    def part_save(self, id=None):
        c.part = Session.query(ProductPart).get(id)
        if not c.part:
            abort(404)
        try:
            self.__update_product_part(record=c.part)
        except IntegrityError:
            response = self._part_edit_base()
            defaults = ProductPartForm().from_python(self.form_result)
            return h.render_bootstrap_form(response,
                defaults=defaults,
                errors={'name': 'A part number with this name already exists.'},
                error_formatters=h.tw_bootstrap_error_formatters)
        session['flash'] = 'Part number saved.'
        session.save()
        return redirect(url(controller='reagents', action='parts', id=c.part.product_line.id))

    def __all_validation_plate_query(self):
        return Session.query(ProductValidationPlate)\
                      .join(ProductValidationPlate.plate)\
                      .options(joinedload_all(ProductValidationPlate.spec, ProductValidationSpec.part, ProductPart.product_line, innerjoin=True),
                               joinedload_all(ProductValidationPlate.plate, Plate.box2, innerjoin=True))\
                      .order_by(Plate.run_time.desc())

    def _plate_base(self, query, pager_kwargs=None):
        c.product_line_field = product_line_field()
        c.paginator = paginate.Page(
            query,
            page=int(request.params.get('page', 1)),
            items_per_page=15
        )
        c.pager_kwargs = pager_kwargs or {}
        return render('/reagents/plate_list.html')

    def plates(self):
        query = self.__all_validation_plate_query()
        response = self._plate_base(query)
        return h.render_bootstrap_form(response)

    @validate(schema=PlateFilterForm(), form='plates', post_only=False, on_get=True, error_formatters=h.tw_bootstrap_error_formatters)
    def plate_filter(self):
        query = self.__all_validation_plate_query()
        if self.form_result['product_line_id'] is not None:
            query = query.join(ProductValidationPlate.spec)\
                         .join(ProductValidationSpec.part)\
                         .filter(ProductPart.product_line_id == self.form_result['product_line_id'])
        response = self._plate_base(query, dict(self.form_result))
        return h.render_bootstrap_form(response, defaults=PlateFilterForm.from_python(self.form_result))


    def part_plates(self, id=None):
        c.part = Session.query(ProductPart).get(id)
        if not c.part:
            abort(404)

        c.test_plates = c.part.recent_validation_plates(eagerload_plates=True)\
            .options(joinedload_all(ProductValidationPlate.plate, ProductValidationPlate.spec, Plate.box2, innerjoin=True)).all()

        return render('/reagents/part_tests.html')


    def lots(self, id=None):
        part = Session.query(ProductPart).filter_by(id=id)\
        .options(joinedload_all(ProductPart.lot_numbers)).first()
        if not part:
            abort(404)

        c.part = part
        c.lot_numbers = sorted(part.lot_numbers, key=operator.attrgetter('date_added'))
        return render('/reagents/lots.html')

    def _lot_new_base(self, id=None):
        c.title = "Create Lot Number"
        c.part_id = id
        c.submit_action = url(controller='reagents', action='lot_create', id=id)
        c.call_to_action = "Create Lot Number"
        c.record_exists = False
        c.allow_delete = False
        response = render('/reagents/lot_edit.html')
        return response

    @AuthProtector(has_permission('product-edit'))
    def lot_new(self, id=None):
        c.part = Session.query(ProductPart).get(id)
        if not c.part:
            abort(404)

        response = self._lot_new_base(id)
        return h.render_bootstrap_form(response)

    def _lot_many_base(self, id):
        c.part = Session.query(ProductPart).get(id)
        if not c.part:
            abort(404)

        if not hasattr(c, 'lots_length'):
            c.lots_length = 0

        response = render('/reagents/multilot_create.html')
        return response

    @AuthProtector(has_permission('product-edit'))
    def lot_many(self, id=None):
        response = self._lot_many_base(id)
        return h.render_bootstrap_form(response)

    def _lot_edit_base(self, id=None):
        c.title = "Edit Lot Number"
        c.submit_action = url(controller='reagents', action='lot_save', id=id)
        c.call_to_action = 'Save Lot Number'
        c.record_exists = True
        c.allow_delete = False
        response = render('/reagents/lot_edit.html')
        return response

    def __correct_lot_date_manufactured_display(self, lot, defaults):
        if defaults.get('date_manufactured', None):
            defaults['date_manufactured'] = lot.date_manufactured.strftime(DATE_MANUFACTURED_FORMAT)
        return defaults

    @AuthProtector(has_permission('product-edit'))
    def lot_edit(self, id=None):
        """
        NOTE: does not allow (yet) for editing the rev of the product that
        the lot is tied to.
        """
        lot = Session.query(ProductLot).get(id)
        if not lot:
            abort(404)

        c.lot = lot
        response = self._lot_edit_base(id)
        defaults = lot.__dict__
        self.__correct_lot_date_manufactured_display(c.lot, defaults)
        return h.render_bootstrap_form(response, defaults=lot.__dict__)

    def __update_product_lot(self, part=None, record=None):
        if part and not record:
            # tie lot number with product rev here
            record = ProductLot(number=self.form_result['number'],
                                date_manufactured=self.form_result['date_manufactured'],
                                notes=self.form_result['notes'],
                                product_rev=part.rev)
            part.lot_numbers.append(record)
        else:
            record.number = self.form_result['number']
            record.date_manufactured = self.form_result['date_manufactured']
            record.notes = self.form_result['notes']

        # this try/catch may not be necessary, but I might add uniqueness constraint
        try:
            Session.add(record)
            Session.commit()
        except IntegrityError, e:
            Session.rollback()
            raise e

    @AuthProtector(has_permission('product-edit'))
    @restrict('POST')
    @validate(schema=ProductLotForm(), form='_lot_new_base', error_formatters=h.tw_bootstrap_error_formatters)
    def lot_create(self, id=None):
        c.part = Session.query(ProductPart).get(id)
        if not c.part:
            abort(404)
        try:
            self.__update_product_lot(part=c.part)
        except IntegrityError:
            response = self._lot_new_base()
            defaults = ProductLotForm().from_python(self.form_result)
            return h.render_bootstrap_form(response,
                defaults=defaults,
                errors={'name': 'A lot number with this name already exists.'},
                error_formatters=h.tw_bootstrap_error_formatters)

        session['flash'] = 'Lot number created.'
        session.save()
        return redirect(url(controller='reagents', action='lots', id=c.part.id))

    @AuthProtector(has_permission('product-edit'))
    @restrict('POST')
    @multi_validate(schema=ProductLotsForm(), form='_lot_many_base', error_formatters=h.tw_bootstrap_alert_error_formatters)
    def lot_create_many(self, id=None):
        part = Session.query(ProductPart).get(id)
        if not part:
            abort(404)
        try:
            for lot in self.form_result['lots']:
                # tie product rev to lot here
                record = ProductLot(number=lot['number'],
                                    date_manufactured=lot['date_manufactured'],
                                    product_rev=part.rev)
                part.lot_numbers.append(record)
                Session.add(record)
            Session.commit()
        except IntegrityError, e:
            session['flash'] = 'One of these lot numbers is already in use.'
            session['flash_class'] = 'error'
            session.save()
            response = self._lot_many_base(part.id)
            defaults = ProductLotsForm().from_python(self.form_result)
            return h.render_bootstrap_form(response,
                defaults=defaults,
                errors={'name': 'A lot number with this name already exists.'},
                error_formatters=h.tw_bootstrap_error_formatters)

        session['flash'] = 'Lots created.'
        session.save()
        return redirect(url(controller='reagents', action='lots', id=part.id))

    @AuthProtector(has_permission('product-edit'))
    @restrict('POST')
    @validate(schema=ProductLotForm(), form='_lot_edit_base', error_formatters=h.tw_bootstrap_error_formatters)
    def lot_save(self, id=None):
        c.lot = Session.query(ProductLot).get(id)
        if not c.lot:
            abort(404)
        try:
            self.__update_product_lot(record=c.lot)
        except IntegrityError:
            response = self._lot_edit_base()
            defaults = ProductLotForm().from_python(self.form_result)
            self.__correct_lot_date_manufactured_display(c.lot, defaults)
            return h.render_bootstrap_form(response,
                defaults=defaults,
                errors={'name': 'A lot number with this name already exists.'},
                error_formatters=h.tw_bootstrap_error_formatters)
        session['flash'] = 'Lot number saved.'
        session.save()
        return redirect(url(controller='reagents', action='lots', id=c.lot.part.id))

    def specs(self, id=None):
        part = Session.query(ProductPart).filter_by(id=id)\
        .options(joinedload_all(ProductPart.specs)).first()
        if not part:
            abort(404)

        c.part = part
        c.specs = sorted(part.specs, key=operator.attrgetter('date'))[::-1]
        return render('/reagents/specs.html')

    def _spec_new_base(self, id=None):
        c.part = Session.query(ProductPart).get(id)
        if not c.part:
            abort(404)

        c.title = "Create Spec"
        c.part_id = id
        c.line_id = c.part.product_line_id
        c.submit_action = url(controller='reagents', action='spec_create', id=id)
        c.template_types = template_type_field()
        c.call_to_action = "Create Spec"
        if not hasattr(c, 'positive_items_length'):
            c.positive_items_length = 0
        if not hasattr(c, 'negative_items_length'):
            c.negative_items_length = 0
        c.record_exists = False
        c.allow_delete = False
        c.metrics = fl.comparable_metric_field()
        c.operators = ProductValidationSpecItem.compare_operator_field()
        c.channel_nums = fl.channel_field(blank=True, empty='N/A')
        response = render('/reagents/spec_edit.html')
        return response

    @AuthProtector(has_permission('product-spec-edit'))
    def spec_new(self, id=None):
        response = self._spec_new_base(id)
        return h.render_bootstrap_form(response)

    def _spec_edit_base(self, part_id):
        c.title = "Edit Spec"
        c.submit_action = url(controller='reagents', action='spec_create', id=part_id)
        c.call_to_action = 'Save Spec'
        c.record_exists = True
        c.allow_delete = False
        c.template_types = template_type_field()
        c.metrics = fl.comparable_metric_field()
        c.operators = ProductValidationSpecItem.compare_operator_field()
        c.channel_nums = fl.channel_field(blank=True, empty='N/A')
        response = render('/reagents/spec_edit.html')
        return response

    def __insert_product_spec(self, part):
        spec = ProductValidationSpec(
            name=self.form_result['name'],
            notes=self.form_result['notes'],
            test_template_id=self.form_result['test_template_id'])
        spec.items = []
        for item in self.form_result['positive_items']:
            if item['value1'] is not None:
                record = ProductValidationSpecItem(metric="%s.%s" % tuple(item['metric']),
                    operator=item['operator'],
                    value1=item['value1'],
                    value2=item['value2'],
                    channel_num=item['channel_num'],
                    well_type=ProductValidationSpecItem.POSITIVE_ITEM)
                spec.items.append(record)
        for item in self.form_result['negative_items']:
            if item['value1'] is not None:
                record = ProductValidationSpecItem(metric="%s.%s" % tuple(item['metric']),
                    operator=item['operator'],
                    value1=item['value1'],
                    value2=item['value2'],
                    channel_num=item['channel_num'],
                    well_type=ProductValidationSpecItem.NEGATIVE_ITEM)
                spec.items.append(record)

        part.specs.append(spec)
        Session.add(spec)
        Session.commit()

    @AuthProtector(has_permission('product-spec-edit'))
    def spec_edit(self, id=None):
        c.spec = Session.query(ProductValidationSpec).get(id)
        c.part = c.spec.part
        c.part_id = c.part.id
        c.line_id = c.spec.part.product_line.id

        if not c.spec:
            abort(404)

        positive_items = [item.__dict__ for item in c.spec.positive_items]
        negative_items = [item.__dict__ for item in c.spec.negative_items]
        for i in chain(positive_items, negative_items):
            i['metric'] = i['metric'].split('.')
        spec = c.spec.__dict__
        spec['positive_items'] = positive_items
        spec['negative_items'] = negative_items
        c.positive_items_length = len(c.spec.positive_items)
        c.negative_items_length = len(c.spec.negative_items)
        response = self._spec_edit_base(c.part_id)
        return h.render_bootstrap_form(response, defaults=ProductSpecForm().from_python(spec))





    @AuthProtector(has_permission('product-spec-edit'))
    @restrict('POST')
    @multi_validate(schema=ProductSpecForm(), form='_spec_new_base', error_formatters=h.tw_bootstrap_alert_error_formatters)
    def spec_create(self, id=None):
        c.part = Session.query(ProductPart).get(id)
        if not c.part:
            abort(404)
        try:
            self.__insert_product_spec(c.part)
        except IntegrityError:
            response = self._spec_new_base()
            defaults = ProductSpecForm().from_python(self.form_result)
            return h.render_bootstrap_form(response,
                defaults=defaults,
                errors={'name': 'A spec with this name already exists.'},
                error_formatters=h.tw_bootstrap_error_formatters)

        session['flash'] = 'Spec created.'
        session.save()
        return redirect(url(controller='reagents', action='parts', id=c.part.product_line.id))

    def __metric_display(self, metric):
        # TODO make this a global function
        metric_lookup_dict = dict()
        for category, mappings in fl.comparable_metric_field():
            metric_lookup_dict.update(dict(mappings))

        return metric_lookup_dict.get(metric, 'Unknown')

    def __operator_display(self, opcode):
        operator_lookup_dict = dict(ProductValidationSpecItem.compare_operator_field()['options'])
        return operator_lookup_dict.get(opcode, '?')

    def spec(self, id=None):
        c.spec = Session.query(ProductValidationSpec).get(id)
        if not c.spec:
            abort(404)

        tab = request.params.get('tab', 'spec')
        if tab not in ('plates', 'spec'):
            c.tab = 'spec'
        else:
            c.tab = tab

        # setup for pagination later
        c.test_plates = c.spec.recent_validation_plates(eagerload_plates=True)\
            .options(joinedload_all(ProductValidationPlate.plate, Plate.box2, innerjoin=True)).all()

        c.positive_spec_items = []
        for item in c.spec.positive_items:
            c.positive_spec_items.append({'metric': self.__metric_display(item.metric),
                                 'operator': self.__operator_display(item.operator),
                                 'value1': item.value1,
                                 'value2': item.value2,
                                 'channel_display': item.channel_display})

        c.negative_spec_items = []
        for item in c.spec.negative_items:
            c.negative_spec_items.append({'metric': self.__metric_display(item.metric),
                                          'operator': self.__operator_display(item.operator),
                                          'value1': item.value1,
                                          'value2': item.value2,
                                          'channel_display': item.channel_display})
        return render('/reagents/spec.html')

    def lot_tests(self, id=None):
        c.lot = Session.query(ProductLot).get(id)
        if not c.lot:
            abort(404)

        c.tests = c.lot.recent_test_query(eagerload_plates=True)
        return render('/reagents/lot_tests.html')

    def _template_setup_context(self, part_id=None):
        c.part = Session.query(ProductPart)\
                        .filter_by(id=part_id)\
                        .options(joinedload_all(ProductPart.lot_numbers)).first()

        if not c.part:
            abort(404)

        c.spec = c.part.current_spec

    def _template_base(self, id=None):
        self._template_setup_context(id)
        c.lot_numbers = lot_number_field(c.part)
        validation_layout = c.spec.test_template.layout
        control_positives = validation_layout.control_positive_names
        control_negatives = validation_layout.control_negative_names
        test_positives = validation_layout.test_positive_names
        test_negatives = validation_layout.test_negative_names

        c.controls = enumerate(zip(control_negatives, control_positives))
        c.tests = enumerate(zip(test_negatives, test_positives))
        return render('/reagents/template.html')

    def template(self, id=None):
        response = self._template_base(id)
        return h.render_bootstrap_form(response)

    @restrict('POST')
    @multi_validate(schema=MakeTemplateForm(), form='_template_base', error_formatters=h.tw_bootstrap_alert_error_formatters)
    def make_template(self, id=None):
        # assert lots belong to product part
        self._template_setup_context(id)

        product_lots = {lot.id : lot.number for lot in c.part.lot_numbers}
        controls = self.form_result['controls']
        tests = self.form_result['tests']

        errors = {}
        for idx, control in enumerate(controls):
            if control['lot_number'] not in product_lots:
                errors['controls-%s.lot_number' % idx] = 'Invalid lot.'

        for idx, test in enumerate(tests):
            if test['lot_number'] not in product_lots:
                errors['tests-%s' % idx] = 'Invalid lot.'

        if errors:
            resp = self._template_base()
            defaults = MakeTemplateForm().from_python(self.form_result)
            return h.render_bootstrap_form(resp,
                defaults=defaults,
                errors=errors,
                error_formatters=h.tw_bootstrap_error_formatters)

        # if we get here, everything is OK -- make the plate.
        layout = c.spec.test_template.layout
        control_names = [product_lots[control['lot_number']] for control in controls]
        test_names = [product_lots[test['lot_number']] for test in tests]
        qlplate = make_qlplate_for_layout(layout, control_names, test_names)

        # TODO figure out run order here

        prefix = '%s__%s' % (c.part.name, c.spec.name)
        if self.form_result['name'] is not None:
            prefix = "%s__%s" % (prefix, self.form_result['name'])
        response.headers['Content-Type'] = 'application/quantalife-template'
        h.set_download_response_header(request, response, "%s.qlt" % prefix)

        fg, bg = singlecolor_label_funcs(153,0,0)
        writer = QLTWriter(fgcolorfunc=fg,bgcolorfunc=bg)
        qlt = writer.getbytes(qlplate)
        return qlt

    def test_plate(self, id=None):
        c.validation_plate = Session.query(ProductValidationPlate).get(id)
        if not c.validation_plate:
            abort(404)

        # get plate metrics tree -- assume no reprocess support for now
        root_pm = dbplate_metrics_tree(c.validation_plate.plate_id)

        # grab positive and negative tests by lot number
        lot_tests = c.validation_plate.lot_tests
        control_results = defaultdict(lambda: {'positives': [], 'negatives': []})
        test_results = defaultdict(lambda: {'positives': [], 'negatives': []})
        wells = dict([(wm.well_name, wm) for wm in root_pm.well_metrics])

        for test_coll, results_coll in (('control_lot_tests', control_results),
                                        ('test_lot_tests', test_results)):
            for test in getattr(c.validation_plate, test_coll):
                if test.wells:
                    tested_wells = [wells[well] for well in test.wells.split(',')]
                else:
                    continue

                if test.well_type == ProductValidationPlateLotTest.WELL_TYPE_POSITIVE:
                    pos_items = c.validation_plate.spec.positive_items
                    spec_test_results = [(wm.well.sample_name, wm.well_name, item.record_val(wm), item.is_passed_by(wm)) for wm in tested_wells for item in pos_items]
                    results_coll[test.lot.number]['positives'] = spec_test_results
                elif test.well_type == ProductValidationPlateLotTest.WELL_TYPE_NEGATIVE:
                    neg_items = c.validation_plate.spec.negative_items
                    spec_test_results = [(wm.well.sample_name, wm.well_name, item.record_val(wm), item.is_passed_by(wm)) for wm in tested_wells for item in neg_items]
                    results_coll[test.lot.number]['negatives'] = spec_test_results

        control_results_by_sample = sorted(control_results.items())
        test_results_by_sample = sorted(test_results.items())

        c.control_results = [(sample_name, {'positives': sorted(groupinto(groups['positives'], lambda tup: tup[1])),
                                            'negatives': sorted(groupinto(groups['negatives'], lambda tup: tup[1]))})
                                for sample_name, groups in control_results_by_sample]
        c.test_results = [(sample_name, {'positives': sorted(groupinto(groups['positives'], lambda tup: tup[1])),
                                         'negatives': sorted(groupinto(groups['negatives'], lambda tup: tup[1]))})
                             for sample_name, groups in test_results_by_sample]

        for result_set in (c.control_results, c.test_results):
            for sample_name, pos_neg in result_set:
                for pos_or_neg, well_info in pos_neg.items():
                    if pos_or_neg == 'positives':
                        spec_items = c.validation_plate.spec.positive_items
                    else:
                        spec_items = c.validation_plate.spec.negative_items
                    sums = [0]*len(spec_items)
                    for well_name, results in well_info:
                        for idx, result in enumerate(results):
                            sums[idx] = sums[idx] + result[2]

                    averages_row = []
                    for item, thesum in zip(spec_items, sums):
                        avg = thesum/float(len(well_info))
                        averages_row.append((sample_name, 'Avg', avg, item.value_passes(avg)))
                    well_info.insert(0, ('Avg', averages_row))

        c.positive_metric_displays = []
        c.negative_metric_displays = []
        for item in c.validation_plate.spec.positive_items:
            if item.channel_display is not None:
                c.positive_metric_displays.append("%s %s" % (item.channel_display, self.__metric_display(item.metric)))
            else:
                c.positive_metric_displays.append(self.__metric_display(item.metric))

        for item in c.validation_plate.spec.negative_items:
            if item.channel_display is not None:
                c.negative_metric_displays.append("%s %s" % (item.channel_display, self.__metric_display(item.metric)))
            else:
                c.negative_metric_displays.append(self.__metric_display(item.metric))

        c.positive_criteria_displays = [item.criteria_display for item in c.validation_plate.spec.positive_items]
        c.negative_criteria_displays = [item.criteria_display for item in c.validation_plate.spec.negative_items]
        return render("/reagents/test_plate.html")


    def test_result(self, id=None):
        """
        This method is currently busted.
        """
        c.test = Session.query(ProductValidationPlate).get(id)
        if not c.test:
            abort(404)

        # right now assuming that reprocessor won't figure into the mix
        root_pm = dbplate_metrics_tree(c.test.plate_id)

        wells = dict([(wm.well_name, wm) for wm in root_pm.well_metrics])
        # ignore wells, order by s
        if c.test.wells:
            tested_wells = [wells[well] for well in c.test.wells.split(',')]
        else:
            tested_wells = wells.values()

        test_results = [(wm.well.sample_name, wm.well_name, item.record_val(wm), item.is_passed_by(wm) if 'NTC' not in wm.well.sample_name else None) for wm in tested_wells for item in c.test.spec.items]

        test_results_by_sample = sorted(groupinto(test_results, lambda tup: tup[0]))
        c.test_results = [(sample_name, sorted(groupinto(rows, lambda tup: tup[1]))) for sample_name, rows in test_results_by_sample]


        for sample_name, well_names in c.test_results:
            sums = [0]*len(c.test.spec.items)
            for well_name, results in well_names:
                for idx, result in enumerate(results):
                    sums[idx] = sums[idx] + result[2]

            averages_row = []
            for item, thesum in zip(c.test.spec.items, sums):
                avg = thesum/float(len(well_names))
                averages_row.append((sample_name, 'Avg', avg, item.value_passes(avg) if 'NTC' not in sample_name else None))
            well_names.insert(0, ('Avg', averages_row))



        c.metric_displays = []
        for item in c.test.spec.items:
            if item.channel_display is not None:
                c.metric_displays.append("%s %s" % (item.channel_display, self.__metric_display(item.metric)))
            else:
                c.metric_displays.append(self.__metric_display(item.metric))

        c.criteria_displays = [item.criteria_display for item in c.test.spec.items]
        return render("/reagents/test_result.html")
