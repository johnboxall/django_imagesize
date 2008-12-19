import hashlib
import urllib
from StringIO import StringIO
import Image

from imagesize.models import ImageSize


def get_image_size(url):
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
    
def _get_image_size(url):
    "Helper used interally to get the size of an image."
    # http://tinyurl.com/3pqegb
    f = urllib.urlopen(url)
    s = StringIO(f.read(512))
    size = Image.open(s).size
    return size
    
def url_hash(url):
    "Get the hash of a URL."
    m = hashlib.md5()
    m.update(url)
    digest = m.hexdigest()
    return digest
    
