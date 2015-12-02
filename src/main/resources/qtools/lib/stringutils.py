"""
String manipulation functions.
"""
import re
ALPHA_ONLY_RE = re.compile('[\W_]+')

def initial(text):
    """
    Create initials out of the specified words.

    input: Jeff Mellen
    output: JM
    """
    return ''.join([tok[0].upper() for tok in text.split(' ')])

def militarize(text, bit_length=3):
    """
    Converts the phrase into a military short abbreviation,
    like 'Central Command' -> 'CenCom' (I know, it's CentCom,
    but the bit_length is fixed)
    """
    return ''.join([tok[:bit_length].capitalize() if not tok[:bit_length].isupper() else tok[:bit_length] for tok in text.split(' ')])

def camelize(text):
    """
    join whitespace and then do only alphanumeric characters.
    """
    train = ''.join([tok.capitalize() if not tok.isupper() else tok for tok in text.split(' ')])
    return ALPHA_ONLY_RE.sub('', train)