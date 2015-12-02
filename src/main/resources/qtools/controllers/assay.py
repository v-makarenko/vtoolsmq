import logging

from pylons import request, response, session, tmpl_context as c, url, config
from pylons.controllers.util import abort, redirect
from pylons.decorators import validate
from pylons.decorators.rest import restrict

import qtools.lib.assay as assayutil
import qtools.lib.fields as fl
import qtools.lib.helpers as h

from qtools.lib.base import BaseController, render
from qtools.lib.bio import reverse_complement
from qtools.lib.dbservice.ucsc import HG19Source
from qtools.lib.deltag import dg_assay, dg_seq, dg_pcr_sequence
from qtools.lib.tm import tm_assay, tm_probe, tm_pcr_sequence
from qtools.lib.validators import PrimerSequence, Chromosome, SNPName, Strand, DNASequence
from qtools.lib.validators import KeyValidator, UniqueKeyValidator, IntKeyValidator, NullableStringBool
from qtools.lib.webservice.ucsc import UCSCSequenceSource

from qtools.model import Session, Assay, HG19AssayCache, SNP131AssayCache, Person, Plate
from qtools.model import Enzyme, EnzymeConcentration
from qtools.model.sequence import Sequence

import formencode
from formencode import htmlfill
from formencode.variabledecode import NestedVariables
import urllib

log = logging.getLogger(__name__)

class SNPForm(formencode.Schema):
    allow_extra_fields = True
    filter_extra_fields = True
    
    bin = formencode.validators.Int(min=0)
    chrom = formencode.validators.String(not_empty=True)
    chromStart = formencode.validators.Int(not_empty=True)
    chromEnd = formencode.validators.Int(not_empty=True)
    name = formencode.validators.String(not_empty=True)
    score = formencode.validators.Int()
    strand = Strand(not_empty=True)
    refNCBI = formencode.validators.String()
    refUCSC = formencode.validators.String(not_empty=True)
    observed = formencode.validators.String(not_empty=True)
    
    # TODO, these 3 are enums
    molType = formencode.validators.String()
    class_ = formencode.validators.String(not_empty=True)
    valid = formencode.validators.String()
    avHet = formencode.validators.Number()
    avHetSE = formencode.validators.Number()
    # TODO, these 2 are enums
    func = formencode.validators.String()
    locType = formencode.validators.String()
    weight = formencode.validators.Int()

class SequenceForm(formencode.Schema):
    allow_extra_fields = True
    filter_extra_fields = True
    pre_validators = [NestedVariables()]
    
    chromosome = Chromosome()
    start_pos = formencode.validators.Int(min=1)
    end_pos = formencode.validators.Int(min=1)
    # TODO: ensure start_pos <= end_pos
    
    padding_pos5 = formencode.validators.Int(min=0, if_missing=0)
    padding_pos3 = formencode.validators.Int(min=0, if_missing=0)
    positive_sequence = DNASequence(if_missing=None)
    negative_sequence = DNASequence(if_missing=None)
    strand = Strand()
    snps = formencode.foreach.ForEach(SNPForm())

class AssayForm(formencode.Schema):
    allow_extra_fields = True
    filter_extra_fields = True
    pre_validators = [NestedVariables()]
    
    name = formencode.validators.Regex(r'[\w\-]+', not_empty=True)
    gene = formencode.validators.String(if_missing=None)
    owner_id = IntKeyValidator(Person, "id", not_empty=False)
    primer_fwd = PrimerSequence(if_missing=None)
    primer_rev = PrimerSequence(if_missing=None)
    chromosome = Chromosome(if_missing=None)
    probe_pos = formencode.validators.Int(min=0, if_missing=None)
    probe_seq = DNASequence(if_missing=None)
    dye = formencode.validators.String(if_missing=None)
    quencher = formencode.validators.String(if_missing=None)
    amplicon_width = formencode.validators.Int(min=1, if_missing=None)
    snp_rsid = SNPName(if_missing=None)
    seq_padding_pos5 = formencode.validators.Int(min=0, if_missing=1000)
    seq_padding_pos3 = formencode.validators.Int(min=0, if_missing=1000)
    sequences = formencode.foreach.ForEach(SequenceForm())

    secondary_structure = NullableStringBool(not_empty=False)
    notes = formencode.validators.String(not_empty=False)
    reference_source = formencode.validators.String(not_empty=False)
    optimal_anneal_temp = formencode.validators.Number(not_empty=False)

class SaveAssayForm(formencode.Schema):
    allow_extra_fields = True
    filter_extra_fields = True
    
    # TODO figure out a way to field-level handle IntegrityError
    name = formencode.validators.Regex(r'[\w\-]+', not_empty=True)
    gene = formencode.validators.String(if_missing=None)
    owner_id = IntKeyValidator(Person, "id", not_empty=False)
    primer_fwd = PrimerSequence(if_missing=None)
    primer_rev = PrimerSequence(if_missing=None)
    chromosome = Chromosome(if_missing=None)
    probe_pos = formencode.validators.Int(min=0, if_missing=None)
    probe_seq = DNASequence(if_missing=None)
    dye = formencode.validators.String(if_missing=None)
    quencher = formencode.validators.String(if_missing=None)
    amplicon_width = formencode.validators.Int(min=0, if_missing=None)
    snp_rsid = SNPName(if_missing=None)

    secondary_structure = NullableStringBool(not_empty=False)
    notes = formencode.validators.String(not_empty=False)
    reference_source = formencode.validators.String(not_empty=False)
    optimal_anneal_temp = formencode.validators.Number(not_empty=False)

class AssaySequenceForm(formencode.Schema):
    allow_extra_fields = True
    filter_extra_fields = True
    
    assay_id = formencode.validators.Int(not_empty=True)


class PrimerSequenceForm(formencode.Schema):
    allow_extra_fields = True
    filter_extra_fields = True
    
    primer_fwd = PrimerSequence(not_empty=True)
    primer_rev = PrimerSequence(not_empty=True)


class LocationSequenceForm(formencode.Schema):
    allow_extra_fields = True
    filter_extra_fields = True
    
    chromosome = Chromosome(not_empty=True)
    location = formencode.validators.Int(min=0, not_empty=True)
    width = formencode.validators.Int(min=1, not_empty=True)


class SNPSequenceForm(formencode.Schema):
    allow_extra_fields = True
    filter_extra_fields = True
    
    snp_rsid = SNPName(not_empty=True)
    width = formencode.validators.Int(min=1, not_empty=True)


class EnzymeConcentrationForm(formencode.Schema):
    allow_extra_fields = True
    filter_extra_fields = True
    
    enzyme_id = KeyValidator(Enzyme, 'name', not_empty=True)
    assay_id = IntKeyValidator(Assay, 'id', not_empty=True)
    minimum_conc = formencode.validators.Number(not_empty=False, if_missing=None)
    maximum_conc = formencode.validators.Number(not_empty=False, if_missing=None)
    source_plate_id = IntKeyValidator(Plate, 'id', not_empty=False, if_missing=None)
    author_id = IntKeyValidator(Person, 'id', not_empty=True)
    notes = formencode.validators.String(not_empty=False)

    

class AssayController(BaseController):

    def __before__(self):
        if not h.wowo('show_assays'):
            abort(403)
    
    def new(self):
        dye_field = fl.assay_dye_field()
        quencher_field = fl.assay_quencher_field()
        owner_field = fl.person_field()
        secondary_structure = fl.tertiary_field()
        c.form = h.LiteralFormSelectPatch(
            value = {'dye': dye_field['value'],
                     'quencher': quencher_field['value'],
                     'owner_id': owner_field['value'],
                     'secondary_structure': secondary_structure['value']},
            option = {'chromosome': [('','--')] + [(chr, chr) for chr in Chromosome.chrom_list],
                      'owner_id':[('','--')]+owner_field['options'],
                      'dye': dye_field['options'],
                      'quencher': quencher_field['options'],
                      'secondary_structure': secondary_structure['options']}
        )
        
        return render('/assay/new.html')
    
    def list(self):
        """
        TODO: add pagination if necessary
        """
        show_blanks = request.params.get('blank', False)
        if show_blanks:
            assay_q = Session.query(Assay)
        else:
            assay_q = Assay.populated_valid_query(Session)
        c.assays = assay_q.order_by(Assay.name).all()
        assay_field = fl.assay_field(empty='', include_empties=show_blanks, blank=True)
        c.assay_form = h.LiteralFormSelectPatch(
          value = {'assay_id': assay_field['value']},
          option = {'assay_id': assay_field['options']}
        )
        return render('/assay/list.html')
    
    def edit(self, id):
        """
        Edits an assay.
        """
        assay_q = Session.query(Assay)
        assay = assay_q.filter_by(id=id).first()
        dye_field = fl.assay_dye_field(assay.dye)
        quencher_field = fl.assay_quencher_field(assay.quencher)
        secondary_structure = fl.tertiary_field(assay.secondary_structure)

        if assay is None:
            abort(404)
        else:
            c.assay = assay
        
        owner_field = fl.person_field(c.assay.owner_id)
        c.form = h.LiteralFormSelectPatch(
            value = {'dye': dye_field['value'],
                     'quencher': quencher_field['value'],
                     'owner_id': unicode(owner_field['value']),
                     'secondary_structure': secondary_structure['value']},
            option = {'chromosome': [('','--')] + [(chr, chr) for chr in Chromosome.chrom_list],
                      'owner_id': owner_field['options'],
                      'dye': dye_field['options'],
                      'quencher': quencher_field['options'],
                      'secondary_structure': secondary_structure['options']}
        )
        values = {'name': assay.name,
                  'gene': assay.gene,
                  'owner_id': unicode(assay.owner_id),
                  'primer_fwd': assay.primer_fwd,
                  'primer_rev': assay.primer_rev,
                  'chromosome': assay.chromosome,
                  'probe_pos': assay.probe_pos,
                  'probe_seq': assay.probe_seq,
                  'dye': assay.dye,
                  'quencher': assay.quencher,
                  'secondary_structure': secondary_structure['value'],
                  'amplicon_width': assay.amplicon_width,
                  'snp_rsid': assay.snp_rsid,
                  'notes': assay.notes,
                  'reference_source':assay.reference_source,
                  'optimal_anneal_temp':assay.optimal_anneal_temp}
        
        if assay.assay_type == Assay.TYPE_LOCATION:
            c.selectedTab = 1
        elif assay.assay_type == Assay.TYPE_SNP:
            c.selectedTab = 2
        else:
            c.selectedTab = 0
        return htmlfill.render(render('/assay/edit.html'), values)
    
    @restrict('POST')
    def reject(self, id=None):
        if id is None:
            abort(404)
        
        assay = Session.query(Assay).get(id)
        if not assay:
            abort(404)
        
        assay.rejected = True
        Session.commit()
        session['flash'] = 'Assay marked as invalid.'
        session.save()
        redirect(url(controller='assay', action='view', id=id))
    
    @restrict('POST')
    def unreject(self, id=None):
        if id is None:
            abort(404)
        
        assay = Session.query(Assay).get(id)
        if not assay:
            abort(404)
        
        assay.rejected = False
        Session.commit()
        session['flash'] = 'Assay marked as valid.'
        session.save()
        redirect(url(controller='assay', action='view', id=id))
        
    @restrict('POST')
    @validate(schema=AssayForm(), form='new')
    def create(self):
        assay = Assay()
        for k, v in self.form_result.items():
            if k not in ('seq_padding_pos5', 'seq_padding_pos3', 'sequences'):
                setattr(assay, k, v)
        
        # avoids double lookup if lookup has already been done
        if self.form_result['sequences']:
            # add 1000-padding sequence and snps to each.
            seq_source = UCSCSequenceSource()
            snp_source = HG19Source()
        
            for seq in self.form_result['sequences']:
                # TODO: just call sequences_for_assay here?  logic the same.
                if not seq['positive_sequence'] or seq['negative_sequence']:
                    sequence = seq_source.sequence(seq['chromosome'],
                                                   seq['start_pos']-self.form_result['seq_padding_pos5'],
                                                   seq['end_pos']+self.form_result['seq_padding_pos3'])
                    
                    cache_rec = HG19AssayCache(chromosome = sequence.chromosome,
                                               start_pos = seq['start_pos'],
                                               end_pos = seq['end_pos'],
                                               seq_padding_pos5 = self.form_result['seq_padding_pos5'],
                                               seq_padding_pos3 = self.form_result['seq_padding_pos3'],
                                               positive_sequence = sequence.positive_strand_sequence)
                else:
                    cache_rec = HG19AssayCache(chromosome = seq['chromosome'],
                                               start_pos = seq['start_pos'],
                                               end_pos = seq['end_pos'],
                                               seq_padding_pos5 = seq['padding_pos5'],
                                               seq_padding_pos3 = seq['padding_pos3'],
                                               positive_sequence = seq['positive_sequence'] or None,
                                               negative_sequence = seq['negative_sequence'] or None)
                
                for snp in seq['snps']:
                    cache_rec.snps.append(SNP131AssayCache(bin=snp['bin'],
                                                           chrom=snp['chrom'],
                                                           chromStart=snp['chromStart'],
                                                           chromEnd=snp['chromEnd'],
                                                           name=snp['name'],
                                                           score=snp['score'],
                                                           strand=snp['strand'],
                                                           refNCBI=snp['refNCBI'],
                                                           refUCSC=snp['refUCSC'],
                                                           observed=snp['observed'],
                                                           molType=snp['molType'],
                                                           class_=snp['class_'],
                                                           valid=snp['valid'],
                                                           avHet=snp['avHet'],
                                                           avHetSE=snp['avHetSE'],
                                                           func=snp['func'],
                                                           locType=snp['locType'],
                                                           weight=snp['weight']))
                
                assay.cached_sequences.append(cache_rec)
        
        
        Session.add(assay)
        self.__update_tms(assay)


        Session.commit()
        redirect(url(controller='assay', action='view', id=assay.id))
    
    @restrict('POST')
    def delete(self, id=None):
        """
        """
        if id is None:
            abort(404)
        assay_q = Session.query(Assay)
        assay = assay_q.filter_by(id=id).first()
        if assay:
            Session.delete(assay)
        Session.commit()
        session['flash'] = 'Assay deleted.'
        session.save()
        redirect(url(controller='assay', action='list'))
    
    @restrict('POST')
    @validate(schema=SaveAssayForm(), form='edit')
    def save(self, id=None):
        """
        """
        if id is None:
            abort(404)
        assay_q = Session.query(Assay)
        assay = assay_q.filter_by(id=id).first()
        if assay is None:
            abort(404)
        
        reload_sequences = False
        for k, v in self.form_result.items():
            if k in ('primer_fwd', 'primer_rev', 'chromosome', 'probe_pos', 'amplicon_width', 'snp_rsid'):
                if getattr(assay, k) != v:
                    reload_sequences = True
            if k not in ('id'):
                setattr(assay, k, v)
        
        # blow away previous sequences; on view, this will update.
        if reload_sequences:
            cached_sequences = assay.cached_sequences
            for i in range(len(cached_sequences)):
                cs = cached_sequences[-1]
                snps = cs.snps
                for j in range(len(snps)):
                    snp = snps.pop()
                    Session.delete(snp)
                cached_sequences.pop()
                Session.delete(cs)
        
        self.__update_tms(assay)
        
        Session.commit()
        session.save()
        redirect(url(controller='assay', action='view', id=assay.id))
    
    
    def primer(self):
        c.form = h.LiteralForm()
        return render('/assay/primer.html')
    
    def view(self, id):
        sequences = []
        assay = Session.query(Assay).filter_by(id=id).first()
        if not assay:
            abort(404)
        
        seq_source = UCSCSequenceSource()
        snp_source = HG19Source()
        sequences = assayutil.sequences_snps_for_assay(config, assay, seq_source, snp_source, 1000, 1000)
        
        c.sequences = [tm_pcr_sequence(config, dg_pcr_sequence(config, seq)) for seq in sequences]
        assayutil.set_amplicon_snps(c.sequences)
        
        if assay.assay_type == Assay.TYPE_PRIMER:
            for seq in c.sequences:
                self.__add_sequence_primer_display_attrs(seq, assay=assay)
        else:
            for seq in c.sequences:
                seq.positive_display_sequence = seq.amplicon.positive_strand_sequence.lower()
                seq.negative_display_sequence = seq.amplicon.negative_strand_sequence.lower()[::-1]
        
        c.assay = assay
        c.hide_save = True
        return render('/assay/view.html')
                        
    
    @restrict('POST')
    @validate(schema=PrimerSequenceForm(), form='primer')
    def process_primer(self):
        source = UCSCSequenceSource()
        left_padding = 1000
        right_padding = 1000
        sequences = source.sequences_for_primers(self.form_result['primer_fwd'],
                                                 self.form_result['primer_rev'],
                                                 left_padding, right_padding)
        
        # TODO: better selective update method
        c.primer_fwd = self.form_result['primer_fwd']
        c.primer_rev = self.form_result['primer_rev']
        c.left_padding = left_padding
        c.right_padding = right_padding
        c.sequences = sequences
        
        for seq in c.sequences:
            seq.snps = self._get_snps(seq.chromosome, seq.start, seq.end)
            self.__add_sequence_primer_display_attrs(seq, primer_fwd=self.form_result['primer_fwd'], primer_rev=self.form_result['primer_rev'])
        
        assayutil.set_amplicon_snps(c.sequences)
        
        c.assay_form = h.LiteralForm(
            value = {
                'primer_fwd': self.form_result['primer_fwd'],
                'primer_rev': self.form_result['primer_rev']
            }
        )
        
        return render('/assay/primer_output.html')
    
    def location(self):
        c.form = h.LiteralForm(
            option = {'chromosome': [(chr, chr) for chr in Chromosome.chrom_list]}
        )
        return render('/assay/location.html')
    
    @restrict('POST')
    @validate(schema=LocationSequenceForm(), form='location')
    def process_location(self):
        source = UCSCSequenceSource()
        left_padding = 1000
        right_padding = 1000
        sequence = source.sequence_around_loc(self.form_result['chromosome'],
                                              self.form_result['location'],
                                              self.form_result['width'],
                                              left_padding, right_padding)
        # TODO: better selective update method
        c.chromosome = self.form_result['chromosome']
        c.location = self.form_result['location']
        c.width = self.form_result['width']
        c.left_padding = left_padding
        c.right_padding = right_padding
        c.sequence = sequence
        c.sequences = [sequence]
        
        for seq in c.sequences:
            seq.snps = self._get_snps(seq.chromosome, seq.start, seq.end)
            seq.positive_display_sequence = seq.amplicon.positive_strand_sequence.lower()
            seq.negative_display_sequence = seq.amplicon.negative_strand_sequence.lower()
        
        assayutil.set_amplicon_snps(c.sequences)
        
        c.assay_form = h.LiteralForm()
        return render('/assay/location_output.html')
    
    def snp(self):
        c.form = h.LiteralForm()
        return render('/assay/snp.html')
    
    @restrict('POST')
    @validate(schema=SNPSequenceForm(), form='snp')
    def process_snp(self):
        snp_source = HG19Source()
        seq_source = UCSCSequenceSource()
        left_padding = 1000
        right_padding = 1000
        snps = snp_source.snps_by_rsid(self.form_result['snp_rsid'])
        
        c.assay_form = h.LiteralForm()
        
        c.snp_rsid = self.form_result['snp_rsid']
        c.width = self.form_result['width']
        
        # override
        if not snps or len(snps) == 0:
            # TODO: figure out how to make this appear on the field error instead
            session['flash'] = "Could not find a SNP with the name %s" % self.form_result['snp_rsid']
            session['flash_class'] = 'error'
            session.save()
            return render('/assay/snp_output.html')
        
        sequences = []
        for snp in snps:
            chromStart = snp['chromStart']
            chromEnd = snp['chromEnd']
        
            # handle insertions and single variations, normally the chromStart
            # refers to the gap just before the base # 
            if snp['chromStart'] == snp['chromEnd']:
                chromStart = chromEnd
            else:
                chromStart += 1
        
            sequence = seq_source.sequence_around_region(snp['chrom'][3:],
                                                         chromStart,
                                                         chromEnd,
                                                         self.form_result['width'], left_padding, right_padding)
            #sequence.snps = self._get_snps(sequence.chromosome, sequence.start, sequence.end)
            sequences.append(sequence)
        
        c.left_padding = left_padding
        c.right_padding = right_padding
        c.sequences = sequences
        for seq in c.sequences:
            seq.snps = self._get_snps(seq.chromosome, seq.start, seq.end)
            seq.positive_display_sequence = seq.amplicon.positive_strand_sequence.lower()
            seq.negative_display_sequence = seq.amplicon.negative_strand_sequence.lower()[::-1]
        
        assayutil.set_amplicon_snps(c.sequences)
        
        return render('/assay/snp_output.html')
    
    def enzyme_conc_new(self):
        enzyme_field = fl.enzyme_field()
        assay_field = fl.assay_field(blank=True, empty='', selected=request.params.get('assay_id', None))
        author_field = fl.person_field()

        c.plate = None
        if request.params.get('plate_id', None):
            plate = Session.query(Plate).get(int(request.params.get('plate_id')))
            if plate:
                c.plate = plate
        
        c.form = h.LiteralFormSelectPatch(
            value = {'enzyme_id': enzyme_field['value'],
                     'assay_id': assay_field['value'],
                     'author_id': author_field['value']},
            option = {'enzyme_id': enzyme_field['options'],
                      'assay_id': assay_field['options'],
                      'author_id': author_field['options']}
        )

        return render('/assay/enzyme/new.html')
    
    @restrict('POST')
    @validate(schema=EnzymeConcentrationForm(), form='enzyme_conc_new')
    def enzyme_conc_create(self):
        conc = EnzymeConcentration()

        for k, v in self.form_result.items():
            setattr(conc, k, v)
        
        Session.add(conc)
        Session.commit()

        redirect(url(controller='assay', action='view', id=self.form_result['assay_id']))
    
    def enzyme_conc_edit(self, id=None):
        if id is None:
            abort(404)
        
        conc = Session.query(EnzymeConcentration).get(id)
        if not conc:
            abort(404)
        
        c.conc = conc
        
        enzyme_field = fl.enzyme_field(selected=unicode(conc.enzyme_id))
        assay_field = fl.assay_field(blank=True, selected=unicode(conc.assay.id))
        author_field = fl.person_field(selected=unicode(conc.author_id))
        c.plate = None
        c.form = h.LiteralFormSelectPatch(
            value = {'enzyme_id': enzyme_field['value'],
                     'assay_id': assay_field['value'],
                     'author_id': author_field['value'],
                     'minimum_conc': conc.minimum_conc,
                     'maximum_conc': conc.maximum_conc,
                     'source_plate_id': conc.source_plate_id,
                     'notes': conc.notes},
            option = {'enzyme_id': enzyme_field['options'],
                      'assay_id': assay_field['options'],
                      'author_id': author_field['options']}
        )
        return render('/assay/enzyme/edit.html')
    
    @restrict('POST')
    @validate(schema=EnzymeConcentrationForm(), form='enzyme_conc_edit')
    def enzyme_conc_save(self, id=None):
        if id is None:
            abort(404)
        
        conc = Session.query(EnzymeConcentration).get(id)
        if not conc:
            abort(404)
        
        for k, v in self.form_result.items():
            if k not in ('id',):
                setattr(conc, k, v)
            
        Session.commit()
        redirect(url(controller='assay', action='view', id=self.form_result['assay_id']))
    
    @restrict('POST')
    def enzyme_conc_delete(self, id=None):
        if id is None:
            abort(404)
        
        conc = Session.query(EnzymeConcentration).get(id)
        if not conc:
            abort(404)
        
        assay_id = conc.assay_id
        Session.delete(conc)
        Session.commit()

        redirect(url(controller='assay', action='view', id=assay_id))


    
    def _get_snps(self, chrom, start, end):
        snp_source = HG19Source()
        snps = snp_source.snps_in_range(chrom, start, end)
        return snps
    
    def __add_sequence_primer_display_attrs(self, seq, **kwargs):
        assay = kwargs.get('assay', None)
        if assay:
            primer_fwd = assay.primer_fwd
            primer_rev = assay.primer_rev
            probe_seq = assay.probe_seq
        else:
            primer_fwd = kwargs.get('primer_fwd', None)
            primer_rev = kwargs.get('primer_rev', None)
            probe_seq = kwargs.get('probe_seq', None)
        
        posq = seq.amplicon.positive_strand_sequence
        negq = seq.amplicon.negative_strand_sequence
        
        posf = posq.find(primer_fwd)
        posn = posq.find(reverse_complement(primer_rev))
        
        if posf != -1:
            posq = "%s%s%s" % (posq[:len(primer_fwd)], posq[len(primer_fwd):posn].lower(), posq[posn:])
            negq = negq.lower()
        else:
            negf = negq.find(primer_fwd)
            negn = negq.find(reverse_complement(primer_rev))
            
            negq = "%s%s%s" % (negq[:len(primer_fwd)], negq[len(primer_fwd):negn].lower(), negq[negn:])
            posq = posq.lower()
        
        if probe_seq:
            posp = posq.upper().find(reverse_complement(probe_seq))
            negp = negq.upper().find(reverse_complement(probe_seq))
            
            if posp != -1:
                #raise Exception, posq
                posq = "%s|%s|%s" % (posq[:posp], posq[posp:posp+len(probe_seq)], posq[posp+len(probe_seq):])
            elif negp != -1:
                negq = "%s|%s|%s" % (negq[:negp], negq[negp:negp+len(probe_seq)], negq[negp+len(probe_seq):])
            
        seq.positive_display_sequence = posq
        seq.negative_display_sequence = negq[::-1]
        return seq
    
    def __update_tms(self, assay):
        # check assay type
        if assay.assay_type == Assay.TYPE_PRIMER:
            # add tm, dg
            assay.forward_primer_tm, assay.reverse_primer_tm, assay.probe_tm = tm_assay(config, assay)
            assay.forward_primer_dG, assay.reverse_primer_dG, assay.probe_dG = dg_assay(config, assay)