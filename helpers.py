import hashlib
from StringIO import StringIO
import Image
import urllib
import ImageFile

from django.core.cache import cache

from imagesize.models import ImageSize

cache_timeout = 60 * 60 * 24  ## time in seconds before the image cache times out


def get_image_size(url, defaults=None, force_process=False):
    return get_image_sizes(url, defaults, force_process)[1]

def get_image_sizes(url, defaults=None, force_process=False):
    "Uses cache and the DB to get image sizes."
    key = _image_size_cache_key(url)
    img_data = cache.get(key)

    if img_data is None or (force_process and img_data.size == 0):
        image_cache, created = ImageSize.objects.get_or_create(url=url, defaults=defaults)
        if force_process:
            image_cache.process(save=True)
        img_dim = image_cache.size
        img_bytes = image_cache.bytes
        cache.set(key, (img_bytes, img_dim), cache_timeout)
        img_data = (img_bytes, img_dim)
    return img_data  ## (bytes, (width, height))
    
def process(qs=None):
    "Go through all unprocessed images and give them a size. Also clear the image cache."    
    if qs is None:
        qs = ImageSize.objects.filter(processed=False)
    for image in qs:
        image.process(save=True)
    count = qs.count()
    return count
    
def url_hash(url):
    "Get the hash of a URL."
    m = hashlib.md5()
    if type(url) is not type(''):
        print "Foo"
    m.update(url)
    digest = m.hexdigest()
    return digest
    
def _image_size_cache_key(url):
    return "_image_size_cache.%s" % url_hash(url)

def getsizes(uri):
    """
    Retrieve the image size in bytes, and a tuple containing dimensions (or None, if they cannot be determined)
    """
    #size = f.headers.get("content-length")    
    f = urllib.urlopen(uri)
    imagedata = f.read()
    f.close()
    size = len(imagedata)
    p = ImageFile.Parser()
    p.feed(imagedata)
    if p.image:
        return size, p.image.size
    return size, None
