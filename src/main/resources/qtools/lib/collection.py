"""
Collection (array, set, etc.) helper methods and classes.
"""
from collections import defaultdict

class AttrDict(dict):
    """
    From http://code.activestate.com/recipes/576972-attrdict

    Uses __dict__ to subvert all __getattribute__ methods
    """
    def __init__(self, *args, **kwargs):
        dict.__init__(self, *args, **kwargs)
        self.__dict__ = self

class ImmutableAttrDict(AttrDict):
    """
    An AttrDict which will noop subsequent sets
    and dels after initialization.  Initialization
    can be done either by supplying a dicts as
    arguments or by using kwargs.
    """
    def __init__(self, *args, **kwargs):
        for arg in args:
            if isinstance(arg, dict):
                for k, v in arg.items():
                    super(ImmutableAttrDict, self).__setattr__(k, v)
        for k, v in kwargs.items():
            super(ImmutableAttrDict, self).__setattr__(k, v)

    def __getitem__(self, key):
        return super(ImmutableAttrDict, self).__dict__[key]

    def __setitem__(self, key, value):
        pass

    def __contains__(self, key):
        # TODO figure out why this doesn't work (is this even the right method)
        return key in super(ImmutableAttrDict, self).__dict__

    def __repr__(self):
        return repr(super(ImmutableAttrDict, self).__dict__)

    def __str__(self):
        return str(super(ImmutableAttrDict, self).__dict__)

    # make immutable; set all on construct
    def __setattr__(self, key, value):
        pass

    def __delattr__(self, key):
        pass

def groupinto(seq, func):
	# not like itertools.groupby, which will return segments at a time.
    groups = defaultdict(list)
    for el in seq:
        groups[func(el)].append(el)
    return groups.items()

def condition_split(seq, condition):
	# split the sequence into a group where the condition is true,
	# and where the condition is False.

	# go with list comprehension approach
	trues = [s for s in seq if condition(s)]
	falses = [s for s in seq if not condition(s)]
	return trues, falses