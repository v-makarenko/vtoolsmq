import operator, json

from sqlalchemy import Column, Integer, Sequence, Unicode, ForeignKey, UnicodeText, Float, Text, DateTime, Date, String
from sqlalchemy import orm
from sqlalchemy.orm import backref, contains_eager

from qtools.model import now, Plate
from qtools.model.meta import Session, Base
from qtools.model.platewell import get_well_metric_col_accessor, get_well_channel_metric_col_accessor

from .templates import ValidationTestLayout


metadata = Base.metadata

__all__ = ['ProductLine', 'ProductPart', 'ProductLot',
           'ProductValidationSpec', 'ProductValidationSpecItem', 'ProductValidationPlate',
           'ProductValidationPlateLotTest', 'ValidationTestTemplate']

class ProductLine(Base):
    __tablename__ = "product_line"
    __table_args__ = {"mysql_engine": 'InnoDB', 'mysql_charset': 'utf8'}

    TYPE_REAGENT = 0
    TYPE_CONSUMABLE = 1

    id = Column(Integer, Sequence('product_line_seq_id', optional=True), primary_key=True)
    name = Column(Unicode(255), nullable=False)
    type = Column(Integer, nullable=False, default=0)
    part_numbers = orm.relation('ProductPart', backref='product_line')

    @classmethod
    def type_display_options(cls):
        return [(ProductLine.TYPE_REAGENT, 'Reagent'),
                (ProductLine.TYPE_CONSUMABLE, 'Consumable')]

    @property
    def type_display(self):
        return dict(self.__class__.type_display_options()).get(self.type, '')


class ProductPart(Base):
    __tablename__ = "product_part"
    __table_args__ = {"mysql_engine": 'InnoDB', 'mysql_charset': 'utf8'}

    id = Column(Integer, Sequence('product_part_seq_id', optional=True), primary_key=True)
    name = Column(Unicode(255), nullable=False)
    product_line_id = Column(Integer, ForeignKey('product_line.id'), nullable=False)
    rev = Column(String(1), nullable=False, default='A')

    lot_numbers = orm.relation('ProductLot', backref='part')
    specs = orm.relation('ProductValidationSpec', backref='part')

    @property
    def current_spec(self):
        if not self.specs:
            return None
        else:
            return sorted(self.specs, key=operator.attrgetter('date'))[-1]

    def spec_for_date(self, dt):
        """
        Return the spec that was active at the specified time.
        If there are no associated specs, return None.  If the time
        was before any of the specs were established, return the first
        known spec.
        """
        specs = sorted(self.specs, key=operator.attrgetter('date'))
        if not specs:
            return None
        for s in specs:
            if dt < s.date:
                return s
        return specs[-1]

    @property
    def current_rev_lots(self):
        """
        Return the lots for the current rev of the product.
        """
        return self.lots_for_rev(self.rev)

    def lots_for_rev(self, rev):
        """
        Return the lots for the specified product rev.  The rev is
        assumed to be an uppercase letter.
        """
        return [lot for lot in self.lot_numbers if lot.product_rev == rev.upper()]

    def recent_validation_plates(self, eagerload_plates=False):
        """
        Returns the most recent tests for this part.
        """
        if eagerload_plates:
            query = Session.query(ProductValidationPlate)\
                           .join(ProductValidationSpec)\
                           .join(ProductPart)\
                           .join(ProductValidationPlate.plate)\
                           .options(contains_eager(ProductValidationPlate.plate))
        else:
            query = Session.query(ProductValidationPlate)\
                           .join(ProductValidationSpec)\
                           .join(ProductPart)\
                           .join(ProductValidationPlate.plate)

        query = query.filter(ProductValidationSpec.part_number_id==self.id)\
                     .order_by(Plate.run_time.desc())
        return query

class ProductLot(Base):
    __tablename__ = "product_lot"
    __table_args__ = {"mysql_engine": 'InnoDB', 'mysql_charset': 'utf8'}

    id = Column(Integer, Sequence('product_lot_seq_id', optional=True), primary_key=True)
    number = Column(String(64), nullable=False)
    product_part_id = Column(Integer, ForeignKey('product_part.id'), nullable=False)
    product_rev = Column(String(1), nullable=False, default='A')
    date_added = Column(DateTime, nullable=False, default=now)
    date_manufactured = Column(Date, nullable=True)
    notes = Column(UnicodeText, nullable=True)

    # tests = orm.relation('ProductPlateTest', backref='lot_number')
    # todo: test specs, secondary join

    #def recent_test_query(self, eagerload_plates=False):
    #    """
    #    Returns the most recent tests for this spec.
    #    """
    #    if eagerload_plates:
    #        query = Session.query(ProductPlateTest)\
    #                       .join(ProductPlateTest.plate)\
    #                       .options(contains_eager(ProductPlateTest.plate))
    #    else:
    #        query = Session.query(ProductPlateTest).join(Plate)
    #
    #    query = query.filter(ProductPlateTest.lot_id==self.id)\
    #                 .order_by(Plate.run_time.desc())
    #
    #    return query

class ProductValidationSpec(Base):
    __tablename__ = "product_validation_spec"
    __table_args__ = {"mysql_engine": 'InnoDB', 'mysql_charset': 'utf8'}

    id = Column(Integer, Sequence('product_validation_spec_seq_id', optional=True), primary_key=True)
    date = Column(DateTime, nullable=False, default=now)
    part_number_id = Column(Integer, ForeignKey('product_part.id'), nullable=False)
    test_template_id = Column(Integer, ForeignKey('validation_template_type.id'), nullable=False)
    name = Column(Unicode(255), nullable=True)
    notes = Column(UnicodeText, nullable=True)

    items = orm.relation('ProductValidationSpecItem', backref='spec')
    test_plates = orm.relation('ProductValidationPlate', backref='spec')
    test_template = orm.relation('ValidationTestTemplate')

    @property
    def next_spec(self):
        """
        Returns the next test iteration for this spec's part.
        """
        part_specs = sorted(self.part.specs, key=operator.attrgetter('id'))
        current_idx = -1
        for idx, spec in enumerate(part_specs):
            if spec.id == self.id:
                current_idx = idx
                break

        if current_idx == len(part_specs)-1:
            return None
        else:
            return part_specs[current_idx+1]

    @property
    def positive_items(self):
        return [item for item in self.items if item.well_type == ProductValidationSpecItem.POSITIVE_ITEM]

    @property
    def negative_items(self):
        return [item for item in self.items if item.well_type == ProductValidationSpecItem.NEGATIVE_ITEM]

    def recent_validation_plates(self, eagerload_plates=False):
        """
        Returns the most recent tests for this spec.
        """
        if eagerload_plates:
            query = Session.query(ProductValidationPlate)\
                           .join(ProductValidationPlate.plate)\
                           .options(contains_eager(ProductValidationPlate.plate))
        else:
            query = Session.query(ProductValidationPlate).join(Plate)

        query = query.filter(ProductValidationPlate.spec_id==self.id)\
                     .order_by(Plate.run_time.desc())

        return query

    def is_passed_by(self, well_metric):
        return all([item.is_passed_by(well_metric) for item in self.items])


class ProductValidationSpecItem(Base):
    __tablename__ = "product_validation_spec_item"
    __table_args__ = {"mysql_engine": 'InnoDB', 'mysql_charset': 'utf8'}

    EQUAL = 'eq'
    LESS_THAN = 'lt'
    GREATER_THAN = 'gt'
    BETWEEN = 'in'
    OUTSIDE = 'out'

    NEGATIVE_ITEM = -1
    # 0 is the default for non-nullable ints in MySQL; I don't want the
    # default to be a valid item type
    POSITIVE_ITEM = 1

    id = Column(Integer, Sequence('product_validation_spec_item_seq_id', optional=True), primary_key=True)
    spec_id = Column(Integer, ForeignKey('product_validation_spec.id'), nullable=False)
    metric = Column(String(255), nullable=False)
    operator = Column(String(10), nullable=False)
    value1 = Column(Float, nullable=False)
    value2 = Column(Float, nullable=True)
    channel_num = Column(Integer, nullable=True)

    # negative or positive control type
    well_type = Column(Integer, nullable=False)

    @property
    def channel_display(self):
        if self.channel_num == 0:
            return 'FAM'
        elif self.channel_num == 1:
            return 'VIC'
        else:
            return None

    @property
    def criteria_display(self):
        if self.operator == self.__class__.EQUAL:
            return "= %s" % self.value1
        elif self.operator == self.__class__.LESS_THAN:
            return "< %s" % self.value1
        elif self.operator == self.__class__.GREATER_THAN:
            return "> %s" % self.value1
        elif self.operator == self.__class__.BETWEEN:
            return "between (%s, %s)" % (self.value1, self.value2)
        elif self.operator == self.__class__.OUTSIDE:
            return "outside (%s, %s)" % (self.value1, self.value2)
        else:
            return "?"

    # TODO: move to a fields class and reuse?
    @classmethod
    def compare_operator_field(cls, selected=None):
        field = {'value': selected or '',
                 'options': [(cls.EQUAL, '='),
                             (cls.LESS_THAN, '<'),
                             (cls.GREATER_THAN, '>'),
                             (cls.BETWEEN, 'Between'),
                             (cls.OUTSIDE, 'Outside')]}
        return field


    @staticmethod
    def getter_for_metric(metric):
        entity, attr = metric.split('.')
        if entity == 'well':
            return get_well_metric_col_accessor(attr)
        elif entity == 'channel':
            return get_well_channel_metric_col_accessor(attr)

    def record_val(self, well_metric):
        if self.channel_num is not None:
            entity = well_metric.well_channel_metrics[self.channel_num]
        else:
            entity = well_metric

        val = self.__class__.getter_for_metric(self.metric)(entity)
        return val

    def value_passes(self, val):
        # TODO val percentage transformation here?
        if self.operator == self.__class__.EQUAL:
            return val == self.value1
        elif self.operator == self.__class__.LESS_THAN:
            return val < self.value1
        elif self.operator == self.__class__.GREATER_THAN:
            return val > self.value1
        elif self.operator == self.__class__.BETWEEN:
            return val >= self.value1 and val <= self.value2
        elif self.operator == self.__class__.OUTSIDE:
            return val < self.value1 or val > self.value2
        else:
            return False

    def is_passed_by(self, well_metric):
        val = self.record_val(well_metric)
        return self.value_passes(val)


class ProductValidationPlate(Base):
    __tablename__ = "product_validation_plate"
    __table_args__ = {"mysql_engine": 'InnoDB', 'mysql_charset': 'utf8'}

    id = Column(Integer, Sequence('product_validation_plate_seq_id', optional=True), primary_key=True)
    plate_id = Column(Integer, ForeignKey('plate.id'), nullable=False)
    spec_id = Column(Integer, ForeignKey('product_validation_spec.id'), nullable=False)
    notes = Column(UnicodeText, nullable=True)

    plate = orm.relation('Plate')
    lot_tests = orm.relation('ProductValidationPlateLotTest', backref='validation_plate')

    @property
    def control_lot_tests(self):
        return [test for test in self.lot_tests if test.test_type == ProductValidationPlateLotTest.TEST_TYPE_CONTROL]

    @property
    def test_lot_tests(self):
        return [test for test in self.lot_tests if test.test_type == ProductValidationPlateLotTest.TEST_TYPE_TEST]

    @property
    def positive_lot_tests(self):
        return [test for test in self.lot_tests if test.well_type == ProductValidationPlateLotTest.WELL_TYPE_POSITIVE]

    @property
    def negative_lot_tests(self):
        return [test for test in self.lot_tests if test.well_type == ProductValidationPlateLotTest.WELL_TYPE_NEGATIVE]


class ProductValidationPlateLotTest(Base):
    __tablename__ = "product_validation_plate_lot_test"
    __table_args__ = {"mysql_engine": 'InnoDB', 'mysql_charset': 'utf8'}

    WELL_TYPE_NEGATIVE = -1
    WELL_TYPE_POSITIVE = 1

    TEST_TYPE_CONTROL = 1
    TEST_TYPE_TEST = 2

    id = Column(Integer, Sequence('product_validation_plate_lot_test_seq_id', optional=True), primary_key=True)
    validation_plate_id = Column(Integer, ForeignKey('product_validation_plate.id'), nullable=False)
    lot_id = Column(Integer, ForeignKey('product_lot.id'), nullable=False)
    wells = Column(Text, nullable=True)
    well_type = Column(Integer, nullable=False)
    test_type = Column(Integer, nullable=False)

    lot = orm.relation('ProductLot')


class ValidationTestTemplate(Base):
    __tablename__ = "validation_template_type"
    __table_args__ = {"mysql_engine": 'InnoDB', 'mysql_charset': 'utf8'}

    id = Column(Integer, Sequence('validation_template_type_seq_id', optional=True), primary_key=True)
    name = Column(String(50), nullable=False)
    layout_json = Column(Text, nullable=False)

    @property
    def layout(self):
        return ValidationTestLayout.from_json(self.layout_json)

    @classmethod
    def all_display_options(cls):
        return Session.query(cls.id, cls.name).order_by(cls.name).all()