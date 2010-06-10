import hashlib

from django.db import models
from django.utils.encoding import smart_str
from django.core.cache import cache

import caching.base


# class URLProperties(caching.base.CachingMixin, models.Model):
class URLProperties(models.Model):
    # Time in seconds before the image cache times out. 30 days.
    CACHE_EXPIRY = 60 * 60 * 24 * 30
    HEADERS = {
        'User-Agent': 'Mozilla/5.0 (Macintosh; U; Intel Mac OS X 10.5; en-US; rv:1.9.0.5) Gecko/2008120121 Firefox/3.0.5',
    }

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
    
    def cache(self):
        cache.set(self.cachekey, self, self.CACHE_EXPIRY)
    
    def process(self):    
        try:
            self._process()
        except Exception, e:
            print e
            self.broken = True
        self.processed = True
        self.save()
        self.cache()
    
    def _process(self):
        import ImageFile
        from bloom.http import http_request
        
        referer = "/".join(self.url.split("/", 3)[0:3])
        data = http_request(self.url, retries=1, referer_url=referer, use_proxy=True,
            headers=self.HEADERS, use_accept_encoding=False, follow_redirects=True).content
        self.bytes = len(data)
        parser = ImageFile.Parser()
        parser.feed(data)
        if parser.image:
            self.width, self.height = parser.image.size