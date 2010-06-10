import hashlib

from django.db import models
from django.utils.encoding import smart_str

import caching.base


# class URLProperties(caching.base.CachingMixin, models.Model):
class URLProperties(models.Model):
    # Track size of url.
    url = models.URLField(verify_exists=False, max_length=512, db_index=True)
    width = models.IntegerField(null=True, default=0)
    height = models.IntegerField(null=True, default=0)
    bytes = models.IntegerField(null=True, default=0)
    processed = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    broken = models.BooleanField(default=False)
    
    # objects = caching.base.CachingManager()
    
    def __unicode__(self):
        return "<URLProperties:%s>" % self.url
    
    @staticmethod
    def getcachekey(url):
        key = 'urlprop%s' % smart_str(url, errors="ignore")
        return hashlib.sha1(key).hexdigest()
    
    @property
    def cachekey(self):
        return self.getcachekey(self.url)
    
    @property
    def size(self):
        # Returns a tuple size of the image or None.
        if self.width and self.height:
            return self.width, self.height
        return None
    
    def process(self):
        try:
            self._process()
        except Exception, e:
            self.broken = True
        self.processed = True
        self.save()
    
    def _process(self):
        # TODO: Send image accept headers.
        # Follow redirects  = True        
        # TODO: better handling of errors here :)
        import ImageFile
        from jungle.utils.http import http_request
        
        referer = "/".join(self.url.split("/", 3)[0:3])
        data = http_request(self.url, retries=1, referer_url=referer).content
        self.bytes = len(data)
        parser = ImageFile.Parser()
        parser.feed(data)
        if parser.image:
            self.width, self.height = parser.image.size