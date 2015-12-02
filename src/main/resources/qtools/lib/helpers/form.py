"""
TODO: deprecate, and use Bootstrap.  There is still
a fair amount of pages that rely on the old-style
FormBuild forms and fields, but FormBuild is busted
and ugly.
"""
from formbuild import Form
from webhelpers.html import literal

__all__ = ['LiteralForm','SelectPatch','LiteralFormSelectPatch']

# FormBuild 3 -- http://jimmyg.org/work/code/formbuild/3.0.1/manual.html
# LF from 3.0.2 distribution
class LiteralForm(Form):
    def __getattribute__(self, name):
        if name in [
            'value',
            'option',
            'error',
            'checked',
            'table_class',
        ]:
            return Form.__getattribute__(self, name)
        def make_literal(*k, **p):
            return literal(getattr(Form, name)(self, *k, **p))
        return make_literal

# fixes single value dropdown bug in FormBuild-- otherwise, any option
# whose value is a substring of the selected field value will be
# selected in html.
class SelectPatch(Form):
    def dropdown(self, name, attributes=None, get_option_attributes=None):
        """
        Monkey patch for FormBuild 3.0.3 bug 
        """
        value = self.value.get(name, [])
        if isinstance(value, basestring):
            value = [value]
        return SelectPatch.select(value, self.option.get(name, []), False, name, attributes, get_option_attributes, self)
    
    @staticmethod
    def select(value,
        options,
        multiple,
        name,
        attributes=None,
        get_option_attributes=None,
        self=None,
    ):
        """
        This is the same as formbuild.internal._select, with two changes.
        """
        from bn import HTMLFragment
        from formbuild.internal import _select, check_attributes, html_open

        attributes = check_attributes(attributes, ['name', 'multiple'])
        if multiple:
            attributes['multiple'] = 'multiple'
        attributes['name'] = name

        # change number 1
        values = [unicode(val) for val in value]
        
        fragment = HTMLFragment()
        fragment.safe(html_open(u'select', False, attributes)+'\n')
        counter = 0
        for v, k in options:
            if get_option_attributes:
                option_attr = get_option_attributes(self, v, k)
            else:
                option_attr = {}
            option_attr = check_attributes(option_attr, ['value', 'selected'])
            
            # change number 2
            if unicode(v) in values:
                option_attr['selected'] = 'selected'
            option_attr['value'] = v
            fragment.safe(html_open(u'option', False, option_attr))
            fragment.write(k)
            fragment.safe('</option>\n')
        fragment.safe(u'</select>')
        return fragment.getvalue()
    

# FormBuild 3.0.3 monkey patch for correct selection
class LiteralFormSelectPatch(LiteralForm, SelectPatch):
    def __getattribute__(self, name):
        if name == "dropdown":
            return SelectPatch.__getattribute__(self, "dropdown")
        else:
            return LiteralForm.__getattribute__(self, name)