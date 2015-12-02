import logging

from pylons import request, response, session, tmpl_context as c, url, config
from pylons.controllers.util import abort, redirect
from pylons.decorators import validate
from pylons.decorators.rest import restrict

from qtools.lib.base import BaseController, render
from qtools.model import Session, MapCache

import formencode, json
from formencode.variabledecode import NestedVariables

from collections import defaultdict

log = logging.getLogger(__name__)

class AddressForm(formencode.Schema):
    allow_extra_fields = True
    filter_extra_fields = True

    row = formencode.validators.Int(not_empty=True)
    address = formencode.validators.String(not_empty=True)

class MapEntryForm(formencode.Schema):
    allow_extra_fields = True
    filter_extra_fields = True

    validated = formencode.validators.StringBool(not_empty=True)
    address = formencode.validators.String(not_empty=True)
    lat = formencode.validators.Number(not_empty=False, if_missing=None)
    lon = formencode.validators.Number(not_empty=False, if_missing=None)

class MapCacheForm(formencode.Schema):
    allow_extra_fields = True
    filter_extra_fields = True

    pre_validators = [NestedVariables()]
    addresses = formencode.ForEach(AddressForm(), not_empty=False)

class MapAddCacheForm(formencode.Schema):
    allow_extra_fields = True
    filter_extra_fields = True

    pre_validators = [NestedVariables()]
    addresses = formencode.ForEach(MapEntryForm(), not_empty=False)

class MapController(BaseController):

    def index(self):
        return render('/map/index.html')

    def iframe(self):
        c.origin = config['qtools.map.origin']
        return render('/map/iframe.html')

    def noop(self):
        return render('/map/noop.html')

    @restrict('POST')
    @validate(schema=MapCacheForm(), form='noop')
    def gmap(self):
        addresses = self.form_result['addresses']
        address_row_map = defaultdict(list)

        for a in addresses:
            address_row_map[a['address']].append(a['row'])

        if addresses:
            known_address_tuples = Session.query(MapCache.address, MapCache)\
                                     .filter(MapCache.address.in_([a['address'] for a in addresses])).all()
        
        known_address_json = []
        for a, k in known_address_tuples:
            if not k.verified:
                continue
            rows = address_row_map[a]
            for r in rows:
                known_address_json.append([r, a, k.lat, k.lon])

        c.known_address_json = json.dumps(known_address_json)
        unknown_address_json = []
        known_addresses = [a for a, k in known_address_tuples]
        for a in addresses:
            if a['address'] not in known_addresses:
                unknown_address_json.append((a['row'], a['address']))

        c.unknown_address_json = json.dumps(sorted(unknown_address_json))
        # todo make config
        c.api_key = 'AIzaSyCJmLePQj0ZLMbxVvJorxcL65AKUp8OH9w'
        c.origin = config['qtools.map.origin']

        return render('/map/gmap.html')

    @restrict('POST')
    @validate(schema=MapAddCacheForm(), form='noop')
    def cache(self):
        addresses = self.form_result['addresses']
        for a in addresses:
            if a['validated']:
                cache = MapCache(verified = a['validated'],
                                 address = a['address'],
                                 lat = a['lat'],
                                 lon = a['lon'])
            else:
                cache = MapCache(verified = False,
                                 address = a['address'])
            try:
                Session.add(cache)
                Session.commit()
            except Exception, e:
                # in case multiple same addresses per update
                # just fail
                continue
        response.content_type = 'text/plain'
        return 'OK'

    def loader(self):
        response.content_type = 'text/javascript'
        c.protocol = config['qtools.map.protocol']
        c.origin = config['qtools.map.origin']
        c.server_root = config['qtools.map.server_root']
        return render('/map/loader.js');



