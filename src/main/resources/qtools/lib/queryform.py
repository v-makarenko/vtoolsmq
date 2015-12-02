"""
Old query form components.  This can probably be deleted, mostly.
"""
import re
import formencode
from formencode.variabledecode import NestedVariables

MYSQL_SPEC_RE = re.compile(r'[\(\)]')


class CompareValidator(formencode.validators.OneOf):
    comparators = (('=', '__eq__'),
                   ('>=', '__ge__'),
                   ('>',  '__gt__'),
                   ('<',  '__lt__'),
                   ('<=', '__le__'),
                   ('!=', '__ne__'))
    
    def __init__(self):
        super(CompareValidator, self).__init__([tup[1] for tup in self.comparators], if_missing='__eq__')
    
    def _to_python(self, value, state):
        return dict(self.__class__.comparators).get(value, None)


class SortByValidator(formencode.validators.OneOf):
    directions = (('asc', 'Ascending'),
                  ('desc', 'Descending'))
                  
    def __init__(self, *args, **kwargs):
        super(SortByValidator, self).__init__([tup[0] for tup in self.directions], if_missing='asc')



class QueryForm(formencode.Schema):
    allow_extra_fields = True
    filter_extra_fields = True
    allow_empty_fields = False
    
    pre_validators = [NestedVariables()]
    include_id_fields = False
    
    entity = None
    join_entities = []
    
    col_display_names = {}
    exclude_fields = []
    
    order_by_direction = SortByValidator()
    

    def __init__(self, *args, **kwargs):
        """
        table can be a table or relation.
        """
        self.fields['conditions'] = formencode.foreach.ForEach(Condition(self.entity, self.join_entities, not_empty=not(self.allow_empty_fields)))
        self.fields['order_by'] = ColumnValidator(self.entity, self.join_entities, not_empty=True)
        self.fields['return_fields'] = formencode.foreach.ForEach(ColumnValidator(self.entity, self.join_entities))
        self.field_tuples = []
        
        if not self.join_entities:
            columns = self.entity.__mapper__.columns
            if not self.include_id_fields:
                columns = [(col.name, col.name) for col in columns if not (col.name.endswith('_id') or col.name == 'id')]
            else:
                columns = [(col.name, col.name) for col in columns]
        
        else:
            columns = []
            for e in [self.entity] + list(self.join_entities):
                cols = e.__mapper__.columns
                table = e.__table__.name
                if not self.include_id_fields:
                    columns.extend([("%s.%s" % (table, col.name), col.name) for col in cols \
                                    if not (col.name.endswith('_id') or col.name == 'id')])
                else:
                    columns.extend([("%s.%s" % (table, col.name), col.name) for col in cols])
            
        self.field_tuples = sorted([(col[0], self.col_display_names.get(col[0], col[1])) for col in columns if col[0] not in self.exclude_fields], key=lambda k: k[1].lower())
        super(QueryForm, self).__init__(*args, **kwargs)
    

class ColumnValidator(formencode.validators.OneOf):
    def __init__(self, entity, join_entities=None, **kwargs):
        if not join_entities:
            self.columns = dict([(col.name, col) for col in entity.__mapper__.columns])
        else:
            self.columns = {}
            for e in [entity] + list(join_entities):
                cols = e.__mapper__.columns
                table = e.__table__.name
                self.columns.update(dict([("%s.%s" % (table, col.name), col) for col in cols]))
        
        super(ColumnValidator, self).__init__(self.columns.values(), **kwargs)
    
    def _to_python(self, value, state):
        return self.columns.get(value, None)
    

class Condition(formencode.Schema):
    allow_extra_fields = True
    filter_extra_fields = True
    
    compare = CompareValidator()
    
    def __init__(self, entity, join_entities=None, not_empty=True):
        self.fields['field'] = ColumnValidator(entity, join_entities)
        self.not_empty = not_empty
        super(Condition, self).__init__()
    
    def _to_python(self, field_dict, state):
        # delayed creation of self.fields['value'] based off of type
        col_name = field_dict.get('field', None)
        
        if col_name is None:
            return super(Condition, self)._to_python(field_dict, state)
        
        # TODO: this might be better served as a form validator, but you
        # need to establish the type of the second field up front to display
        # field-specific validation (in the @validate context)
        col_spec = self.fields['field']._to_python(field_dict['field'], state)
        
        col_params = MYSQL_SPEC_RE.split(str(col_spec.type))
        
        # this is MySQL specific-- if I ever release this to the general
        # public, make sure it obeys a more general case.  Then again,
        # this depends on SQLAlchemy, so that's unlikely.
        if col_params[0] == "VARCHAR":
            self.fields['value'] = formencode.validators.String(not_empty=self.not_empty, max=col_params[1], if_missing=None)
        elif col_params[0] == "INTEGER":
            self.fields['value'] = formencode.validators.Int(not_empty=self.not_empty, if_missing=None)
        elif col_params[0] in ('NUMERIC', 'FLOAT'):
            self.fields['value'] = formencode.validators.Number(not_empty=self.not_empty, if_missing=None)
        elif col_params[0] in ('DATE', 'DATETIME', 'TIMESTAMP', 'TIME'):
            self.fields['value'] = formencode.validators.DateConverter(not_empty=self.not_empty, if_missing=None)
        
        return super(Condition, self)._to_python(field_dict, state)

def full_column_name(col):
    return "%s.%s" % (col.table.name, col.name)

class NameDescriptionForm(formencode.Schema):
    allow_extra_fields = True
    filter_extra_fields = True

    name = formencode.validators.String(not_empty=True)
    description = formencode.validators.String(not_empty=False, if_missing=None)
