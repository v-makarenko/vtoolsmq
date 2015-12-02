"""
Download header helper functions.  Most needed for older
versions of Internet Explorer, and where the backing
files have spaces or other characters that need
escaping.
"""
import re

__all__ = ['set_download_response_header', 'download_file_name']

def set_download_response_header(request, response, file_name):
    # TODO scrub out more illegal chars here
    response.headers['Content-Disposition'] = "attachment; filename=%s" % \
        download_file_name(request, file_name.replace(',','_'))

MSIE_EXEC_VERSION_RE = re.compile(r'Trident\/(\d+)\.(\d+)')
def download_file_name(request, desired_name):
    user_agent = request.environ['HTTP_USER_AGENT']
    subst = False
    # detect ie8 and below
    if 'MSIE' in user_agent:
        match = MSIE_EXEC_VERSION_RE.search(user_agent)
        # TODO need to test this on other browsers
        desired_name = desired_name.replace('#','%23')
        if not match:
            subst = True
        else:
            trident_major = int(match.group(1))
            if trident_major > 4:
                subst = False
            else:
                subst = True

    if subst:
        return desired_name.replace(' ','%20')
    else:
        return desired_name