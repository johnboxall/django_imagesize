from django.db import models

from imagesize.managers import ImageSizeManager


class ImageSize(models.Model):
    "Keeps track of image sizes. Images are mapped to URLs then MD5 hashes."
    objects = ImageSizeManager()
    url = models.URLField(verify_exists=False, max_length=255)
    digest = models.CharField(max_length=32, db_index=True)
    width = models.IntegerField(null=True, default=0)
    height = models.IntegerField(null=True, default=0)
    bytes = models.IntegerField(null=True, default=0)
    processed = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    def save(self, process=False, *args, **kwargs):
        "If process is true find out the size of the image right now."
        if not self.digest:
            from imagesize.helpers import url_hash
            self.digest = url_hash(url)
        if process:
            self.process()
        return super(ImageSize, self).save(*args, **kwargs)
        
    def process(self, save=False):
        "Get the size of the image. If save is true save it as well."
        from imagesize.helpers import getsizes
        try:
            image_bytes, image_dimensions = getsizes(self.url)
            self.bytes = image_bytes
            if image_dimensions: 
                self.width, self.height = image_dimensions
        except Exception, e:
            print e
            pass
        self.processed = True
        if save:
            return self.save()
        return self
        
    @property
    def size(self):
        "Return the size of the image or none if it isn't processed."
        if self.width is not None and self.height is not None:
            return self.width, self.height
        return None