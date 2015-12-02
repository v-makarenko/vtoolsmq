"""
Helper methods for reading QLP/QLB objects from the filesystem,
and computing QTools-specific values from these QLP/QLB objects
based off specific sample/target naming standards.
"""
from pyqlb.constants import *
from pyqlb.factory import QLNumpyObjectFactory
from qtools.lib.qlb_objects import ExperimentMetadataQLPlate, ExperimentMetadataQLWell

def get_well(path):
    """
    Read a QLB at the specified location, and populate additional QTools
    tracked fields derived from the sample and assay naming standards.
    """
    factory = ExperimentMetadataObjectFactory()
    well = factory.parse_well(path)
    return well

def get_plate(path):
    """
    Read a QLP at the specified location, and populate additional QTools
    tracked fields derived from the sample and assay naming standards.
    """
    factory = ExperimentMetadataObjectFactory()
    plate = factory.parse_plate(path)
    return plate

class ExperimentMetadataObjectFactory(QLNumpyObjectFactory):
    """
    An extension of the object factory in PyQLB, which returns
    instrumented QLPlate/QLWell objects.  These objects have
    additional fields specific to QTools, whose values are
    derived from special naming conventions in the sample name
    and target fields for each well and channel.
    """
    def init_plate(self, *args, **kwargs):
        return ExperimentMetadataQLPlate(*args, **kwargs)
    
    def init_well(self, *args, **kwargs):
        return ExperimentMetadataQLWell(*args, **kwargs)