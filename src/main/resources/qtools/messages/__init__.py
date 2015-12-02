from qtools.lib.collection import AttrDict
from abc import *
import json

class Message(object):
	__metaclass__ = ABCMeta

	@abstractmethod
	def serialize(self):
		pass
	
	@classmethod
	# cheap way out
	def unserialize(cls, payload):
		raise NotImplementedError


class JSONMessage(AttrDict, Message):
	def serialize(self):
		return json.dumps(self.__dict__)
	
	@classmethod
	def unserialize(cls, payload):
		return cls(json.loads(payload))


class JSONErrorMessage(JSONMessage):
	def __init__(self, msg):
		super(JSONErrorMessage, self).__init__(error=msg)