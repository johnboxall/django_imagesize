import hashlib
import urllib
from StringIO import StringIO
import Image

from imagesize.models import ImageSize


# why not put this in the real cache so everyone can use it?
# try on a real server and see
# memoize decorator:
# http://code.activestate.com/recipes/496879/

def get_image_size(url):
    "Uses cache and the DB to get image sizes."
    if not hasattr(get_image_size, '_cache'):
        get_image_size._cache = {}
    # an easy fix would be to only cache it if its none non
    elif url in get_image_size._cache:
        return get_image_size._cache[url]
    print get_image_size._cache
    image_size, created = ImageSize.objects.get_or_create(url=url)
    size = image_size.size
    get_image_size._cache[url] = size
    return size

def process(qs=None):
    "Go through all unprocessed images and give them a size. Also clear the image cache."
    if hasattr(get_image_size, '_cache'):
        del get_image_size._cache
    
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