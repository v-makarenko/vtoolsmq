import logging, re, cgi, operator, StringIO

from pylons import request, response, session, tmpl_context as c, url
from pylons.controllers.util import abort, redirect
from pylons.decorators import validate
from pylons.decorators.rest import restrict

from qtools.lib.base import BaseController, render
from qtools.lib.fields import model_distinct_field, model_kv_field
from qtools.lib.queryform import NameDescriptionForm
import qtools.lib.helpers as h
from qtools.lib.validators import IntKeyValidator
from qtools.model import Session, ConsumableBatch, ConsumableMoldingStyle, ConsumableBondingStyle
from qtools.model import ConsumableBatchTest, ConsumableBatchSizeChannel, ConsumableBatchFillChannel

from sqlalchemy.orm import joinedload_all

import formencode
from formencode import Invalid
from formencode.variabledecode import NestedVariables

from datetime import datetime
from collections import defaultdict

log = logging.getLogger(__name__)

class NewBatchForm(formencode.Schema):
    allow_extra_fields = True
    filter_extra_fields = True

    manufacturer = formencode.validators.String(not_empty=True)
    insert = formencode.validators.String(not_empty=True)
    molding_style = IntKeyValidator(ConsumableMoldingStyle, 'id', not_empty=False, if_missing=None)
    bonding_style = IntKeyValidator(ConsumableBondingStyle, 'id', not_empty=False, if_missing=None)
    bside = formencode.validators.String(not_empty=False)
    lot_number = formencode.validators.String(not_empty=True)
    manufacture_date = formencode.validators.DateConverter(not_empty=True)

class UpdateBatchForm(formencode.Schema):
    allow_extra_fields = True
    filter_extra_fields = True

    manufacturer = formencode.validators.String(not_empty=True)
    insert = formencode.validators.String(not_empty=True)
    molding_style = IntKeyValidator(ConsumableMoldingStyle, 'id', not_empty=False, if_missing=None)
    bonding_style = IntKeyValidator(ConsumableBondingStyle, 'id', not_empty=False, if_missing=None)
    bside = formencode.validators.String(not_empty=False)
    manufacture_date = formencode.validators.DateConverter(not_empty=True)

class DropletChannelForm(formencode.Schema):
    allow_extra_fields = True
    filter_extra_fields = True

    channel_num = formencode.validators.Int(not_empty=True)
    mean = formencode.validators.Number(not_empty=False, if_missing=None)
    stdev = formencode.validators.Number(not_empty=False, if_missing=None)
    droplet_count = formencode.validators.Int(not_empty=False, if_missing=None)

class DropletChipForm(formencode.Schema):
    allow_extra_fields = True
    filter_extra_fields = True

    chip_num = formencode.validators.Int(not_empty=True)
    pre_validators = [NestedVariables()]
    channels = formencode.ForEach(DropletChannelForm(), not_empty=False)

class SizeTestForm(formencode.Schema):
    allow_extra_fields = True
    filter_extra_fields = True

    pre_validators = [NestedVariables()]
    chips = formencode.ForEach(DropletChipForm(), not_empty=False)
    pixel_calibration = formencode.validators.Number(not_empty=False, if_missing=None)

class DropletFillChannelForm(formencode.Schema):
    allow_extra_fields = True
    filter_extra_fields = True

    channel_num = formencode.validators.Int(not_empty=True)
    fill_time = formencode.validators.Number(not_empty=False, if_missing=None)

class DropletFillChipForm(formencode.Schema):
    allow_extra_fields = True
    filter_extra_fields = True

    chip_num = formencode.validators.Int(not_empty=True)
    pre_validators = [NestedVariables()]
    channels = formencode.ForEach(DropletFillChannelForm(), not_empty=False)

class FillTimeForm(formencode.Schema):
    allow_extra_fields = True
    filter_extra_fields = True

    pre_validators = [NestedVariables()]
    chips = formencode.ForEach(DropletFillChipForm(), not_empty=False)

FILENUM_RE = re.compile(r'_(\d+)\-')

class ConsumableUploadConverter(formencode.validators.FieldStorageUploadConverter):
    def _to_python(self, value, state=None):
        if isinstance(value, cgi.FieldStorage):
            batch_dict = {}
            # todo stricter upload rules
            if value.filename and FILENUM_RE.search(value.filename):
                file_num = int(FILENUM_RE.search(value.filename).group(1))
                batch_dict['file_num'] = file_num
                with value.file as f:
                    for line in f:
                        if line.startswith('Mean: '):
                            batch_dict['mean'] = float(line.split(' ')[-1])
                        elif line.startswith('Std: '):
                            batch_dict['stdev'] = float(line.split(' ')[-1])
                        elif line.startswith('Nb Droplets'):
                            batch_dict['droplet_count'] = float(line.split(' ')[-1])
                            break
                
                if 'mean' not in batch_dict.keys():
                    raise Invalid('Mean missing from %s' % value.filename, value, state)
                elif 'stdev' not in batch_dict.keys():
                    raise Invalid('Stdev missing from %s' % value.filename, value, state)
                elif 'droplet_count' not in batch_dict.keys():
                    raise Invalid('Droplet count missing from %s' % value.filename, value, state)
                
                return batch_dict
            else:
                raise Invalid('Invalid filename: %s' % value.filename, value, state)
        else:
            return value

class BatchSizeUploadForm(formencode.Schema):
    allow_extra_fields = True
    filter_extra_fields = True

    pre_validators = [NestedVariables()]
    sizes = formencode.ForEach(ConsumableUploadConverter(), not_empty=False)
    pixel_calibration = formencode.validators.Number(not_empty=True)



class ConsumableController(BaseController):

    def __batches(self):
        return Session.query(ConsumableBatch).order_by(ConsumableBatch.manufacturer,
                                                       ConsumableBatch.insert,
                                                       ConsumableBatch.manufacturing_date).all()
    
    def __batch(self, id=None):
        if id is None:
            return None
        
        return Session.query(ConsumableBatch).filter(ConsumableBatch.id == int(id))\
                                             .options(joinedload_all(ConsumableBatch.consumable_molding_style),
                                                      joinedload_all(ConsumableBatch.consumable_bonding_style)).first()
        
    # todo: separate test results per pixel calibration
    def __batch_test(self, id=None, pixel_calibration=None):
        if id is None:
            return None
        
        return Session.query(ConsumableBatchTest).filter(ConsumableBatchTest.consumable_batch_id == int(id))\
                                                 .options(joinedload_all(ConsumableBatchTest.size_channels)).first()

    
    def list(self):
        c.batches = self.__batches()
        return render('/product/consumable/list.html')
    
    def __batch_form(self, batch=None):
        manufacturers = model_distinct_field(ConsumableBatch.manufacturer,
                                             additional=('Weidmann','ThinXXS'),
                                             selected=batch.manufacturer if batch else '')
        insert = model_distinct_field(ConsumableBatch.insert,
                                      additional=('3',),
                                      selected=batch.insert if batch else '')
        molding_style = model_kv_field(ConsumableMoldingStyle.id, ConsumableMoldingStyle.name,
                                       selected=str(batch.consumable_molding_style_id) if batch else '')
        bonding_style = model_kv_field(ConsumableBondingStyle.id, ConsumableBondingStyle.name,
                                       selected=str(batch.consumable_bonding_style_id) if batch else '')
        bsides = model_distinct_field(ConsumableBatch.bside,
                                      selected=batch.bside if batch else '')
        return h.LiteralFormSelectPatch(
            value = {'manufacturer': manufacturers['value'],
                     'insert': insert['value'],
                     'molding_style': molding_style['value'],
                     'bonding_style': bonding_style['value'],
                     'bside': bsides['value'],
                     'manufacture_date': batch.manufacturing_date.strftime('%m/%d/%Y') if batch else ''},
            option = {'manufacturer': manufacturers['options'],
                      'insert': insert['options'],
                      'molding_style': molding_style['options'],
                      'bonding_style': bonding_style['options'],
                      'bside': bsides['options']}
        )

    
    def new(self):
        c.form = self.__batch_form()
        return render('/product/consumable/new.html')
    
    @restrict('POST')
    @validate(schema=NewBatchForm(), form='new')
    def create(self):
        batch = ConsumableBatch(manufacturer=self.form_result['manufacturer'],
                                insert=self.form_result['insert'],
                                consumable_molding_style_id=self.form_result['molding_style'],
                                consumable_bonding_style_id=self.form_result['bonding_style'],
                                bside=self.form_result['bside'],
                                lot_num=self.form_result['lot_number'],
                                manufacturing_date=self.form_result['manufacture_date'])
        Session.add(batch)
        Session.commit()
        session.flash = 'Created batch %s' % self.form_result['lot_number']
        session.save()
        return redirect(url(controller='consumable', action='details', id=batch.id))

    def edit(self, id=None):
        c.batch = self.__batch(id)
        c.form = self.__batch_form(batch=c.batch)
        return render('/product/consumable/edit.html')
    
    @restrict('POST')
    @validate(schema=UpdateBatchForm(), form='edit')
    def update(self, id=None):
        batch = self.__batch(id)
        batch.manufacturer = self.form_result['manufacturer']
        batch.insert = self.form_result['insert']
        batch.consumable_molding_style_id=self.form_result['molding_style']
        batch.consumable_bonding_style_id=self.form_result['bonding_style']
        batch.manufacturing_date=self.form_result['manufacture_date']
        batch.bside=self.form_result['bside']
        Session.commit()
        session.flash = 'Updated batch %s' % batch.lot_num
        return redirect(url(controller='consumable', action='details', id=batch.id))
    
    def details(self, id=None):
        c.batch = self.__batch(id)
        if not c.batch:
            abort(404)
        
        return render('/product/consumable/details.html')
    
    def size(self, id=None):
        # for now, just return the test
        c.batch_test = self.__batch_test(id)
        c.batch = self.__batch(id)
        if not c.batch:
            abort(404)

        c.test_exists = True
        if not c.batch_test:
            c.test_exists = False
            # if batch id exists, this is OK, the test has not yet been created
            c.batch_test = ConsumableBatchTest(consumable_batch_id = int(id))
        

        c.form = h.LiteralForm(
            value = {'pixel_calibration': c.batch_test.pixel_calibration}
        )

        c.chips = defaultdict(lambda: defaultdict(lambda: None))
        for chan in c.batch_test.size_channels:
            c.chips[chan.chip_num-1][chan.channel_num-1] = chan
        
        return render('/product/consumable/size.html')
    
    def size_csv(self, id=None):
        c.batch_test = self.__batch_test(id)
        c.batch = self.__batch(id)
        if not c.batch or not c.batch_test:
            abort(404)
        
        c.chips = defaultdict(lambda: defaultdict(lambda: None))
        for chan in c.batch_test.size_channels:
            c.chips[chan.chip_num-1][chan.channel_num-1] = chan
        
        # print in row order
        out = StringIO.StringIO()
        out.write('Chip,Channel1,Channel2,Channel3,Channel4,Channel5,Channel6,Channel7,Channel8\n')
        for i in range(5):
            out.write('%s,' % (i+1))
            out.write(','.join([str(c.chips[i][j].size_mean) if c.chips[i][j] else '' for j in range(8)]))
            out.write('\n,')
            out.write(','.join([str(c.chips[i][j].size_stdev) if c.chips[i][j] else '' for j in range(8)]))
            out.write('\n,')
            out.write(','.join([str(c.chips[i][j].droplet_count) if c.chips[i][j] else '' for j in range(8)]))
            out.write('\n')
        
        csv = out.getvalue()

        response.headers['Content-Type'] = 'text/csv'
        h.set_download_response_header(request, response, '%s.csv' % c.batch.lot_num)
        return csv


    
    @restrict('POST')
    @validate(schema=SizeTestForm(), form='size')
    def update_size(self, id=None):
        batch = self.__batch(id)
        if not batch:
            abort(404)
        
        batch_test = self.__batch_test(id)
        if not batch_test:
            batch_test = ConsumableBatchTest(consumable_batch_id = batch.id)
            Session.add(batch_test)
        
        batch_test.pixel_calibration = self.form_result['pixel_calibration']


        garbage = []
        # check for cleared entities first
        for chan in batch_test.size_channels:
            thechip = [chip for chip in self.form_result['chips'] if chip['chip_num'] == chan.chip_num]
            if not thechip:
                garbage.append(chan)
                continue
            
            thechan = [c for c in thechip[0]['channels'] if c['channel_num'] == chan.channel_num]
            if not thechan:
                garbage.append(chan)
                continue
            
            if thechan[0]['droplet_count'] is None and thechan[0]['mean'] is None and thechan[0]['stdev'] is None:
                garbage.append(chan)
        
        for g in garbage:
            batch_test.size_channels.remove(g)
            Session.delete(g)
        
        # This is the case for a GAE-like Entity or a Mongo object or storing
        # JSON in a text column or whatever
        for chip in self.form_result['chips']:
            for channel in chip['channels']:
                if channel['droplet_count'] is not None or channel['mean'] is not None or channel['stdev'] is not None:
                    dbchan = batch_test.size_channel(chip['chip_num'], channel['channel_num'])
                    if not dbchan:
                        dbchan = ConsumableBatchSizeChannel(chip_num=chip['chip_num'], channel_num=channel['channel_num'])
                        batch_test.size_channels.append(dbchan)
                
                    dbchan.size_mean = channel['mean']
                    dbchan.size_stdev = channel['stdev']
                    dbchan.droplet_count = channel['droplet_count']
        
        Session.commit()
        session['flash'] = 'Sizes updated.'
        session.save()

        return redirect(url(controller='consumable', action='size', id=batch.id))

    def batch_size(self, id=None):
        c.batch_test = self.__batch_test(id)
        c.batch = self.__batch(id)
        if not c.batch:
            abort(404)

        c.form = h.LiteralForm(
            value = {'pixel_calibration': 0.645}
        )
        
        return render('/product/consumable/batch_size.html')
    
    @restrict('POST')
    @validate(schema=BatchSizeUploadForm(), form='batch_size')
    def batch_size_upload(self, id=None):
        batch = self.__batch(id)
        if not batch:
            abort(404)
        
        batch_test = self.__batch_test(id)
        if not batch_test:
            batch_test = ConsumableBatchTest(consumable_batch_id = batch.id)
            Session.add(batch_test)
        
        batch_test.pixel_calibration = self.form_result['pixel_calibration']
        for i in range(len(batch_test.size_channels)):
            sc = batch_test.size_channels.pop()
            Session.delete(sc)
        
        # place files in order
        chip_num = 0
        pc = batch_test.pixel_calibration
        for idx, channel in enumerate(sorted(self.form_result['sizes'], key=operator.itemgetter('file_num'))):
            if idx % 8 == 0:
                chip_num = chip_num + 1
            
            dbchan = ConsumableBatchSizeChannel(chip_num=chip_num,
                                                channel_num=(idx%8)+1,
                                                size_mean=channel['mean']*pc,
                                                size_stdev=channel['stdev']*pc,
                                                droplet_count=channel['droplet_count'])
            batch_test.size_channels.append(dbchan)
        
        Session.commit()
        session['flash'] = 'Sizes updated.'
        session.save()

        return redirect(url(controller='consumable', action='size', id=batch.id))
    
    def fill(self, id=None):
        c.batch = self.__batch(id)
        if not c.batch:
            abort(404)
        
        c.form = h.LiteralForm()

        c.chips = defaultdict(lambda: defaultdict(lambda: None))
        for chan in c.batch.fill_channels:
            c.chips[chan.chip_num-1][chan.channel_num-1] = chan
        
        return render('/product/consumable/fill.html')
    
    @restrict('POST')
    @validate(schema=FillTimeForm(), form='fill')
    def update_fill(self, id=None):
        batch = self.__batch(id)
        if not batch:
            abort(404)
        
        garbage = []
        # check for cleared entities
        for chan in batch.fill_channels:
            thechip = [chip for chip in self.form_result['chips'] if chip['chip_num'] == chan.chip_num]
            if not thechip:
                garbage.append(chan)
                continue
            
            thechan = [c for c in thechip[0]['channels'] if c['channel_num'] == chan.channel_num]
            if not thechan:
                garbage.append(chan)
                continue
            
            if thechan[0]['fill_time'] is None:
                garbage.append(chan)
        
        for g in garbage:
            batch.fill_channels.remove(g)
            Session.delete(g)
        
        for chip in self.form_result['chips']:
            for channel in chip['channels']:
                if channel['fill_time'] is not None:
                    dbchan = batch.fill_channel(chip['chip_num'], channel['channel_num'])
                    if not dbchan:
                        dbchan = ConsumableBatchFillChannel(chip_num=chip['chip_num'], channel_num=channel['channel_num'])
                        batch.fill_channels.append(dbchan)
                    
                    dbchan.fill_time = channel['fill_time']
        
        Session.commit()
        session['flash'] = 'Fill times updated.'
        session.save()

        return redirect(url(controller='consumable', action='fill', id=batch.id))


    def new_molding(self):
        c.form = h.LiteralForm()
        c.title = "Create New Molding Style"
        c.submit_action = url(controller='consumable', action='create_molding')
        return render('/product/consumable/subform.html')
    
    @restrict('POST')
    @validate(schema=NameDescriptionForm(), form='new_molding')
    def create_molding(self):
        style = ConsumableMoldingStyle(name=self.form_result['name'],
                                       description=self.form_result['description'])
        Session.add(style)
        Session.commit()
        session['flash'] = "Molding style '%s' created." % style.name
        return redirect(url(controller='consumable', action='new'))
    
    def new_bonding(self):
        c.title = "Create New Bonding Style"
        c.form = h.LiteralForm()
        c.submit_action = url(controller='consumable', action='create_bonding')
        return render('/product/consumable/subform.html')
    
    @restrict('POST')
    @validate(schema=NameDescriptionForm(), form='new_bonding')
    def create_bonding(self):
        style = ConsumableBondingStyle(name=self.form_result['name'],
                                       description=self.form_result['description'])
        Session.add(style)
        Session.commit()
        session['flash'] = "Bonding style '%s' created." % style.name
        return redirect(url(controller='consumable', action='new'))
