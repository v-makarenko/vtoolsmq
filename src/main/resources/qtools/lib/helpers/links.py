"""
Helper functions to link to specific pages in QTools.
"""
from pylons import config, url
from webhelpers.html import literal
from qtools.lib.wowo import wowo
from urllib import quote_plus

dr_host_map = {}

def get_dr_subdomain(box2):
    global dr_host_map
    if not box2.fileroot in dr_host_map:
        filedomain = config.get('qlb.filedomain.%s' % box2.fileroot, None)
        dr_host_map[box2.fileroot] = filedomain
    
    return dr_host_map[box2.fileroot]

def dr_url(box2, **kwargs):
    if not wowo('dr_subdomains'):
        return url(**kwargs)

    subdomain = get_dr_subdomain(box2)
    if not subdomain:
        return url(**kwargs)
    else:
        kwargs['qualified'] = True
        # because I can't get the Routes subdomain URL bullcrap to work
        kwargs['host'] = subdomain
        return url(**kwargs)

def assay_link(assay):
    if not assay:
        return ''
    href = url(controller='sequence', action='view_details', id=assay.id)
    return literal('<a href="%s">%s</a>' % (href, assay.name))

def ucsc_link(chr, start, end, db='hg19'):
    """
    Links to UCSC Genome Browser.
    """
    return literal('<a href="http://genome.ucsc.edu/cgi-bin/hgTracks?db=%(db)s&position=chr%(chr)s:%(start)s-%(end)s" target="_new">chr%(chr)s:%(start)s-%(end)s</a>' % locals())

def wiki_link(page_name, space='KB', link_text=None):
    """
    Links to a page inside the ddPCR Wiki, hosted at ddwiki.global.bio-rad.com.
    """
    return literal('<a href="http://ddwiki.global.bio-rad.com/display/%s/%s">%s</a>' % (space, quote_plus(page_name), link_text or page_name))

def help_link(uri, text='Page Help'):
    help_base = config.get('qtools.docs.base_url', '/')
    return literal('<a href="%s/%s">%s</a>' % (help_base, uri, text))

def ucsc_content_link(chr, start, end, content, db='hg19'):
    return literal('<a href="http://genome.ucsc.edu/cgi-bin/hgTracks?db=%(db)s&position=chr%(chr)s:%(start)s-%(end)s" target="_new">%(content)s</a>' % locals())

def ucsc_transcript_link(gene, content, db='hg19'):
    """
    Links to UCSC Genome Browser.
    """
    return literal('<a href="http://genome.ucsc.edu/cgi-bin/hgTracks?db=%(db)s&position=%(gene)s" target="_new">%(content)s</a>' % locals())

def ucsc_sequence_link(sequence, db='hg19'):
    return ucsc_link(sequence.chromosome, sequence.start, sequence.end, db=db)

def ucsc_sequence_amplicon_link(sequence, db='hg19'):
    return ucsc_link(sequence.chromosome, sequence.amplicon.start, sequence.amplicon.end, db=db)

def ucsc_transcript_genomic_link(transcript, db='hg19'):
    return ucsc_content_link(transcript.chromosome,
                             transcript.genomic_start, transcript.genomic_end,
                             transcript.exon_span_string,
                             db=db)

def ucsc_transcript_local_link(transcript, db='hg19'):
    return ucsc_transcript_link(transcript.ucsc_id, '%s__%s:%d%s%d' % \
                                    (transcript.ucsc_id, transcript.gene, transcript.start, transcript.strand, transcript.end),
                                db=db)