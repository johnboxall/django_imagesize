from django.test import TestCase

from urlproperties.models import URLProperties
from urlproperties.helpers import get_image_properties


class TestURLProperties(TestCase):
    def test_get_image_properties(self):
        u = get_image_properties("http://www.python.org/images/success/nasa.jpg")
        self.assertEquals(u.size, None)
        
        u.process()
        self.assertEquals(u.size, (240,90))
        
        # Doubleclick urls :\
        # get_image_properties("http://ad.doubleclick.net/ad/spin.blackrock/spinmobile;sect=spinmobile;sz=120x30;tile=1;ord=1247683618?")
        
        # Defaulting
        u = get_image_properties("http://youtube.com/vid", 
            defaults={"width": 160, "height": 160})
        self.assertEquals(u.size, (160, 160))