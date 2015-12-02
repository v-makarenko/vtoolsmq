"""
Basic biological/sequence methods, operations, and classes.
"""
import re, operator

# there might be a way to make this quicker with encoding and
# bit shifting, but that's really premature optimization.
COMPLIMENTS = {'A': 'T',
               'T': 'A',
               'C': 'G',
               'G': 'C',
               'U': 'A',
               'a': 't',
               't': 'a',
               'c': 'g',
               'g': 'c',
               'u': 'a',
               '?': '?'}
               
BASE_RE = re.compile(r'[ATCGU\?atcgux]')
CG_CONTENT_RE = re.compile(r'[CG]')

def antiparallel(sequence):
    """
    Return the antiparallel strand of the specified sequence.
    
    If a U (uracil) is encountered, the complement will be 
    an A.  If an adenine (A) is encountered, the complement will
    be a thymidine (T)
    
    In: CGTA
    Out: TACG
    
    TODO unit test
    """
    if not sequence:
        return sequence
    
    return complement(sequence[::-1])

def reverse_complement(sequence):
    """
    Alias of antiparallel
    """
    return antiparallel(sequence)

def complement(sequence):
    """
    Return the complementary strand of the specified sequence.
    
    Will return in uppercase.  If a U (uracil) is encountered,
    the complement at that base will be an adenine (A).  If
    an adenine is encountered, the complement at that base will
    be a thymidine (T)
    
    In: CGTA
    Out: GCAT
    
    TODO unit test
    """
    if not sequence:
        return sequence
    
    upseq = sequence.upper()
    # is there a better way to do this?  match object seems heavy
    return re.sub(BASE_RE, lambda m: COMPLIMENTS[m.group(0)], upseq)

REGEXP_SUB_MAP = {'R': '[AG]',
                  'Y': '[CT]',
                  'W': '[AT]',
                  'S': '[CG]',
                  'M': '[AC]',
                  'K': '[GT]',
                  'H': '[ACT]',
                  'B': '[CGT]',
                  'D': '[AGT]',
                  'N': '[ACGT]'}
REGEXP_SUB_RE = re.compile(r'[RYWSMKHBDN]')

def base_regexp_expand(str, overlap=False):
    """
    Given an ambiguous base pair string, create the regular expression
    that will match sequences with that ambiguous base pair.  It is
    assumed the sequences will be unambiguous.
    
    Returns the format that will match uppercase letters only.

    :param overlap: Whether to return a regex that will detect
                    overlapping sequences.  In this case, the end()
                    attribute of any matches will be equal to the
                    start() (because the match will have been done
                    with lookahead), so be sure to factor that into
                    your upstream usage.
    """
    base_raw = r'%s' % re.sub(REGEXP_SUB_RE, lambda s: REGEXP_SUB_MAP[s.group(0)], str.upper())
    if overlap:
        return re.compile(r'(?=(%s))' % base_raw)
    else:
        return re.compile(base_raw)

def gc_content(seq):
    """
    Returns the percentage of the sequence which is Gs and Cs.
    Matches confirmed bases only-- does not do IUPAC expansion
    (though C/G match may be useful)

    Strips out trailing and leading spaces, just in case.
    """
    upseq = seq.strip().upper()
    instances = CG_CONTENT_RE.findall(upseq)
    return float(len(instances))/len(upseq)

def maximal_binding_seq(oligo1, oligo2):
    """
    Return the longest consecutive binding length, and oligo
    offsets (TODO: add total bound bases in this config)

    Take these sequences: TACGGAAAG, CTTATAAGG

    TACGGAAAG
          |||
    CCTTATAAG (oligo2 reverse complement)

    3 is your maximal matching sequence, your offsets are (6,6)

    :param oligo1: 5'->3' oligo sequence.
    :param oligo2: 5'->3' oligo sequence.
    :return (max_len, (oligo1-offset, oligo2-rc-offset))

    Equal offsets means the bases form a butt.  Offset1 greater
    than offset2 means there is more 5' overhang on oligo1 than
    3' overhang on oligo2.  Offset2 greater than offset1 means
    there is more 3' overhang on oligo1 than 5' overhang on
    oligo2 (I need to clean up the wording here with Ryan.)
    """
    o1 = oligo1
    o2 = reverse_complement(oligo2)
    M = [[0]*(1+len(o2)) for i in xrange(1+len(o1))]
    longest, xpos, ypos = 0, [], []
    for x in xrange(1,1+len(o1)):
        for y in xrange(1,1+len(o2)):
            if o1[x-1] == o2[y-1]:
                M[x][y] = M[x-1][y-1] + 1
                # pick out ties
                if M[x][y] > longest:
                    longest = M[x][y]
                    xpos = [x]
                    ypos = [y]
                elif M[x][y] == longest and M[x][y] > 0:
                    xpos.append(x)
                    ypos.append(y)
            else:
                M[x][y] = 0

    # figure out more accurate tiebreak; for now, just pick
    # first
    #
    # also TODO: total binding bases of longest
    return (longest, (xpos[0]-longest, ypos[0]-longest))

class SimpleGenomeSequence(object):
    """
    Specifies a genome sequence, without its associated metadata, such as
    source, organism, originating database, or annotations.  Just specifies
    a location and a sequence, for easy comparison (and structured passing
    between variables)
    """

    def __init__(self, chromosome, start, end, strand, full_sequence=None, **kwargs):
        """
        Stores a sequence, or an address of a sequence if the full_sequence
        param is empty.  Start and end are inclusive.  Strand is either
        '+' or '-'.
        """
        self._ch = chromosome
        self._start = start
        self._end = end
        self._strand = strand
        self._seq = full_sequence
        self.name = kwargs.get('name', '')

    @property
    def chromosome(self):
        return self._ch

    @property
    def start(self):
        return self._start

    @property
    def end(self):
        return self._end

    @property
    def strand(self):
        return self._strand

    @property
    def sequence(self):
        return self._seq

    @property
    def positive_strand_sequence(self):
        if self._strand == "+":
            return self._seq
        else:
            return reverse_complement(self._seq)

    @property
    def negative_strand_sequence(self):
        if self._strand == "+":
            return reverse_complement(self._seq)
        else:
            return self._seq

    def reverse_complement(self):
        inverse = reverse_complement(self._seq)
        return SimpleGenomeSequence(self.chromosome, self.start, self.end, '+' if self.strand == '-' else '-', inverse)

    def __len__(self):
        # TODO list sequence length instead if stored?
        # remember inclusive.
        return (self.end - self.start)+1

    def __eq__(self, other):
        return isinstance(other, self.__class__)\
               and self.start == other.start\
               and self.end == other.end\
               and self.chromosome == other.chromosome\
               and self.strand == other.strand\
        and self.sequence == other.sequence

    def __ne__(self, other):
        return not self == other

    def __getitem__(self, arg):
        """
        Allows you to address the sequence directly by base pair.  You would address it
        like FASTA format-- both first base and last base inclusive (this is different
        from Python slicing, where the end is exclusive, and hg19 chromStart/chromEnd,
        where the start is exclusive)
        """
        if isinstance(arg, slice):
            if arg.start is None:
                start = self.start
            else:
                start = arg.start or self.start

            if arg.stop is None:
                stop = self.end+1
            else:
                stop = arg.stop
            step = arg.step

            start_idx = start-self.start
            end_idx = stop-self.start
            if self.strand == "-":
                new_start_idx = len(self._seq)-(end_idx+1)
                new_end_idx = len(self._seq)-(start_idx+1)
            else:
                new_start_idx = start_idx
                new_end_idx = end_idx
            return self._seq[new_start_idx:new_end_idx+1:step]
        else:
            if arg < self.start or arg > self.end:
                raise IndexError, "Index out of bounds: %s [this sequence: %s%s%s]" % (arg, self.start, self.strand, self.end)
            idx = arg-self.start
            if self.strand == "-":
                idx = len(self._seq)-(idx+1)
            return self._seq[idx]

    def base(self, index):
        """
        Returns the base number given an index.  Right now only
        works with nonnegative indices.

        TODO support negative indices as need arises
        """
        if index >= len(self) or index < 0:
            raise IndexError, "There is no base at position %s" % index

        if self.strand == '+':
            return self.start + index
        else:
            return self.end - index

    def contains_coordinate(self, coord, chromosome=None):
        """
        Returns whether or not this sequence contains the specified
        coordinate.  If the chromosome is supplied, checks the
        chromosome as well; otherwise, just checks location and base
        pair numbers.  (TODO: This decision sprung out of convenience,
        but is it right?)

        TODO unit test
        """
        if chromosome is None:
            chromosome = self.chromosome

        if chromosome != self.chromosome:
            return False
        else:
            return (self.start >= coord and self.end <= coord)

    # TODO: establish some sort order

    def __str__(self):
        """
        TODO: verify in FASTA format
        """
        return 'chr%s %s%s%s\n%s' % (self.chromosome, self.start, self.strand, self.end, self.sequence)

    def __unicode__(self):
        """
        TODO: verify in FASTA format
        """
        return u'chr%s %s%s%s\n%s' % (self.chromosome, self.start, self.strand, self.end, self.sequence)

    @property
    def fasta(self):
        """
        Returns FASTA code only (no sequence)
        """
        return 'chr%s %s%s%s' % (self.chromosome, self.start, self.strand, self.end)


class ExonSpanningSequence(SimpleGenomeSequence):
    """
    A genome sequence that spans exons.

    TODO: there might be a better abstraction than atop SimpleGenomeSequence.
    TODO: should the need arise for a TransformedGenomeSequence atop
    the exon spanning sequence, some other things need to be abstracted.
    """
    def __init__(self, embedded_sequences, **kwargs):
        """
        Constructs an exon spanning sequence out of a set of
        SimpleGenomeSequences.
        """
        chs = set([s.chromosome for s in embedded_sequences])
        if len(embedded_sequences) == 0:
            raise ValueError, "empty sequence not supported"
        if len(chs) > 1:
            raise ValueError, "sequences must be on same chromosome"
        strands = set([s.strand for s in embedded_sequences])
        if len(strands) > 1:
            raise ValueError, "spans on different strands not yet supported"

        self._seqs = sorted(embedded_sequences, key=operator.attrgetter('start'))
        self._start = self._seqs[0].start # inclusive start
        self._end = self._seqs[-1].end
        self._strand = self._seqs[0].strand
        self._ch = self._seqs[0].chromosome
        if self._strand == '-':
            self._seqs.reverse()

        if any([s.sequence is None for s in self._seqs]):
            self._seq = None
        else:
            self._seq = "".join([s.sequence for s in self._seqs])
        self.name = kwargs.get('name', '')

        # we'll see if we need these
        #self._gene = gene
        #self._gene_start = gene_start
        #self._gene_end = gene_end

    def __len__(self):
        return sum([len(s) for s in self._seqs])

    def __eq__(self, other):
        if not super(ExonSpanningSequence, self).__eq__(other):
            return False
            # check spanning of diff exons?

    def __getitem__(self, arg):
        """
        Allows you to address the sequence directly by base pair.  You would
        address it like FASTA format- both first and last base inclusive.

        If the FASTA sequence spans an exon, it will only return the sequence
        that is within those addresses.

        If either end is not in the spanned exons, will return an IndexError.
        """
        if isinstance(arg, slice):
            if arg.start is None:
                start = self.start
            else:
                start = arg.start or self.start

            if arg.stop is None:
                stop = self.end
            else:
                stop = arg.stop
            step = arg.step
            if step not in (1, None):
                raise NotImplementedError, "stepping not yet supported"

            subseqs = []
            started = False
            # TODO: step ha
            if self.strand == '-':
                for s in self._seqs:
                    if not started:
                        if s.contains_coordinate(stop):
                            started = True
                            if s.contains_coordinate(start):
                                subseqs.append(s[start:stop])
                                break
                            else:
                                subseqs.append(s[:stop])
                    else:
                        if s.contains_coordinate(start):
                            subseqs.append(s[start:])
                            break
                        else:
                            subseqs.append(s[:])
            else:
                for s in self._seqs:
                    if not started:
                        if s.contains_coordinate(start):
                            started = True
                            if s.contains_coordinate(stop):
                                subseqs.append(s[start:stop])
                                break
                            else:
                                subseqs.append(s[start:])
                    else:
                        if s.contains_coordinate(stop):
                            subseqs.append(s[:stop])
                            break
                        else:
                            subseqs.append(s[:])
            return "".join(subseqs)
        else:
            if arg < self.start or arg > self.end:
                raise IndexError, "Index out of bounds: %s"
            for s in self._seqs:
                if s.contains_coordinate(arg):
                    return s[arg]




    def base(self, index):
        """
        Returns the base number given an index.  Right now only
        works with nonnegative indices.
        """
        if index >= len(self) or index < 0:
            raise IndexError, "There is no base at position %s" % index

        # this works because of underlying SGS structs and the
        # reverse ordering of exons if it's a negative strand
        idx = 0
        offset = index
        for s in self._seqs:
            if index < idx + len(s):
                return s.base(offset)
            else:
                offset = offset - len(s)
                idx = idx + len(s)

    def exon_slice(self, start=None, end=None):
        """
        Returns the genomic regions spanned by the slice, both inclusive.
        """
        idx = 0
        start_index = start or 0
        end_index = end or len(self)-1
        start_offset = start_index
        end_offset = end_index
        subseqs = []
        started = False
        ended = False
        for s in self._seqs:
            if started:
                start_base = s.base(0)
            elif start_index < idx + len(s):
                started = True
                start_base = s.base(start_offset)

            if started and end_index < idx + len(s):
                end_base = s.base(end_offset)
                ended = True
            else:
                end_base = s.base(len(s)-1)

            if started:
                subseqs.append((start_base,end_base))
            if ended:
                break
            else:
                start_offset = start_offset - len(s)
                end_offset = end_offset - len(s)
                idx = idx + len(s)

        if self.strand == '-':
            return [(end, start) for start, end in subseqs]
        else:
            return subseqs


    def contains_coordinate(self, coord, chromosome=None):
        if chromosome is None:
            chromosome = self.chromosome

        if chromosome != self.chromosome:
            return False

        return any([s.contains_coordinate(coord, chromosome=chromosome) for s in self._seqs])

    def __str__(self):
        """
        This isn't FASTA (this would be the good use case for gene name, indices)
        """
        pass

    def __unicode__(self):
        return unicode(str(self))

    @property
    def fasta(self):
        pass


class TransformedGenomeSequence(SimpleGenomeSequence):
    """
    A genome sequence that keeps track of how it's been translated.  Ugh.
    """
    @classmethod
    def from_sequence(cls, seq, name=None):
        if isinstance(seq, cls):
            fullname = "%s%s" % (seq.name, name or '')
        else:
            fullname = name or ''

        return cls(seq.chromosome, seq.start, seq.end, seq.strand, seq.sequence, name=fullname)

    def __init__(self, *args, **kwargs):
        super(TransformedGenomeSequence, self).__init__(*args, **kwargs)
        # just care about the shifts for now
        self.insert_locations = []
        self.delete_locations = []

    def __len__(self):
        return len(self.sequence)

    def __getitem__(self, arg):
        """
        Allows you to address the sequence directly by base pair.  You would address it
        like FASTA format-- both first base and last base inclusive. (this is different
        from Python slicing, where the end is exclusive, and hg19 chromStart/chromEnd,
        where the start is exclusive)

        Somewhat undefined return result if the argument is a single variable
        """
        if isinstance(arg, slice):
            if arg.start is None:
                start = self.start
            else:
                start = arg.start

            if arg.stop is None:
                stop = self.end
            else:
                stop = arg.stop

            # secondary step, probably shouldn't use this as it's mathematically unstable
            step = arg.step
            if start < self.start or stop > self.end:
                raise IndexError, "Slice out of bounds: %s,%s [this sequence: %s%s%s]" % (start, stop, self.start, self.strand, self.end)
            start_offset = self.sequence_index(start)
            end_offset = self.sequence_index(stop)
            return self._seq[start_offset:end_offset+1:step]
        else:
            if arg < self.start or arg > self.end:
                raise IndexError, "Index out of bounds: %s [this sequence: %s%s%s]" % (arg, self.start, self.strand, self.end)
            return self._seq[self.sequence_index(arg)]

    def base(self, index):
        """
        TODO
        """
        return NotImplementedError

    def sequence_index(self, base):
        """
        Given a base number, return the index number on the transformed sequence
        that corresponds to the base.

        Returns -1 if the base has been deleted in the transformed sequence.

        TODO: unit test more carefully.

        """
        if base < self.start or base > self.end:
            return -1

        net_shift = 0
        # TODO: figure out if delete/insert behavior is symmetric

        for loc, width in sorted(self.insert_locations):
            if loc <= base:
                net_shift += width
            else:
                break

        for loc, width in sorted(self.delete_locations):
            if loc <= base:
                net_shift -= width
            else:
                if loc-base < width:
                    return -1
                break

        positive_idx = (base - self.start)+net_shift

        if positive_idx < 0: # not in sequence
            return -1

        if self.strand == '+':
            return positive_idx
        else:
            return (len(self._seq)-1) - positive_idx

    def sequence_slice_indices(self, base_start, base_end):
        """
        Returns the slice that corresponds to the base_start and base_end,
        inclusive.
        """
        return tuple(sorted([self.sequence_index(base_start), self.sequence_index(base_end)]))

    def single(self, location, base):
        """
        ASSUMES POSITIVE STRANDING FOR NOW (TODO: FIX).
        """
        offset = location - self.start
        remainder = offset+1
        self._seq = "%s%s%s" % (self._seq[:offset], base, self._seq[remainder:])
        return self

    def delete(self, begin_base, end_base):
        """
        ASSUMES POSITIVE STRANDING FOR NOW (TODO: FIX)

        Delete from begin_base to end_base, inclusive.
        A single deletion will have a begin_base and end_base
        that is the same.  **NOTE** This is in contrast to
        the way the SNPs are stored in snp131, but consistent
        with the FASTA base coordinate naming mechanism.
        """
        width = end_base - begin_base + 1
        offset = begin_base - self.start
        if offset < 0:
            offset = 0
            width -= (self.start - begin_base)
        self.delete_locations.append((max(self.start, begin_base), width))
        remainder = (end_base - self.start)+1
        self._seq = "%s%s" % (self._seq[:offset], self._seq[remainder:])
        return self

    def replace(self, begin_base, end_base, replace):
        """
        ASSUMES POSITIVE STRANDING FOR NOW (TODO: FIX)

        Superset of delete/indel/mixed.  Replaces the contents between
        begin_base and end_base (inclusive) with the base to replace.
        """
        width = end_base - begin_base + 1
        offset = begin_base - self.start
        if offset < 0:
            offset = 0
            width -= (self.start - begin_base)
        remainder = (end_base - self.start)+1

        diff = len(replace) - width
        if diff > 0:
            self.insert_locations.append((max(self.start, begin_base+1), diff))
        else:
            self.delete_locations.append((max(self.start, begin_base), diff))

        self._seq = "%s%s%s" % (self._seq[:offset], replace, self._seq[remainder:])
        return self

    def insert(self, location, base):
        """
        ASSUMES POSITIVE STRANDING FOR NOW (TODO: FIX)
        """
        offset = location - self.start + 1
        self._seq = "%s%s%s" % (self._seq[:offset], base, self._seq[offset:])
        self.insert_locations.append((location+1, len(base)))
        return self

    def reverse_complement(self):
        inverse = reverse_complement(self._seq)
        seq = TransformedGenomeSequence(self.chromosome, self.start, self.end, '+' if self.strand == '-' else '-', inverse)
        seq.delete_locations = self.delete_locations
        seq.insert_locations = self.insert_locations
        return seq


class SequenceGroup(list):
    """
    A group of sequences that may or may not be contiguous.
    If it is contiguous, you can get a merged sequence object.
    """

    @property
    def contiguous(self):
        """
        Returns whether or not the subsequences in the SequenceGroup
        are contiguous (in the 5' -> 3' direction).  Stupid for now
        in that it won't do the right thing on 3' -> 5' direction
        sequences, and if it encounters two strands of opposite
        polarity, will return false.

        Also stupid in that if the sequences overlap, it will return
        False.
        """
        if len(self) == 0:
            return False
        if len(self) == 1:
            return True

        segment = self[0]
        for i in range(1,len(self)):
            if self[i].chromosome != segment.chromosome\
            or self[i].start != segment.end+1:
                return False
            segment = self[i]

        return True


    @property
    def merged_sequence(self):
        """
        Returns the merged sequence as a SimpleGenomeSequence if the group
        is contiguous.  Otherwise, returns None.

        Stupid in that if the sequences overlap, it won't return the merged
        sequence (for now).  TODO: support overlapping method + merge.

        Right now assumes 5' -> 3' direction.
        """
        if not self.contiguous:
            return None

        strand = self[0].strand
        for seq in self:
            if seq.strand != strand:
                raise ValueError, "Cannot return merged_sequence because of stranding; call merged_positive_sequence or merged_negative_sequence"

        if len([seq for seq in self if seq.sequence is None]) > 0 and len([seq for seq in self if seq.sequence is not None]) > 0:
            raise ValueError, "Cannot generate reliable merged sequence-- only partial sequence data stored"

        full_seq = ''.join([seq.sequence for seq in self])
        return SimpleGenomeSequence(self[0].chromosome, self[0].start, self[-1].end, self[0].strand, full_seq)

    @property
    def merged_positive_sequence(self):
        """
        Returns the merged sequence (positive strand) as a SimpleGenomeSequence if
        the group is contiguous.  Otherwise, returns None.
        """
        if not self.contiguous:
            return None

        if len([seq for seq in self if seq.sequence is None]) > 0 and len([seq for seq in self if seq.sequence is not None]) > 0:
            raise ValueError, "Cannot generate reliable merged sequence-- only partial sequence data stored"

        full_seq = ''.join([seq.positive_strand_sequence for seq in self])
        return SimpleGenomeSequence(self[0].chromosome, self[0].start, self[-1].end, '+', full_seq)


    @property
    def merged_negative_sequence(self):
        """
        Returns the merged sequence (negative strand) as a SimpleGenomeSequence if
        the group is contiguous.  Otherwise, returns None.
        """
        if not self.contiguous:
            return None

        if len([seq for seq in self if seq.sequence is None]) > 0 and len([seq for seq in self if seq.sequence is not None]) > 0:
            raise ValueError, "Cannot generate reliable merged sequence-- only partial sequence data stored"

        full_seq = ''.join([seq.negative_strand_sequence for seq in reversed(self)])
        return SimpleGenomeSequence(self[0].chromosome, self[0].start, self[-1].end, '-', full_seq)

    @property
    def width(self):
        return sum([len(seq) for seq in self])


class SequenceMutation(object):
    """
    Describes a sequence mutation, such as a SNP.

    NOTE: chromStart is snp131.chromStart+1,
    to align with FASTA sequence descriptions.

    TODO: write ucsc-specific input to generate SequenceMutations,
    such that the sequence transformer and "in sequence" methods
    are generic.
    """
    def __init__(self, name, type, chrom, chromStart, chromEnd, strand, observed, variations, verified=True, frequency=0.0):
        self.chrom = chrom
        self.chromStart = chromStart
        self.chromEnd = chromEnd
        self.type = type
        self.name = name
        self.observed = observed
        self.variations = variations
        self.verified = verified
        self.frequency = frequency

    @property
    def observed_complement(self):
        return reverse_complement(self.observed)

    @property
    def observed_positive(self):
        if self.strand == '+':
            return self.observed
        else:
            return self.observed_complement

    @property
    def observed_negative(self):
        if self.strand == '-':
            return self.observed
        else:
            return self.observed_complement

    @property
    def variations_complement(self):
        return [reverse_complement(base) for base in self.variations]

    @property
    def variations_positive(self):
        if self.strand == '+':
            return self.variations
        else:
            return self.variations_complement




class PCRSequence(SequenceGroup):
    """
    Simple abstraction for a PCR sequence.

    TODO might need some more methods.  Maybe should also be immutable?
    """
    def __init__(self, amplicon, left_padding=None, right_padding=None):
        self.append(amplicon)
        if left_padding:
            self.insert(0, left_padding)
            self.has_left_padding = True
        else:
            self.has_left_padding = False

        if right_padding:
            self.append(right_padding)
            self.has_right_padding = True
        else:
            self.has_right_padding = False

        if not self.contiguous:
            raise ValueError, "PCR amplicon/padding sequences must be contiguous"

    @property
    def left_padding(self):
        if self.has_left_padding:
            return self[0]
        else:
            return None

    @property
    def right_padding(self):
        if self.has_right_padding:
            return self[-1]
        else:
            return None

    @property
    def amplicon(self):
        if self.has_left_padding:
            return self[1]
        else:
            return self[0]

    @property
    def start(self):
        return self[0].start

    @property
    def end(self):
        return self[-1].end

    @property
    def chromosome(self):
        return self[0].chromosome

    @property
    def strand(self):
        return self[0].strand

