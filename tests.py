from django.contrib.sessions.middleware import SessionMiddleware
from django.core.handlers.wsgi import WSGIRequest
from django.test.client import Client
from django.test import TestCase

from urlproperties.helpers import request_page_bytes

class RequestFactory(Client):
    def request(self, **kwargs):
        """Returns a mock request object."""
        environ = {
            'HTTP_COOKIE': self.cookies,
            'PATH_INFO': '/',
            'QUERY_STRING': '',
            'REQUEST_METHOD': 'GET',
            'SCRIPT_NAME': '',
            'SERVER_NAME': 'testserver',
            'SERVER_PORT': 80,
            'SERVER_PROTOCOL': 'HTTP/1.1',
        }
        environ.update(self.defaults)
        environ.update(kwargs)
        return WSGIRequest(environ)




class URLPropertiesTest(TestCase):

    def test_request_page_bytes(self):
        "urlproperties.helpers.request_page_bytes: Just make sure it works."
        # true pimp niggas spend no dough on the booty.
        url = "http://www.seductioncommunityexposed.com/"
        request = RequestFactory().request()
        # ...
        SessionMiddleware().process_request(request)
        request_page_bytes(url, request)

        




__test__ = {
    "urlproperties_tests": """
>>> from urlproperties.models import URLProperties
>>> from urlproperties.helpers import get_image_properties, process
>>> get_image_properties("http://www.python.org/images/success/nasa.jpg")
<URLProperties: URLProperties object>
>>> obj = get_image_properties("http://www.python.org/images/success/nasa.jpg")
>>> obj.size
>>> obj.width
0L
>>> obj.height
0L
>>> obj.process_image()
>>> obj.width
240
>>> obj.height
90
>>> obj = get_image_properties("http://www.python.org/images/success/nasa.jpg")
>>> obj.width
240L
>>> obj.height
90L
>>> pobj = get_image_properties("http://ad.doubleclick.net/ad/spin.blackrock/spinmobile;sect=spinmobile;sz=120x30;tile=1;ord=1247683618?")
>>> pobj
<URLProperties: URLProperties object>
>>> pobj.id
>>> pobj.width
120
>>> pobj.height
30
>>> pobj = get_image_properties("http://ad.doubleclick.net/ad/spin.blackrock/spinmobile;sect=spinmobile;sz=120x30;tile=1;ord=1247683618?", process=True)
>>> pobj.id
>>> pobj.width
120
>>> pobj.height
30
>>> URLProperties(url="http://www.python.org/images/success/nasa.jpg").save()
>>> obj = get_image_properties("http://www.python.org/images/success/nasa.jpg")
>>> obj.width
240L
>>> obj.height
90L
>>> obj = get_image_properties("http://youtube.com/vid", defaults={"width":160, "height":160})
>>> obj.width
160
>>> obj.height
160
>>> obj.id
>>> pobj = get_image_properties("http://img0.gmodules.com/logos/moonlanding09_res.gif")
>>> pobj.width
0
>>> pobj.height
0
>>> process()
>>> pobj = get_image_properties("http://img0.gmodules.com/logos/moonlanding09_res.gif")
>>> pobj.width
150L
>>> pobj.height
60L
"""}