from qtools.lib.bio import base_regexp_expand, reverse_complement, TransformedGenomeSequence
from qtools.lib.exception import ReturnWithCaveats

def mutate_sequences(transformer, original, mutations=None, combination_width=0, strand='+'):
    """
    Return the list of sequences that arise by applying the
    mutations to the sequence.  Return either the positive
    or negative strand by default.
    
    Filters the result such that the input sequence doesn't appear
    more than once (TODO: fix such that sequence_variants only
    return variants, not the original)

    :param transformer: The MutationTransformer that takes in the original sequence
                        and applies the SNP mutations.  Mutation structures will vary
                        with each transformer.
    """
    xf = transformer
    e = None
    try:
        sequences = xf.sequence_variants(original, mutations, combination_width, strand)
    except ReturnWithCaveats, e:
        rc = e
        sequences = e.return_value
    
    sequences = [seq for seq in sequences if seq.positive_strand_sequence != original.positive_strand_sequence]
    if original.strand == strand:
        sequences.insert(0, TransformedGenomeSequence.from_sequence(original))
    else:
        sequences.insert(0, TransformedGenomeSequence.from_sequence(original.reverse_complement()))
    
    if e:
        raise ReturnWithCaveats(e.explanations, sequences)
    else:
        return sequences


def find_in_sequence(fragment, sequence):
    regex = base_regexp_expand(fragment, overlap=True)
    return __find_in_sequence_regex(regex, sequence, overlapped=True)

def __find_in_sequence_regex(regex, sequence, overlapped=True):
    seq_matches = []
    nseq = sequence.reverse_complement()

    results = regex.finditer(sequence.sequence)
    for match in results:
        if overlapped:
            pos = match.start()
            endpos = pos+len(match.group(1))
        else:
            pos = match.start()
            endpos = match.end()
        seq_matches.append((pos, endpos, sequence.strand))
    nresults = regex.finditer(nseq.sequence)
    for match in nresults:
        if overlapped:
            pos = match.start()
            endpos = pos+len(match.group(1))
        else:
            pos = match.start()
            endpos = match.end()
        # only verify if it's a new one
        inverse_end = len(nseq.sequence)-pos
        inverse_start = len(nseq.sequence)-endpos
        if (inverse_start, inverse_end, sequence.strand) in seq_matches:
            continue
        else:
            seq_matches.append((pos, endpos, nseq.strand))
    
    return seq_matches

def find_in_sequences(fragment, sequences):
    """
    Find the position of the fragment in the specified sequences.
    
    @param the fragment (sequence of base pairs)
    @param sequences SimpleGenomeSequence[]
    """
    regex = base_regexp_expand(fragment, overlap=True)
    matches = []
    for seq in sequences:
        seq_matches = __find_in_sequence_regex(regex, seq, overlapped=True)
        if seq_matches:
            matches.append((seq, seq_matches))
    
    return matches

def find_in_sequence_map(fragment, sequences):
    """
    Like find_in_sequences, but returns only the matches
    themselves, essentially a mapping operation. Returns empty
    lists for a sequence slot if there are no matches.  The
    length of the return value should always equal
    the length of the sequence array; this is
    a shortcut to [find_in_sequence(fragment, sequence) for sequence in sequences]
    """
    regex = base_regexp_expand(fragment, overlap=True)
    return_list = []
    for seq in sequences:
        return_list.append(__find_in_sequence_regex(regex, seq, overlapped=True))
    
    return return_list

def find_multiple_in_sequence_map(fragment_dict, sequences, omit_empty=True):
    """
    Like find_in_sequence_map, but returns a mapping of fragment
    to cut pattern for all fragments in fragment_dict.  The
    return value is guaranteed to be of the same length as
    sequences; this function operates like a map (thus the name)
    
    [(d -> p)*, sequences^] => [((d -> match)*)^]
    
    Maps the sequences list.
    
    @param fragment_dict {fragment_name -> fragment}
    @param sequences GenomeSequence array
    """
    multiple_dicts = [dict() for sequence in sequences]
    for name, fragment in fragment_dict.items():
        matches = find_in_sequence_map(fragment, sequences)
        for d, match in zip(multiple_dicts, matches):
            if match or not omit_empty:
                d[name] = match
    return multiple_dicts

def find_multiple_for_fragments_map(fragment_dict, sequences):
    """
    Transpose of find_multiple_in_sequence_map.  Returns
    a dictionary of length fragment_dict, which shows
    for each fragment the sequence matching (found by
    find_in_sequence_map).
    
    TODO: needs a better name.
    
    Maps the fragment_dict.
    
    [(d -> p)*, sequences^] => [((d -> match)^)*]
    """
    fragment_return = dict()
    for name, fragment in fragment_dict.items():
        matches = find_in_sequence_map(fragment, sequences)
        fragment_return[name] = matches
    
    return fragment_return