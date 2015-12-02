"""
Tools for working with plates that have sample/assay combinations from
multiple plate types.
"""

AUTO_VALIDATION_EXP_NAME_MAPPINGS = {'Validation-Carryover': 'mfgco',
                                     'Validation-CNV': 'bcnv',
                                     'Validation-DNR': 'bdnr',
                                     'Validation-Duplex': 'bdplex',
                                     'Validation-Dye': 'bdye2',
                                     'Validation-RED': 'bred',
                                     'Validation-Singleplex': 'bsplex'}

MIXED_PLATE_TYPE_CODES = ('av',)

def well_plate_type_code(well):
    return AUTO_VALIDATION_EXP_NAME_MAPPINGS.get(well.experiment_name, '')

def compute_metric_foreach_mixed_qlwell(qlplate, plate_metric, plate_type_calc_map):
    """
    For each analyzed well in the plate, update the metric through the
    transform in the supplied calculator.  The calculator used will be dependent
    on the plate type that the well corresponds to.
    """
    pm_well_map = plate_metric.well_metric_name_dict
    for name, qlwell in sorted(qlplate.analyzed_wells.items()):
        wm = pm_well_map[name]
        calc = plate_type_calc_map.get(well_plate_type_code(qlwell), None)
        if calc:
            calc.compute(qlwell, wm)

def compute_metric_foreach_mixed_qlwell_channel(qlplate, plate_metric, plate_type_calc_map):
    """
    For each analyzed well in the plate, update the metrics through the
    transform in the calculator specific to that well's plate type.
    """
    pm_well_map = plate_metric.well_metric_name_dict
    for name, qlwell in sorted(qlplate.analyzed_wells.items()):
        wm = pm_well_map[name]
        calc = plate_type_calc_map.get(well_plate_type_code(qlwell), None)
        if calc:
            for idx, channel in enumerate(qlwell.channels):
                calc.compute(qlwell, channel, wm.well_channel_metrics[idx])


