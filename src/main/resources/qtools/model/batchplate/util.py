from qtools.model import Session, PlateType
from qtools.model.batchplate import *

from sqlalchemy import and_

def query_plate_type_dg_method(plate_type_code=None,
                               plate_type_codes=None,
                               dg_method=None,
                               dg_methods=None):
	query = Session.query(ManufacturingPlateBatch)
	if plate_type_code is not None or plate_type_codes is not None:
		query = query.join(PlateType)
	
	if plate_type_code is not None:
		query = query.filter(PlateType.code == plate_type_code)
	if plate_type_codes is not None:
		query = query.filter(PlateType.code.in_(plate_type_codes))
	if dg_method is not None:
		query = query.filter(ManufacturingPlateBatch.default_dg_method == dg_method)
	if dg_methods is not None:
		query = query.filter(ManufacturingPlateBatch.default_dg_method.in_(dg_methods))
	return query
