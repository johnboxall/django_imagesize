from django.db import models

import caching.base

class URLProperties(caching.base.CachingMixin,models.Model):
    """
    Keeps track of the size of a url target. If the target is an image, then 
    image width & height are also tracked. 
    
    In the future, we may track other properties.      
    """
    url = models.URLField(verify_exists=False, max_length=512, db_index=True)
    width = models.IntegerField(null=True, default=0)
    height = models.IntegerField(null=True, default=0)
    bytes = models.IntegerField(null=True, default=0)
    processed = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    objects = caching.base.CachingManager()
            
    def process_image(self):
        """Retrieve and save the properties of the image."""
        from urlproperties.helpers import _webfetch_image_properties, is_valid_image
        if not is_valid_image(self.url):
            # print "-- deleted invalid image: %s" % self.url
            # self.delete()
            return

        try:
            self.bytes, dimensions = _webfetch_image_properties(self.url)
        except Exception, e:
            print "Retrieving asset raised an exception, deleting it: %s" % self.url
            print "exception was: %s" % e
            self.delete()
            return

        if dimensions is not None: 
            self.width, self.height = dimensions

        self.processed = True
        return self.save()

    @property
    def size(self):
        """Return the size of the image or none if it isn't an image"""
        if self.width and self.height:
            return self.width, self.height
        return None