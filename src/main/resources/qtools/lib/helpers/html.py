"""
Helper methods for manipulating HTML, and dynamically changing
the class of certain content given under conditions.
"""
from qtools.lib.helpers.text import wrapped
from webhelpers.html import literal
from webhelpers.html.builder import HTML

__all__ = ['htmlwrapped','warn_if_not','advise_warn_if','recursive_class_tag']

def htmlwrapped(str, width, overhang=0):
    return wrapped(str, width, joiner='<br/>', overhang=overhang)

def warn_if_not(val, func):
    if not func(val):
        # TODO: class instead?
        return literal("<span style='color: red; font-weight: bold;'>"+val+"</span>")
    else:
        return val

def advise_warn_if(val, warn_func, error_func):
    """
    Like warn_if_not, but adds an orange advisory condition.
    """
    if error_func(val):
        return literal("<span style='color: red; font-weight: bold;'>"+val+"</span>")
    elif warn_func(val):
        return literal("<span style='color: orange; font-weight: bold;'>"+val+"</span>")
    else:
        return val

def recursive_class_tag(tags, content, **keywords):
    """
    Builds a tag hierarchy where the tags have the
    same attributes.  Order the tags from outer to
    inner.

    Returns a literal object.
    """
    shell = list(reversed(tags))
    shell.insert(0, content)
    return reduce(lambda inner, outer: HTML.tag(outer, c=inner, **keywords), shell)