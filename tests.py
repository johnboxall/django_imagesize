__test__ = {
    "urlproperties_tests": """
>>> from urlproperties.models import URLProperties
>>> from urlproperties.helpers import get_image_properties
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
"""}