## -*- coding: utf-8 -*-

from pyPdf import PdfFileReader
import re, operator
import urllib2
from cStringIO import StringIO
from BeautifulSoup import BeautifulSoup

# this required a lot of poking
NEB_PRICE_LINE_RE = re.compile(r'R\d+S/L([\w\.\-]+)([IV](\-+\d?)*\s*[\d\,]+)/([\d\,]*)\sunits\$([\d\,]*)/\$([\d\,]*)')
NEB_PRICE_LIST_URL = "http://www.neb.com/nebecomm/price_list.pdf"
NEB_BUFFER_LIST_URL = "http://www.neb.com/nebecomm/tech_reference/restriction_enzymes/buffer_activity_restriction_enzymes.asp"
NEB_BASE_URL = "http://www.neb.com/nebecomm/products/"

# this is probably covered by some locale function, but whatever
# actually, I'd rather not have reading a comma from a page side-effect the localization of
# the entire app
def int_comma(str):
    return int(str.replace(',',''))

def float_currency(str):
    return float(str.replace('$',''))

def read_neb_enzyme_price_list():
    # throws URLError, IOError
    price_list = urllib2.urlopen(NEB_PRICE_LIST_URL)
    file_buffer = StringIO(price_list.read())
    
    reader = PdfFileReader(file_buffer)
    enzymes = []
    for p in range(reader.getNumPages()):
        # fi/fl misread hacks-- little nasty in here-- poor PDF read
        for match in NEB_PRICE_LINE_RE.finditer(reader.getPage(p).extractText().replace(u'\u02dc','fi').replace(u'˚','fl')):
            # format of the groups will be: name prefix, lastletter(+supplement)+small_cost, supplement, large_cost, small_unit, large_unit
            name_prefix, transition, supplement, large_cost, small_unit, large_unit = match.groups()
            if supplement:
                carryover = transition.index(supplement)+len(supplement)
                name = "%s%s" % (name_prefix, transition[:carryover])
                small_cost = int_comma(transition[carryover:])
            else:
                name = "%s%s" % (name_prefix, transition[0])
                small_cost = int_comma(transition[1:])
            
            large_cost = int_comma(large_cost)
            small_unit = int_comma(small_unit)
            large_unit = int_comma(large_unit)
            
            enzymes.append((name, small_cost, large_cost, small_unit, large_unit))
    
    return sorted(enzymes, key=operator.itemgetter(0))

def read_neb_buffer_list():
    # throws URLError, IOError
    buffer_response = urllib2.urlopen(NEB_BUFFER_LIST_URL)
    buffer_html = buffer_response.read()
    
    tree = BeautifulSoup(buffer_html)
    buffer_table = tree.find('table', {'class': 'tableborder'})
    buffer_rows = buffer_table.findAll('tr')
    
    name_buffers = []
    for row in buffer_rows:
        links = row.findAll('a')
        if len(links) == 2 and '-HF&trade;' not in links[0].text and links[1].text != "top":
            name_buffers.append((links[0].text.replace('&#945;',''), links[1].text))
    
    return sorted(name_buffers, key=operator.itemgetter(0))


class NEBEnzymeSource(object):
    LIST_URI = "category1.asp"

    def __init__(self, base_url=NEB_BASE_URL):
        self.base_url = base_url

    def iter_restriction_enzymes(self, page_uri=LIST_URI, ignore_hf=True, ignore_mix=True):
        """
        :raises IOError:
        :raises URLError:
        :raises ValueError:
        """
        response = urllib2.urlopen("%s%s" % (self.base_url, page_uri))
        list_html = response.read()
        tree = BeautifulSoup(list_html)
        # hoo boy subject to much breakage
        anchor = tree.find('a', {'name': '2'})
        enzyme_table = anchor.findNextSibling('table')
        for link in enzyme_table.findAll('a', {'class': 'bodycopy'}):
            if ignore_hf and '-HF' in link.contents[0]:
                continue
            if ignore_mix and 'RE-Mix' in link.contents[0]:
                continue
            yield (link.contents[0], link['href'])

    def enzyme_details(self, enzyme, page_uri):
        """
        Yields a dict of information about the enzyme, including:

        * sequence (though overhang info cannot readily be extracted)
        * unit_cost_1 (lower)
        * unit_cost_2 (higher)
        * buffer
        * methylation sensitivity
        """
        response = urllib2.urlopen("%s%s" % (self.base_url, page_uri))
        enzyme_html = response.read()
        tree = BeautifulSoup(enzyme_html)
        sequence = tree.find('meta', {'name': 'sequence'})['content']
        vendor_serial = tree.find('meta', {'name': 'basecatalognumber'})['content'].split(',')[0]
        cost_serial_1, cost_serial_2 = self.__get_enzyme_prices(tree)
        enz_buffer = self.__get_enzyme_buffer(tree)
        methylation_sensitivity = ','.join(sorted(self.__get_methylation(tree)))

        return {'sequence': sequence,
                'unit_cost_1': cost_serial_1[0],
                'unit_cost_2': cost_serial_2[0],
                'unit_serial_1': cost_serial_1[1],
                'unit_serial_2': cost_serial_2[1],
                'vendor_serial': vendor_serial,
                'buffer': enz_buffer,
                'methylation_sensitivity': methylation_sensitivity}
        

    def __get_enzyme_prices(self, tree):
        """
        Iterate through the details response tree to get the list of enzyme prices.

        :param tree: BeautifulSoup representation of the enzyme page.
        """
        forms = tree.findAll('form', {'name': 'addProduct'})
        cost_serial_1 = (None, None)
        cost_serial_2 = (None, None)
        for form in forms:
            row = form.findNextSibling('tr')
            # hacky as shit
            cols = row.findAll('td', {'valign': 'middle'})
            serial_col = cols[0].contents[0]
            units_col = int_comma(cols[1].contents[0].split()[0])
            price_col = float_currency(cols[3].contents[0])
            if serial_col.endswith('S'):
                cost_serial_1 = (price_col/(units_col/100.0), serial_col)
            elif serial_col.endswith('L'):
                cost_serial_2 = (price_col/(units_col/100.0), serial_col)

        return cost_serial_1, cost_serial_2

    def __get_enzyme_buffer(self, tree):
        """
        Foolproof?
        """
        related = tree.find('a', {'class': 'relatedproductnav'})
        return related.contents[0]

    def __get_methylation(self, tree):
        """
        SUPER FRAGILE.
        """
        # this relies on all sorts of formatting problems
        # to get at the data, but I'll take it
        # such is the web scrapin name of the game
        sensitivity = []

        span = tree.find('span', colspan=2)
        if not span:
            return sensitivity
        meth_table = span.findNextSibling('table')
        for td in meth_table.findAll('td'):
            content = td.contents[0]
            if 'Blocked' in content:
                sensitivity.append(content.split('&nbsp;')[0])
        return sensitivity








