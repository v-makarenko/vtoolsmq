from collections import defaultdict

from qtools.model import Session, Plate, QLBPlate, QLBWell, PlateMetric, WellMetric, AssaySampleCNV, EnzymeConcentration
from sqlalchemy.orm import joinedload_all

class ModelView(object):
    """
    A convenience class for displaying SQLAlchemy model objects.
    """
    def __init__(self,
                 model_class,
                 columns=None,
                 exclude_columns=None,
                 include_columns=None,
                 global_label_transform=None,
                 column_label_transforms=None,
                 global_value_transform=None,
                 column_value_transforms=None):
        """
        Creates a ModelView.

        :params columns: If supplied, the names of the columns to display.
        :param exclude_columns: The columns to exclude (normally, columns that do not end in _id are included.)
        :param include_columns: The columns to include that would normally be included ()
        :param global_label_transform: How to convert the column names to string labels (applies to all)
        :param column_label_transforms: How to convert individual column names to string labels (type dict, with column names as keys)
        :param global_value_transform: How to convert the object values to display values (applies to all)
        :param column_value_transforms: How to convert the object values to display values (type dict, with column names as keys)
        """
        self.model_class = model_class
        if not columns:
            # default -- get rid of ids
            self.columns = model_class.__mapper__.columns.keys()
            self.columns.remove('id')
            self.columns = [col for col in self.columns if not col.endswith('_id')]
        else:
            self.columns = columns
        
        if exclude_columns:
            for col in exclude_columns:
                self.columns.remove(col)
        
        if include_columns:
            for col in include_columns:
                if col not in self.columns:
                    self.columns.append(col)
        
        self.global_label_transform = global_label_transform if global_label_transform else lambda k: k
        self.column_label_transforms = defaultdict(lambda: self.global_label_transform)

        # maybe a few wasted lambda: whatever references but I'm willing to live with that
        if column_label_transforms:
            for k, v in column_label_transforms.items():
                self.column_label_transforms[k] = v
        
        self.global_value_transform = global_value_transform if global_value_transform else lambda v: v
        self.column_value_transforms = defaultdict(lambda: self.global_value_transform)
        if column_value_transforms:
            for k, v in column_value_transforms.items():
                self.column_value_transforms[k] = v
        
    def labeleditems(self, obj):
        """
        Like obj.items(), except returns key-value pairs of labels and values, as
        transformed by the label and value transforms.
        """
        return dict([self.labeleditem(obj, col) for col in self.columns])
    
    def labeleditem(self, obj, attr):
        return (self.column_label_transforms[attr](attr),
                self.column_value_transforms[attr](getattr(obj, attr, None)))


class DocModelView(ModelView):
    """
    ModelView which uses the doc attribute on a Column to create a label.
    """
    def __init__(self, model_class,
                 columns=None,
                 exclude_columns=None,
                 include_columns=None,
                 column_label_transforms=None,
                 global_value_transform=None,
                 column_value_transforms=None):
        
        # closure
        def doclabel(k):
            col = model_class.__mapper__.columns.get(k, None)
            if col is not None:
                return col.doc or k
            else:
                return k
        
        super(DocModelView, self).__init__(model_class,
                                           columns=columns,
                                           exclude_columns=exclude_columns,
                                           include_columns=include_columns,
                                           global_label_transform=doclabel,
                                           column_label_transforms=column_label_transforms,
                                           global_value_transform=global_value_transform,
                                           column_value_transforms=column_value_transforms)

def delete_plate_recursive(plate_id):
    """
    Given a plate id, delete:
    -- The plate and its wells (recursively).
    -- Any plate metrics associated with the plate.
    -- Any connection to analysis groups or reprocess configs.
    -- 

    Keep in mind that if the QLP backing this file is present
    in the source filesystem, it will be reanalyzed.
    """
    # Well, crap.  The joinedload is necessary to populate
    # the qlbwell/qlbwell_channel tree, such that deleting
    # the underlying metrics don't orphan the well or channel.
    # The cascade on PlateMetrics is set to delete-orphan,
    # which may not be the right thing to do
    #
    # The workaround/fix would be to make all plate metric
    # deletion explicit, and remove the delete-orphan cascade
    # from plate metric, as children include refs to qlbwell
    # and qlbwell_channel.
    plate = Session.query(Plate).filter_by(id=plate_id)\
                                .options(joinedload_all(Plate.qlbplate, QLBPlate.wells, QLBWell.channels),
                                         joinedload_all(Plate.metrics, PlateMetric.well_metrics, WellMetric.well_channel_metrics)).first()
                              
    if not plate:
        return
    
    # secondary tables first
    for ag in plate.analysis_groups:
        Session.delete(ag)

    for tag in plate.tags:
        Session.delete(tag)

    for lot_number in plate.lot_numbers:
        Session.delete(lot_number)

    cnv_evidence = Session.query(AssaySampleCNV).filter_by(source_plate_id=plate_id).all()
    for cev in cnv_evidence:
        Session.delete(c)
    
    enzyme_evidence = Session.query(EnzymeConcentration).filter_by(source_plate_id=plate_id).all()
    for eev in enzyme_evidence:
        Session.delete(eev)
    
    for pm in plate.metrics:
        for wm in pm.well_metrics:
            for wcm in wm.well_channel_metrics:
                Session.delete(wcm)
            wm.well_channel_metrics = []
            Session.delete(wm)
        pm.well_metrics = []
        Session.delete(pm)
    plate.metrics = []
    
    from qtools.model.batchplate import ManufacturingPlate
    related_batches = Session.query(ManufacturingPlate).filter_by(plate_id=plate.id).all()
    for rb in related_batches:
        rb.plate_id = None

    for w in plate.qlbplate.wells:
        for c in w.channels:
            Session.delete(c)
        w.channels = []
        if w.file_id != -1:
            Session.delete(w.file)
        Session.delete(w)
    plate.qlbplate.wells = []
    if plate.qlbplate.file_id != -1:
        Session.delete(plate.qlbplate.file)
    Session.delete(plate.qlbplate)
    Session.delete(plate)







