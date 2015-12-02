"""
Helper links to images stored in predetermined locations in QTools.
"""
from pylons import config, url
from datetime import date
from qtools.lib.helpers.date import *
from qtools.model import Session, QLBPlate
from qtools.lib.storage import QLBImageSource

def get_plate_image_url( qlbplate_id ):
    # still using qlbplate is bad but hard to unwind without complete rename of all folders...
    plate = Session.query(QLBPlate).get(qlbplate_id)
    local = plate.plate.box2.fileroot in config['qlb.local_fileroots']

    if local:
        image_url = config['qlb.image_url']
    else:
        image_url = config['qlb.%s_image_url' % plate.plate.box2.fileroot]

    image_source = QLBImageSource( image_url, isLocal = False )
    plate_image_url = image_source.get_path(  str( plate.id ) )

    return plate_image_url

def qlb_thumbnail(qlbplate_id, well_name, channel, size=60):
    plate_image_url = get_plate_image_url( qlbplate_id )
    
    return '<img src="%s/%s_%s.png" class="chan%s" alt="%s" title="%s" height="%s"/>' % (plate_image_url, well_name, channel, channel, well_name, well_name, size)

def qlb_batch_thumbnail(qlbplate_id, major_version, minor_version, well_name, channel, size=60):
    plate_image_url = get_plate_image_url( qlbplate_id )
    
    return '<img src="%s/%s_%s/%s_%s.png" class="chan%s" alt="%s" title="%s" height="%s"/>' % (plate_image_url, major_version, minor_version, well_name, channel, channel, well_name, well_name, size)

def qlb_thumbnail_2d(qlbplate_id, well_name, size=60):
    plate_image_url = get_plate_image_url( qlbplate_id )

    return '<img src="%s/%s_2d.png" class="chan01" alt="%s" title="%s" height="%s"/>' % (plate_image_url, well_name, well_name, well_name, size)

def plot_thumbnail(type, date):
    return '<img src="%s/%s/%st.png" />' % (config['qlb.plot_url'], type, date.strftime('%Y%m%d'))

def beta_thumbnail(type):
    return '<img src="%s/%s/betat.png" />' % (config['qlb.plot_url'], type)

def plot_image(type, date):
    return '<img src="%s/%s/%s.png" />' % (config['qlb.plot_url'], type, date.strftime('%Y%m%d'))

def beta_image(type):
    return '<img src="%s/%s/beta.png" />' % (config['qlb.plot_url'], type)

def plot_galaxy_link(type, date, title='Galaxy'):
    return '<a href="%s/%s/%sg.png">%s</a>' % (config['qlb.plot_url'], type, date.strftime('%Y%m%d'), title)

def plot_box_weeks_ago_thumbnail(type, box_code, weeks_ago):
    return '<img src="%s/%s/%s-%st.png" />' % (config['qlb.plot_url'], type, box_code, weeks_ago_ymd(weeks_ago))

def plot_box_weeks_ago(type, box_code, weeks_ago):
    return '<img src="%s/%s/%s-%s.png" />' % (config['qlb.plot_url'], type, box_code, weeks_ago_ymd(weeks_ago))

def plot_beta_box_thumbnail(type, box_code):
    return '<img src="%s/%s/%s-betat.png" />' % (config['qlb.plot_url'], type, box_code)

def plot_beta_box(type, box_code):
    return '<img src="%s/%s/%s-beta.png" />' % (config['qlb.plot_url'], type, box_code)

def plot_box_galaxy_link(type, box_code, weeks_ago, title='Galaxy'):
    return '<a href="%s/%s/%s-%sg.png">%s</a>' % (config['qlb.plot_url'], type, box_code, weeks_ago_ymd(weeks_ago), title)

def plot_channel_weeks_ago_thumbnail(type, channel, weeks_ago):
    return '<img src="%s/%s/%s-c%st.png" />' % (config['qlb.plot_url'], type, weeks_ago_ymd(weeks_ago), channel)

def plot_channel_weeks_ago(type, channel, weeks_ago):
    return '<img src="%s/%s/%s-c%s.png" />' % (config['qlb.plot_url'], type, weeks_ago_ymd(weeks_ago), channel)

def plot_beta_channel(type, channel):
    return '<img src="%s/%s/%s-cbeta.png" />' % (config['qlb.plot_url'], type, channel)
