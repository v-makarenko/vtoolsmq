from qtools.model import Session, Box2Log, Box2Circuit
from qtools.model.util import ModelView, DocModelView
from qtools.tests import DatabaseTest
from sqlalchemy.orm import joinedload_all

class TestDocModelView(DatabaseTest):
	def __init__(self, *args, **kwargs):
		self.logview = DocModelView(Box2Log)
		super(TestDocModelView, self).__init__(*args, **kwargs)
	
	@property
	def logobj(self):
		# uncommitted item
		return Box2Log(pickup_line='Sample Pickup Line')
	
	@property
	def logobj_joined(self):
		return Session.query(Box2Log)\
		              .options(joinedload_all(Box2Log.circuit))\
		              .first()
	
	def test_labeleditems_basic(self):
		"""
		Test stuff.
		"""
		logobj = self.logobj
		labeleditems = self.logview.labeleditems(logobj)
		assert labeleditems['Pickup Line'] == 'Sample Pickup Line'
		assert labeleditems['Waste Bottle Full Value'] is None
	
	def test_labeleditems_addin(self):
		"""
		More tests
		"""
		circuit = Box2Circuit(name='TestCircuit')
		log = Box2Log(pickup_line='TestPickupLine', circuit=circuit)
		# column_label_transforms is weird.  I should fix this.
		mv = DocModelView(Box2Log,
		                  include_columns=['circuit'],
		                  column_label_transforms={'circuit': lambda k: 'Circuit'},
		                  column_value_transforms={'circuit': lambda v: v.name if v else None})
		
		assert mv.labeleditems(log)['Pickup Line'] == 'TestPickupLine'
		print mv.labeleditems(log)
		assert mv.labeleditems(log)['Circuit'] == 'TestCircuit'

