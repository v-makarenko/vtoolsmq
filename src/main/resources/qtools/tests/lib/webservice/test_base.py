from qtools.lib.webservice import *
import urllib2

def test_request_response_proxy():
    class SimpleRequestProxy(RequestProxy):
        def __init__(self, proxy_class):
            super(SimpleRequestProxy, self).__init__(proxy_class)
            self.reads = 0
    
    class SimpleResponseProxy(ResponseProxy):
        def _on_read(self, *args):
            self.proxy.reads += 1
    
    reqp = SimpleRequestProxy(SimpleResponseProxy)
    response = reqp.request('http://www.bio-rad.com')
    html = response.read()
    assert reqp.reads == 1
    assert 'HTML' in html
    
    response = reqp.request('http://www.bio-rad.com')
    html = response.read()
    assert reqp.reads == 2

def test_response_proxy():
    rp = ResponseProxy([],urllib2.urlopen('http://www.bio-rad.com'))
    assert len(rp.read()) is not 0

def test_response_proxy_handler():
    class FirstResponseProxy(ResponseProxy):
        def _on_read(self, bytes):
            self.firstline = bytes.split('\n')[0]
    
    rp = FirstResponseProxy([], urllib2.urlopen('http://qlbudev.global.bio-rad.com'))
    assert len(rp.read()) is not 0
    assert 'html' in rp.firstline

def test_make_get_request_url():
    base1 = "http://www.bio-rad.com"
    base2 = "https://www.bio-rad.com/"
    uri1 = "foo"
    uri2 = "/foo"
    uri3 = ''
    dict1 = {}
    dict2 = {'foo': 4, 'bar': 'baz'}
    
    def _t(*args):
        return make_get_request_url(*args)
    
    assert _t(base1) == "http://www.bio-rad.com/"
    assert _t(base1, uri1) == "http://www.bio-rad.com/foo"
    assert _t(base1, uri2) == "http://www.bio-rad.com/foo"
    assert _t(base2, uri2) == "https://www.bio-rad.com/foo"
    assert _t(base2, uri1) == "https://www.bio-rad.com/foo"
    assert _t(base2, uri3) == "https://www.bio-rad.com/"
    assert _t(base1, uri1, dict1) == "http://www.bio-rad.com/foo"
    
    # note: may need to use a MultiDict to ensure correct ordering 
    assert _t(base1, uri1, dict2) == "http://www.bio-rad.com/foo?foo=4&bar=baz"


def test_make_request_params():
    def _t(defs=None, **kwargs):
        return make_request_params(defs, **kwargs)
    
    assert _t() == dict()
    assert _t({'a': 1}) == {'a': 1}
    assert _t({'a': 1, 'c': 4}, a=2, b=3) == {'a': 2, 'b': 3, 'c': 4}