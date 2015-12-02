"""
Classes and methods for determining whether a plate meets
predetermined metrics specifications.

Many of the classes here are basically view UI objects, which
extract wells and well statistics from collections of one or
more plates.

This file has gotten increasingly brittle over time, but is
still used vitally in manufacturing validation.
"""
import numpy as np
import math
from collections import defaultdict
from qtools.constants import HEX_SCALE_FACTOR
from qtools.lib.nstats import percentile
from qtools.lib.metrics.mixedplate import well_plate_type_code
from qtools.model import Session, AnalysisGroup, Plate, PlateType, PlateMetric, WellMetric
from qtools.model import SystemVersion, WellChannelMetric, Plate, QLBWell, analysis_group_plate_table
from sqlalchemy.orm import joinedload_all
from sqlalchemy import select, and_, not_, or_
from pylons import config

NONEVENT_SAMPLE_NAMES = ('stealth', 'Stealth', None, '', 'HEX 500nM', 'HEX 100nM')
EXPECTED_LOW_EVENT_WELLS = ('stealth', 'Stealth', None, '')

class AnalysisGroupMetrics(object):
    """
    Looks at an AnalysisGroup object and extracts which
    plates/wells do not meet spec, and calculates aggregate
    metrics over plates in the analysis group.
    """
    def __init__(self, analysis_group_id, reprocess_config_id=None, **kwargs):
        self.reprocess_config_id = reprocess_config_id
    
        plate_ids = Session.execute(select([analysis_group_plate_table.c.plate_id]).where(analysis_group_plate_table.c.analysis_group_id==analysis_group_id)).fetchall()
        plate_ids = [p[0] for p in plate_ids]

        pm = Session.query(PlateMetric).filter(and_(PlateMetric.reprocess_config_id==(reprocess_config_id or None),
                                                    PlateMetric.plate_id.in_(plate_ids)))\
                    .options(joinedload_all(PlateMetric.plate, Plate.plate_type),
                         joinedload_all(PlateMetric.plate, Plate.box2, innerjoin=True),
                             joinedload_all(PlateMetric.well_metrics, WellMetric.well_channel_metrics, WellChannelMetric.well_channel, innerjoin=True),
                             joinedload_all(PlateMetric.well_metrics, WellMetric.well, QLBWell.plate, innerjoin=True)).all()

        self.plate_filter = kwargs.get('plate_filter', lambda p: p)
        self.plate_type_filter = kwargs.get('plate_type_filter', lambda pt: True)
        self.well_filter = kwargs.get('well_filter', lambda w: w)
        self.well_metric_filter = kwargs.get('well_metric_filter', lambda wm: wm)

        if ( len( pm ) and pm[-1].plate.qlbplate.system_version is not None ):
            sv_id = pm[-1].plate.qlbplate.system_version
            self.system_version = Session.query(SystemVersion).get(sv_id).type
        else:
            self.system_version = 'QX100';

        if pm: #added by Richard
            self.program_version = pm[0].plate.program_version 
        else:
            self.program_version = None

        ## make param loading generic...
        self.load_config_params( code=self.system_version, **kwargs )

        self.all_plate_metrics = [p for p in pm if self.plate_filter(p.plate) and self.plate_type_filter(p.plate.plate_type)]
        self.metric_plates = [pm.plate for pm in self.all_plate_metrics]

    def load_config_params( self, code='QX100', **kwargs):
        """ load system specfic parameteres
        param: code = system version type
        """
        
        #Added by Richard for checking between Quantasoft Versions
        if self.program_version != None:
            version = self.program_version.split()[1].split('.')
            if len(version) > 2:
                if int(version[0]) == 1:
                    if int(version[1]) >= 7:
                        code = code+'.new'
                    else:
                        code = code+'.old'

        ## Probes event count mins
        if ( kwargs.get('low_event_count') is not None ):
            self.low_event_count = kwargs.get('low_event_count')
        else :
            self.low_event_count = int( config.get( code + '.low_event_count', 12000 ) )

        ## Eva event count mins
        if ( kwargs.get('low_event_count_eva') is not None ):
            self.low_event_count_eva = kwargs.get('low_event_count_eva')
        else :
            self.low_event_count_eva = int( config.get( code + '.low_event_count_eva', 12000 ) )

        if ( kwargs.get('low_data_quality') is not None ):
            self.low_data_quality = kwargs.get('low_data_quality')
        else:
            self.low_data_quality = float( config.get( code +'.low_data_quality', 0.85) )

        if ( kwargs.get('accepted_event_cutoff') is not None ):
            self.accepted_event_cutoff = kwargs.get('accepted_event_cutoff')
        else:
            self.accepted_event_cutoff = int( config.get(code + '.accepted_event_cutoff', 1000) )

        self.low_event_fail_numerator = int(   config.get( code + '.low_event_fail_numerator', 1 ) )
        self.low_event_fail_denominator = float( config.get( code + '.low_event_fail_denominator', 48 ) )

        self.ncc_low_event_fail_numerator = int(   config.get( code + '.ncc_low_event_fail_numerator', 1 ) )
        self.ncc_low_event_fail_denominator = float( config.get( code + '.ncc_low_event_fail_denominator', 48 ) )

        self.probe_event_fail_numerator = int(   config.get( code + '.probe_event_fail_numerator', 1 ) )
        self.probe_event_fail_denominator = float( config.get( code + '.probe_event_fail_denominator', 48 ) )

        self.eva_event_fail_numerator = int(   config.get( code + '.eva_event_fail_numerator', 0 ) )
        self.eva_event_fail_denominator = float( config.get( code + '.eva_event_fail_denominator', 1 ) )

        self.cc_low_event_fail_numerator = int(   config.get( code + '.cc_low_event_fail_numerator', 0 ) )
        self.cc_low_event_fail_denominator = float( config.get( code + '.cc_low_event_fail_denominator', 4 ) )

        ## carry over stats
        self.low_quality_fail_numerator = int(   config.get( code + '.low_quality_fail_numerator', 1 ) )
        self.low_quality_fail_denominator = float( config.get( code + '.low_quality_fail_denominator', 48 ) )

        self.SingUniformityPct = int( config.get( code + '.SingUniformityPct', 20 ) )

        self.carryover_per_n_wells  = int(config.get( code + '.carryover_per_n_wells', 2 ))
        self.carryover_n_wells      = int(config.get( code + '.carryover_n_wells', 8 ))

        ## color call statas
        self.FamAmp350 = int( config.get(code + '.FamAmp350', 20000 ) )
        self.VicAmp350 = int( config.get(code + '.VicAmp350', 10000 ) )
        self.HexAmp350 = int( config.get(code + '.HexAmp350', 8100 ) )

        self.FamAmpLo  = int( config.get(code + '.FamAmpLo', 2285 ) )
        self.VicAmpLo  = int( config.get(code + '.VicAmpLo', 2000 ) )
        self.HexAmpLo  = int( config.get(code + '.HexAmpLo', 1620 ) )

        self.Ch1AmpCV = float( config.get( code + '.Ch1AmpCV', 0.045 ) )
        self.Ch2AmpCV = float( config.get( code + '.Ch2AmpCV', 0.045 ) )

        self.Ch1AmpVariationPct     = int( config.get(code + '.Ch1AmpVariationPct', 10 ) )
        self.Ch1AmpVariationPctQC   = int( config.get(code + '.Ch1AmpVariationPctQC', 5 ) )
        self.Ch2AmpVariationPct     = int( config.get(code + '.Ch2AmpVariationPct', 10 ) )
        self.Ch2AmpVariationPctQC   = int( config.get(code + '.Ch2AmpVariationPctQC', 5 ) )
        self.HEXAmpLoVariationPctQC = int( config.get(code + '.HEXAmpLoVariationPctQC', 20 ) ) 

        if ( config.get( code +'.WidthMean', None) is not None and float( config.get( code + '.WidthMean', None)) > 0):
            widthMean         = float(config.get( code + '.WidthMean', 1)) 
            widthVariationPct = float(config.get( code + '.WidthVariationPct', 0))/100.0
            
            self.WidthGateMin = round( widthMean * (1.0-widthVariationPct), 2)
            self.WidthGateMax = round( widthMean * (1.0+widthVariationPct), 2)
        else:
            self.WidthGateMin = float( config.get(code + '.WidthGateMin', 8 ))
            self.WidthGateMax = float( config.get(code + '.WidthGateMax', 10 ))

        self.QCMaxPolydispersitiy = float(config.get(code + '.QCMaxPolydispersitiy', 0.15 ))
        self.MaxPolydispersitiy   = float(config.get(code + '.MaxPolydispersitiy', 0.30 ))

        self.DeltaWidthToleranceMax = float( config.get(code + '.DeltaWidthToleranceMax', 0.5 )) 
        self.DeltaWidthToleranceMin = float( config.get(code + '.DeltaWidthToleranceMin', -0.5 )) 

        self.QCDeltaWidthToleranceMax = float( config.get(code + '.QCDeltaWidthToleranceMax', 0.4 ))
        self.QCDeltaWidthToleranceMin = float( config.get(code + '.QCDeltaWidthToleranceMin', -0.4 ))

    def plate_metrics_by_plate_type(self, code):
        """
        Return the set of plate metric objects in this collection by
        the specified plate type code (PlateType.code)

        :rtype: PlateMetric[]
        """
        if not isinstance(code, basestring):
            return [pm for pm in self.all_plate_metrics if pm.plate.plate_type_code in code and self.plate_filter(pm.plate)]
        else:
            return [pm for pm in self.all_plate_metrics if pm.plate.plate_type_code == code and self.plate_filter(pm.plate)]

    @property
    def all_well_metrics(self):
        """
        Return all WellMetric objects in the group.

        :rtype: WellMetric[]
        """
        return [w for p in self.all_plate_metrics for w in p.well_metrics if (self.well_metric_filter(w) and self.well_filter(w.well))]

    def well_metrics_by_type(self, code):
        """
        Return the set of WellMetric objects in this group that belong to plates
        with the specified code.

        :param code: A single code or list of PlateType codes.
        :rtype: WellMetric[]
        """
        if not isinstance(code, basestring):
            wells = [w for w in self.all_well_metrics if w.plate_metric.plate.plate_type_code in code]
            wells.extend([w for w in self.all_well_metrics if w.plate_metric.plate.is_auto_validation_plate and well_plate_type_code(w.well) in code])
        else:
            wells = [w for w in self.all_well_metrics if w.plate_metric.plate.plate_type_code == code]
            wells.extend([w for w in self.all_well_metrics if w.plate_metric.plate.is_auto_validation_plate and well_plate_type_code(w.well) == code])
        return wells

    def well_metrics_excluding_type(self, code):
        """
        Return the set of WellMetric objects in this group except for those belonging
        to plates with the specified code (or codes)

        :param code: A single PlateType.code or sequence of codes
        :rtype: WellMetric[]
        """
        if not isinstance(code, basestring):
            wells = [w for w in self.all_well_metrics if w.plate_metric.plate.plate_type_code not in code]
            wells.extend([w for w in self.all_well_metrics if w.plate_metric.plate.is_auto_validation_plate and well_plate_type_code(w.well) not in code])
        else:
            wells = [w for w in self.all_well_metrics if w.plate_metric.plate.plate_type_code != code]
            wells.extend([w for w in self.all_well_metrics if w.plate_metric.plate.is_auto_validation_plate and well_plate_type_code(w.well) != code])
        return wells

    def well_metrics_by_type_sample(self, code, sample):
        """
        Return the set of WellMetric objects in this group that belong to plates with the specified
        code, and have the specified sample name (or names)

        :param code: A single PlateType.code or sequence of codes
        :param sample: A single sample name or list of names
        :rtype: WellMetric[]
        """
        if not isinstance(sample, basestring):
            return [w for w in self.well_metrics_by_type(code) if w.well.sample_name in sample]
        else:
            return [w for w in self.well_metrics_by_type(code) if w.well.sample_name == sample]

    def well_metrics_by_target(self, well_metrics, target, channel_num=0):
        """
        Return the set of WellMetric objects in this group that have the target specified
        :param well_metrics:  a list of wellmetrics
        :param target: A single channel target
        :param: channel_num 
        :rtype: WellMetric[]
        """
        
        return [w for w in well_metrics if w.well.channels[channel_num].target == target ]

    def targets(self, well_metrics, channel_num ):
        """
        Return the set of targets in the WellMetric objects specified
        :param well_metrics:  a list of wellmetrics
        :param: channel_num 
        :rtype: [str]
        """
        targetList = list();
        for w in well_metrics:
            target = w.well.channels[channel_num].target
            if ( target not in targetList ):
                targetList.append(target)
        return targetList

    @staticmethod
    def eventful(well_metrics, event_count=0):
        """
        Returns the list of well metrics from the list that have greater than
        event_count accepted events.

        :param well_metrics: WellMetric[]
        :param event_count: int
        :rtype: WellMetric[]
        """
        return [w for w in well_metrics if w.accepted_event_count > event_count]

    @staticmethod
    def total_eventful(well_metrics, event_count=0):
        """
        Returns the list of well metrics from the list that have greater than
        event_count total events.

        :param well_metrics: WellMetric[]
        :param event_count: int
        :rtype: WellMetric[]
        """
        # special case to throw out min amplitude peaks
        return [w for w in well_metrics if w.total_event_count > event_count]

    @staticmethod
    def triggered_eventful(well_metrics, event_count=0):
        """
        Returns the list of well metrics from the list that have greater than
        event_count triggered events.  A triggered event is an event that was
        detected and over the min amplitude threshold in the VIC channel.

        :param well_metrics: WellMetric[]
        :param event_count: int
        :rtype: WellMetric[]
        """
        return [w for w in well_metrics if w.triggered_event_count > event_count]

    @staticmethod
    def thresholded(well_metrics, channel_num):
        """
        Returns the list of well metrics from the list where there was an
        automatic (or manual) threshold drawn in the specified channel.

        :param well_metrics: WellMetric[]
        :param channel_num: which channel
        :rtype: WellMetric[]
        """
        return [w for w in well_metrics if w.well_channel_metrics[channel_num].threshold \
                and w.well_channel_metrics[channel_num].threshold != 0]

    @staticmethod
    def nonthresholded(well_metrics, channel_num):
        """
        Returns the list of well metrics from the list where there was not
        an automatic (or manual) threshold drawn in the specified channel.

        :param well_metrics: WellMetric[]
        :param channel_num: int
        :rtype: WellMetric[]
        """
        return [w for w in well_metrics if not w.well_channel_metrics[channel_num].threshold]


    @staticmethod
    def attr_mean_variance_ci95(well_metrics, attr_name):
        """
        Returns the mean, standard deviation, and 95% confidence interval
        of the specified well metric attribute across the specified wells.

        :param well_metrics: WellMetric[]
        :param attr_name: Name of the attribute to analyze.
        :rtype: tuple (mean, stdev, low_ci, high_ci)
        """
        if not well_metrics:
            return (0, 0, 0, 0)
        attrs = [getattr(w, attr_name) for w in well_metrics]
        attrs = [a for a in attrs if a is not None]
        mean = np.mean(attrs)
        stdev = np.std(attrs)
        ci025, ci975 = percentile(attrs, .025), percentile(attrs, .975)
        return (mean, stdev, ci025, ci975)

    @staticmethod
    def channel_attr_mean_variance_ci95(well_metrics, channel_num, attr_name):
        """
        Returns the mean, standard deviation, and 95% confidence interval
        of the specified channel metric attribute across the specified wells.

        :param well_metrics: WellMetric[]
        :param channel_num: Which channel to compute aggregate values for.
        :param attr_name: Name of the attribute to analyze.
        :rtype: tuple (mean, stdev, low_ci, high_ci)
        """
        if not well_metrics:
            return (0, 0, 0, 0)
        attrs = [getattr(w.well_channel_metrics[channel_num], attr_name) for w in well_metrics]
        attrs = [a for a in attrs if a is not None]
        mean = np.mean(attrs)
        stdev = np.std(attrs)
        ci025, ci975 = percentile(attrs, .025), percentile(attrs, .975)
        return (mean, stdev, ci025, ci975)


    @property
    def low_event_wells(self):
        """
        Return the wells in this group which have lower than the standard
        low event count of accepted events.

        :rtype: WellMetric[]
        """
        return [w for w in self.event_count_wells if w.accepted_event_count < self.low_event_count]

    def low_event_wells_in(self, wells):
        """
        Return the wells in the specified list that have lower than the standard
        low event count of accepted events.

        :param wells: WellMetric[]
        :rtype: WellMetric[]
        """
        return [w for w in wells if w.accepted_event_count < self.low_event_count]

    @property
    def high_event_wells(self, maxCount = 20000):
        """
        Return the wells in this group which have lower than the standard
        low event count of accepted events.

        :rtype: WellMetric[]
        """
        return [w for w in self.event_count_wells if w.accepted_event_count > maxCount]


    @property
    def low_event_wells_qx200(self, minCount = 15000):
        """
        Return the wells in this group which have lower than the standard
        low event count of accepted events.

        :rtype: WellMetric[]
        """
        return [w for w in self.event_count_wells if w.accepted_event_count < minCount]


    @property
    def quality_eligible_wells(self):
        """
        Returns the list of wells that are expected to have a quality metric
        in at least one channel of > 0.85.

        :rtype: WellMetric[]
        """
        eligible_wells = []
        for w in self.all_well_metrics:
            for c in w.well_channel_metrics:
                if c.auto_threshold_expected:
                    eligible_wells.append(w)
                    break
        return eligible_wells

    @property
    def quality_eligible_wells_qx200(self):
        """
        Returns the list of wells that are expected to have a quality metric
        in at least one channel of > 0.85.
        RED assays are exempt

        :rtype: WellMetric[]
        """
        eligible_wells = []


        for w in self.all_well_metrics:
            if (w.plate_metric.plate.plate_type_code == 'bred'):
                continue
            for c in w.well_channel_metrics:
                if c.auto_threshold_expected:
                    eligible_wells.append(w)
                    break
        return eligible_wells

    @property
    def low_quality_wells(self):
        """
        Return the list of wells that are expected to have a quality
        metric in at least one channel of > 0.85, but do not.

        :rtype: WellMetric[]
        """
        return self.low_quality_wells_in(self.quality_eligible_wells)

    @property
    def low_quality_wells_qx200(self):
        """
        Return the list of wells that are expected to have a quality
        metric in at least one channel of > 0.85, but do not.

        :rtype: WellMetric[]
        """
        return self.low_quality_wells_in(self.quality_eligible_wells_qx200)

    def low_quality_wells_in(self, wells):
        """
        Return the list of wells in the supplied list
        that are expected to have a quality metric in at least one
        channel of > 0.85, but do not.

        :param wells: WellMetric[]; the list of wells to analyze.
        :rtype: WellMetric[]
        """
        bad_wells = []
        for w in wells:
            for c in w.well_channel_metrics:
                if c.auto_threshold_expected and c.threshold_conf < self.low_data_quality:
                    bad_wells.append(w)
                    break
        return bad_wells

    @property
    def check_quality_wells(self):
        """
        Deprecated/kinda useless.  Like low_quality_wells, but uses the
        decision tree flags to make the determination.
        """
        bad_wells = []
        for w in self.quality_eligible_wells:
            for c in w.well_channel_metrics:

                # set of flags that are 'ok'                
                decision_tree_flags = c.decision_tree_flags;
                for i in [256,  2**28]:
                    if ( decision_tree_flags  & i ):
                        decision_tree_flags = decision_tree_flags - i

                if ( not decision_tree_flags ):
                    continue;

                if c.auto_threshold_expected and c.decision_tree_flags != 0:
                    bad_wells.append(w)
                    break
        return bad_wells

    @property
    def check_quality_wells_qx200(self):
        """
        Deprecated/kinda useless.  Like low_quality_wells, but uses the
        decision tree flags to make the determination.
        """
        bad_wells = []
        for w in self.quality_eligible_wells_qx200:
            for c in w.well_channel_metrics:

                # set of flags that are 'ok'                
                decision_tree_flags = c.decision_tree_flags;
                for i in [256,  2**28]:
                    if ( decision_tree_flags  & i ):
                        decision_tree_flags = decision_tree_flags - i
                
                if ( not decision_tree_flags ):
                    continue;

                if c.auto_threshold_expected and c.decision_tree_flags != 0:
                    bad_wells.append(w)
                    break
        return bad_wells

    @property
    def fpfn_false_positive_wells(self):
        """
        Return the list of wells which are designated false positive
        wells in a False Positive/False Negative (FPFN) beta plate.

        :rtype: WellMetric[]
        """
        fp_wells = []
        for w in self.well_metrics_by_type('bfpfn'):
            for c in w.well_channel_metrics:
                if c.false_positive_peaks is not None:
                    fp_wells.append(w)
                    break
        return fp_wells

    @property
    def fpfn_false_positive_ci95(self):
        """
        Return the upper value of the 95% confidence interval
        of number of positives in FP/FN false positive wells.

        Establishes a baseline for false positives when you
        run an NTC after saturation.

        :rtype: float
        """
        wells = self.fpfn_false_positive_wells
        # TODO: move into utility func?
        def fp_rate(w):
            if w.accepted_event_count == 0:
                return 0
            return w.well_channel_metrics[1].false_positive_peaks * (10000.0/w.accepted_event_count)

        return percentile(wells, .95, fp_rate)

    @property
    def fpfn_false_negative_wells(self):
        """
        Return the list of wells which are designated false negative
        wells in a False Positive/False Negative (FPFN) beta plate.

        :rtype: WellMetric[]
        """
        fn_wells = []
        for w in self.well_metrics_by_type('bfpfn'):
            for c in w.well_channel_metrics:
                if c.false_negative_peaks is not None:
                    fn_wells.append(w)
                    break
        return fn_wells

    @property
    def fpfn_false_negative_ci95(self):
        """
        Return the upper value of the 95% confidence interval
        of number of positives in FP/FN false positive wells.

        Establishes a baseline for false positives when you
        run an NTC after saturation.

        :rtype: float
        """
        wells = self.fpfn_false_negative_wells
        # TODO: move into utility func?
        def fp_rate(w):
            if w.accepted_event_count == 0:
                return 0
            return w.well_channel_metrics[1].false_negative_peaks * (10000.0/w.accepted_event_count)

        return percentile(wells, .95, fp_rate)

    @property
    def singleplex_wells(self):
        """
        Return the wells in this group that belong to
        singleplex beta plates.

        :rtype: WellMetric[]
        """
        return self.well_metrics_by_type('bsplex')

    @property
    def duplex_wells(self):
        """
        Return the wells in this group that belong to
        duplex beta plates.

        :rtype: WellMetric[]
        """
        return self.well_metrics_by_type('bdplex')

    @property
    def dplex200_wells(self):
        """
        Return the wells in this group that belong to
        duplex qx200 plates.

        :rtype: WellMetric[]
        """
        return self.well_metrics_by_type('dplex200')

    @property
    def event_count_wells(self):
        """
        Return the wells in this group that belong to
        event count beta plates.

        :rtype: WellMetric[]
        """
        return [w for w in self.all_well_metrics if w.well.sample_name not in EXPECTED_LOW_EVENT_WELLS]

    @property
    def probe_event_count_wells(self):
        """
        Return the wells in this group that belong to Probe event count plates.

        :rtype: WellMetric[]
        """
        return self.well_metrics_by_type('probeec')

    @property
    def eva_event_count_wells(self):
        """
        Return the wells in this group that belong to Eva Event count plates.

        :rtype: WellMetric[]
        """
        return self.well_metrics_by_type('evaec')


    @property
    def colorcomp_wells(self):
        """
        Return the wells in this group that belong to
        multi-well color comp beta plates.

        :rtype: WellMetric[]
        """
        return self.well_metrics_by_type(('bcc','mfgcc','scc'))

    @property
    def dnr_eva_staph_wells(self):
        """
        DEPRECATED AND CONFUSING... Groove beta was kinda messy...
        """
        return self.well_metrics_by_type('gdnr')

    @property
    def qx200_dnr_wells(self):
        """
        gets qx200 dnr (dnr200) wells
        """
        return self.well_metrics_by_type('dnr200')

    @property
    def eg200_wells(self):
        """
        gets qx200 evergreen (eg200) wells
        """
        return self.well_metrics_by_type('eg200')

    @property
    def tq200_wells(self):
        """
        gets qx200 taqman (tq200) wells
        """
        return self.well_metrics_by_type('tq200')

    @property
    def dnr_eva_staph_bg_wells(self):
        """
        DEPRECATED AND CONFUSING... Groove beta was kinda messy...
        """
        return self.well_metrics_by_type('2x10')

    @property
    def dnr_eva_hgdna_wells(self):
        """
        DEPRECATED AND CONFUSING... Groove beta was kinda messy...
        """
        return self.well_metrics_by_type('egdnr')

    @property
    def event_count_count_mean_variance_ci95(self):
        """
        Return mean, stdev and confidence interval of the number
        of accepted events among wells in event count plates.

        :rtype: tuple (len 4)
        """
        return AnalysisGroupMetrics.attr_mean_variance_ci95(self.event_count_wells, 'accepted_event_count')

    @property
    def event_count_undercount_wells(self):
        """
        Return the list of wells in event count plates where there
        were fewer accepted events than the low event count threshold.

        :rtype: WellMetric[]
        """
        return [w for w in self.event_count_wells if w.accepted_event_count < self.low_event_count]

    def conc_ci95(self, wells):
        """
        Returns the mean and confidence intervals of the concentrations of the
        specified wells, where a threshold was computed.  Wells that do not have
        a threshold called are not factored into the calculation.

        :param wells: WellMetric[]
        :return: tuple (mean, low_ci, high_ci)
        """
        ok_wells = [w for w in wells if w.well_channel_metrics[0].concentration is not None and w.well_channel_metrics[0].threshold]
        # TODO move into utility func?
        def fam_conc(w):
            return float(w.well_channel_metrics[0].concentration)

        return np.mean([fam_conc(w) for w in ok_wells]), percentile(ok_wells, .025, fam_conc), percentile(ok_wells, .975, fam_conc)

    @property
    def all_singleplex_conc_ci95(self):
        """
        Returns the mean and confidence intervals of the concentrations of the
        singleplex plate wells, where a threshold was computed.  Wells that do
        not have a threshold called are not factored into the calculation.

        :return: tuple (mean, low_ci, high_ci)
        """
       
        # if qx100 only include wells that pass threshold..
        if ( self.system_version == 'QX200' ): 
            eligible_wells = []
            for w in  self.singleplex_wells:
                for c in w.well_channel_metrics:
                    if c.auto_threshold_expected and c.threshold_conf >= self.low_data_quality:
                        eligible_wells.append(w)
                        break
        else:
            eligible_wells = self.singleplex_wells

        return self.conc_ci95(eligible_wells)

    @property
    def singleplex_conc_rise_ratio_ci95(self):
        """
        Computes a mean and confidence interval of the 4Q/1Q FAM concentration
        ratio of the singleplex plate wells, where a ratio was computed.

        :return: tuple (mean, low_ci, high_ci)
        """
        return self.conc_rise_ratio_ci95(self.singleplex_wells)

    def conc_rise_ratio_ci95(self, wells, channel_num=0):
        """
        Computes a mean and confidence interval of the 4Q/1Q concentration
        ratio of the specified wells, where a ratio was computed.

        :param wells: WellMetric[]
        :param channel_num: Which channel to use.
        :return: tuple (mean, low_ci, high_ci)
        """
        wells = [w for w in wells if w.well_channel_metrics[channel_num].concentration_rise_ratio]
        def fam_rise_ratio(w):
            return float(w.well_channel_metrics[channel_num].concentration_rise_ratio)

        return np.mean([fam_rise_ratio(w) for w in wells]), percentile(wells, .025, fam_rise_ratio), percentile(wells, .975, fam_rise_ratio)

    def positive_mean_variance_ci95(self, wells, channel_num=0):
        """
        Returns the mean, standard deviation, and 95% confidence interval
        of the positive mean in the specified channel across the specified wells.

        :param wells: WellMetric[]
        :param channel_num: 0 for FAM, 1 for VIC.
        :rtype: tuple (mean, stdev, low_ci, high_ci)
        """
        wells = [w for w in wells if w.well_channel_metrics[channel_num].positive_mean is not None]
        return AnalysisGroupMetrics.channel_attr_mean_variance_ci95(wells, channel_num, 'positive_mean')

    def negative_mean_variance_ci95(self, wells, channel_num=0):
        """
        Returns the mean, standard deviation, and 95% confidence interval
        of the negative mean in the specified channel across the specified wells.

        :param wells: WellMetric[]
        :param channel_num: 0 for FAM, 1 for VIC.
        :rtype: tuple (mean, stdev, low_ci, high_ci)
        """
        wells = [w for w in wells if w.well_channel_metrics[channel_num].negative_mean is not None]
        return AnalysisGroupMetrics.channel_attr_mean_variance_ci95(wells, channel_num, 'negative_mean')

    def s_value_mean_variance_ci95(self, wells, channel_num=0):
        """
        Returns the mean, standard deviation, and 95% confidence interval
        of the S (separation) value in the specified channel across the specified wells.

        :param wells: WellMetric[]
        :param channel_num: 0 for FAM, 1 for VIC.
        :rtype: tuple (mean, stdev, low_ci, high_ci)
        """
        wells = [w for w in wells if w.well_channel_metrics[channel_num].s_value is not None]
        return AnalysisGroupMetrics.channel_attr_mean_variance_ci95(wells, channel_num, 's_value')

    def eg200_singleplex_stats(self):
        """
        Returns the assay, mean Conc, mean S2D, mean single rain, mean double rain 
        EvaGreen plate grouped by assay target
        :rtype: tuple( target, mean Conc, mean S2D, mean single rain, mean double rain )
        """
        plate_code = 'eg200'
        channel_num = 0

        return self.target_singleplex_stats(plate_code, channel_num)

    def tq200_singleplex_stats(self, channel_num):
        """
        Returns the assay, mean Conc, mean S2D, mean single rain, mean double rain 
        grouped by assy target for channlexx
        :param channel_num: 0 for FAM, 1 for VIC.
        :rtype: tuple( target, mean Conc, mean S2D, mean single rain, mean double rain  )
        """
        plate_code = 'tq200'
        return self.target_singleplex_stats(plate_code, channel_num)

    def target_singleplex_stats(self, plate_code, channel_num):
        """
        Returns a list of assayname, mean Conc, mean S2D, mean single rain, mean double rain 
        for a particular plate type
        :param plate_code: str giving the plate code like eg200 or tq200
        :param channel_num: 0 for FAM, 1 for VIC.
        :rtype: tuple( target, meanConc, mean S2D, mean single rain, mean double rain )
        """
        ## first select wells
        wells = [w for w in self.well_metrics_by_type((plate_code)) if 'NTC' not in w.well.sample_name  ]
        
        ## get list of targest present
        targets = self.targets( wells, channel_num )
        
        ## group and process by target 
        statHolder = []
        for target in targets:
            if not (target):
                continue

            targetWells = self.well_metrics_by_target( wells, target, channel_num )

            Conc   = [ w.well_channel_metrics[channel_num].concentration for w in targetWells 
                            if w.well_channel_metrics[channel_num].concentration is not None ]            
            S2Dval = [ w.well_channel_metrics[channel_num].s2d_value for w in targetWells 
                            if w.well_channel_metrics[channel_num].s2d_value is not None ]
            SRain  = [ w.well_channel_metrics[channel_num].single_rain_pct for w in targetWells 
                            if w.well_channel_metrics[channel_num].single_rain_pct is not None ]
            
            #ugly hack to get double positive rain in oposit channel
            if ( channel_num == 0):
                DRain  = [w.well_channel_metrics[1].double_rain_pct for w in targetWells
                            if w.well_channel_metrics[1].double_rain_pct is not None ]
            else:
                DRain  = [w.well_channel_metrics[0].double_rain_pct for w in targetWells
                            if w.well_channel_metrics[0].double_rain_pct is not None ]


            meanConc   = np.mean(Conc)
            meanS2Dval = np.mean(S2Dval)
            meanSRain  = np.mean(SRain)
            meanDRain  = np.mean(DRain)
            statHolder.append( (target, meanConc, meanS2Dval, meanSRain, meanDRain ) )

        return statHolder
    
    def new_droplet_metrics_stats(self, channel_num): 
        """
        Returns a list of new drolet metrics mean single rain, mean double rain 
        for a particular plate type
        :param plate_code: str giving the plate code like eg200 or tq200
        :param channel_num: 0 for FAM, 1 for VIC.
        :rtype: tuple( bscore, S2D, hfValue, lf, value, single rain, double rain )
        """
        ## first select wells
        wells = [w for w in self.all_well_metrics if 'NTC' not in w.well.sample_name  ]

        ## group and process by target 

        bscore   = [ w.balance_score for w in wells if w.balance_score is not None ]

        S2Dval = [ w.well_channel_metrics[channel_num].s2d_value for w in wells
                            if w.well_channel_metrics[channel_num].s2d_value is not None ]
        HFliers  = [ w.well_channel_metrics[channel_num].high_flier_pct for w in wells
                            if w.well_channel_metrics[channel_num].high_flier_pct is not None ]
        LFliers  = [w.well_channel_metrics[channel_num].low_flier_pct for w in wells
                            if w.well_channel_metrics[channel_num].low_flier_pct is not None ]
        SRain  = [ w.well_channel_metrics[channel_num].single_rain_pct for w in wells
                            if w.well_channel_metrics[channel_num].single_rain_pct is not None ]
        DRain  = [w.well_channel_metrics[channel_num].double_rain_pct for w in wells
                            if w.well_channel_metrics[channel_num].double_rain_pct is not None ]

        meanBscore = np.mean(bscore)
        meanS2Dval = np.mean(S2Dval)
        meanHFval  = np.mean(HFliers)
        meanLFval  = np.mean(LFliers)
        meanSRain  = np.mean(SRain)
        meanDRain  = np.mean(DRain)

        return (meanBscore, meanS2Dval, meanHFval, meanLFval, meanSRain, meanDRain )

    def fam_conc_ci95(self, wells, expected_concentration):
        """
        Returns the mean and 95% confidence interval
        of the FAM concentration the wells with the specified expected
        concentration.

        :param wells: WellMetric[]
        :param expected_concentration: int (cp/uL).  This will be stored
               in the database, populated by qtools.lib.metrics.beta.
        :rtype: tuple (mean, low_ci, high_ci)
        """
        conc_wells = self.fam_conc_well_metrics(wells, expected_concentration)

        ok_wells = [w for w in conc_wells if w.well_channel_metrics[0].threshold is not None and w.well_channel_metrics[0].threshold > 0]
        def fam_conc(w):
            return float(w.well_channel_metrics[0].concentration)

        return np.mean([fam_conc(w) for w in ok_wells]), percentile(ok_wells, .025, fam_conc), percentile(ok_wells, .975, fam_conc)

    def fam_conc_well_metrics(self, wells, expected_concentration):
        """
        Returns the subset of WellMetrics which have the specified
        FAM concentration, in cp/uL.  This value will be set in the database,
        and will have been set by logic in qtools.lib.metrics.beta.

        :param wells: WellMetric[]
        :param expected_concentration: int (cp/uL).  This will be stored
               in the database, populated by qtools.lib.metrics.beta.
        :rtype: WellMetric[]
        """
        return [w for w in wells if w.well_channel_metrics[0].expected_concentration == expected_concentration]

    def duplex_fam_conc_well_metrics(self, expected_concentration):
        """
        Returns the duplex wells which have the specified
        FAM concentration, in cp/uL.  This value will be set in the database,
        and will have been set by logic in qtools.lib.metrics.beta.

        :param expected_concentration: int (cp/uL).  This will be stored
               in the database, populated by qtools.lib.metrics.beta.
        :rtype: WellMetric[]
        """
        return [w for w in self.well_metrics_by_type(('bdplex','dplex200')) if w.well_channel_metrics[0].expected_concentration == expected_concentration]


    def duplex_fam_conc_ci95(self, expected_concentration):
        """
        Returns the mean, standard deviation, and 95% confidence interval
        of the FAM concentration of the group's duplex wells with the
        specified expected FAM concentration.

        :param expected_concentration: int (cp/uL).  This will be stored
               in the database, populated by qtools.lib.metrics.beta.
        :rtype: tuple (mean, low_ci, high_ci)
        """
        return self.fam_conc_ci95(self.well_metrics_by_type(('bdplex','dplex200')), expected_concentration)

    @property
    def all_duplex_vic_conc_ci95(self):
        """
        Returns the mean and 95% confidence interval
        of the VIC concentration of the group's duplex wells.

        :rtype: tuple (mean, low_ci, high_ci)
        """
        wells = [w for w in self.duplex_wells if w.well_channel_metrics[1].threshold is not None and w.well_channel_metrics[1].threshold > 0]
        def vic_conc(w):
            return float(w.well_channel_metrics[1].concentration)

        return np.mean([vic_conc(w) for w in wells]), percentile(wells, .025, vic_conc), percentile(wells, .975, vic_conc)

    def duplex_vic_conc_ci95(self, expected_concentration):
        """
        Returns the mean and 95% confidence interval
        of the VIC concentration of the group's duplex wells with the
        specified expected FAM concentration.

        :param expected_concentration: int (cp/uL).  This will be stored
               in the database, populated by qtools.lib.metrics.beta.
        :rtype: tuple (mean, low_ci, high_ci)
        """
        wells = self.duplex_fam_conc_well_metrics(expected_concentration)

        # todo make conc ci95 generic?
        wells = [w for w in wells if w.well_channel_metrics[1].threshold is not None and w.well_channel_metrics[1].threshold > 0]
        def vic_conc(w):
            return float(w.well_channel_metrics[1].concentration)

        return np.mean([vic_conc(w) for w in wells]), percentile(wells, .025, vic_conc), percentile(wells, .975, vic_conc)

    def conc_rise_ci95(self, wells, expected_concentration, channel_num):
        """
        Returns the mean and 95% confidence interval of the 4Q/1Q
        concentration ratio of the specified wells with the
        specified expected concentration.

        :param wells: WellMetric[]
        :param expected_concentration: int (cp/uL).  This will be stored
               in the database, populated by qtools.lib.metrics.beta.
        :param channel_num: 0 for FAM, 1 for VIC
        :rtype: tuple (mean, low_ci, high_ci)
        """
        wells = self.fam_conc_well_metrics(wells, expected_concentration)
        return self.conc_rise_ratio_ci95(wells, channel_num=channel_num)

    def duplex_conc_rise_ci95(self, expected_concentration, channel_num):
        """
        Returns the mean and 95% confidence interval
        of the FAM concentration the group's duplex wells with the
        specified expected concentration.

        :param expected_concentration: int (cp/uL).  This will be stored
               in the database, populated by qtools.lib.metrics.beta.
        :rtype: tuple (mean, low_ci, high_ci)
        """
        wells = self.duplex_fam_conc_well_metrics(expected_concentration)
        return self.conc_rise_ratio_ci95(wells, channel_num=channel_num)

    @property
    def all_duplex_vic_conc_rise_ci95(self):
        """
        Returns the mean and 95% confidence interval
        of the VIC 4Q/1Q rise ratio of the group's duplex wells.

        :rtype: tuple (mean, low_ci, high_ci)
        """
        wells = [w for w in self.duplex_wells if w.well_channel_metrics[1].threshold is not None and w.well_channel_metrics[1].threshold > 0]
        return self.conc_rise_ratio_ci95(wells, channel_num=1)

    def duplex_bscore_mean_variance_ci95(self, expected_concentration):
        """
        Returns the mean, standard deviation, and 95% confidence interval
        of the B-score of the duplex plate type wells with the expected
        concentration.

        :param expected_concentration: cp/uL, int (1000, 500, etc.)
        :rtype: tuple (mean, stdev, low_ci, high_ci)
        """
        wells = self.duplex_fam_conc_well_metrics(expected_concentration)
        return AnalysisGroupMetrics.attr_mean_variance_ci95(wells, 'balance_score')

    def dnr_conc_well_metrics(self, expected_concentration):
        """
        Returns the subset of HighDNR plate type WellMetrics which have the specified
        FAM concentration, in cp/uL.  This value will be set in the database,
        and will have been set by logic in qtools.lib.metrics.beta.

        :param expected_concentration: int (cp/uL).  This will be stored
               in the database, populated by qtools.lib.metrics.beta.
        :rtype: WellMetric[]
        """
        return [w for w in self.well_metrics_by_type(('bdnr','gdnr','dnr200')) if w.well_channel_metrics[0].expected_concentration == expected_concentration]

    def dnr_conc_ci95(self, expected_concentration):
        """
        Returns the mean and 95% confidence interval of the
        FAM concentration of the HighDNR wells with the
        specified expected concentration.

        :param expected_concentration: int (cp/uL).  This will be stored
               in the database, populated by qtools.lib.metrics.beta.
        :rtype: tuple (mean, low_ci, high_ci)
        """
        wells = self.dnr_conc_well_metrics(expected_concentration)
        # filter if threshold = 0
        wells = [w for w in wells if w.well_channel_metrics[0].threshold is not None and w.well_channel_metrics[0].threshold > 0]
        def fam_conc(w):
            return float(w.well_channel_metrics[0].concentration)

        return np.mean([fam_conc(w) for w in wells]), percentile(wells, .025, fam_conc), percentile(wells, .975, fam_conc)

    def dnr_conc_rise_ci95(self, expected_concentration):
        """
        Returns the mean and 95% confidence interval of the 4Q/1Q
        FAM concentration ratio of the HighDNR wells with the
        specified expected concentration.

        :param expected_concentration: int (cp/uL).  This will be stored
               in the database, populated by qtools.lib.metrics.beta.
        :rtype: tuple (mean, low_ci, high_ci)
        """
        wells = self.dnr_conc_well_metrics(expected_concentration)
        return self.conc_rise_ratio_ci95(wells)

    def red_lod_wells(self, sample_name):
        """
        Returns the RED beta plate wells with the specified name.

        :param sample_name: Name of the sample to match.
        :rtype: WellMetric[]
        """
        return [w for w in self.well_metrics_by_type('bred') if w.well.sample_name == sample_name]

    def red_lod_ci95(self, sample_name, per_droplet_count):
        """
        Returns the mean and 95% confidence interval of the
        FAM concentration of the RED plate type wells with the
        specified name.

        :param sample_name: name of the sample to filter wells by
        :param per_droplet_count: The rate to compute by (/10000 droplets, /20000 droplets, etc.)
        :rtype: tuple (mean, low_ci, high_ci)
        """
        def fp_rate(w):
            if w.accepted_event_count == 0:
                return 0
            return w.well_channel_metrics[0].false_positive_peaks * (float(per_droplet_count)/w.accepted_event_count)

        return percentile(self.red_lod_wells(sample_name), .95, fp_rate)

    def manual_red_lod_ci95(self, sample_name, per_droplet_count):
        """
        Returns the mean and 95% confidence interval of the
        FAM concentration of the RED plate type wells with the
        specified name.

        :param sample_name: name of the sample to filter wells by
        :param per_droplet_count: The rate to compute by (/10000 droplets, /20000 droplets, etc.)
        :rtype: tuple (mean, low_ci, high_ci)
        """
        def fp_rate(w):
            if w.accepted_event_count == 0:
                return 0
            elif w.well_channel_metrics[0].positive_peaks == 0 or w.well_channel_metrics[0].positive_peaks is None:
                return 0
            return w.well_channel_metrics[0].positive_peaks * (float(per_droplet_count)/w.accepted_event_count)

        return percentile(self.red_lod_wells(sample_name), .95, fp_rate)

    @property
    def mean_width_mean_variance_ci95(self):
        """
        Returns the mean, standard deviation, and 95% confidence interval
        of the mean width of the eventful wells (# events > some threshold,
        normally 100).

        :rtype: tuple (mean, stdev, low_ci, high_ci)
        """
        wells = AnalysisGroupMetrics.triggered_eventful(self.all_well_metrics, 100)
        return self.mean_width_mean_variance_ci95_in(wells)

    def mean_width_mean_variance_ci95_in(self, wells):
        """
        Returns the mean, standard deviation, and 95% confidence interval
        of the mean width of the specified wells.

        :param wells: WellMetric[]
        :rtype: tuple (mean, stdev, low_ci, high_ci)
        """
        return AnalysisGroupMetrics.attr_mean_variance_ci95(wells, 'width_mean')

    @property
    def width_variance_mean_variance_ci95(self):
        """
        Returns the mean, standard deviation, and 95% confidence interval
        of the width sigma of the eventful wells (# events > some threshold,
        normally 100).

        :rtype: tuple (mean, stdev, low_ci, high_ci)
        """
        wells = AnalysisGroupMetrics.triggered_eventful(self.all_well_metrics, 100)
        return AnalysisGroupMetrics.attr_mean_variance_ci95(wells, 'width_variance')

    @property
    def mean_accepted_width_mean_variance_ci95(self):
        """
        Returns the mean, standard deviation, and 95% confidence interval
        of the mean width of the accepted events in eventful wells (# events
        > some threshold, normally 100).

        :rtype: tuple (mean, stdev, low_ci, high_ci)
        """
        wells = AnalysisGroupMetrics.triggered_eventful(self.all_well_metrics, 100)
        return self.mean_accepted_width_mean_variance_ci95_in(wells)

    def mean_accepted_width_mean_variance_ci95_in(self, wells):
        """
        Returns the mean, standard deviation, and 95% confidence interval
        of the mean width of the accepted events in the specified wells.

        :param wells: WellMetric[]
        :rtype: tuple (mean, stdev, low_ci, high_ci)
        """
        return AnalysisGroupMetrics.attr_mean_variance_ci95(wells, 'accepted_width_mean')

    @property
    def accepted_width_stdev_mean_variance_ci95(self):
        """
        Returns the mean, standard deviation, and 95% confidence interval
        of the width sigma of the accepted events in eventful wells (# events
        > some threshold, normally 100).

        :rtype: tuple (mean, stdev, low_ci, high_ci)
        """
        wells = AnalysisGroupMetrics.triggered_eventful(self.all_well_metrics, 100)
        return AnalysisGroupMetrics.attr_mean_variance_ci95(wells, 'accepted_width_stdev')

    @property
    def min_width_gate_mean_variance_ci95(self):
        """
        Returns the mean, standard deviation, and 95% confidence interval
        of the min width gate of the eventful wells (# events
        > some threshold, normally 100).

        :rtype: tuple (mean, stdev, low_ci, high_ci)
        """
        wells = AnalysisGroupMetrics.triggered_eventful(self.all_well_metrics, 100)
        channels = [wm.well_channel_metrics[0] for wm in wells]
        return AnalysisGroupMetrics.attr_mean_variance_ci95(channels, 'min_width_gate')

    @property
    def max_width_gate_mean_variance_ci95(self):
        """
        Returns the mean, standard deviation, and 95% confidence interval
        of the max width gate of the eventful wells (# events
        > some threshold, normally 100).

        :rtype: tuple (mean, stdev, low_ci, high_ci)
        """
        wells = AnalysisGroupMetrics.triggered_eventful(self.all_well_metrics, 100)
        channels = [wm.well_channel_metrics[0] for wm in wells]
        return AnalysisGroupMetrics.attr_mean_variance_ci95(channels, 'max_width_gate')

    @property
    def sum_baseline_mean_mean_variance_ci95(self):
        """
        Returns the mean, standard deviation, and 95% confidence interval
        of the sum baseline mean of the eventful wells

        :rtype: tuple (mean, stdev, low_ci, high_ci)
        """
        wells = AnalysisGroupMetrics.eventful(self.all_well_metrics)
        return AnalysisGroupMetrics.attr_mean_variance_ci95(wells, 'sum_baseline_mean')

    @property
    def sum_baseline_stdev_mean_variance_ci95(self):
        """
        Returns the mean, standard deviation, and 95% confidence interval
        of the sum baseline stdev of the eventful wells

        :rtype: tuple (mean, stdev, low_ci, high_ci)
        """
        wells = AnalysisGroupMetrics.eventful(self.all_well_metrics)
        return AnalysisGroupMetrics.attr_mean_variance_ci95(wells, 'sum_baseline_stdev')

    @property
    def fam_baseline_mean_mean_variance_ci95(self):
        """
        Returns the mean, standard deviation, and 95% confidence interval
        of the FAM baseline mean of the eventful wells

        :rtype: tuple (mean, stdev, low_ci, high_ci)
        """
        wells = AnalysisGroupMetrics.eventful(self.all_well_metrics)
        return AnalysisGroupMetrics.channel_attr_mean_variance_ci95(wells, 0, 'baseline_mean')

    @property
    def fam_baseline_stdev_mean_variance_ci95(self):
        """
        Returns the mean, standard deviation, and 95% confidence interval
        of the FAM baseline stdev of the eventful wells

        :rtype: tuple (mean, stdev, low_ci, high_ci)
        """
        wells = AnalysisGroupMetrics.eventful(self.all_well_metrics)
        return AnalysisGroupMetrics.channel_attr_mean_variance_ci95(wells, 0, 'baseline_stdev')

    @property
    def vic_baseline_mean_mean_variance_ci95(self):
        """
        Returns the mean, standard deviation, and 95% confidence interval
        of the VIC baseline mean of the eventful wells

        :rtype: tuple (mean, stdev, low_ci, high_ci)
        """
        wells = AnalysisGroupMetrics.eventful(self.all_well_metrics)
        return AnalysisGroupMetrics.channel_attr_mean_variance_ci95(wells, 1, 'baseline_mean')

    @property
    def vic_baseline_stdev_mean_variance_ci95(self):
        """
        Returns the mean, standard deviation, and 95% confidence interval
        of the VIC baseline stdev of the eventful wells

        :rtype: tuple (mean, stdev, low_ci, high_ci)
        """
        wells = AnalysisGroupMetrics.eventful(self.all_well_metrics)
        return AnalysisGroupMetrics.channel_attr_mean_variance_ci95(wells, 1, 'baseline_stdev')


    def well_metrics_of_cnv_num(self, expected_cnv):
        """
        Returns the subset of CNV plate type WellMetrics which have the
        expected CNV number.  This value will be set in the database,
        and will have been set by logic in qtools.lib.metrics.beta.

        :param expected_cnv: int (copy number).  This will be stored
               in the database, populated by qtools.lib.metrics.beta.
        :rtype: WellMetric[]
        """
        wells = self.well_metrics_by_type(('bcnv','gcnv','cnv200'))
        return [w for w in wells if w.expected_cnv == expected_cnv]

    def cnv_misses(self, expected_cnv):
        """
        Returns the subset of CNV plate type WellMetrics which have
        a CNV on the 'wrong side' of the expected value, for the
        specified copy number.

        :param expected_cnv: int (copy number).  This will be stored
               in the database, populated by qtools.lib.metrics.beta.
        :rtype: WellMetric[]
        """
        wells = self.well_metrics_of_cnv_num(expected_cnv)
        return [w for w in wells if not w.cnv or abs(w.cnv - w.expected_cnv) > 0.5]

    def cnv_mean_variance(self, expected_cnv):
        """
        Returns the mean and standard deviation of the copy number
        of all wells with the expected copy number.

        :param expected_cnv: int (copy number).  This will be stored
               in the database, populated by qtools.lib.metrics.beta.
        :rtype: WellMetric[]
        """
        wells = self.well_metrics_of_cnv_num(expected_cnv)
        cnvs = [float(w.cnv) for w in wells if w.cnv]
        if not cnvs:
            return (0, 0)
        return np.mean(cnvs), np.std(cnvs)

    def cnv_rise_ratio_mean_stdev_ci95(self, expected_cnv):
        """
        Returns the mean, standard deviation, and 95% confidence interval
        of the 4Q/1Q CNV rise ratio of the wells with the expected
        copy number.

        :param expected_cnv: int (copy number).  This will be stored
               in the database, populated by qtools.lib.metrics.beta.
        :rtype: tuple (mean, stdev, low_ci, high_ci)
        """
        wells = self.well_metrics_of_cnv_num(expected_cnv)
        return AnalysisGroupMetrics.attr_mean_variance_ci95(wells, 'cnv_rise_ratio')

    def cnv_min_max(self, expected_cnv):
        """
        Returns the min and max observed copy number
        of all wells with the expected copy number.

        :param expected_cnv: int (copy number).  This will be stored
               in the database, populated by qtools.lib.metrics.beta.
        :rtype: WellMetric[]
        """
        wells = self.well_metrics_of_cnv_num(expected_cnv)
        cnvs = [w.cnv for w in wells]
        if not cnvs:
            return (0, 0)
        return min(cnvs), max(cnvs)

    @property
    def null_linkage_wells(self):
        """
        I don't know what this means anymore.
        :return: Your guess is as good as mine!
        """
        wells = [wm for wm in self.all_well_metrics if wm.null_linkage is not None]
        return wells

    @property
    def width_gated_pct_mean_variance(self):
        """
        Returns the mean, standard deviation, and 95% confidence interval
        of the percentage of events per well that were gated out
        due to being too wide or two narrow.

        :rtype: tuple (mean, stdev, low_ci, high_ci)
        """
        wells = self.all_well_metrics
        gated_pct = [float(w.well_channel_metrics[0].width_gated_peaks)/w.triggered_event_count for w in wells if w.triggered_event_count > self.accepted_event_cutoff]
        return 100*np.mean(gated_pct), 100*np.std(gated_pct)

    # todo: change non mean_variance_attr_ci95 methods to them (conc_ci95, pct_95)
    @property
    def width_gated_pct_95(self):
        """
        Returns the 95% confidence interval
        of the percentage of events per well that were gated out
        for any reason.

        :rtype: tuple (low_ci, high_ci)
        """
        wells = self.all_well_metrics
        gated_pct = [float(w.well_channel_metrics[0].width_gated_peaks)/w.triggered_event_count for w in wells if w.triggered_event_count > self.accepted_event_cutoff]
        if not gated_pct:
            return (0,0)
        return 100*percentile(gated_pct, 0.025), 100*percentile(gated_pct, 0.975)

    @property
    def min_amplitude_gated_mean_variance_ci95(self):
        """
        Returns the mean, standard deviation, and 95% confidence interval
        of the percentage of events per well that were gated out
        due to a VIC amplitude below the expected HEX spike threshold.

        :rtype: tuple (mean, stdev, low_ci, high_ci)
        """
        wells = self.all_well_metrics
        minamp_pct = [100*float(w.min_amplitude_peaks)/w.total_event_count for w in wells if w.accepted_event_count > self.accepted_event_cutoff and w.min_amplitude_peaks is not None]
        if not minamp_pct:
            return (0, 0, 0, 0)
        return (np.mean(minamp_pct), np.std(minamp_pct), percentile(minamp_pct, 0.025), percentile(minamp_pct, 0.975))

    @property
    def quality_gated_pct_mean_variance(self):
        """
        Returns the mean, standard deviation, and 95% confidence interval
        of the percentage of events per well that were gated out
        due to being of insufficient quality (RED mode only)

        :rtype: tuple (mean, stdev, low_ci, high_ci)
        """
        wells = self.all_well_metrics
        gated_pct = [float(w.well_channel_metrics[0].quality_gated_peaks)/w.triggered_event_count for w in wells if w.triggered_event_count > self.accepted_event_cutoff]
        return 100*np.mean(gated_pct), 100*np.std(gated_pct)

    @property
    def quality_gated_pct_95(self):
        """
        Returns the 95% confidence interval of the percentage of events
        per well that were gated out for low quality (RED mode only).

        :rtype: tuple (low_ci, high_ci)
        """
        wells = self.all_well_metrics
        gated_pct = [float(w.well_channel_metrics[0].quality_gated_peaks)/w.triggered_event_count for w in wells if w.triggered_event_count > self.accepted_event_cutoff]
        if not gated_pct:
            return (0, 0)
        return 100*percentile(gated_pct, 0.025), 100*percentile(gated_pct, 0.975)

    @property
    def vertical_streak_pct_mean_variance(self):
        """
        Returns the mean, standard deviation
        of the percentage of events per well that were gated out
        as part of vertical streaks.

        :rtype: tuple (mean, stdev)
        """
        wells = self.all_well_metrics
        gated_pct = [float(w.vertical_streak_events)/w.triggered_event_count for w in wells if w.triggered_event_count > self.accepted_event_cutoff]
        return 100*np.mean(gated_pct), 100*np.std(gated_pct)

    @property
    def vertical_streak_pct_95(self):
        """
        Returns the 95% confidence interval of the percentage of events
        per well that were gated out as part of vertical streaks.

        :rtype: tuple (low_ci, high_ci)
        """
        wells = self.all_well_metrics
        gated_pct = [float(w.vertical_streak_events)/w.triggered_event_count for w in wells if w.triggered_event_count > self.accepted_event_cutoff]
        if not gated_pct:
            return (0, 0)
        return 100*percentile(gated_pct, 0.025), 100*percentile(gated_pct, 0.975)

    @property
    def rejected_peak_pct_mean_variance(self):
        """
        Returns the mean, standard deviation
        of the percentage of events per well that were
        rejected (peaks were not processed)

        :rtype: tuple (mean, stdev)
        """
        wells = self.all_well_metrics
        gated_pct = [float(w.rejected_peaks)/(w.rejected_peaks+w.total_event_count) for w in wells if w.total_event_count > self.accepted_event_cutoff]
        return 100*np.mean(gated_pct), 100*np.std(gated_pct)

    @property
    def rejected_peak_pct_95(self):
        """
        Returns the 95% confidence interval of the percentage of events
        per well that were rejected (peaks were not processed)

        :rtype: tuple (low_ci, high_ci)
        """
        wells = self.all_well_metrics
        gated_pct = [float(w.rejected_peaks)/(w.rejected_peaks+w.total_event_count) for w in wells if w.total_event_count > self.accepted_event_cutoff]
        if not gated_pct:
            return (0, 0)
        return 100*percentile(gated_pct, 0.025), 100*percentile(gated_pct, 0.975)

    @property
    def null_linkage_mean_variance_ci95(self):
        wells = self.null_linkage_wells
        return AnalysisGroupMetrics.attr_mean_variance_ci95(wells, 'null_linkage')

    @property
    def null_linkage_wells_sub1(self):
        return [wm for wm in self.null_linkage_wells if wm.null_linkage < 1]

    def colorcomp_sample_wells(self, sample):
        """
        Return the wells in multi-well colorcomp plates of the specified name (such as
        FAM HI, VIC HI, etc.)

        :rtype: WellMetric[]
        """
        colorcomp_plates = self.plate_metrics_by_plate_type(('bcc','mfgcc'))
        if not colorcomp_plates:
            return []
        last_plate = sorted(colorcomp_plates, key=lambda pm: pm.plate.run_time)[-1]

        if not isinstance(sample, basestring):
            return [w for w in last_plate.well_metrics if w.well.sample_name in sample]
        else:
            return [w for w in last_plate.well_metrics if w.well.sample_name == sample]

    def singlewell_colorcomp_well(self, dyeset):
        """
        Return the latest singlewell colorcomp well in the group with the specified dyeset
        (FAM/VIC, FAM/HEX)

        :param dyeset: string, FAM/VIC or FAM/HEX
        :rtype: WellMetric
        """
        singlewell_plate = self.singlewell_colorcomp_plate(dyeset)
        if not singlewell_plate:
            return None
        return [w for w in singlewell_plate.well_metrics if w.well.sample_name == dyeset][-1]

    def singlewell_colorcomp_plate(self, dyeset):
        """
        Return the latest singlewell colorcomp plate in the group with the specified dyeset
        (FAM/VIC, FAM/HEX)

        :param dyeset: string, FAM/VIC or FAM/HEX
        :rtype: PlateMetric
        """
        singlewell_plates = self.singlewell_colorcomp_plates
        if not singlewell_plates:
            return None
        # find most recent 'FAM/VIC' sample, then most recent 'FAM/HEX' sample.
        for plate in reversed(sorted(singlewell_plates, key=lambda pm: pm.plate.run_time)):
            fv = [fv for fv in plate.well_metrics if fv.well.sample_name == dyeset]
            if len(fv) > 0:
                return plate

    @property
    def singlewell_colorcomp_plates(self):
        """
        Return the single-well colorcal plates in the group.

        :rtype: WellMetric[]
        """
        return self.plate_metrics_by_plate_type('scc')

    @property
    def singlewell_famvic_colorcomp_plate(self):
        """
        Return the latest singlewell FAM/VIC colorcomp plate in the group.

        :rtype: PlateMetric
        """
        return self.singlewell_colorcomp_plate('FAM/VIC')

    @property
    def singlewell_famhex_colorcomp_plate(self):
        """
        Return the latest singlewell FAM/HEX colorcomp plate in the group.

        :rtype: PlateMetric
        """
        return self.singlewell_colorcomp_plate('FAM/HEX')

    @property
    def singlewell_famvic_colorcomp_well(self):
        """
        Return the latest singlewell FAM/VIC colorcomp well in the group.

        :rtype: WellMetric
        """
        return self.singlewell_colorcomp_well('FAM/VIC')

    @property
    def singlewell_famhex_colorcomp_well(self):
        """
        Return the latest singlewell FAM/HEX colorcomp plate in the group.

        :rtype: WellMetric
        """
        return self.singlewell_colorcomp_well('FAM/HEX')

    @property
    def colorcomp_fam_high_wells(self):
        """
        Returns the multi-well colorcal FAM HI wells.

        :rtype: WellMetric[]
        """
        return [w for w in self.colorcomp_wells if w.well.sample_name in ('FAM 350nM', 'FAM HI')]

    @property
    def colorcomp_vic_high_wells(self):
        """
        Returns the multi-well colorcal VIC HI wells.

        :rtype: WellMetric[]
        """
        return [w for w in self.colorcomp_wells if w.well.sample_name in ('VIC 350nM', 'VIC HI')]

    def colorcomp_amplitude_stats(self, sample, channel_num):
        """
        Returns the mean and standard deviations of the
        amplitudes of colorcomp wells with the specified
        sample name.

        :param sample: The name of the sample to filter by.
        :param channel_num: Which channel to measure.
        :rtype: (mean amplitude mean, mean amplitude stdev)
        """
        wells = self.colorcomp_sample_wells(sample)
        # scale both mean, stdev
        means = []
        stdevs = []

        # this is for the four wells FAM/VIC.
        # does not account for HEX or adjusted/artificially boosted dyes
        # (see singlewell_colorcomp_amplitude_stats below)
        for wm in wells:
            mean = wm.well_channel_metrics[channel_num].amplitude_mean
            stdev = wm.well_channel_metrics[channel_num].amplitude_stdev
            if channel_num == 0 and wm.plate_metric.software_pmt_gain_fam:
                means.append(mean/wm.plate_metric.software_pmt_gain_fam)
                stdevs.append(stdev/wm.plate_metric.software_pmt_gain_fam)
            elif channel_num == 1 and wm.plate_metric.software_pmt_gain_vic:
                means.append(mean/wm.plate_metric.software_pmt_gain_vic)
                stdevs.append(stdev/wm.plate_metric.software_pmt_gain_vic)
            else:
                means.append(mean)
                stdevs.append(stdev)
        if len(means) == 0:
            return (None, None)
        return (np.mean(means), np.mean(stdevs))

    def singlewell_colorcomp_amplitude_stats(self, dyeset):
        """
        Return:

        blue HI mean, blue HI stdev,
        blue LO mean, blue LO stdev,
        green HI mean, green HI stdev,
        green LO mean, green LO stdev
        """
        # unrecoginized dye set
        if dyeset not in (('FAM/VIC','FAM/HEX')):
            return [None, None, None, None, None, None, None, None]
        well = self.singlewell_colorcomp_well(dyeset)

        # no well found
        if not well:
            return [None, None, None, None, None, None, None, None]
 
        # if we are missing any droplet poputation...
        if (  not well.well_channel_metrics[0].positive_mean  
           or not well.well_channel_metrics[1].positive_mean 
           or not well.well_channel_metrics[0].negative_mean
           or not well.well_channel_metrics[1].negative_mean ):
            return [None, None, None, None, None, None, None, None]


        if not well.plate_metric.software_pmt_gain_fam:
            fam_gain = 1.0
        else:
            fam_gain = well.plate_metric.software_pmt_gain_fam
        if not well.plate_metric.software_pmt_gain_vic:
            vic_gain = 1.0
        else:
            vic_gain = well.plate_metric.software_pmt_gain_vic

        # in the case where no new CCM is stored and thus there is
        # no software gain on the CCM, and the dye is HEX, factor
        # out an artificial software boost of 10000/8600
        if vic_gain == 1.0 and dyeset == 'FAM/HEX':
            # in this case, the vic_gain is 10000/8600,
            # as it is factored into the CCM
            vic_gain = HEX_SCALE_FACTOR

        return (well.well_channel_metrics[0].positive_mean/fam_gain,
                well.well_channel_metrics[0].positive_stdev/fam_gain,
                well.well_channel_metrics[0].negative_mean/fam_gain,
                well.well_channel_metrics[0].negative_stdev/fam_gain,
                well.well_channel_metrics[1].positive_mean/vic_gain,
                well.well_channel_metrics[1].positive_stdev/vic_gain,
                well.well_channel_metrics[1].negative_mean/vic_gain,
                well.well_channel_metrics[1].negative_stdev/vic_gain)

    def singlewell_colorcomp_delta_widths(self, dyeset):
        """
        Return: blue HI mean width - green HI mean width
        """

        if dyeset not in (('FAM/VIC','FAM/HEX')):
            return None
        
        well = self.singlewell_colorcomp_well(dyeset)
        if not well:
            return None

        """

        if (  well.well_channel_metrics[0].width_mean_hi is None \
           or well.well_channel_metrics[1].width_mean_hi is None ):
            return None
        
        delta_widths = well.well_channel_metrics[0].width_mean_hi \
                     - well.well_channel_metrics[1].width_mean_hi

        return delta_widths
        """
        if ( well.delta_widths is None ):
            return None
        else:
            return well.delta_widths


    @property
    def carryover_plate_metrics(self):
        """
        Return the plate metrics for carryover plates in the group.

        :rtype: PlateMetric[]
        """
        return self.plate_metrics_by_plate_type(('bcarry','mfgco'))

    @property
    def events_plate_metrics(self):
        """
        Return the plate metrics for event count beta plates in the group.

        :rtype: PlateMetric[]
        """
        return self.plate_metrics_by_plate_type('betaec')

    @property
    def probe_events_plate_metrics(self):
        """
        Return the plate metrics for probe event count plates in the group.

        :rtype: PlateMetric[]
        """
        return self.plate_metrics_by_plate_type('probeec')

    @property
    def eva_events_plate_metrics(self):
        """
        Return the plate metrics for Eva event count plates in the group.

        :rtype: PlateMetric[]
        """
        return self.plate_metrics_by_plate_type('evaec')

    @property
    def colorcomp_plate_metrics(self):
        """
        Return the plate metrics for multi-well colorcomp plates in the group.

        :rtype: PlateMetric[]
        """
        return self.plate_metrics_by_plate_type(('bcc','mfgcc'))

    @property
    def total_carryover_stats(self):
        """
        Return carryover-specific statistics for carryover plates in
        the group.

        :rtype: list (#plates, total carryover peaks, total gated contamination,
                      total contamination, #total stealth wells)
        """
        plates = self.carryover_plate_metrics
        return [len(plates)]+[sum([p.carryover_peaks or 0 for p in plates]),
                              sum([p.gated_contamination_peaks or 0 for p in plates]),
                              sum([p.contamination_peaks or 0 for p in plates]),
                              sum([p.stealth_wells or 0 for p in plates])]

    @property
    def carryover_eventful_wells(self):
        """
        Return eventful (non-stealth) wells in carryover plates.

        :rtype: WellMetric[]
        """
        wm = self.well_metrics_by_type(('bcarry','mfgco'))
        return [w for w in wm if not w.well.sample_name or w.well.sample_name.lower() != 'stealth']

    @property
    def carryover_stealth_wells(self):
        """
        Return stealth wells in carryover plates.

        :rtype: WellMetric[]
        """
        wm = self.well_metrics_by_type(('bcarry','mfgco'))
        return [w for w in wm if w.well.sample_name and w.well.sample_name.lower() == 'stealth']

    @property
    def carryover_eventful_rejected_peaks_ci95(self):
        """
        Return mean, variance, and confidence interval of the number of
        rejected peaks in non-stealth carryover wells.

        :rtype: (mean, stdev, low_ci, high_ci)
        """
        return AnalysisGroupMetrics.attr_mean_variance_ci95(self.carryover_eventful_wells, 'rejected_peaks')

    @property
    def carryover_stealth_rejected_peaks_ci95(self):
        """
        Return mean, variance, and confidence interval of the number of
        rejected peaks in stealth carryover wells.

        :rtype: (mean, stdev, low_ci, high_ci)
        """
        return AnalysisGroupMetrics.attr_mean_variance_ci95(self.carryover_stealth_wells, 'rejected_peaks')

    @property
    def short_droplet_spacing_ci95(self):
        """
        Return mean, variance, and confidence interval of the percentage of events
        that are 'close' in eventful wells in the group.

        :rtype: (mean, stdev, low_ci, high_ci)
        """
        wells = AnalysisGroupMetrics.triggered_eventful(self.all_well_metrics, 100)
        short_ratios = [float(w.short_interval_count)/w.triggered_event_count for w in wells if w.short_interval_count is not None and w.triggered_event_count > 0]
        if not short_ratios:
            return (0, 0, 0, 0)
        mean = np.mean(short_ratios)
        stdev = np.std(short_ratios)
        ci025, ci975 = percentile(short_ratios, .025), percentile(short_ratios, .975)
        return (mean, stdev, ci025, ci975)

    def analyzed_channel_stats(self, well_metrics, channel_num, attr):
        """
        Returns the mean, variance, ci95 for the attr over the specified channel for the specified
        wells, provided the attribute for that channel was populated with a non-None value.
        """
        wells = [w for w in well_metrics if getattr(w.well_channel_metrics[channel_num], attr) is not None]
        return AnalysisGroupMetrics.channel_attr_mean_variance_ci95(wells, channel_num, attr)

    def polydispersity_fam_stats(self, well_metrics):
        """
        Mean, stdev and confidence interval of the ratio of polydisperse droplets
        in the FAM channel for the specified wells.

        :param well_metrics: WellMetric[]
        :rtype: (mean, stdev, low_ci, high_ci)
        """
        return self.analyzed_channel_stats(well_metrics, 0, 'polydispersity')

    def polydispersity_vic_stats(self, well_metrics):
        """
        Mean, stdev and confidence interval of the ratio of polydisperse droplets
        in the VIC channel for the specified wells.

        :param well_metrics: WellMetric[]
        :rtype: (mean, stdev, low_ci, high_ci)
        """
        return self.analyzed_channel_stats(well_metrics, 1, 'polydispersity')

    def polydispersity_revb_fam_stats(self, well_metrics):
        """
        Mean, stdev and confidence interval of the ratio of polydisperse droplets
        in the FAM channel for the specified wells.  The ratio is calculated
        using the amplitude-bin width gates, and not min/max width gates for the well.

        :param well_metrics: WellMetric[]
        :rtype: (mean, stdev, low_ci, high_ci)
        """
        return self.analyzed_channel_stats(well_metrics, 0, 'revb_polydispersity')

    def polydispersity_revb_vic_stats(self, well_metrics):
        """
        Mean, stdev and confidence interval of the ratio of polydisperse droplets
        in the VIC channel for the specified wells.  The ratio is calculated
        using the amplitude-bin width gates, and not min/max width gates for the well.

        :param well_metrics: WellMetric[]
        :rtype: (mean, stdev, low_ci, high_ci)
        """
        return self.analyzed_channel_stats(well_metrics, 1, 'revb_polydispersity')

    def extracluster_fam_stats(self, well_metrics):
        """
        Mean, stdev and confidence interval of the ratio of extracluster droplets
        in the FAM channel for the specified wells.

        :param well_metrics: WellMetric[]
        :rtype: (mean, stdev, low_ci, high_ci)
        """
        return self.analyzed_channel_stats(well_metrics, 0, 'extracluster')

    def extracluster_revb_fam_stats(self, well_metrics):
        """
        Mean, stdev and confidence interval of the ratio of extracluster droplets
        in the FAM channel for the specified wells.  The boundaries are computed
        using the amplitude-bin width gates.

        :param well_metrics: WellMetric[]
        :rtype: (mean, stdev, low_ci, high_ci)
        """
        return self.analyzed_channel_stats(well_metrics, 0, 'extracluster')

    def extracluster_vic_stats(self, well_metrics):
        """
        Mean, stdev and confidence interval of the ratio of extracluster droplets
        in the VIC channel for the specified wells.

        :param well_metrics: WellMetric[]
        :rtype: (mean, stdev, low_ci, high_ci)
        """
        return self.analyzed_channel_stats(well_metrics, 1, 'revb_extracluster')

    def extracluster_revb_vic_stats(self, well_metrics):
        """
        Mean, stdev and confidence interval of the ratio of extracluster droplets
        in the FAM channel for the specified wells.  The boundaries are computed
        using the amplitude-bin width gates.

        :param well_metrics: WellMetric[]
        :rtype: (mean, stdev, low_ci, high_ci)
        """
        return self.analyzed_channel_stats(well_metrics, 1, 'revb_extracluster')

    @property
    def polydispersity_all_fam_stats(self):
        """
        Mean, stdev and confidence interval of the ratio of polydisperse droplets
        in the FAM channel for all wells in the group.

        :rtype: (mean, stdev, low_ci, high_ci)
        """
        return self.polydispersity_fam_stats(self.all_well_metrics)

    @property
    def polydispersity_all_vic_stats(self):
        """
        Mean, stdev and confidence interval of the ratio of polydisperse droplets
        in the VIC channel for all wells in the group.

        :rtype: (mean, stdev, low_ci, high_ci)
        """
        return self.polydispersity_vic_stats(self.all_well_metrics)

    @property
    def extracluster_all_fam_stats(self):
        """
        Mean, stdev and confidence interval of the ratio of extracluster droplets
        in the FAM channel for all wells in the group.

        :rtype: (mean, stdev, low_ci, high_ci)
        """
        return self.extracluster_fam_stats(self.all_well_metrics)

    @property
    def extracluster_all_vic_stats(self):
        """
        Mean, stdev and confidence interval of the ratio of extracluster droplets
        in the VIC channel for all wells in the group.

        :rtype: (mean, stdev, low_ci, high_ci)
        """
        return self.extracluster_vic_stats(self.all_well_metrics)

    def gap_rain_fam_stats(self, well_metrics):
        """
        Returns mean, stdev, low_ci, high_ci and number of wells
        with a FAM gap rain count of greater than 0, from the specified wells.

        :param well_metrics: WellMetric[]
        :rtype: (mean, stdev, low_ci, high_ci, well_count)
        """
        wells = self.fam_gap_rain_wells
        stats = list(AnalysisGroupMetrics.channel_attr_mean_variance_ci95(wells, 0, 'gap_rain_droplets'))
        stats.append(len([w for w in wells if w.well_channel_metrics[0].gap_rain_droplets > 0]))
        stats.append(len(wells))
        return stats

    def gap_rain_vic_stats(self, well_metrics):
        """
        Returns mean, stdev, low_ci, high_ci and number of wells
        with a VIC gap rain count of greater than 0, from the specified wells.

        :param well_metrics: WellMetric[]
        :rtype: (mean, stdev, low_ci, high_ci, well_count)
        """
        wells = self.vic_gap_rain_wells
        stats = list(AnalysisGroupMetrics.channel_attr_mean_variance_ci95(wells, 1, 'gap_rain_droplets'))
        stats.append(len([w for w in wells if w.well_channel_metrics[1].gap_rain_droplets > 0]))
        stats.append(len(wells))
        return stats

    @property
    def gap_rain_all_fam_stats(self):
        """
        Returns mean, stdev, low_ci, high_ci and number of wells
        with a FAM gap rain count of greater than 0.

        :rtype: (mean, stdev, low_ci, high_ci, well_count)
        """
        return self.gap_rain_fam_stats(self.all_well_metrics)

    @property
    def gap_rain_all_vic_stats(self):
        """
        Returns mean, stdev, low_ci, high_ci and number of wells
        with a VIC gap rain count of greater than 0.

        :rtype: (mean, stdev, low_ci, high_ci, well_count)
        """
        return self.gap_rain_vic_stats(self.all_well_metrics)

    @property
    def fam_gap_rain_wells(self):
        """
        Returns the set of wells where the FAM gap rain (number
        of events at low amplitude in between fluorescent droplet
        packs) is greater than 0.

        :rtype: WellMetric[]
        """
        return [w for w in self.all_well_metrics if w.well_channel_metrics[0].gap_rain_droplets is not None]

    @property
    def vic_gap_rain_wells(self):
        """
        Returns the set of wells where the VIC gap rain (number
        of events at low amplitude in between fluorescent droplet
        packs) is greater than 0.

        :rtype: WellMetric[]
        """
        return [w for w in self.all_well_metrics if w.well_channel_metrics[1].gap_rain_droplets is not None]

    @property
    def ok_carryover_eventful_wells(self):
        """
        Returns the set of wells in a carryover beta plate where
        a threshold was drawn.

        :rtype: WellMetric[]
        """
        return [w for w in self.carryover_eventful_wells if w.well_channel_metrics[0].threshold]

    @property
    def air_droplets_wells(self):
        """
        Returns the set of wells where we should be looking for computed air droplets.  This should
        be carryover non-stealth wells, singleplex plate wells, and event count plate wells.

        Kind of deprecated...

        :rtype: WellMetric[]
        """
        return (self.ok_carryover_eventful_wells or []) + \
               (self.singleplex_wells or []) + \
               (self.event_count_wells or [])

    @property
    def air_droplets_stats(self):
        """
        Mean, standard deviation, and confidence interval of observed air
        droplets.  Air droplets are gap rain in FAM for eligible plates.

        :rtype: (mean, stdev, low_ci, high_ci)
        """
        wells = self.air_droplets_wells
        if not wells:
            return (0, 0, 0, 0)
        return AnalysisGroupMetrics.attr_mean_variance_ci95(wells, 'air_droplets')

    @property
    def air_droplet_count_test(self):
        """
        Number of wells with observed air droplets among the eligible group,
        and then total number of air-detectable wells.
        """
        wells = self.air_droplets_wells
        return (len([w for w in wells if w.air_droplets]), len(wells))

    @property
    def carryover_air_droplet_stats(self):
        """
        Mean, standard deviation, and confidence interval of air
        in carryover plates.

        :rtype: (mean, stdev, low_ci, high_ci)
        """
        wells = self.ok_carryover_eventful_wells
        return AnalysisGroupMetrics.attr_mean_variance_ci95(wells, 'air_droplets')

    @property
    def carryover_air_droplet_count_test(self):
        """
        Number of wells with observed air droplets among carryover plates,
        and then total number of wells in carryover plates.
        """
        wells = self.ok_carryover_eventful_wells
        return (len([w for w in wells if w.air_droplets]), len(wells))

    @property
    def carryover_event_middle_rain_stats(self):
        """
        Mean, standard deviation, and confidence interval of middle rain
        ratio in eventful (non-stealth) carryover wells.

        :rtype: (mean, stdev, low_ci, high_ci)
        """
        wells = self.ok_carryover_eventful_wells
        return AnalysisGroupMetrics.channel_attr_mean_variance_ci95(wells, 0, 'rain_p')

    @property
    def carryover_event_negative_rain_stats(self):
        """
        Mean, standard deviation, and confidence interval of negative rain
        ratio in eventful (non-stealth) carryover wells.

        :rtype: (mean, stdev, low_ci, high_ci)
        """
        wells = self.ok_carryover_eventful_wells
        return AnalysisGroupMetrics.channel_attr_mean_variance_ci95(wells, 0, 'rain_p_minus')


class DRCertificationMetrics(AnalysisGroupMetrics):
    """
    Extension of GroupMetrics that looks for the last plate of a particular type
    per reader, and uses that as the group from which to calculate aggregate
    metrics.  Selectors and filters are also a little more specific to
    manufacturing reader plate layouts.
    """

    def __init__(self, dr_id, **kwargs):
        self.reprocess_config_id = None
        self.dr_id = dr_id
    
        pm = Session.query(PlateMetric).join(Plate, PlateType)\
                                       .filter(and_(PlateMetric.reprocess_config_id==self.reprocess_config_id,
                                                    Plate.box2_id == dr_id,
                                                    PlateType.code.in_(('bcarry','bcc', 'betaec','mfgco','mfgcc','scc','probeec','evaec')),
                                                    or_(Plate.onsite == None, not_(Plate.onsite)),
                                                    or_(Plate.mfg_exclude == None, not_(Plate.mfg_exclude))))\
                    .options(joinedload_all(PlateMetric.plate, Plate.plate_type),
                             joinedload_all(PlateMetric.plate, Plate.box2, innerjoin=True),
                             joinedload_all(PlateMetric.well_metrics, WellMetric.well_channel_metrics, innerjoin=True),
                             joinedload_all(PlateMetric.well_metrics, WellMetric.well, QLBWell.plate, innerjoin=True)).all()

        self.plate_filter = kwargs.get('plate_filter', lambda p: p)
        self.plate_type_filter = kwargs.get('plate_type_filter', lambda pt: pt)
        self.well_filter = kwargs.get('well_filter', lambda w: w)
        self.well_metric_filter = kwargs.get('well_metric_filter', lambda wm: wm)
       
        ## this sets the metric type from the plate, put maybe it should by by the DR! 
        if ( len(pm) and pm[-1].plate.qlbplate.system_version is not None ):
            sv_id = pm[-1].plate.qlbplate.system_version
            self.system_version = Session.query(SystemVersion).get(sv_id).type
        else:
            self.system_version = 'QX100';

        if pm: #added by Richard
            self.program_version = pm[0].plate.program_version 
        else:
            self.program_version = None

        ## make param loading generic...
        self.load_config_params( code= self.system_version, **kwargs )

        plate_metrics = [p for p in pm if self.plate_filter(p.plate) and self.plate_type_filter(p.plate.plate_type)]
        self.all_plate_metrics = self.__most_recent_plate_filter(plate_metrics)
        self.metric_plates = [pm.plate for pm in self.all_plate_metrics]

    def __most_recent_plate_filter(self, plate_metrics):
        # mfgco/bcarry are the same;
        # mfgcc/bcc are the same
        # this is a terrible hack
        # I'm so sorry, why did I introduce two different types
        #
        # ...
        secondary_dict = defaultdict()
        plate_types = Session.query(PlateType).filter(PlateType.code.in_(('bcarry','bcc','mfgcc','mfgco','scc'))).all()
        bcarry = [p for p in plate_types if p.code == 'bcarry'][0]
        bcc    = [p for p in plate_types if p.code == 'bcc'][0]
        mfgco  = [p for p in plate_types if p.code == 'mfgco'][0]
        mfgcc  = [p for p in plate_types if p.code == 'mfgcc'][0]
        scc  = [p for p in plate_types if p.code == 'scc']

        secondary_dict = defaultdict(lambda: lambda i: i,
            {bcarry.id: lambda i: mfgco.id,
             bcc.id: lambda i: mfgcc.id})

        plate_type_dict = dict()
        ## check and add most recent version of scc SCC
            ## broken as is (plates not yet set...), try to phenocopy methods to get one vic and one hex.

        scc_plate_metrics = []
        for dyeset in ['FAM/VIC', 'FAM/HEX']:
            for plate_metric in reversed(sorted( plate_metrics, key=lambda pm: pm.plate.run_time)):
                if ( plate_metric.plate.plate_type_code != 'scc' ):
                    continue
                elif ( any( [wm.well.sample_name == dyeset for wm in plate_metric.well_metrics] ) ):
                    #add first instance of plate with dyset and is scc...
                    scc_plate_metrics.append( plate_metric )
                    break

        ## sets most recent version of each plate....
        for pm in plate_metrics:
            # skip scc -- allow all since multiple readings may be in diff plates
            if pm.plate.plate_type_code == 'scc':
                # scc_plate_metrics.append(pm)
                continue
            key = secondary_dict[pm.plate.plate_type.id](pm.plate.plate_type.id)
            old_plate = plate_type_dict.get(key, None)
            if not old_plate or old_plate.plate.run_time < pm.plate.run_time:
                plate_type_dict[key] = pm

        pms = plate_type_dict.values()
        # add back in all scc plates, as multiple plates may be necessary
        pms.extend(scc_plate_metrics)
        return pms
    
    def get_amplitude_stat_func( self, amplitude, variablitiy ):
        """
        Generates the function needed to determine if a given amplitude passes spec

        :rtype: a function that takes one variable (int)
        """
        maxAmpDelta = float( amplitude ) * ( float(variablitiy) / 100)
        return lambda val: abs(val-amplitude) <= maxAmpDelta

    @property
    def singleplex_wells(self):
        """
        Uses carryover eventful wells to perform singleplex calculations.

        :rtype: WellMetric[]
        """
        wm = self.well_metrics_by_type(('bcarry','mfgco'))
        return [w for w in wm if w.well.sample_name not in ('stealth', 'Stealth')]

    @property
    def air_droplets_wells(self):
        """
        Uses carryover eventful wells to perform air droplet calculations.

        :rtype: WellMetric[]
        """
        ce = self.ok_carryover_eventful_wells
        ec = self.well_metrics_by_type('betaec')
        return ce + ec

    def __test_event_count_mean(self, ec = None, ec_spec = None):
        """
        Returns whether or not the well group passes the event count spec.
        :input: ec : event count plates to process
                ec_spec : Min ev value to consider
        :rtype: (mean event count, test desc, whether test passed)
        """
        if not ec:
            ec = self.event_count_wells
        if not ec_spec:
            ec_spec = self.low_event_count
        stats = AnalysisGroupMetrics.attr_mean_variance_ci95(ec, 'accepted_event_count')
        return (int(stats[0]), '> %d' % ec_spec, stats[0] > ec_spec, ec_spec)

    @property
    def test_event_count_mean(self):
        """
        Returns whether or not the well group passes the event count spec.

        :rtype: (mean event count, test desc, whether test passed)
        """
        ec = self.event_count_wells
        ec_spec = self.low_event_count
        
        return self.__test_event_count_mean( ec, ec_spec )

    @property
    def test_probe_event_count_mean(self):
        """
        Returns whether or not the well group passes the event count spec.

        :rtype: (mean event count, test desc, whether test passed)
        """
        ec = self.probe_event_count_wells
        ec_spec = self.low_event_count

        return self.__test_event_count_mean( ec, ec_spec )

    @property
    def test_eva_event_count_mean(self):
        """
        Returns whether or not the well group passes the event count spec.

        :rtype: (mean event count, test desc, whether test passed)
        """
        ec = self.eva_event_count_wells
        ec_spec = self.low_event_count_eva

        return self.__test_event_count_mean( ec, ec_spec )

    @property
    def test_carryover_event_count_mean(self):
        """
        Returns whether or not the well group passes the event count spec.
        Excludes eventful carryover plates only wells from the calculation.

        :rtype: (mean event count, spec desc, whether test passed)
        """
        ec = self.carryover_eventful_wells
        ec_spec = self.low_event_count
        return self.__test_event_count_mean( ec, ec_spec )
        #ec = [w for w in ec if w.well.sample_name not in EXPECTED_LOW_EVENT_WELLS]
        #stats = AnalysisGroupMetrics.attr_mean_variance_ci95(ec, 'accepted_event_count')
        #return (int(stats[0]), '> %s' % self.low_event_count, stats[0] > self.low_event_count)

    @property
    def test_noncolorcomp_event_count_mean(self):
        """
        Depricated
        Returns whether or not the well group passes the event count spec.
        Excludes colorcomp wells from the calculation.

        :rtype: (mean event count, spec desc, whether test passed)
        """
        ec = self.well_metrics_excluding_type(('bcc','mfgcc','scc'))
        ec = [w for w in ec if w.well.sample_name not in EXPECTED_LOW_EVENT_WELLS]
        ec_spec = self.low_event_count
        return self.__test_event_count_mean( ec, ec_spec )
        #stats = AnalysisGroupMetrics.attr_mean_variance_ci95(ec, 'accepted_event_count')
        #return (int(stats[0]), '> %s' % self.low_event_count, stats[0] > self.low_event_count)

    def _test_event_count_low(self, ec_wells, low_count, lef_num, lef_den):
        """
        Returns whether or not the well group passes the spec for allowed low
        event count wells.
        :param ec_well: list of qlwell objects
        :param low_count: int for the minim number of accepted events to 'pass'
        :param lef_num: num for low event count wells metricc
        :param lef_den: denomitator for low event count wells metric
    
        :rtype: (# low wells/# total, spec desc, whether test passed)
        """
        low = len([w for w in ec_wells if w.accepted_event_count < low_count])

        ## process results
        message = '<= %s/%s' % (lef_num, int(lef_den))
        if ( len( ec_wells) > 0 ):
            test_result = low/float( len(ec_wells) ) <= float(lef_num) / lef_den
        else:
            test_result = False

        return ('%s/%s' % (low, len(ec_wells)), message, test_result, low_count)

    @property
    def test_event_count_low(self):
        """
        Returns whether or not the well group passes the spec for allowed low
        event count wells.

        :rtype: (# low wells/# total, spec desc, whether test passed)
        """
        ## specs for plate/DR
        lef_num = self.low_event_fail_numerator
        lef_den = self.low_event_fail_denominator
        low_count = self.low_event_count

        ## filter wells
        ec_wells = self.event_count_wells
        
        return self._test_event_count_low( ec_wells, low_count, lef_num, lef_den )
        
    @property
    def test_probe_event_count_low(self):
        """
        Returns whether or not the well group passes the spec for allowed low
        event count wells.

        :rtype: (# low wells/# total, spec desc, whether test passed)
        """
        ## specs for plate/DR
        lef_num   = self.probe_event_fail_numerator
        lef_den   = self.probe_event_fail_denominator
        low_count =  self.low_event_count
    
        ## filter wells
        ec_wells = self.probe_event_count_wells

        return self._test_event_count_low( ec_wells, low_count, lef_num, lef_den )

    @property
    def test_eva_event_count_low(self):
        """
        Returns whether or not the well group passes the spec for allowed low
        event count wells.

        :rtype: (# low wells/# total, spec desc, whether test passed)
        """
        ## specs for plate/DR
        lef_num   = self.eva_event_fail_numerator
        lef_den   = self.eva_event_fail_denominator
        low_count =  self.low_event_count_eva

        ## filter wells
        ec_wells = self.eva_event_count_wells

        return self._test_event_count_low( ec_wells, low_count, lef_num, lef_den )    

    @property
    def test_colorcomp_event_count_low(self):
        """
        Returns whether or not the well group passes the spec for allowed low
        event count wells (in color comp wells)

        :rtype: (# low wells/# total, spec desc, whether test passed)
        """
        ## specs for plate/DR
        lef_num = self.cc_low_event_fail_numerator
        lef_den = self.cc_low_event_fail_denominator
        low_count =  self.low_event_count

        ## filter wells
        cc_wells = self.colorcomp_wells

        ## get results
        return self._test_event_count_low( cc_wells, low_count, lef_num, lef_den )

    @property
    def test_carryover_event_count_low(self):
        """
        Returns whether or not the well group passes the spec for allowed low
        event count wells (in carryover plates)

        :rtype: (# low wells/# total, spec desc, whether test passed)
        """
        ## specs for plate/DR
        lef_num = self.ncc_low_event_fail_numerator
        lef_den = self.ncc_low_event_fail_denominator
        low_count =  self.low_event_count

        ## filterwells
        ec_wells = self.carryover_eventful_wells
        #ec_wells = [w for w in ec if w.well.sample_name not in EXPECTED_LOW_EVENT_WELLS]

        ## get results
        return self._test_event_count_low( ec_wells, low_count, lef_num, lef_den )

    @property
    def test_noncolorcomp_event_count_low(self):
        """
        Depricated
        Returns whether or not the well group passes the spec for allowed low
        event count wells (in non-color comp wells)

        :rtype: (# low wells/# total, spec desc, whether test passed)
        """
        ## specs for plate/DR
        lef_num = self.ncc_low_event_fail_numerator
        lef_den = self.ncc_low_event_fail_denominator
        low_count =  self.low_event_count

        ## filterwells
        ec = self.well_metrics_excluding_type(('bcc','mfgcc','scc'))
        ec_wells = [w for w in ec if w.well.sample_name not in EXPECTED_LOW_EVENT_WELLS]

        ## get results
        return self._test_event_count_low( ec_wells, low_count, lef_num, lef_den )

    @property
    def test_quality_low(self):
        """
        Returns whether or not the well group passes the spec for allowed low
        data quality wells

        :rtype: (# low-quality wells/# total, spec desc, whether test passed)
        """
        lq_num = self.low_quality_fail_numerator
        lq_den = self.low_quality_fail_denominator

        q = self.low_quality_wells
        e = self.quality_eligible_wells
    
        message = '<= %s/%s' % ( lq_num, int(lq_den) )
        if ( len(e) > 0 ):
            test_result = len(q)/float( len(e) ) <= lq_num / lq_den
        else:
            test_result = False

        return ('%s/%s' % (len(q), len(e)), message, test_result)

    @property
    def test_singleplex_uniformity(self):
        """
        Returns whether or not the well group passes the spec for variability
        in singleplex concentration.

        :rtype: (conc confidence interval spread/mean, spec desc, whether test passed)
        """
        UniformityPct = self.SingUniformityPct 

        ## need to ignore lowquality wells...

        message = '< %d%% of mean' % UniformityPct

        s = self.all_singleplex_conc_ci95

        test_result = False
        if s[2] is None or s[1] is None:
            var = float('nan')
        else:
            var = s[2]-s[1]
        mean = s[0]

        if math.isnan(mean) or math.isnan(var) or not mean:
            diff = float('nan')
        else:
            diff = var/float(mean)
            test_result = abs( diff ) < UniformityPct/100.0

        return ( diff, message, test_result )

    def test_fam350_amplitude(self, plate_type_code=None, qc_plate=False):
        """
        Returns whether or not the well group passes the spec for FAM HI
        mean amplitude

        :rtype: (FAM HI mean amp, spec desc, whether test passed)
        """
        AmpSpec = self.FamAmp350
        AmpVar =  self.Ch1AmpVariationPct

        ## update percent and message
        if qc_plate:
            AmpVar = self.Ch1AmpVariationPctQC
            stat_desc = str(AmpSpec) + " +/- " + str(AmpVar) + "% (QC)"
        elif(plate_type_code == 'fvtitr'):
            AmpVar = self.Ch1AmpVariationPctQC
            stat_desc = str(AmpSpec) + " +/- " + str(AmpVar) + "%"
        else:
            stat_desc = str(AmpSpec) + " +/- " + str(AmpVar) + "%"
        
        ## generate the stats function
        stat_func = self.get_amplitude_stat_func( AmpSpec, AmpVar )

        ## get the stats
        if plate_type_code == 'scc' or not plate_type_code:
            stats = self.singlewell_colorcomp_amplitude_stats('FAM/VIC')
            if stats[0] is None:
                stats = self.singlewell_colorcomp_amplitude_stats('FAM/HEX')
            if stats[0] is None:
                stats = self.colorcomp_amplitude_stats(('FAM 350nM', 'FAM HI'), 0)
        
        elif plate_type_code in ('bcc', 'mfgcc'):
            stats = self.colorcomp_amplitude_stats(('FAM 350nM', 'FAM HI'), 0)

        elif plate_type_code == 'fvtitr':
            stats = self.famvic_amplitude_stats(0)    

        ## return results
        if stats[0] is not None:
            return (stats[0], stat_desc, stat_func(stats[0]))
        else:
            return (float('nan'), stat_desc, False)


    def test_qc_fam_lo_amplitude(self, plate_type_code=None):
        """
        Tests the low amplitude for a batch QC plate.
        Spec is 2285 +/- 10%
        """
        AmpSpec = self.FamAmpLo 
        AmpVar  = self.Ch1AmpVariationPct 

        stat_desc = str(AmpSpec) + " +/- " + str(AmpVar) + "% (QC)"
        stat_func =  self.get_amplitude_stat_func( AmpSpec, AmpVar )

        # try single-well first, if not, fall back to multi-well
        if plate_type_code == 'scc' or not plate_type_code:
            # try single-well, then
            stats = self.singlewell_colorcomp_amplitude_stats('FAM/VIC')
            if stats[2] is None:
                stats = self.singlewell_colorcomp_amplitude_stats('FAM/HEX')
            if stats[2] is not None:
                return (stats[2], stat_desc, stat_func(stats[2]))

        # fallback
        stats = self.colorcomp_amplitude_stats(('FAM 40nM', 'FAM LO'), 0)
        if stats[0] is None:
            return (float('nan'), stat_desc, False)
        else:
            return (stats[0], stat_desc, stat_func(stats[0]))


    def test_fam350_cv(self, plate_type_code=None):
        """
        Returns whether or not the well group passes the spec for FAM HI
        amplitude spread

        :rtype: (FAM HI amp stdev, spec desc, whether test passed)
        """
        AmpCV = self.Ch1AmpCV
        stat_desc = '< %0.2f%% amplitude mean' % (100* AmpCV)
        stat_func = lambda std, mean: std/mean < AmpCV

        if plate_type_code == 'scc' or not plate_type_code:
            stats = self.singlewell_colorcomp_amplitude_stats('FAM/VIC')
            if stats[0] is None:
                stats = self.singlewell_colorcomp_amplitude_stats('FAM/HEX')
            
            if stats[0] is not None and stats[0] > 0:
                return (stats[1]/stats[0], stat_desc, stat_func(stats[1], stats[0]))

            stats = self.colorcomp_amplitude_stats(('FAM 350nM', 'FAM HI'), 0)
            if stats[0] is not None and stats[0] > 0:
                return (stats[1]/stats[0], stat_desc, stat_func(stats[1], stats[0]))
            else:
                return (float('nan'), stat_desc, False)
        elif plate_type_code in ('bcc', 'mfgcc'):
            c = self.colorcomp_amplitude_stats(('FAM 350nM', 'FAM HI'), 0)
        elif plate_type_code == 'fvtitr':
            c = self.famvic_amplitude_stats(0)

        if c[0] is None or c[0] == 0:
            return (float('nan'), stat_desc, False)
        else:
            return (c[1]/c[0], stat_desc, stat_func(c[1], c[0]))

    def test_vic350_amplitude(self, plate_type_code=None, qc_plate=False):
        """
        Returns whether or not the well group passes the spec for VIC HI
        mean amplitude

        :rtype: (VIC HI mean amp, spec desc, whether test passed)
        """

        AmpSpec = self.VicAmp350
        AmpVar  = self.Ch2AmpVariationPct

        if qc_plate:
            AmpVar = self.Ch2AmpVariationPctQC
            stat_desc = str(AmpSpec) + " +/- " + str(AmpVar) + "% (QC)"
        elif(plate_type_code == 'fvtitr'):
            AmpVar = self.Ch2AmpVariationPctQC
            stat_desc = str(AmpSpec) + " +/- " + str(AmpVar) + "%"
        else:
            stat_desc = str(AmpSpec) + " +/- " + str(AmpVar) + "%"

        ## generate the stats function
        stat_func = self.get_amplitude_stat_func( AmpSpec, AmpVar )

        ## get the stats
        if plate_type_code == 'scc' or not plate_type_code:
            ## single well cc, Vic data in spot 4....
            stats = self.singlewell_colorcomp_amplitude_stats('FAM/VIC')
            if stats[4] is not None:
                return (stats[4], stat_desc, stat_func(stats[4]))

            stats = self.colorcomp_amplitude_stats(('VIC 350nM', 'VIC HI'), 1)

        elif plate_type_code in ('bcc', 'mfgcc'):
            stats = self.colorcomp_amplitude_stats(('VIC 350nM', 'VIC HI'), 1)

        elif plate_type_code == 'fvtitr':
            stats = self.famvic_amplitude_stats(1)

        ## return results
        if stats[0] is not None:
            return (stats[0], stat_desc, stat_func(stats[0]))
        else:
            return (float('nan'), stat_desc, False)

    def test_qc_vic_lo_amplitude(self, plate_type_code=None):
        """
        Tests the low VIC amplitude for a batch QC plate.
        Spec is 2000 +/- 10%
        """

        AmpSpec = self.VicAmpLo
        AmpVar  = self.Ch2AmpVariationPct

        stat_desc = str(AmpSpec) + " +/- " + str(AmpVar) + "% (QC)"
        stat_func =  self.get_amplitude_stat_func( AmpSpec, AmpVar )

        # try single-well first, if not, fall back to multi-well
        if plate_type_code == 'scc' or not plate_type_code:
            # try single-well, then
            stats = self.singlewell_colorcomp_amplitude_stats('FAM/VIC')
            if stats[6] is not None:
                return (stats[6], stat_desc, stat_func(stats[6]))

        # fallback
        stats = self.colorcomp_amplitude_stats(('VIC 70nM', 'VIC LO'), 1)
        if stats[0] is None:
            return (float('nan'), stat_desc, False)
        else:
            return (stats[0], stat_desc, stat_func(stats[0]))

    def test_vic350_cv(self, plate_type_code=None):
        """
        Returns whether or not the well group passes the spec for VIC HI
        amplitude spread

        :rtype: (FAM HI amp stdev, spec desc, whether test passed)
        """
        AmpCV = self.Ch2AmpCV
        stat_desc = '< %0.2f%% amplitude mean' % (100* AmpCV)
        stat_func = lambda std, mean: std/mean < AmpCV
        
        if plate_type_code == 'scc' or plate_type_code is None:
            stats = self.singlewell_colorcomp_amplitude_stats('FAM/VIC')
            if stats[4] is not None and stats[4] > 0:
                return (stats[5]/stats[4], stat_desc, stat_func(stats[5], stats[4]))

            stats = self.colorcomp_amplitude_stats(('VIC 350nM', 'VIC HI'), 1)
            if stats[0] is not None and stats[0] > 0:
                return (stats[1]/stats[0], stat_desc, stat_func(stats[1], stats[0]))
            else:
                return (float('nan'), stat_desc, False)
        elif plate_type_code in ('bcc', 'mfgcc'):
            c = self.colorcomp_amplitude_stats(('VIC 350nM', 'VIC HI'), 1)
        else:
            c = self.famvic_amplitude_stats(1)

        if c[0] is None or c[0] == 0:
            return (float('nan'), stat_desc, False)
        else:
            return (c[1]/c[0], stat_desc, stat_func(c[1], c[0]))

    def test_hex350_amplitude(self, plate_type_code=None, qc_plate=False):
        """
        Returns whether or not the well group passes the spec for Hex HI
        mean amplitude

        :rtype: (Hex HI mean amp, spec desc, whether test passed)
        """
        AmpSpec = self.HexAmp350
        AmpVar =  self.Ch1AmpVariationPct
        stat_desc = str(AmpSpec) + " +/- " + str(AmpVar) + "%"

        stat_func =  self.get_amplitude_stat_func( AmpSpec, AmpVar )

        if plate_type_code == 'scc' or plate_type_code is None:
            stats = self.singlewell_colorcomp_amplitude_stats('FAM/HEX')
            if stats[4] is not None:
                if qc_plate:
                    disp_stat = "%d (%d scaled)" % (stats[4], stats[4]*HEX_SCALE_FACTOR)
                else:
                    disp_stat = stats[4]
                return (disp_stat, stat_desc, stat_func(stats[4]))
            else:
                return (float('nan'), stat_desc, False)
        else:
            return (float('nan'), stat_desc, False)

    def test_qc_hex_lo_amplitude(self, plate_type_code=None):
        """
        Tests the low HEX amplitude for a batch QC plate.
        Spec is 1620 +/- 20%
        """
        AmpSpec = self.HexAmpLo
        AmpVar  = self.HEXAmpLoVariationPctQC
        stat_desc = str(AmpSpec) + " +/- " + str(AmpVar) + "% (QC)"
        stat_func = self.get_amplitude_stat_func( AmpSpec, AmpVar )

        # try single-well first, if not, fall back to multi-well
        if plate_type_code == 'scc' or not plate_type_code:
            # try single-well, then
            stats = self.singlewell_colorcomp_amplitude_stats('FAM/HEX')
            if stats[6] is not None:
                return ('%d (%d scaled)' % (stats[6], stats[6]*HEX_SCALE_FACTOR), stat_desc, stat_func(stats[6]))

        # fallback
        stats = self.colorcomp_amplitude_stats(('HEX 40nM', 'HEX LO'), 1)
        if stats[0] is None:
            return (float('nan'), stat_desc, False)
        else:
            return ('%d (%d scaled)' % (stats[0], stats[0]*HEX_SCALE_FACTOR), stat_desc, stat_func(stats[0]))

    def test_hex350_cv(self, plate_type_code=None):
        """
        Returns whether or not the well group passes the spec for HEX HI
        amplitude spread

        :rtype: (FAM HI amp stdev, spec desc, whether test passed)
        """
        AmpCV = self.Ch2AmpCV
        stat_desc = '< %0.2f%% amplitude mean' % (100* AmpCV)
        stat_func = lambda std, mean: std/mean < AmpCV

        if plate_type_code == 'scc' or plate_type_code is None:
            stats = self.singlewell_colorcomp_amplitude_stats('FAM/HEX')
            if stats[4] is not None and stats[4] > 0:
                return (stats[5]/stats[4], stat_desc, stat_func(stats[5], stats[4]))
            else:
                return (float('nan'), stat_desc, False)
        else:
            return (float('nan'), stat_desc, False)

    @property
    def test_colorcomp_identity(self):
        """
        Returns whether or not the latest single-well colorcomp matrix
        had the identity matrix saved or not.

        :rtype: (# wells with identity matrix saved, spec desc, whether test passed)
        """
        stat_desc = 'Must be zero'
        stat_func = lambda val: val == 0
        # try an attempt here
        famvic = self.singlewell_colorcomp_plate('FAM/VIC')
        famhex = self.singlewell_colorcomp_plate('FAM/HEX')

        cc_pms = []
        if not famvic and not famhex:
            cc = self.colorcomp_plate_metrics
            if cc:
                cc_pms.append(cc[-1])
        else:
            if famvic:
                cc_pms.append(famvic)
            if famhex:
                cc_pms.append(famhex)

        identity_count = len([pm for pm in cc_pms if (pm.plate.qlbplate.color_compensation_matrix_11 == 1\
                                                 and pm.plate.qlbplate.color_compensation_matrix_12 == 0\
                                                 and pm.plate.qlbplate.color_compensation_matrix_21 == 0\
                                                 and pm.plate.qlbplate.color_compensation_matrix_22 == 1)])
        return ('%s/%s' % (identity_count, len(cc_pms)), stat_desc, stat_func(identity_count))


    @property
    def test_carryover(self):
        """
        Returns whether or not the well group passes the carryover droplet spec.

        :rtype: (high CI of carryover drops per 8 wells, spec desc, whether test passed)
        """
        wells = [w for w in self.carryover_stealth_wells]

        ## get params
        carryover_per_n_wells = self.carryover_per_n_wells
        carryover_n_wells     = self.carryover_n_wells 

        carryover_spec_text = '95%% CI < %d per %d wells' % (carryover_per_n_wells, carryover_n_wells)

        ## get carryover peaks
        carryover_peaks = [w.carryover_peaks for w in wells if w.carryover_peaks is not None]
        if not carryover_peaks:
            return (float('nan'), carryover_spec_text, False)

        ## calc mean/std per plate
        carryover_mean = np.mean(carryover_peaks)
        carryover_stdev = np.std(carryover_peaks)

        ## get mean per n wells
        mean_per_n = carryover_mean * carryover_n_wells
        ## get upper 95% ci for value 
        ci95 = mean_per_n+2*carryover_stdev

        ## return if ci95 is less then max carry over per n wells
        return (ci95, carryover_spec_text, ci95 < carryover_per_n_wells)

    @property
    def test_widths(self):
        """
        Returns whether or not the well group passes the width spec.

        :rtype: (mean width, spec desc, whether test passed)
        """
        WidthGateMin = self.WidthGateMin
        WidthGateMax = self.WidthGateMax

        WGdesc = str(WidthGateMin) + ' < Avg < ' + str(WidthGateMax)

        widths = self.mean_width_mean_variance_ci95
        return (widths[0], WGdesc, widths[0] > WidthGateMin and widths[0] < WidthGateMax)

    
    def test_delta_widths(self,plate_type_code=None,qc_plate=False):
        """
        Tests if the difference in droplet widths between hi ch1 ad ch2 from the color call pates is geater then some value

        :rtype: (delta width, spec desc, whether test passed)
        """
        
        if qc_plate:
            DeltaWidthMin = self.QCDeltaWidthToleranceMin
            DeltaWidthMax = self.QCDeltaWidthToleranceMax
            temp_desc = '%s < Avg < %s (QC)'
        else:
            DeltaWidthMin = self.DeltaWidthToleranceMin
            DeltaWidthMax = self.DeltaWidthToleranceMax
            temp_desc = '%s < Avg < %s '

        WGdesc = temp_desc % (str(DeltaWidthMin), str(DeltaWidthMax) )

        ## delta widths only valid for scc plates.....
        if plate_type_code == 'scc' or plate_type_code is None:
            delta_widths = self.singlewell_colorcomp_delta_widths('FAM/VIC')
            if ( delta_widths is None ):
                delta_widths = self.singlewell_colorcomp_delta_widths('FAM/HEX')
        

        if 'delta_widths' in locals() and delta_widths is not None:
            return (delta_widths, WGdesc, delta_widths > DeltaWidthMin and delta_widths < DeltaWidthMax)
        else:
            return (float('nan'), WGdesc, False)


    @property
    def test_polydispersity_fam(self):
        """
        Returns whether or not the well group passes the polydispersity spec.

        :rtype: (mean FAM polydispersity, spec desc, whether test passed)
        """
        pd = self.polydispersity_carryover_fam_stats
        wells = self.carryover_eventful_wells

        records = [plate.mfg_record for plate in self.metric_plates]
        # QC DDS plate, lower threshold
        if all([r and r.qc_plate and r.batch and r.batch.plate_type.code in ('mfgco', 'bcarry') for r in records]):
            threshold = self.QCMaxPolydispersitiy
        else:
            threshold = self.MaxPolydispersitiy

        if len(wells) > 0:
            return (pd[0]*100, 'Mean < %.02f%%' % threshold, pd[0]*100 < threshold)
        else:
            return (None, "Mean < %.02f%%" % threshold, False)

    # override to ignore stealth
    @property
    def short_droplet_spacing_ci95(self):
        """
        Return mean, variance, and confidence interval of the percentage of events
        that are 'close' in eventful wells in the group.

        :rtype: (mean, stdev, low_ci, high_ci)
        """
        wells = self.event_count_wells
        short_ratios = [float(w.short_interval_count)/w.triggered_event_count for w in wells if w.short_interval_count is not None and w.triggered_event_count > 0]
        if not short_ratios:
            return (0, 0, 0, 0)
        mean = np.mean(short_ratios)
        stdev = np.std(short_ratios)
        ci025, ci975 = percentile(short_ratios, .025), percentile(short_ratios, .975)
        return (mean, stdev, ci025, ci975)

    @property
    def colorcomp_fam_rain_stats(self):
        """
        Returns the FAM rain ratio for the FAM HI well in the last multi-well color comp plate.

        :return: (rain, threshold returned)
        """
        wells = self.colorcomp_fam_high_wells
        if not wells:
            return (0, 'N/A')
        fam_hi = wells[0]

        rain_stat = 0
        if fam_hi.well_channel_metrics[0].rain_p_minus:
            rain_stat = rain_stat + fam_hi.well_channel_metrics[0].rain_p_minus
        if fam_hi.well_channel_metrics[0].rain_p:
            rain_stat = rain_stat + fam_hi.well_channel_metrics[0].rain_p

        return (rain_stat, 'Yes' if fam_hi.well_channel_metrics[0].threshold else 'No')

    @property
    def colorcomp_vic_rain_stats(self):
        """
        Returns the FAM rain ratio for the VIC HI well in the last multi-well color comp plate.

        :return: (rain, threshold returned)
        """
        wells = self.colorcomp_vic_high_wells
        if not wells:
            return (0, 'N/A')
        vic_hi = wells[0]

        rain_stat = 0
        if vic_hi.well_channel_metrics[1].rain_p_minus:
            rain_stat = rain_stat + vic_hi.well_channel_metrics[1].rain_p_minus
        if vic_hi.well_channel_metrics[1].rain_p:
            rain_stat = rain_stat + vic_hi.well_channel_metrics[1].rain_p

        return (rain_stat, 'Yes' if vic_hi.well_channel_metrics[1].threshold else 'No')

    @property
    def colorcomp_carryover_total(self):
        """
        Returns the number of carryover peaks found in the last multi-well colorcomp plate.

        :rtype: int
        """
        pm = self.plate_metrics_by_plate_type(('bcc','mfgcc'))
        if not pm:
            return 0

        last_plate = sorted(pm, key=lambda p: p.plate.run_time)[-1]
        return last_plate.carryover_peaks or 0

    @property
    def polydispersity_carryover_fam_stats(self):
        """
        Mean, stdev and confidence interval of the ratio of polydisperse droplets
        in the FAM channel for the eventful carryover wells.

        :rtype: (mean, stdev, low_ci, high_ci)
        """
        return self.polydispersity_fam_stats(self.carryover_eventful_wells)

    @property
    def polydispersity_colorcomp_fam_stats(self):
        """
        Mean, stdev and confidence interval of the ratio of polydisperse droplets
        in the FAM channel for the colorcomp wells.

        :rtype: (mean, stdev, low_ci, high_ci)
        """
        return self.polydispersity_fam_stats(self.colorcomp_fam_high_wells)

    @property
    def polydispersity_colorcomp_vic_stats(self):
        """
        Mean, stdev and confidence interval of the ratio of polydisperse droplets
        in the VIC channel for the colorcomp wells.

        :rtype: (mean, stdev, low_ci, high_ci)
        """
        return self.polydispersity_vic_stats(self.colorcomp_vic_high_wells)

    @property
    def famvic_fam_wells(self):
        """
        Return the FAM wells in F+/V+ plates.

        :rtype: WellMetric[]
        """
        wm = self.well_metrics_by_type('fvtitr')
        # check FAM wells first
        fam = [w for w in wm if w.well.sample_name and 'fam' in w.well.sample_name.lower()]
        if not fam:
            fam = [w for w in wm if w.well_name[1:] in ('05','06','07','08')]

        return fam

    @property
    def famvic_vic_wells(self):
        """
        Return the VIC wells in F+/V+ plates.

        :rtype: WellMetric[]
        """
        wm = self.well_metrics_by_type('fvtitr')
        # check FAM wells first
        vic = [w for w in wm if w.well.sample_name and 'vic' in w.well.sample_name.lower()]
        if not vic:
            vic = [w for w in wm if w.well_name[1:] in ('09','10','11','12')]

        return vic

    def famvic_amplitude_stats(self, channel_num):
        """
        Return the amplitude mean and standard deviation for the
        specified channel in F+/V+ plates.

        :param channel_num: 0 for FAM, 1 for VIC
        :rtype: (amplitude mean, amplitude stdev)
        """
        if channel_num == 0:
            wells = self.famvic_fam_wells
        elif channel_num == 1:
            wells = self.famvic_vic_wells

        if not wells:
            return (None, None)
        return (np.mean([wm.well_channel_metrics[channel_num].amplitude_mean for wm in wells]),
                np.mean([wm.well_channel_metrics[channel_num].amplitude_stdev for wm in wells]))


class PlateDRCertificationMetrics(DRCertificationMetrics):
    """
    DRCertification metrics for a single plate, instead of all plates from
    a particular reader.
    """
    def __init__(self, plate_id, **kwargs):

        ## get plate info
        self.reprocess_config_id = kwargs.get('reprocess_config_id', None)
        self.plate_id = plate_id

        pm = Session.query(PlateMetric).filter(and_(PlateMetric.plate_id == plate_id,
                                                    PlateMetric.reprocess_config_id==self.reprocess_config_id))\
                    .options(joinedload_all(PlateMetric.plate, Plate.plate_type),
                             joinedload_all(PlateMetric.plate, Plate.box2, innerjoin=True),
                             joinedload_all(PlateMetric.well_metrics, WellMetric.well_channel_metrics, innerjoin=True),
                             joinedload_all(PlateMetric.well_metrics, WellMetric.well, QLBWell.plate, innerjoin=True)).all()


        self.plate_filter = lambda p: p # hack to ensure plate
        self.plate_type_filter = kwargs.get('plate_type_filter', lambda pt: pt)
        self.well_filter = kwargs.get('well_filter', lambda w: w)
        self.well_metric_filter = kwargs.get('well_metric_filter', lambda wm: wm)

        if ( len(pm) and pm[0].plate.qlbplate.system_version is not None ):
            sv_id = pm[0].plate.qlbplate.system_version
            self.system_version = Session.query(SystemVersion).get(sv_id).type
        else:
            self.system_version = 'QX100';        

        if pm: #added by Richard
            self.program_version = pm[0].plate.program_version 
        else:
            self.program_version = None

        ## make param loading generic...
        self.load_config_params( code=self.system_version, **kwargs )

        if pm:
            self.all_plate_metrics = [pm[0]]
            self.metric_plates = [pm[0].plate]
        else:
            self.all_plate_metrics = None
            self.metric_plates = None

class SinglePlateMetrics(AnalysisGroupMetrics):
    """
    Group metrics for a single plate, instead of all plates from a
    particular analysis group or reader.
    """
    def __init__(self, plate_id, reprocess_config_id=None, **kwargs):
        self.reprocess_config_id = reprocess_config_id

        ## probably need to move above...
        pm = Session.query(PlateMetric).filter(and_(PlateMetric.reprocess_config_id==(reprocess_config_id or None),
                                                    PlateMetric.plate_id == plate_id))\
                    .options(joinedload_all(PlateMetric.plate, Plate.plate_type),
                             joinedload_all(PlateMetric.plate, Plate.box2, innerjoin=True),
                             joinedload_all(PlateMetric.well_metrics, WellMetric.well_channel_metrics, WellChannelMetric.well_channel, innerjoin=True),
                             joinedload_all(PlateMetric.well_metrics, WellMetric.well, QLBWell.plate, innerjoin=True)).all()

        self.plate_filter = kwargs.get('plate_filter', lambda p: p)
        self.plate_type_filter = kwargs.get('plate_type_filter', lambda pt: True)
        self.well_filter = kwargs.get('well_filter', lambda w: w)
        self.well_metric_filter = kwargs.get('well_metric_filter', lambda wm: wm)

        if ( pm is not None and pm[0].plate.qlbplate.system_version is not None ):
            sv_id = pm[0].plate.qlbplate.system_version
            self.system_version = Session.query(SystemVersion).get(sv_id).type
        else:
            self.system_version = 'QX100';


        if pm: #added by Richard
            self.program_version = pm[0].plate.program_version 
        else:
            self.program_version = None

        ## make param loading generic...
        self.load_config_params( code=self.system_version, **kwargs )

        self.all_plate_metrics = pm
        self.metric_plates = [pm.plate for pm in self.all_plate_metrics]

    @property
    def event_count_wells(self):
        """
        Return all wells not marked 'Stealth'

        :rtype: WellMetric[]
        """
        return [wm for wm in self.all_well_metrics if wm.well.sample_name not in ('Stealth','stealth','')]
