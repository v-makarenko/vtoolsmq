"""
Inspection methods for generic Python constructs.
"""
def class_properties(klass):
    """
    For a given class, return a tuple (name, property) of the
    properties of the class.  For example, given this class:

    class Foo(object):
        def __init__(self, val):
            self._val = val

        @property
        def val(self):
            return self._val

        def strval(self):
            return str(self._val)

    class_properties(Foo) will return [('val', <property with Foo.val as fget>)]

    This is used downstream to figure out which attributes in a
    model are derived as opposed to being columns.

    :param klass: The class to inspect.
    :return: See above.
    """
    return [(attr, getattr(klass, attr)) for attr in dir(klass) if isinstance(getattr(klass, attr), property)]