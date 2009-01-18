import hashlib
import urllib
from StringIO import StringIO
import Image

from django.core.cache import cache

from imagesize.models import ImageSize


def get_image_size(url, defaults=None):
    "Uses cache and the DB to get image sizes."
    key = _image_size_cache_key(url)
    size = cache.get(key)
    if size is None:
        image_size, created = ImageSize.objects.get_or_create(url=url, defaults=defaults)
        size = image_size.size
        cache.set(key, size, 60 * 10)
    return size

def process(qs=None):
    "Go through all unprocessed images and give them a size. Also clear the image cache."    
    if qs is None:
        qs = ImageSize.objects.filter(processed=False)
    for image in qs:
        image.process(save=True)
    count = qs.count()
    return count
    
def _get_image_size(url, length=512):
    """
    Helper used interally to get the size of an image.
    Try at first to get the image just from a few bytes.
    If that fails read the whole thing.
    """
    # http://tinyurl.com/3pqegb
    try:
        f = urllib.urlopen(url)
        s = StringIO(f.read(length))
        size = Image.open(s).size
    except IOError:
        if length is None:
            raise
        else:
            return _get_image_size(url, None)    
    return size
    
def url_hash(url):
    "Get the hash of a URL."
    m = hashlib.md5()
    m.update(url)
    digest = m.hexdigest()
    return digest
    
def _image_size_cache_key(url):
    return "_image_size_cache.%s" % url_hash(url)