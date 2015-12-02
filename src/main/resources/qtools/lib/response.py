"""
Methods for manipulating the Pylons response object.
"""
from BeautifulSoup import BeautifulSoup as bs
import re, csv, StringIO

# possible CSS classnames for data tables in QTools.
DATA_TABLE_CLASSES = {"datagrid", "condensed-table", "table-condensed", "zebra-striped", "table-striped",'notable_data'}

def tables_to_csv(html):
    """
    Parse the HTML on the page, find data tables (as defined by
    the classes in DATA_TABLE_CLASSES), and then generate a
    CSV file from the contents of those tables.

    Having interesting table layouts, with variable rowspans
    and colspans, is bound to muck with this.  So this works
    best if you have a simple MxN table.

    :param html: HTML.
    :return: A string of CSV-formatted data.
    """
    tree = bs(html, convertEntities="html")
    # TODO: const
    tables = tree.findAll('table')

    out = StringIO.StringIO()

    writer = csv.writer(out)
    for table in tables:
        attrs = dict(table.attrs)
        classes = set(attrs.get('class', '').split())
        if not classes.intersection(DATA_TABLE_CLASSES):
            continue
        elif ( 'notable_data' in classes ):
            return "Got something!"
        else:
            pass

        # TODO: be smarter about rowspans, colspans (need some sort of state?)
        for tr in table.findAll('tr'):
            writer.writerow([col.text for col in tr.findAll(['td','th'])])

        writer.writerow([])

    content = out.getvalue()
    out.close()
    return content
