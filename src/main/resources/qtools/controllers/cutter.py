import logging, re, urllib, math, operator

from pylons import request, response, session, tmpl_context as c, url, config
from pylons.controllers.util import abort, redirect
from pylons.decorators import validate, jsonify
from pylons.decorators.rest import restrict

from sqlalchemy.sql import func
from sqlalchemy.orm import contains_eager, joinedload_all

from qtools.constants.pcr import *
from qtools.lib.base import BaseController, render
from qtools.lib.bio import base_regexp_expand, reverse_complement, gc_content
from qtools.lib.bio import PCRSequence, SimpleGenomeSequence
import qtools.lib.assay as assayutil
import qtools.lib.helpers as h
import qtools.lib.fields as fl
from qtools.lib.exception import ReturnWithCaveats
from qtools.lib.validators import DNASequence, KeyValidator, IntKeyValidator
from qtools.lib.sequence import mutate_sequences, find_multiple_for_fragments_map
from qtools.lib.dbservice.ucsc import HG19Source, SNP131Transformer
from qtools.lib.webservice.ucsc import UCSCSequenceSource
from qtools.model import Session, VendorEnzyme, Enzyme, Vendor
from qtools.model.sequence import SequenceGroup, Amplicon, AmpliconSequenceCache
from qtools.model.sequence.pcr import pcr_sequences_snps_for_group
from qtools.model.sequence.restriction import sequence_group_min_cuts_by_enzyme
from qtools.model.sequence.util import active_sequence_group_query

import numpy as np

import formencode

log = logging.getLogger(__name__)

class EnzymeForm(formencode.Schema):
    allow_extra_fields = True
    filter_extra_fields = True

    enzymes = formencode.validators.String(not_empty=False, if_missing='')

class SingleEnzymeForm(formencode.Schema):
    allow_extra_fields = True
    filter_extra_fields = True

    enzyme = KeyValidator(Enzyme, 'name', not_empty=True)
    from_list = formencode.validators.String(not_empty=False, if_missing='')

class EnzymeSensitivityForm(formencode.Schema):
    allow_extra_fields = True
    filter_extra_fields = True

    enzyme = KeyValidator(Enzyme, 'name', not_empty=True)
    sensitivity = formencode.validators.String(not_empty=False, if_missing=None)

class EnzymeInStockForm(formencode.Schema):
    allow_extra_fields = True
    filter_extra_fields = True

    vendor_enzyme_id = IntKeyValidator(VendorEnzyme, 'id', not_empty=True)
    in_stock = formencode.validators.Bool(not_empty=False, if_missing=False)

class CutterParamForm(formencode.Schema):
    allow_extra_fields = True
    filter_extra_fields = True
    
    assay = formencode.validators.String(not_empty=True)
    left_padding = formencode.validators.Int(min=0, max=MAX_CACHE_PADDING, if_empty=0)
    right_padding = formencode.validators.Int(min=0, max=MAX_CACHE_PADDING, if_empty=0)
    
class DetailedCutterParamForm(formencode.Schema):
    allow_extra_fields = True
    filter_extra_fields = True
    
    assay = formencode.validators.String(not_empty=True)
    left_padding = formencode.validators.Int(min=0, max=MAX_CACHE_PADDING, if_empty=0)
    right_padding = formencode.validators.Int(min=0, max=MAX_CACHE_PADDING, if_empty=0)
    enzymes = formencode.validators.String(not_empty=False, if_missing='')
    scoring_function = formencode.validators.String(if_missing='cuts')
    allow_methylation = formencode.validators.Bool(not_empty=False, if_missing=False)
    singles_as_doubles = formencode.validators.Bool(not_empty=False, if_missing=False)
    
class MultiCutterParamForm(formencode.Schema):
    allow_extra_fields = True
    filter_extra_fields = True
    
    assays = formencode.ForEach(IntKeyValidator(SequenceGroup, 'id'), if_missing=formencode.NoDefault)
    left_padding = formencode.validators.Int(min=0, max=MAX_CACHE_PADDING, if_empty=0)
    right_padding = formencode.validators.Int(min=0, max=MAX_CACHE_PADDING, if_empty=0)
    enzymes = formencode.validators.String(not_empty=False, if_missing='')
    scoring_function = formencode.validators.String(if_missing='cuts')
    allow_methylation = formencode.validators.Bool(not_empty=False, if_missing=False)
    singles_as_doubles = formencode.validators.Bool(not_empty=False, if_missing=False)

class CutTestForm(formencode.Schema):
    allow_extra_fields = True
    filter_extra_fields = True
    
    left_padding = formencode.validators.Int(min=0, max=MAX_CACHE_PADDING, if_empty=0)
    right_padding = formencode.validators.Int(min=0, max=MAX_CACHE_PADDING, if_empty=0)
    assay_id = IntKeyValidator(SequenceGroup, 'id', not_empty=False, if_missing=None)
    enzyme = KeyValidator(Enzyme, 'name')
    positive_sequence = DNASequence(not_empty=False)
    

class ManualSequenceForm(formencode.Schema):
    allow_extra_fields = True
    filter_extra_fields = True
    
    sequence = DNASequence(not_empty=True)
    enzymes = formencode.validators.String(not_empty=False, if_missing='')
    allow_methylation = formencode.validators.Bool(not_empty=False, if_missing=False)

class CutterController(BaseController):

    def index(self):
        assay_field = fl.sequence_group_field(blank=True, selected=request.params.get('assay', None))

        # this will need to change based on the mode...
        enzyme_field = fl.enzyme_select_field()

        c.assays = assay_field
        c.enzymes = enzyme_field
        
        response = render('/cutter/index.html')
        defaults = {'left_padding': 500, 'right_padding': 500}
        return h.render_bootstrap_form(response, defaults=defaults)
    
    def __scoring_function_field(selected=None):
        options = {'value': selected or '',
                   'options': [(u'frag', u'Min Fragment Length'),
                              (u'cuts', u'Most Cuts')]}
        if h.wowo('show_enzyme_price_bins'):
            options['options'].append((u'cost_bin', u'Cost Tier'))
        else:
            options['options'].append((u'cpu',u'Cuts/Cost'))
        return options
    
    def __multi_scoring_function_field(selected=None):
        options = {'value': selected or '',
                   'options': [(u'multi_mean', u'Mean Fragment Length'),
                               (u'cuts', u'Most Cuts'),
                               (u'multi_similar', u'Fragment Length Similarity')]}
        
        if h.wowo('show_enzyme_price_bins'):
            options['options'].insert(2, (u'cost_bin',u'Cost Tier'))
        else:
            options['options'].insert(2, (u'cpu',u'Cuts/Cost'))
        
        return options
    
    def _pick_base(self):
        assay_field = fl.sequence_group_field(blank=True, selected=request.params.get('assay', None))
        enzyme_field = fl.enzyme_select_field()
        c.assays = assay_field
        c.enzymes = enzyme_field
        c.scoring_function = self.__scoring_function_field()

        # probably need a wowo on which
        return render('/cutter/pick.html')
    
    def pick(self):
        response = self._pick_base()
        defaults = {'left_padding': 500,
                    'right_padding': 500,
                    'allow_methylation': '',
                    'singles_as_doubles': '',
                    'scoring_function': 'frag'}
        return h.render_bootstrap_form(response, defaults=defaults)
    
    def _multipick_base(self):
        assay_field = fl.sequence_group_field()
        enzyme_field = fl.enzyme_select_field()
        c.assays = assay_field
        c.enzymes = enzyme_field
        c.scoring_function = self.__multi_scoring_function_field()
        return render('/cutter/multipick.html')
    
    def multipick(self):
        response = self._multipick_base()
        defaults = {'left_padding': 500,
                    'right_padding': 500,
                    'allow_methylation': '',
                    'singles_as_doubles': '',
                    'scoring_function': 'multi_mean'}
        return h.render_bootstrap_form(response, defaults=defaults)
    
    @validate(schema=DetailedCutterParamForm(), form='_pick_base', post_only=False, on_get=True, error_formatters=h.tw_bootstrap_error_formatters)
    def find_cutters(self):
        # process assay
        sequence_group = self.__sequence_group_for_id(self.form_result['assay'])
        left_padding = self.form_result['left_padding']
        right_padding = self.form_result['right_padding']
        
        c.assay_id = self.form_result['assay']
        c.left_padding = self.form_result['left_padding']
        c.right_padding = self.form_result['right_padding']
        c.enzymes = self.form_result['enzymes']
        c.allow_methylation = self.form_result['allow_methylation'] and 1 or ''
        
        if sequence_group is None:
            abort(404)
        
        c.assay = sequence_group
        
        enzymes = self.__enzymes_from_form()
        ecache = dict([(enz.name, enz) for enz in enzymes])
        
        amplicon_tuples = pcr_sequences_snps_for_group(sequence_group, padding_pos5=c.left_padding, padding_pos3=c.right_padding)
        if len(amplicon_tuples) == 0:
            c.found_sequence = False
            return render('/cutter/results.html')
        c.found_sequence = True

        # flatten sequences
        sequences = []
        for amp, pseqs in amplicon_tuples:
            sequences.extend(pseqs)
        
        sequence_cut_data = self.__cuts_for_sequences(sequences, enzymes)
        
        for seq in sequence_cut_data:
            if self.form_result['singles_as_doubles']:
                seq[1]['left_cutters'].extend(seq[1]['around_cutters'])
                seq[1]['right_cutters'].extend(seq[1]['around_cutters'])
            seq[1]['double_digests'] = self.__compute_double_digests(seq[1]['left_cutters'], seq[1]['right_cutters'])
            # decorate with prices
            for enz in seq[1]['around_cutters']:
                enz['cost'] = ecache[enz['name']].VendorEnzyme.unit_cost_1
                enz['cost_bin'] = ecache[enz['name']].VendorEnzyme.unit_cost_bin
            for enz in seq[1]['double_digests']:
                enz['cost'] = ecache[enz['pair'][0]].VendorEnzyme.unit_cost_1 + ecache[enz['pair'][1]].VendorEnzyme.unit_cost_1
                enz['cost_bin'] = max(ecache[enz['pair'][0]].VendorEnzyme.unit_cost_bin,
                                      ecache[enz['pair'][1]].VendorEnzyme.unit_cost_bin)
                enz['buffer'] = ecache[enz['pair'][0]].VendorEnzyme.buffer.name
            
            # TODO: right to do here or in the template?
            seq[1]['left_cutters'] = [lcut['name'] for lcut in seq[1]['left_cutters']]
            seq[1]['right_cutters'] = [rcut['name'] for rcut in seq[1]['right_cutters']]
            
            seq[1]['around_cutters'] = self.__score_digests(seq[1]['around_cutters'], self.form_result['scoring_function'])
            seq[1]['double_digests'] = self.__score_digests(seq[1]['double_digests'], self.form_result['scoring_function'])
        
        c.cut_results = sequence_cut_data
        return render('/cutter/results.html')
    
    @validate(schema=MultiCutterParamForm(), form='_multipick_base', on_get=True, post_only=False, error_formatters=h.tw_bootstrap_error_formatters)
    def multi_cutters(self):

        assay_ids = self.form_result['assays']
        left_padding = self.form_result['left_padding']
        right_padding = self.form_result['right_padding']
        c.left_padding = left_padding
        c.right_padding = right_padding
        c.enzymes = self.form_result['enzymes']
        c.allow_methylation = 1 if self.form_result['allow_methylation'] else ''
        c.singles_as_doubles = 1 if self.form_result['singles_as_doubles'] else ''
        c.scoring_function = self.form_result['scoring_function']

        c.assay_ids = assay_ids

        c.form = h.LiteralForm(
            value = {'scoring_function': u'cuts',
                     'left_padding': left_padding,
                     'right_padding': right_padding}
        )
        
        enzymes = self.__enzymes_from_form()
        
        sequence_groups = active_sequence_group_query().filter(SequenceGroup.id.in_(assay_ids)).order_by('name').all()
        c.assay_names = ', '.join([sg.name for sg in sequence_groups])

        sequences = []
        for sg in sequence_groups:
            amplicon_tuples = pcr_sequences_snps_for_group(sg, padding_pos5=c.left_padding, padding_pos3=c.right_padding)
            for amp, pseqs in amplicon_tuples:
                sequences.extend(pseqs)
        if len(sequences) == 0:
            c.found_sequences = False
            return render('/cutter/multiresults.html')
        c.found_sequences = True

        sequence_cut_data = self.__cuts_for_sequences(sequences, enzymes)
        all_cut_dict = dict([(enz.name, dict(name=enz.name, cuts=0, buffer=enz.VendorEnzyme.buffer.name, min_rightmost_lefts=[], max_leftmost_rights=[])) for enz in enzymes])
        one_cut_dict = {}
        amplicon_cut_dict = {}
        no_cutter_dict = {}
        
        # find around for everyone, lefts, rights, then doubles
        #raise Exception, sequence_cut_data
        for idx, seq in enumerate(sequence_cut_data):
            for enz_name in seq[1]['no_cutters']:
                all_cut_dict.pop(enz_name, None)
                one_cut_dict.pop(enz_name, None)
                if not amplicon_cut_dict.has_key(enz_name):
                    no_cutter_dict[enz_name] = enz_name
            
            for enz_name in seq[1]['amplicon_cutters']:
                all_cut_dict.pop(enz_name, None)
                one_cut_dict.pop(enz_name, None)
                no_cutter_dict.pop(enz_name, None)
                amplicon_cut_dict[enz_name] = enz_name
            
            # TODO: this could be smoother (combine left/right?)
            for enz in seq[1]['left_cutters']:
                enz_name = enz['name']
                record = all_cut_dict.pop(enz_name, None)
                if record:
                    one_cut_dict[enz_name] = {'name': enz_name,
                                              'cut_order': ['B']*idx,
                                              'cuts': record['cuts'],
                                              'buffer': record['buffer'],
                                              'max_leftmost_rights': list(record['max_leftmost_rights']),
                                              'min_rightmost_lefts': list(record['min_rightmost_lefts'])}
                
                if one_cut_dict.has_key(enz_name):
                    one_cut_dict[enz_name]['cut_order'].append('L')
                    one_cut_dict[enz_name]['cuts'] += enz['cuts']
                    one_cut_dict[enz_name]['min_rightmost_lefts'].append(enz['min_rightmost_left'])
                    one_cut_dict[enz_name]['max_leftmost_rights'].append(None) 
            
            for enz in seq[1]['right_cutters']:
                enz_name = enz['name']
                record = all_cut_dict.pop(enz_name, None)
                if record:
                    one_cut_dict[enz_name] = {'name': enz_name,
                                              'cut_order': ['B']*idx,
                                              'cuts': record['cuts'],
                                              'buffer': record['buffer'],
                                              'min_rightmost_lefts': list(record['min_rightmost_lefts']),
                                              'max_leftmost_rights': list(record['max_leftmost_rights'])}
                
                if one_cut_dict.has_key(enz_name):
                    one_cut_dict[enz_name]['cut_order'].append('R')
                    one_cut_dict[enz_name]['cuts'] += enz['cuts']
                    one_cut_dict[enz_name]['max_leftmost_rights'].append(enz['max_leftmost_right'])
                    one_cut_dict[enz_name]['min_rightmost_lefts'].append(None)
            
            for enz in seq[1]['around_cutters']:
                enz_name = enz['name']
                if all_cut_dict.has_key(enz_name):
                    all_cut_dict[enz_name]['cuts'] += enz['cuts']
                    all_cut_dict[enz_name]['min_rightmost_lefts'].append(enz['min_rightmost_left'])
                    all_cut_dict[enz_name]['max_leftmost_rights'].append(enz['max_leftmost_right'])
                elif one_cut_dict.has_key(enz_name):
                    one_cut_dict[enz_name]['cut_order'].append('B')
                    one_cut_dict[enz_name]['cuts'] += enz['cuts']
                    one_cut_dict[enz_name]['min_rightmost_lefts'].append(enz['min_rightmost_left'])
                    one_cut_dict[enz_name]['max_leftmost_rights'].append(enz['max_leftmost_right'])
        
        double_digests = []

        if self.form_result['singles_as_doubles']:
            for enz, val in all_cut_dict.items():
                val['cut_order'] = len(sequence_cut_data)*['B']
            one_cut_dict.update(all_cut_dict)
        
        # todo: multiple more levels down (keep tracking no-cutters so you can pick combos?)
        for name1, info1 in one_cut_dict.items():
            for name2, info2 in one_cut_dict.items():
                if name2 <= name1:
                    continue
                
                if info1['buffer'] != info2['buffer']:
                    continue
                
                same_side = False
                for cut1, cut2 in zip(info1['cut_order'], info2['cut_order']):
                    if (cut1 == 'R' and cut2 == 'R') or (cut1 == 'L' and cut2 == 'L'):
                        same_side = True
                        break
                
                if same_side:
                    continue
                
                # find min_fragment lengths for the combination.
                min_fragment_lengths = []
                lefts = zip(info1['min_rightmost_lefts'], info2['min_rightmost_lefts'])
                rights = zip(info1['max_leftmost_rights'], info2['max_leftmost_rights'])
                rightmost_lefts = [max([p for p in pair if p is not None]) for pair in lefts]
                leftmost_rights = [min([p for p in pair if p is not None]) for pair in rights]
                min_fragment_lengths = [a-b for a, b in zip(leftmost_rights, rightmost_lefts)]

                # at this point, both are covered in all sequences.  promote to DD.
                double_digests.append({'pair': (name1, name2),
                                       'cuts': info1['cuts']+info2['cuts'],
                                       'buffer': info1['buffer'],
                                       'min_fragment_lengths': min_fragment_lengths})
        
        around_cutters = all_cut_dict.values()

        # TODO: include option of using single digests as double digest test (Redmine 670)
        
        ecache = dict([(enz.name, enz) for enz in enzymes])
        for cut in around_cutters:
            cut['cost'] = ecache[cut['name']].VendorEnzyme.unit_cost_1
            cut['cost_bin'] = ecache[cut['name']].VendorEnzyme.unit_cost_bin
            cut['cuts'] = cut['cuts']/float(len(sequences))
            cut['min_fragment_lengths'] = [a-b for a, b in zip(cut['max_leftmost_rights'], cut['min_rightmost_lefts'])]
            cut['min_fragment_variance'] = np.std(cut['min_fragment_lengths'])
            cut['min_fragment_mean'] = np.mean(cut['min_fragment_lengths'])

        for cut in double_digests:
            cut['cost'] = ecache[cut['pair'][0]].VendorEnzyme.unit_cost_1 + ecache[cut['pair'][1]].VendorEnzyme.unit_cost_1
            cut['cost_bin'] = max(ecache[cut['pair'][0]].VendorEnzyme.unit_cost_bin,
                                  ecache[cut['pair'][1]].VendorEnzyme.unit_cost_bin)
            cut['cuts'] = cut['cuts']/float(len(sequences))
            cut['buffer_name'] = ecache[cut['pair'][0]].VendorEnzyme.buffer.name
            cut['min_fragment_variance'] = np.std(cut['min_fragment_lengths'])
            cut['min_fragment_mean'] = np.mean(cut['min_fragment_lengths'])
            
    
        c.around_cutters = self.__score_digests(around_cutters, self.form_result['scoring_function'])
        c.double_digests = self.__score_digests(double_digests, self.form_result['scoring_function'])
        c.amplicon_cutters = sorted(amplicon_cut_dict.keys())
        
        return render('/cutter/multiresults.html')

    
    @validate(schema=ManualSequenceForm, form='index', on_get=True, post_only=False)
    def manual(self):
        c.assay_name = "Manual Entry"
        seq = self.form_result['sequence']
        c.amplicon_width = len(seq)
        c.prefix_width = 0
        c.suffix_width = 0
        
        enzymes = self.__enzymes_from_form()
        c.form = h.LiteralForm(
            value = {'enzyme': ''},
            option = {'enzyme': [('','--')]+[(e.cutseq, e.name) for e in enzymes]}
        )
        
        # TODO helper function for later (shared with sequence)
        c.prefix_pct = 0
        c.amplicon_pct = 100
        c.suffix_pct = 0
        c.amplicon_offset_pos = c.prefix_width
        c.amplicon_offset_neg = c.suffix_width
        c.positive_sequence = seq
        c.negative_sequence = reverse_complement(seq)
        c.found_sequence = True
        c.left_padding = 0
        c.right_padding = 0
        c.assay_id = ''
        c.enzymes = self.form_result['enzymes']

        c.form = h.LiteralForm(
            value = {'enzymes': ''},
            option = {'enzymes': [('','--')]+[(e.cutseq, e.name) for e in enzymes]}
        )
        return render('/cutter/sequence.html')
    
    
    @validate(schema=DetailedCutterParamForm(), form='index', post_only=False, on_get=True)
    def sequence(self):
        enzymes = self.__enzymes_from_form()
        
        c.form = h.LiteralForm(
            value = {'enzymes': ''},
            option = {'enzymes': [('','--')]+[(e.cutseq, e.name) for e in enzymes]}
        )
        
        assay = self.__sequence_group_for_id(self.form_result['assay'])
        c.assay = assay
        c.assay_id = c.assay.id
        c.assay_name = assay.name
        
        if assay is None:
            abort(404)
        
        left_padding = self.form_result['left_padding']
        right_padding = self.form_result['right_padding']
        c.left_padding = left_padding
        c.right_padding = right_padding
        c.enzymes = self.form_result['enzymes']
        
        sequences = []
        amplicon_tuples = pcr_sequences_snps_for_group(assay, padding_pos5=left_padding, padding_pos3=right_padding)
        for amp, pseqs in amplicon_tuples:
            sequences.extend(pseqs)
        
        if len(sequences) == 0:
            c.found_sequence = False
            return render('/cutter/sequence.html')
        
        # TODO: handle multi-sequence case
        sequence = sequences[0]
        c.found_sequence = True
        
        c.amplicon_width = len(sequence.amplicon)
        c.prefix_width = len(sequence.left_padding) if sequence.left_padding else 0
        c.suffix_width = len(sequence.right_padding) if sequence.right_padding else 0
        
        total_len = float(sequence.width)
        c.prefix_pct = 100*(c.prefix_width/total_len)
        c.amplicon_pct = 100*(c.amplicon_width/total_len)
        c.suffix_pct = 100*(c.suffix_width/total_len)
        c.amplicon_offset_pos = c.prefix_width
        c.amplicon_offset_neg = c.suffix_width
        
        c.sequence = sequence.merged_positive_sequence
        c.positive_sequence = sequence.merged_positive_sequence.sequence
        c.negative_sequence = sequence.merged_negative_sequence.sequence
        c.positive_sequence_fasta = sequence.merged_positive_sequence.fasta
        c.negative_sequence_fasta = sequence.merged_negative_sequence.fasta
        return render('/cutter/sequence.html')
    
    @jsonify
    @restrict('POST')
    @validate(schema=CutTestForm(), form='sequence')
    def cut(self):
        left_padding = self.form_result['left_padding']
        right_padding = self.form_result['right_padding']
        enzyme = Session.query(Enzyme).get(self.form_result['enzyme'])
        cutseq = enzyme.cutseq
        
        # TODO change to single amplicon?
        if self.form_result['assay_id']:
            assay = Session.query(SequenceGroup).get(self.form_result['assay_id'])
            amplicon_tuples = pcr_sequences_snps_for_group(assay, padding_pos5=left_padding, padding_pos3=right_padding)
            sequences = []
            for amp, pseqs in amplicon_tuples:
                sequences.extend(pseqs)
        else:
            manual_seq = PCRSequence(SimpleGenomeSequence(0, 0, len(self.form_result['positive_sequence'])-1, '+',
                                                          full_sequence=self.form_result['positive_sequence']))
            manual_seq.snps = []
            sequences = [manual_seq]
        
        # TODO: this is arbitrary
        location_cut_data = self.__enzyme_cut_locations(sequences[0], [enzyme])
        
        # TODO support multiple sequences, somehow.
        
        pos_seq = sequences[0].merged_positive_sequence
        total_width = len(pos_seq)
        re_width_pct = 100*float(len(cutseq))/total_width
        
        enzyme_cut_data = location_cut_data[self.form_result['enzyme']]
        
        positive_matches = []
        negative_matches = []
        return_dict = {}
        snp_dict = dict([(s['name'], s) for s in sequences[0].snps])
        # keys here are going to be amplicon_cuts, left_cuts and right_cuts, left_cut
        for k, v in sorted(enzyme_cut_data.items()):
            blank, original_positives, original_negatives = v[0]
            snp_positives = []
            snp_negatives = []
            cancel_positives = []
            cancel_negatives = []
            for cuts in v[1:]:
                snp_name, shifted_positives, shifted_negatives = cuts
                snp = snp_dict[snp_name]
                # TODO: this is an oversimplification but will probably only result
                # in a shift in a particular restriction site
                #
                # TODO: I think this is sketchy right at the edges, needs to be tested. (> vs >=, etc)
                # TODO: the code could stand to be more compact as well.
                if len(shifted_positives) > len(original_positives):
                    found = False
                    for start, end, strand in shifted_positives:
                        if (snp['chromEnd'] >= pos_seq.start+start-1 and snp['chromEnd'] <= pos_seq.start+end) or \
                           (snp['chromStart'] >= pos_seq.start+start-1 and snp['chromStart'] <= pos_seq.start+end):
                            snp_positives.append((start, end, strand))
                            found = True
                    if not found:
                        pass
                        #raise Exception, "ERROR: additional positive strand restriction site not found by analyzing SNPs"
                
                elif len(shifted_positives) < len(original_positives):
                    found = False
                    for start, end, strand in original_positives:
                        if (snp['chromEnd'] >= pos_seq.start+start-1 and snp['chromEnd'] <= pos_seq.start+end) or \
                           (snp['chromStart'] >= pos_seq.start+start-1 and snp['chromStart'] <= pos_seq.start+end) or \
                           (pos_seq.start+start-1 >= snp['chromStart'] and pos_seq.start+end <= snp['chromEnd']):
                            if (start, end, strand) not in cancel_positives:
                                cancel_positives.append((start, end, strand))
                            found = True
                    if not found:
                        pass
                        #raise Exception, "ERROR: cancelled positive strand restriction site not found by analyzing SNPs"
                           
                if len(shifted_negatives) > len(original_negatives):
                    # find where the new snp is
                    found = False
                    for start, end, strand in shifted_negatives:
                        if (snp['chromEnd'] >= pos_seq.end-(end+1) and snp['chromEnd'] <= pos_seq.end-start) or \
                           (snp['chromStart'] >= pos_seq.end-(end+1) and snp['chromStart'] <= pos_seq.end-start):
                            snp_negatives.append((start, end, strand))
                            found = True
                    if not found:
                        pass
                        # insertion screws you here.
                        #raise Exception, (snp['chromEnd'], snp['chromStart'], pos_seq.end, pos_seq.end-(shifted_negatives[0][1]+1), pos_seq.end-(shifted_negatives[0][0]))
                        #raise Exception, "ERROR: additional negative strand restriction site not found by analyzing SNPs"
                    
                elif len(shifted_negatives) < len(original_negatives):
                    found = False
                    for start, end, strand in original_negatives:
                        if (snp['chromEnd'] >= pos_seq.end-(end+1) and snp['chromEnd'] <= pos_seq.end-start) or \
                           (snp['chromStart'] >= pos_seq.end-(end+1) and snp['chromStart'] <= pos_seq.end-start) or \
                           (pos_seq.end-(end+1) >= snp['chromStart'] and pos_seq.end-start <= snp['chromEnd']):
                            if (start, end, strand) not in cancel_negatives:
                                cancel_negatives.append((start, end, strand))
                            found = True
                    
                    if not found:
                        pass
                        #raise Exception, "ERROR: cancelling negative strand restriction site not found by analyzing SNPs"
            
            for tup in cancel_positives:
                original_positives.remove(tup)
            for tup in cancel_negatives:
                original_negatives.remove(tup)
            
            return_dict[k] = len(original_positives) + len(cancel_positives) \
                             + len(original_negatives) + len(cancel_negatives) \
                             + len(snp_positives) + len(snp_negatives)
            
            for start, end, strand in original_positives:
                positive_matches.append({'offset': start, 'pos': '%s%%' % (start*100.0/total_width), 'class': 'stable_re_site'})
            
            for start, end, strand in original_negatives:
                negative_matches.append({'offset': start, 'pos': '%s%%' % (100-(start*100.0/total_width)-re_width_pct), 'class': 'stable_re_site'})
            
            for start, end, strand in snp_positives:
                positive_matches.append({'offset': start, 'pos': '%s%%' % (start*100.0/total_width), 'class': 'snp_re_site'})
            
            for start, end, strand in snp_negatives:
                negative_matches.append({'offset': start, 'pos': '%s%%' % (100-(start*100.0/total_width)-re_width_pct), 'class': 'snp_re_site'})
            
            for start, end, strand in cancel_positives:
                positive_matches.append({'offset': start, 'pos': '%s%%' % (start*100.0/total_width), 'class': 'snp_cancel_re_site'})
            
            for start, end, strand in cancel_negatives:
                negative_matches.append({'offset': start, 'pos': '%s%%' % (100-(start*100.0/total_width)-re_width_pct), 'class': 'snp_cancel_re_site'})
                
        return_dict['positive_cuts'] = positive_matches
        return_dict['negative_cuts'] = negative_matches
        return_dict['re_width_pct'] = "%s%%" % re_width_pct

        # future out amplicon position
        amplicon_start = left_padding
        amplicon_end = len(pos_seq) - (right_padding+1)
        
        left_offsets = [match['offset'] for match in positive_matches if match['offset'] < (amplicon_start - len(cutseq))]
        if left_offsets:
            rightmost_left = max(left_offsets)+len(cutseq)
        else:
            rightmost_left = None
        
        right_offsets = [match['offset'] for match in positive_matches if match['offset'] > amplicon_end]
        if right_offsets:
            leftmost_right = min(right_offsets)
        else:
            leftmost_right = None
        
        amplicon_cuts = [match for match in positive_matches if match['offset'] >= amplicon_start and match['offset'] <= amplicon_end]
        
        # todo: bug if the cutters are asymmetric and the negative cutsite is shorter (redmine 669)
        if rightmost_left is not None and leftmost_right is not None and len(amplicon_cuts) == 0:
            inner_len = leftmost_right - rightmost_left
            inner_seq = pos_seq.sequence[rightmost_left:leftmost_right]
            inner_gc = gc_content(inner_seq)
            left_offset = amplicon_start - rightmost_left
            right_offset = leftmost_right - amplicon_end

            return_dict['fragment'] = {'len': inner_len,
                                       'loff': left_offset,
                                       'roff': right_offset,
                                       'gc': "%.2f%%" % (inner_gc*100)}
            
        return return_dict

    @validate(schema=EnzymeForm(), on_get=True, post_only=False)    
    def enzymes(self):
        enz = self.__enzymes_from_form()
        c.enzymes = enz
        c.from_list = self.form_result['enzymes']
        enzyme_select_field = fl.enzyme_select_field(selected=self.form_result['enzymes'])
        c.enzyme_form = h.LiteralFormSelectPatch(
            value = {'enzymes': enzyme_select_field['value']},
            option = {'enzymes': enzyme_select_field['options']}
        )
        return render('/cutter/enzyme.html')

    @validate(schema=SingleEnzymeForm, on_get=True, post_only=False)
    def digest_control(self):
        c.enzyme = Session.query(Enzyme).get(self.form_result['enzyme'])
        c.from_list = self.form_result['from_list']
        assays = active_sequence_group_query()\
                        .filter(SequenceGroup.status.in_((SequenceGroup.STATUS_TYPE_VALIDATED,
                                                          SequenceGroup.STATUS_TYPE_PREFERRED)))\
                        .options(joinedload_all(SequenceGroup.amplicons,
                                                Amplicon.cached_sequences,
                                                AmpliconSequenceCache.snps, innerjoin=True)).all()
        
        controls = []
        #### TODO resume here
        for a in assays:
            cuts = sequence_group_min_cuts_by_enzyme(a, c.enzyme)
            if cuts > 0:
                controls.append((a, cuts))
        c.controls = sorted(controls, key=lambda tup: tup[0].name)
        return render('/cutter/digest_control.html')

    
    @restrict('POST')
    @validate(schema=EnzymeInStockForm(), form='enzymes')
    def instock(self):
        enz = Session.query(VendorEnzyme).get(self.form_result['vendor_enzyme_id'])
        if self.form_result['in_stock']:
            enz.stock_units = 1
        else:
            enz.stock_units = 0
        
        Session.commit()
        return 'OK'

    @restrict('POST')
    @validate(schema=EnzymeSensitivityForm(), form='enzymes')
    def sensitivity(self):
        enz = Session.query(Enzyme).get(self.form_result['enzyme'])
        if not self.form_result['sensitivity']:
            enz.methylation_sensitivity = None
        else:
            enz.methylation_sensitivity = self.form_result['sensitivity']
        Session.commit()
        return "OK"

    def __sequence_group_for_id(self, id):
        """
        Return the sequence group corresponding to the specified id.
        """
        return Session.query(SequenceGroup).get(int(id))
    
    def __available_enzymes(self):
        return Session.query(VendorEnzyme, Enzyme.name, Enzyme.cutseq, Enzyme.methylation_sensitivity).join(Enzyme)\
                    .filter(VendorEnzyme.stock_units > 0)\
                    .group_by(VendorEnzyme.enzyme_id).all()
    
    def __vendor_enzymes(self, name):
        vendor = Session.query(Vendor).filter_by(name=unicode(name)).first()
        # this might be better off with a regular SQL statement
        all_enzymes = Session.query(VendorEnzyme, Enzyme.name, Enzyme.cutseq, Enzyme.methylation_sensitivity,\
                                    func.sum(VendorEnzyme.stock_units).label('total_stock_units')
                                   ).join(Enzyme).filter(VendorEnzyme.vendor_id == vendor.id).group_by(VendorEnzyme.enzyme_id).all()
        return all_enzymes
    
    def __cut4_enzymes(self):
        all_enzymes = Session.query(VendorEnzyme, Enzyme.name, Enzyme.cutseq, Enzyme.methylation_sensitivity).\
                              join(Enzyme).filter("char_length(cutseq) = 4").group_by(VendorEnzyme.enzyme_id).all()
        return all_enzymes
    
    def __neb_enzymes(self):
        return self.__vendor_enzymes('NEB')
    
    def __vendor4_enzymes(self, vendor):
        enzymes = self.__vendor_enzymes(vendor)
        return [e for e in enzymes if len(e.cutseq) == 4]
    
    def __fermentas_enzymes(self):
        return self.__vendor_enzymes('Fermentas')
    
    def __enzyme_cut_locations(self, pcr_seq, enzymes):
        if not enzymes:
            return dict()
        
        edict = dict([(e.name, e.cutseq) for e in enzymes])
        
        combined_sequence = pcr_seq.merged_positive_sequence
        amplicon_location_start = pcr_seq.amplicon.start
        amplicon_location_end = pcr_seq.amplicon.end
        
        enzyme_length = max([len(enzyme.cutseq) for enzyme in enzymes])
        try:
            mutated_sequences = mutate_sequences(SNP131Transformer(), combined_sequence, pcr_seq.snps, enzyme_length, combined_sequence.strand)
        except ReturnWithCaveats, e:
            # TODO show error message
            mutated_sequences = e.return_value
        
        cutseqs = [e.cutseq for e in enzymes]
        
        # keep in mind mutated sequences are now positive
        cut_data = find_multiple_for_fragments_map(edict, mutated_sequences)
        
        # original sequence just takes name -> match pair, we need to use entire enzyme_data
        
        # get coordinates for amplicon, left_padding, right_padding
        # TODO: make into SimpleGenomeSequences instead?
        pos_xform_positions = [(ms.name, (ms.sequence_slice_indices(pcr_seq.left_padding.start, pcr_seq.left_padding.end) if pcr_seq.left_padding else (-1,-1),
                               ms.sequence_slice_indices(pcr_seq.amplicon.start, pcr_seq.amplicon.end),
                               ms.sequence_slice_indices(pcr_seq.right_padding.start, pcr_seq.right_padding.end) if pcr_seq.right_padding else (-1,-1)))\
                               for ms in mutated_sequences]
        
        neg_xform_positions = [(ms.name, (ms.sequence_slice_indices(pcr_seq.left_padding.start, pcr_seq.left_padding.end) if pcr_seq.left_padding else (-1,-1),
                               ms.sequence_slice_indices(pcr_seq.amplicon.start, pcr_seq.amplicon.end),
                               ms.sequence_slice_indices(pcr_seq.right_padding.start, pcr_seq.right_padding.end) if pcr_seq.right_padding else (-1,-1)))\
                               for ms in [pms.reverse_complement() for pms in mutated_sequences]]
        
        
        enz_results = dict()
        for enz, cuts in cut_data.items():
            # relies on invariant: find_multiple_for_fragments_map will
            # have cuts in same order as mutated_sequences supplied.
            enz_acuts = []
            enz_lcuts = []
            enz_rcuts = []
            
            for i in range(len(cuts)):
                snp_name = pos_xform_positions[i][0]
                
                acuts = (snp_name, [],[])
                lcuts = (snp_name, [],[])
                rcuts = (snp_name, [],[])
                
                pos_xform = pos_xform_positions[i][1]
                neg_xform = neg_xform_positions[i][1]
                
                pxamp = pos_xform[1]
                nxamp = neg_xform[1]
                
                plpad = pos_xform[0]
                nlpad = neg_xform[0]
                
                prpad = pos_xform[2]
                nrpad = neg_xform[2]
                
                # these won't do anything if cuts is empty
                pos_cuts = [cut for cut in cuts[i] if cut[2] == '+']
                neg_cuts = [cut for cut in cuts[i] if cut[2] == '-']
                
                for cut in pos_cuts:
                    if (cut[0] >= pxamp[0] and cut[0] <= pxamp[1]) or \
                       (cut[1] >= pxamp[0] and cut[1] <= pxamp[1]):
                        acuts[1].append(cut)
                    elif (cut[0] >= plpad[0] and cut[0] <= plpad[1]) and \
                         (cut[1] >= plpad[0] and cut[1] <= plpad[1]):
                        lcuts[1].append(cut)
                    elif (cut[0] >= prpad[0] and cut[0] <= prpad[1]) and \
                         (cut[1] >= prpad[0] and cut[1] <= prpad[1]):
                        rcuts[1].append(cut)
                
                for cut in neg_cuts:
                    if (cut[0] >= nxamp[0] and cut[0] <= nxamp[1]) or \
                       (cut[1] >= nxamp[0] and cut[1] <= nxamp[1]):
                        acuts[2].append(cut)
                    elif (cut[0] >= nlpad[0] and cut[0] <= nlpad[1]) and \
                         (cut[1] >= nlpad[0] and cut[1] <= nlpad[1]):
                        lcuts[2].append(cut)
                    elif (cut[0] >= nrpad[0] and cut[0] <= nrpad[1]) and \
                         (cut[1] >= nrpad[0] and cut[1] <= nrpad[1]):
                        rcuts[2].append(cut)
                
                enz_acuts.append(acuts)
                enz_lcuts.append(lcuts)
                enz_rcuts.append(rcuts)
            
            enz_results[enz] = {'amplicon_cuts': enz_acuts,
                                'left_cuts': enz_lcuts,
                                'right_cuts': enz_rcuts}
        return enz_results
    
    # TODO unit test
    def __cuts_for_sequences(self, sequences, enzymes):
        edict = dict([(e.name, e.cutseq) for e in enzymes])
        ecache = dict([(e.name, e) for e in enzymes])
        sequence_cut_data = []
        for pcr_seq in sequences:
            
            enz_results = self.__enzyme_cut_locations(pcr_seq, enzymes)
            
            amplicon_cutters = []
            left_cutters = []
            right_cutters = []
            around_cutters = [] # these are the ones we want
            no_cutters = []
            
            # TODO: this is really more of a UI step.  might want to break this out from the core _cuts method.
            for enz, results in enz_results.items():
                if len([result for result in results['amplicon_cuts'] if len(result[1])+len(result[2]) > 0]) > 0:
                    amplicon_cutters.append(enz)
                    continue
                
                left_cut = False
                right_cut = False

                # note: this isn't quite right, but it's close.  What we really want to do is mutate the sequences
                # and then compare the sequences pair-wise to see what the minimum fragment length is under
                # different combinations of SNPs, which may include insertions to the left of both cut sites.
                #
                # I think the net effect of both insertions and deletions prior to both cut sites is to make
                # the fragment length (length of insertion/deletion) bp higher than it actually is.  In the
                # case of an insertion, the max leftmost right cut site will be (len bp) higher, whereas the
                # normal left cut site will stay in the same spot.  In the case of a deletion, the min
                # rightmost cut site will be (len bp) lower, where the normal right cut site will stay in
                # the same spot.
                #
                # However, the way this code is written, this pairwise analysis is impossible for double digests.
                # My cost-benefit analysis tells me that this is a corner case of a corner case, and thus
                # close enough (unless there is a huuuuuuge deletion or insertion within the padding, which is uncommon)
                max_leftmost_right = None
                min_rightmost_left = None
                
                # must cut left all the time
                left_cut_count = len([result for result in results['left_cuts'] if (len(result[1])+len(result[2]) > 0)])
                min_left_cuts = min([len(result[1])+len(result[2]) for result in results['left_cuts']])
                if left_cut_count == len(results['left_cuts']) and left_cut_count > 0:
                    left_cut = True

                    # get minimum rightmost left cutter on positive strand -- min guaranteed.
                    min_rightmost_left = min([max([end for start, end, strand in result[1]]+[(pcr_seq.width-start) for start, end, strand in result[2]]) for result in results['left_cuts']])
                    
                # must cut right all the time
                right_cut_count = len([result for result in results['right_cuts'] if (len(result[1])+len(result[2]) > 0)])
                min_right_cuts = min([len(result[1])+len(result[2]) for result in results['right_cuts']])
                
                if right_cut_count == len(results['right_cuts']):
                    right_cut = True

                    # get maximum leftmost right cutter on positive strand -- max guaranteed.
                    max_leftmost_right = max([min([start for start, end, strand in result[1]]+[(pcr_seq.width-end) for start, end, strand in result[2]]) for result in results['right_cuts']])
                
                # todo: either rename enz to enz_name, or use enz object as key itself
                if left_cut and right_cut:
                    around_cutters.append({'name': enz, 'cuts': min_left_cuts+min_right_cuts,
                                           'min_rightmost_left': min_rightmost_left,
                                           'max_leftmost_right': max_leftmost_right,
                                           'buffer': ecache[enz].VendorEnzyme.buffer_id})
                    continue
                elif left_cut:
                    left_cutters.append({'name': enz, 'cuts': min_left_cuts,
                                         'min_rightmost_left': min_rightmost_left,
                                         'buffer': ecache[enz].VendorEnzyme.buffer_id})
                    continue
                elif right_cut:
                    right_cutters.append({'name': enz, 'cuts': min_right_cuts,
                                          'max_leftmost_right': max_leftmost_right,
                                          'buffer': ecache[enz].VendorEnzyme.buffer_id})
                    continue
                else:
                    no_cutters.append(enz)
            
            amplicon_cutters.sort()
            left_cutters.sort()
            right_cutters.sort()
            no_cutters.sort()
            
            sequence_cut_data.append((pcr_seq,
                                     {'amplicon_cutters': amplicon_cutters,
                                      'around_cutters': around_cutters,
                                      'left_cutters': left_cutters,
                                      'right_cutters': right_cutters,
                                      'no_cutters': no_cutters}))
            
        return sequence_cut_data
    
    def __compute_double_digests(self, left_digests, right_digests):
        double_digests = []
        # process double-digests
        for lcut in left_digests:
            for rcut in right_digests:
                if lcut['name'] >= rcut['name']:
                    continue
                
                if lcut['buffer'] == rcut['buffer']:
                    double_digests.append({'pair': (lcut['name'], rcut['name']),
                                           'cuts': lcut['cuts']+rcut['cuts'],
                                           'buffer': lcut['buffer'],
                                           'max_leftmost_right': rcut['max_leftmost_right'],
                                           'min_rightmost_left': lcut['min_rightmost_left']})
        
        return double_digests
    
    def __score_digests(self, digests, scoring_function):
        # TODO look up costs here?
        
        scoring_key = {'cuts': lambda rec: -1*rec['cuts'],
                       'cpu': lambda rec: -1*rec['cuts']/float(rec['cost']),
                       'cost_bin': lambda rec: (rec['cost_bin'], rec['name'] if 'name' in rec else (rec['pair'][0], rec['pair'][1])),
                       'cpsu': lambda rec: -1*rec['cuts']/math.sqrt(float(rec['cost'])),
                       'frag': lambda rec: rec['max_leftmost_right']-rec['min_rightmost_left'],
                       'multi_mean': lambda rec: rec['min_fragment_mean'],
                       'multi_similar': lambda rec: rec['min_fragment_variance'],
                       'multi_similar_small': lambda rec: rec['min_fragment_mean']*rec['min_fragment_variance']} # sort desc
        
        digests.sort(key=scoring_key[scoring_function])
        #digests.reverse()
        return digests
    
    def __enzymes_from_form(self):
        # now process either available enzymes or all enzymes
        if not self.form_result['enzymes']:
            enzymes = self.__available_enzymes()
        else:
            enzval = self.form_result['enzymes']
            if enzval == 'NEB' or enzval == 'Fermentas':
                enzymes = self.__vendor_enzymes(enzval)
            elif enzval == 'NEB4':
                enzymes = self.__vendor4_enzymes(enzval[:-1])
            elif enzval == 'All4':
                enzymes = self.__cut4_enzymes()
            else:
                enzymes = []
        
        meth_sensitive = self.form_result.get('allow_methylation', True)
        if not meth_sensitive:
            enzymes = [e for e in enzymes if not e.methylation_sensitivity]
        
        return enzymes
