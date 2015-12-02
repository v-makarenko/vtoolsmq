"""
Patches for broken parts of QTools' dependencies.
"""
import poster

def poster_multipart_encode_patch(params):
    """
    Fixes poster 0.6 interaction bug with Python 2.7
    See http://forums.dropbox.com/topic.php?id=24817
    
    # TODO: check for poster, python versions?
    """
    data, mp_headers = poster.encode.multipart_encode(params)
    if 'Content-Length' in mp_headers:
        mp_headers['Content-Length'] = str(mp_headers['Content-Length'])
    return data, mp_headers