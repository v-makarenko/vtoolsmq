from qtools.messages import JSONMessage

def ProcessSequenceGroupMessage(sequence_group_id):
	return JSONMessage(sequence_group_id=sequence_group_id)

def ProcessPrimerAmpliconMessage(sequence_group_id,
                                 forward_primer_id,
                                 reverse_primer_id,
                                 probe_ids=None):
	"""
	Make a process amplicon job message out of a forward primer and
	reverse primer sequence, and a bunch of probes.
	"""
	return JSONMessage(sequence_group_id=sequence_group_id,
	                   forward_primer_id=forward_primer_id,
	                   reverse_primer_id=reverse_primer_id,
	                   probe_ids=probe_ids or [])

def ProcessLocationAmpliconMessage(sequence_group_id):
    """
    Make a process amplicon job message out of a chromosome base
    and amplicon length.
    """
    return JSONMessage(sequence_group_id=sequence_group_id)

def ProcessSNPRSIDMessage(sequence_group_id):
	return JSONMessage(sequence_group_id=sequence_group_id)

def ProcessSNPAmpliconMessage(sequence_group_id,
                              chromosome,
                              start,
                              end):
	return JSONMessage(sequence_group_id=sequence_group_id,
	                   chromosome=chromosome,
	                   start=start,
	                   end=end)

def ProcessSNPMessage(cached_sequence_id):
	return JSONMessage(cached_sequence_id=cached_sequence_id)

def ProcessGEXSNPMessage(transcript_id):
	return JSONMessage(transcript_id=transcript_id)