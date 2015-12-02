"""
Helper methods to manipulate text.
"""
from textwrap import wrap
from itertools import groupby
from unidecode import unidecode
import re

__all__ = ['yesno', 'wrapped', 'make_horiz_cells', 'make_vert_cells', 'ellipsis', 'alphabify']

NON_ALPHA_RE = re.compile(r'\W+')

def yesno(bool):
    return 'Yes' if bool else 'No'

def wrapped(str, width, joiner='\n', overhang=0):
    if str is None:
        str = ''
    pieces = wrap(str, width)
    if overhang and len(pieces) > 1:
        pieces[1:] = ["%s%s" % (' '*overhang, piece) for piece in pieces[1:]]
    return joiner.join(pieces)

def make_horiz_cells(group, num_cols):
    return groupby(enumerate(group), lambda tup: divmod(tup[0], num_cols)[0])

def make_vert_cells(group, num_cols):
    return groupby(enumerate(group), lambda tup: divmod(tup[0], num_cols)[1])

def ellipsis(string, length):
    if length > 3 and len(string) > length:
        return "%s..." % string[:length-3]
    else:
        return string

def alphabify(string, replace_char='_'):
    return re.sub(NON_ALPHA_RE, replace_char, unidecode(string))
