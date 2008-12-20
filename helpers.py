import hashlib
import urllib
from StringIO import StringIO
import Image

from imagesize.models import ImageSize


def get_image_size(url):


    # it would be very cool to put a local cache in here
    # so that over the course of a render if this was hit multiple times
    # for the same url we'd only do this once.


    "Uses the DB to help get the image size quickly."
    image_size, created = ImageSize.objects.get_or_create(url=url)
    size = image_size.size
    return size

def process(qs=None):
    "Go through all unprocessed images and give them a size."
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