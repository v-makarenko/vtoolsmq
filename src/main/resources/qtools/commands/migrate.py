import sys

from qtools.components.manager import create_manager
from qtools.constants.job import *
from qtools.messages.sequence import *
from qtools.model import Assay, Session
from qtools.model.sequence import Sequence, SequenceGroup, SequenceGroupComponent
from qtools.model.sequence.util import sequence_group_unlink_sequences

from . import QToolsCommand, DoNotRun, WarnBeforeRunning

@DoNotRun("This should have been run already, should not need to be run again.")
class AssaySequenceGroupMigrate(QToolsCommand):
    summary = "Migrates assays to sequence groups."
    usage   = "paster --plugin=qtools migrate-assay-sequence-group [config]"

    def __populate_common_sequence_group_attributes(self, assay, sequence_group):
        """
        Returns the common shell of a SequenceGroup model from an assay model.
        """
        sequence_group.name             = assay.name
        sequence_group.owner_id         = assay.owner_id
        sequence_group.gene             = assay.gene
        sequence_group.notes            = assay.notes
        sequence_group.reference_source = assay.reference_source
        sequence_group.added            = assay.added

        # only set assay status to retired if rejected
        if assay.rejected:
            sequence_group.status = SequenceGroup.STATUS_TYPE_BORKED
        else:
            sequence_group.status = SequenceGroup.STATUS_TYPE_UNKNOWN

        return sequence_group
    
    def __make_forward_primer_component(self, assay, sequence=None):
        seqc = SequenceGroupComponent(sequence=sequence,
                                      role=SequenceGroupComponent.FORWARD_PRIMER,
                                      barcode_label=SequenceGroupComponent.create_label(assay.name,
                                                        SequenceGroupComponent.FORWARD_PRIMER,
                                                        order=0),
                                      primary=True,
                                      order=0)
        return seqc
    
    def __make_reverse_primer_component(self, assay, sequence=None):
        seqc = SequenceGroupComponent(sequence=sequence,
                                      role=SequenceGroupComponent.REVERSE_PRIMER,
                                      barcode_label=SequenceGroupComponent.create_label(assay.name,
                                                        SequenceGroupComponent.REVERSE_PRIMER,
                                                        order=0),
                                      primary=True,
                                      order=0)
        return seqc
    
    def __make_probe_component(self, assay, sequence=None):
        seqc = SequenceGroupComponent(sequence=sequence,
                                      role=SequenceGroupComponent.PROBE,
                                      barcode_label=SequenceGroupComponent.create_label(assay.name,
                                                        SequenceGroupComponent.PROBE,
                                                        order=0,
                                                        dye=assay.dye,
                                                        quencher=assay.quencher),
                                      primary=True,
                                      order=0,
                                      dye=assay.dye,
                                      quencher=assay.quencher)
        return seqc


    def command(self):
        app = self.load_wsgi_app()
        cm = create_manager(app.config)
        job_queue = cm.jobqueue()

        assays = Session.query(Assay).all()

        # subdivide into assay type and then run different logic for each
        primer_assays = [a for a in assays if a.assay_type == Assay.TYPE_PRIMER]
        snp_assays = [a for a in assays if a.assay_type == Assay.TYPE_SNP]
        location_assays = [a for a in assays if a.assay_type == Assay.TYPE_LOCATION]

        answer = raw_input("This command will delete all existing new-style assays.  Are you sure you want to proceed? (Y/n) ")
        if answer != 'Y':
            sys.exit(0)
        
        sequence_groups = Session.query(SequenceGroup).all()
        for sg in sequence_groups:
            sequence_group_unlink_sequences(sg)
            Session.delete(sg)
            Session.commit()

        for pa in primer_assays:
            print "Processing %s..." % pa.name
            # assume taqman in migration?
            # need to look at actual data structure of primer assay

            # this part is duplicated but I'm ok with that for this
            model = SequenceGroup(id=pa.id)
            self.__populate_common_sequence_group_attributes(pa, model)
        
            model.kit_type = SequenceGroup.TYPE_DESIGNED
            
            if pa.primer_fwd and pa.primer_rev and not pa.probe_seq:
                model.chemistry_type = SequenceGroup.CHEMISTRY_TYPE_SYBR
            else:
                model.chemistry_type = SequenceGroup.CHEMISTRY_TYPE_TAQMAN
            
            if pa.primer_fwd:
                seq = Sequence(sequence=pa.primer_fwd,
                               strand='+')
                
                seqc = self.__make_forward_primer_component(pa, sequence=seq)
                model.forward_primers.append(seqc)
                       
            if pa.primer_rev:
                seq = Sequence(sequence=pa.primer_rev,
                               strand='+')
                
                seqc = self.__make_reverse_primer_component(pa, sequence=seq)
                model.reverse_primers.append(seqc)
            
            if pa.probe_seq:
                seq = Sequence(sequence=pa.probe_seq,
                               strand='+')

                seqc = self.__make_probe_component(pa, sequence=seq)
                model.probes.append(seqc)
            
            # OK now set up the job and commit (same as __start_process_job in sequence controller)
            Session.add(model)
            Session.commit()
            job_queue.add(JOB_ID_PROCESS_ASSAY, ProcessSequenceGroupMessage(model.id))
            print "SG %s added to job queue." % model.id
        
        for sa in snp_assays:
            print "Processing %s..." % sa.name
            model = SequenceGroup(id=sa.id)
            self.__populate_common_sequence_group_attributes(sa, model)

            model.kit_type        = SequenceGroup.TYPE_SNP
            model.snp_rsid        = sa.snp_rsid
            model.amplicon_length = sa.amplicon_width

            # reasonable assumption at this juncture
            model.chemistry_type  = SequenceGroup.CHEMISTRY_TYPE_TAQMAN

            # assume we won't have primers/probes
            fp = self.__make_forward_primer_component(sa)
            rp = self.__make_reverse_primer_component(sa)
            p = self.__make_probe_component(sa)

            model.forward_primers.append(fp)
            model.reverse_primers.append(rp)
            model.probes.append(p)

            Session.add(model)
            Session.commit()
            job_queue.add(JOB_ID_PROCESS_ASSAY, ProcessSequenceGroupMessage(model.id))
            print "SG %s added to job queue." % model.id

        for la in location_assays:
            print "Processing %s..." % la.name
            # same general as above
            # look up if primer sequence group components are stored?
            # location_base, location_chromosome, amplicon_length
            model = SequenceGroup(id=la.id)
            self.__populate_common_sequence_group_attributes(la, model)

            model.kit_type            = SequenceGroup.TYPE_LOCATION
            model.location_base       = la.probe_pos
            model.location_chromosome = la.chromosome
            model.amplicon_length     = sa.amplicon_width

            # reasonable assumption at this juncture
            model.chemistry_type  = SequenceGroup.CHEMISTRY_TYPE_TAQMAN

            # assume we won't have primers/probes
            fp = self.__make_forward_primer_component(la)
            rp = self.__make_reverse_primer_component(la)
            p = self.__make_probe_component(la)

            model.forward_primers.append(fp)
            model.reverse_primers.append(rp)
            model.probes.append(p)

            Session.add(model)
            Session.commit()
            job_queue.add(JOB_ID_PROCESS_ASSAY, ProcessSequenceGroupMessage(model.id))
            print "SG %s added to job queue." % model.id

@WarnBeforeRunning("tM and dG are calculated automatically for assays.  This should be redundant.")
class UpdateAssayTMDGCommand(QToolsCommand):
    summary = "Adds TMs and DGs to assays."
    usage = "paster --plugin=qtools assay-tm-dg [config]"

    def command(self):
        app = self.load_wsgi_app()
        mgr = create_manager(app.config)
        tm_calc = mgr.tm_calc(mgr)
        dg_calc = mgr.dg_calc(mgr)

        sequence_groups = Session.query(SequenceGroup).all()
        for sg in sequence_groups:
            if sg.kit_type == SequenceGroup.TYPE_DESIGNED:    
                print "Updating %s..." % sg.name 
                for fp in sg.forward_primers:
                    fp.tm = tm_calc.tm_primer(fp.sequence.sequence)
                    fp.dg = dg_calc.delta_g(fp.sequence.sequence)
                for rp in sg.reverse_primers:
                    rp.tm = tm_calc.tm_primer(rp.sequence.sequence)
                    rp.dg = dg_calc.delta_g(rp.sequence.sequence)
                for p in sg.probes:
                    if p.quencher and p.quencher.upper() == 'MGB':
                        p.tm = tm_calc.tm_probe(p.sequence.sequence, mgb=True)
                        p.dg = dg_calc.delta_g(p.sequence.sequence)
                    else:
                        p.tm = tm_calc.tm_probe(p.sequence.sequence, mgb=False)
                        p.dg = dg_calc.delta_g(p.sequence.sequence)
            Session.commit()
