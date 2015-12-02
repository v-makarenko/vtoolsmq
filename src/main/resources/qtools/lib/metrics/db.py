"""
Methods that read and write metric records from the database,
given a Plate->QLBPlate->QLBWell->QLBWellChannel hierarchy,
and the right QLP file for that plate (and optionally,
algorithm).

The key functions here are *_tree, which eagerly load a
hierarchy of plates and plate metrics for easier processing,
and process_plate(), which will generate a hierarchy of
plate metrics, given a QLP file and the corresponding
storage DB record.
"""
from qtools.model import Plate, QLBPlate, QLBWell, QLBWellChannel
from qtools.model import Session, PlateMetric, WellMetric, WellChannelMetric
from sqlalchemy import and_
from sqlalchemy.orm import joinedload_all
from qtools.lib.metrics import *
from qtools.lib.metrics.beta import fill_beta_plate_metrics

__all__ = ['dbplate_tree',
           'process_plate',
           'make_empty_metrics_tree',
           'get_beta_plate_metrics']

def dbplate_tree(plate_id):
    """
    Get the full tree of DB objects associated with a Plate record.
    """
    return Session.query(Plate).filter_by(id=plate_id)\
                               .options(joinedload_all(Plate.qlbplate, QLBPlate.wells, QLBWell.channels, innerjoin=True),
                                        joinedload_all(Plate.plate_type)).first()

def dbplate_metrics_tree(plate_id, reprocess_config_id=None):
    """
    Get the full tree of DB metric objects associated with a Plate record.

    TODO: identify where this query is being done and redirect to reuse.
    """
    return Session.query(PlateMetric).filter(and_(PlateMetric.plate_id == plate_id,
                                                  PlateMetric.reprocess_config_id == reprocess_config_id))\
                                     .options(joinedload_all(PlateMetric.well_metrics, WellMetric.well_channel_metrics, innerjoin=True),
                                              joinedload_all(PlateMetric.well_metrics, WellMetric.well, innerjoin=True)).first()

def process_plate(dbplate,
                  qlplate,
                  reprocess_config=None):
    """
    Process metrics from the plate.

    :param dbplate: The Plate object that was the original basis for the QLP.
    :param qlplate: The QLPlate objects read directly from a QLP, either the original or reprocessed.
    :param reprocess_config: (optional) The configuration under which this plate was (re)processed.
    """
    # load what we need from original plate
    plate_metrics = make_empty_metrics_tree(dbplate, qlplate, reprocess_config)

    wm_name_dict = plate_metrics.well_metric_name_dict
    for well_name, qlwell in sorted(qlplate.analyzed_wells.items()):
        wmet = wm_name_dict[well_name]
        for num, channel in enumerate(qlwell.channels):
            cmet = wmet.well_channel_metrics[num]
            _compute_well_channel_metrics(qlwell, cmet, num)
            convert_inf_to_max(cmet)
            convert_nan_to_zero(cmet)
        _compute_well_metrics(qlwell, wmet)
        convert_inf_to_max(wmet)
        convert_nan_to_zero(wmet)
    
    _compute_plate_carryover_metrics(qlplate, plate_metrics)
    _compute_plate_metrics(qlplate, plate_metrics)
    return plate_metrics
    

def make_empty_metrics_tree(dbplate, qlplate, reprocess_config=None):
    """
    Construct an empty PlateMetrics hierarchy given the specified
    DB record and QLP-derived QLPlate object of a particular plate.

    Will create WellMetric and WellChannelMetric child records for
    every analyzed well in the plate.
    """
    pmet = PlateMetric(plate=dbplate)
    if reprocess_config:
        pmet.reprocess_config = reprocess_config
    
    well_name_map = dbplate.qlbplate.well_name_map
    for well_name, qlwell in sorted(qlplate.analyzed_wells.items()):
        well = well_name_map[well_name]
        wmet = WellMetric(well=well, well_name=well_name)
        
        for num, channel in enumerate(well.channels):
            cmet = WellChannelMetric(well_channel=channel, channel_num=num)
            wmet.well_channel_metrics.append(cmet)
        
        pmet.well_metrics.append(wmet)
    
    return pmet

def get_beta_plate_metrics(dbplate, qlplate, reprocess_config=None):
    """
    Compute both standard plate metrics and beta type-specific
    plate metrics for the specified plate.

    :param dbplate: The DB record of the plate.
    :param qlplate: A QLPlate object derived from the plate's QLP file
    :param reprocess_config: Which algorithm was used, if not the original.
    :return: a PlateMetrics hierarchy filled with metrics for the plate.
    """
    plate_metrics = process_plate(dbplate, qlplate, reprocess_config)
    plate_type = dbplate.plate_type
    if plate_type:
        plate_type_code = plate_type.code
    else:
        plate_type_code = None
    return fill_beta_plate_metrics(qlplate, plate_metrics, plate_type_code)