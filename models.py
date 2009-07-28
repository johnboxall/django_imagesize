from django.db import models


from django.db import models

class URLProperties(models.Model):
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
            
    def process_image(self):
        """Retrieve and save the properties of the image."""
        try:
            from urlproperties.helpers import _webfetch_image_properties
            image_bytes, image_dimensions = _webfetch_image_properties(self.url)
            self.bytes = image_bytes
            if image_dimensions: 
                self.width, self.height = image_dimensions
                self.processed = True
            return self.save()
        except Exception, e:
            print str(e)
            self.delete()
            pass  #  No big deal if this fails. 

    @property
    def size(self):
        """Return the size of the image or none if it isn't an image"""
        if self.width and self.height:
            return self.width, self.height
        return None