"""
This package contains modules and classes used to interact with external web services.
"""
import urllib, urllib2, cookielib, os

class RequestProxy(object):
    """
    Returns a proxied response object on request.
    
    Not sure if this is the right thing to do yet.
    """
    def __init__(self, proxy_class=None, opener=None):
        self.opener = opener or None
        if not proxy_class:
            self.proxy_class = ResponseProxy
        else:
            self.proxy_class = proxy_class
    
    def request(self, *args, **kwargs):
        """
        Returns a 
        """
        if not self.opener:
            response = urllib2.urlopen(*args, **kwargs)
        else:
            response = self.opener.open(*args, **kwargs)
        
        return self.proxy_class(self, response)


class ResponseProxy(object):
    """
    Proxy object that may edit the proxy object
    when the response is read.
    """
    def __init__(self, proxy, response):
        self._proxy = proxy
        self._response = response
    
    @property
    def proxy(self):
        return self._proxy
    
    def __getattribute__(self, name):
        # note: @property decorator seems to muck with this
        response = object.__getattribute__(self, '_response')
        
        try:
            self_method = object.__getattribute__(self, name)
        except AttributeError, e:
            self_method = None
        
        try:
            handler = object.__getattribute__(self, "_on_%s" % name)
        except AttributeError, e:
            handler = None
        
        if name in response.__dict__ and not self_method:
            if handler:
                def func(*args, **kwargs):
                    retval = response.__dict__[name](*args, **kwargs)
                    handler(retval)
                    return retval
                return func
            else:
                def func(*args, **kwargs):
                    return response.__dict__[name](*args, **kwargs)
                return func
        
        return self_method
            
            



def make_get_request_url(base_url, uri='/', param_dict=None):
    """
    Constructs the get request URL.
    
    (This might not be the right abstraction, let's see what happens with cookies)
    """
    if param_dict is None:
        param_dict = dict()
    
    if not uri:
        uri = '/'
    
    if base_url.endswith('/') and uri.startswith('/'):
        base_url = base_url[:-1]
    elif (not base_url.endswith('/') and not uri.startswith('/')):
        uri = "/%s" % uri
    
    # note, may need to use a MultiDict in source implementation.
    # or maybe let's use WebOb.Request.
    param_str = urllib.urlencode(param_dict)
    
    if param_str:
        full_url = "%s%s?%s" % (base_url, uri, param_str)
    else:
        full_url = "%s%s" % (base_url, uri)
    
    return full_url
    

def make_request_params(defaults, *args, **kwargs):
    if not defaults:
        defaults = dict()
    defaults.update(kwargs)
    return defaults