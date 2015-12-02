"""
Form input validators.
"""
import formencode, cgi, bleach
import re, simplejson

from simplejson.decoder import JSONDecodeError

from datetime import datetime

from qtools.lib.qlb_factory import ExperimentMetadataObjectFactory
from qtools.lib.upload import upload_basename

from qtools.model import Enzyme
from qtools.model.meta import Session

class JSONValidator(formencode.validators.FancyValidator):
    """
    For now, just validate the input as valid JSON.
    """
    messages = {'notjson': 'Invalid JSON format'}

    def _to_python(self, value, state):
        if value is None:
            return None
        try:
            return simplejson.loads(value)
        except JSONDecodeError:
            return formencode.Invalid(self.message('notjson', state),
                value, state)

    def _from_python(self, value, state):
        if value is None:
            return None

        return simplejson.dumps(value)


class KeyValidator(formencode.validators.FancyValidator):
    messages = {'notindb': 'Unknown value'}

    def __init__(self, dataobj, col, *args, **kwargs):
        super(KeyValidator, self).__init__(*args, **kwargs)
        self.dataobj = dataobj
        self.col = col

    def validate_python(self, value, state):
        available = Session.query(self.dataobj).filter(getattr(self.dataobj, self.col) == value).all()
        if not len(available) > 0:
            raise formencode.Invalid(self.message('notindb', state),
                value, state)

class IntKeyValidator(KeyValidator):
    messages = {'integer': 'Please enter an integer value'}

    def _to_python(self, value, state):
        try:
            return int(value)
        except (ValueError, TypeError):
            raise formencode.Invalid(self.message('integer', state),
                value, state)

class UniqueKeyValidator(formencode.validators.FancyValidator):
    messages = {'keyexists': 'A record with this value already exists'}

    def __init__(self, dataobj, col, *args, **kwargs):
        super(UniqueKeyValidator, self).__init__(*args, **kwargs)
        self.dataobj = dataobj
        self.col = col

    def validate_python(self, value, state):
        if Session.query(self.dataobj).filter(getattr(self.dataobj, self.col) == value).first():
            raise formencode.Invalid(self.message('keyexists', state),
                value, state)

class PlateUploadConverter(formencode.validators.FieldStorageUploadConverter):
    def _to_python(self, value, state=None):
        if isinstance(value, cgi.FieldStorage):
            factory = ExperimentMetadataObjectFactory()
            try:
                plate = factory.parse_plate(None, infile=value.file)
                return plate
            except Exception, e:
                raise formencode.Invalid("Could not read file", value, state)
        else:
            raise formencode.Invalid("Need a file upload", value, state)

class FileUploadFilter(formencode.validators.FieldStorageUploadConverter):
    def _to_python(self, value, state=None):
        if isinstance(value, cgi.FieldStorage):
            filename = upload_basename(value.filename)
            if len(filename) > 200:
                raise formencode.Invalid("Filename longer than 200 chars", value, state)
            return value
        else:
            raise formencode.Invalid("Need a file upload", value, state)


class NullableStringBool(formencode.validators.StringBool):
    def _to_python(self, value, state):
        if len(value) == 0 or value is None:
            return None
        else:
            return super(NullableStringBool, self)._to_python(value, state)

    def _from_python(self, value, state):
        if value is None:
            return None
        else:
            return super(NullableStringBool, self)._from_python(value, state)


class SanitizedString(formencode.validators.String):
    def __init__(self, *args, **kwargs):
        self.allowed_tags = kwargs.pop('allowed_tags', [])
        super(SanitizedString, self).__init__(*args, **kwargs)

    def _to_python(self, value, state):
        str_repr = super(SanitizedString, self)._to_python(value, state)
        return bleach.clean(str_repr, tags=self.allowed_tags, strip=True)

class SaveNewIdFields(formencode.validators.FancyValidator):
    """
    If a new value is entered into an id-name table, save the
    id ahead of time.
    """
    def __init__(self, *args):
        """
        Set up the new id fields.
        """
        self.spec = dict()
        for (name, obj, id_col, disp_col, additional_cols) in args:
            self.spec[name] = (obj, id_col, disp_col, additional_cols)

    def _to_python(self, value, state):
        # value is gonna be a dict
        for name, spec in self.spec.items():
            obj, id_col, disp_col, additional_cols = spec
            dict_val = value.get(name)
            if not dict_val:
                continue
            if dict_val and dict_val.isdigit():
                if Session.query(obj).filter(getattr(obj, id_col) == int(dict_val)).one():
                    continue
            additional_cols[disp_col] = dict_val
            newobj = obj(**additional_cols)
            Session.add(newobj)
            Session.commit()
            value[name] = getattr(newobj, id_col)
        return value

class UserNameSegment(formencode.validators.FancyValidator):
    USER_SEGMENT_NAME_MATCH = re.compile(r'^[\w\+\.\-\%\&]+$')

    messages = {'invalid_name': 'The user first/last name contains numbers and/or metacharacters.'}

    def validate_python(self, value, state):
        if not self.USER_SEGMENT_NAME_MATCH.match(value):
            raise formencode.Invalid(self.message('invalid_name', state),
                                     value, state)

class PlateNameSegment(formencode.validators.FancyValidator):
    PLATE_SEGMENT_NAME_MATCH = re.compile(r'^[\w\+\.\-\%\&]+$')
    
    messages = {'invalid_seq': 'The experiment name contains an illegal character.'}
    
    def _to_python(self, value, state):
        return value.strip().replace(' ','_')
    
    def validate_python(self, value, state):
        if not self.PLATE_SEGMENT_NAME_MATCH.match(value):
            raise formencode.Invalid(self.message('invalid_seq', state),
                                     value, state)

class NonCircularFolderPath(formencode.validators.String):
    messages = {'circular': 'No backward paths allowed.'}

    def validate_python(self, value, state):
        if '/../' in value or value.startswith('../') or value.endswith('/..'):
            raise formencode.Invalid(self.message('circular', state),
                                     value, state)

class VersionString(formencode.validators.FancyValidator):
    messages = {'not_enough_parts': "There aren't enough major/minor numbers in the version string.",
                'non_integer': 'Some of the versions are not integers.'}

    def __init__(self, *args, **kwargs):
        min_parts = kwargs.pop('min_parts', 0)
        super(VersionString, self).__init__(*args, **kwargs)
        self.min_parts = min_parts

    def _to_python(self, value, state):
        vals = value.strip().split('.')
        for v in vals:
            if not v.isdigit():
                raise formencode.Invalid(self.message('non_integer', state),
                                                      value, state)
        return [int(v) for v in vals]

    def _from_python(self, value, state):
        return '.'.join(value)

    def validate_python(self, value, state):
        if not len(value) >= self.min_parts:
            raise formencode.Invalid(self.message('not_enough_parts', state),
                                     value, state)

    

class OneOfInt(formencode.validators.OneOf):
    messages = {'integer': 'Please enter an integer value'}
    
    def _to_python(self, value, state):
        try:
            return int(value)
        except (ValueError, TypeError):
            raise formencode.Invalid(self.message('integer', state),
                                     value, state)
    


class RestrictionEnzyme(formencode.validators.FancyValidator):
    messages = {'invalid_enzyme': 'No enzyme with that name exists'}
    
    def validate_python(self, value, state):
        
        if not Session.query(Enzyme).filter_by(name=value).one():
            raise formencode.Invalid(self.message('invalid_enzyme', state),
                                     value, state)


class DNASequence(formencode.validators.FancyValidator):
    """
    Validates that an input sequence is made up of
    A, T, C and G characters.
    """
    DNA_SEQUENCE_MATCH = re.compile(r'^[ATCG]+$')
    
    messages = {'invalid_seq': 'The sequence must be made up of A, T, C and G characters.'}
    
    def _to_python(self, value, state):
        return value.strip().upper()
    
    def validate_python(self, value, state):
        if not self.DNA_SEQUENCE_MATCH.match(value):
            raise formencode.Invalid(self.message('invalid_seq', state),
                                     value, state)


class PrimerSequence(DNASequence):
    
    messages = {'invalid_seq': 'The sequence must be made up of A, T, C and G characters.',
                'primer_too_short': 'The primer length must be %(min)s characters or greater.'}
    
    def __init__(self, *args, **kwargs):
        super(PrimerSequence, self).__init__(*args, **kwargs)
        self.min_length = kwargs.get('min_length', 15)
    
    def validate_python(self, value, state):
        super(PrimerSequence, self).validate_python(value, state)
        if value is not None and len(value) < self.min_length:
            raise formencode.Invalid(self.message('primer_too_short', state, min=self.min_length),
                                     value, state)


class Chromosome(formencode.validators.FancyValidator):
    """
    Validates that an input is a valid chromosome.
    """
    # TODO: how to handle weird ones in UCSC database?
    messages = {'invalid_chr': 'Please enter chromosomes 1-22 or X or Y or M'}
    chrom_list = tuple([u'%s' % chr for chr in range(1,23)]) + ('X', 'Y', 'M')
    
    def _to_python(self, value, state):
        return value.strip().upper()
    
    def validate_python(self, value, state):
        if value is not None and not value in self.__class__.chrom_list:
            raise formencode.Invalid(self.message('invalid_chr', state),
                                     value, state)

class CapitalLetter(formencode.validators.String):
    """
    Validates the field is a single capital letter.
    """
    messages = {'not_capital': 'Character must be a capital letter.'}

    def __init__(self, *args, **kwargs):
        # allow for empty string
        kwargs['max'] = 1
        super(CapitalLetter, self).__init__(*args, **kwargs)

    def validate_python(self, value, state):
        if(value):
            if not value.isupper():
                raise formencode.Invalid(self.message('not_capital', state),
                                         value, state)


class SNPName(formencode.validators.FancyValidator):
    """
    Validates that an input is a valid SNP name.
    """
    messages = {'bad_format': 'The SNP must start with rs (or...)'}
    
    def _to_python(self, value, state):
        return value.strip().lower()
    
    def validate_python(self, value, state):
        if value is not None and not value.startswith('rs'):
            raise formencode.Invalid(self.message('bad_format', state),
                                     value, state)

class Strand(formencode.validators.FancyValidator):
    """
    Validates that a string is either '+' or '-'
    """
    messages = {'invalid': 'The strand must be + or -'}
    
    def validate_python(self, value, state):
        if value is not None and value not in ('+', '-'):
            raise formencode.Invalid(self.message('invalid', state),
                                     value, state)

class FormattedDateConverter(formencode.validators.DateConverter):
    """
    did jimmyg never hear of strptime or am I missing something?
    """
    def __init__(self, *args, **kwargs):
        self.format = kwargs.pop('date_format', '%Y/%m/%d')
        super(FormattedDateConverter, self).__init__(*args, **kwargs)
    
    def _to_python(self, value, state):
        try:
            the_date = datetime.strptime(value, self.format).date()
            return the_date
        except ValueError, e:
            raise formencode.Invalid(self.message('invalidDate', state, exception=str(e)), value, state)
    
    def _from_python(self, value, state):
        return value.strftime(self.format)

class MetricPattern(formencode.validators.FancyValidator):
    def _to_python(self, value, state):
        if value is None or '.' not in value:
            raise formencode.Invalid('Pattern must of form object.attr', value, state)
        else:
            return value.split('.')[0:2]

    def _from_python(self, value, state):
        return '.'.join(value)

def validate_colorcomp_plate(plate):
    messages = {'structure': 'There are not four completed wells in this plate.',
                'names': 'The color comp wells need to be labeled FAM HI, FAM LO, VIC HI and VIC LO.',
                'empties': 'One of the wells was aborted or had zero events.'}

    if len(plate.analyzed_wells) < 4:
        return (False, messages['structure'])
    
    analyzed_wells = plate.analyzed_wells.values()
    fam_hi = [w for w in analyzed_wells if w.sample_name in ('FAM HI', 'FAM 350nM')]
    fam_lo = [w for w in analyzed_wells if w.sample_name in ('FAM LO', 'FAM 40nM')]
    vic_hi = [w for w in analyzed_wells if w.sample_name in ('VIC HI', 'VIC 350nM')]
    vic_lo = [w for w in analyzed_wells if w.sample_name in ('VIC LO', 'VIC 70nM')]
    if len(fam_hi) == 0 or len(fam_lo) == 0 or len(vic_hi) == 0 or len(vic_lo) == 0:
        return (False, messages['names'])
        
    if len(fam_hi[0].peaks) == 0 or len(fam_lo[0].peaks) == 0 or len(vic_hi[0].peaks) == 0 or len(vic_lo[0].peaks) == 0:
        return (False, messages['empties'])
    
    return (True, 'OK')
    
