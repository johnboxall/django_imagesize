import hashlib
import time
import threading
import re
from datetime import timedelta, datetime
import ImageFile
from sets import Set
from lxml import etree as ET
from hashlib import sha1
from django.utils.encoding import smart_str

from django.conf import settings
from django.core.cache import cache

from urlproperties.models import URLProperties


# ### Don't really think we need these...
from jungle.utils.http import http_request
from jungle.core import urlparse
from jungle.website.pagehelpers import getpage, response2doc

# ### BUG: What is done about duplicate objects?
# @@@ Three seperate calls to "http_request" - gotta get it down to one!

THREADSLEEP = .001
MAX_THREAD_LIFE = timedelta(minutes=1)
CACHE_EXPIRY = 60 * 60 * 24 * 30 ## time in seconds before the image cache times out
NEGATIVE_CACHE_EXPIRY = 120 ## cache negative results for a shorter time period
DB_EXPIRY = timedelta(seconds=CACHE_EXPIRY) # DB object timeout, set to same duration as CACHE_EXPIRY by default

MAX_THREADS = 100

VALID_IMG_RE = re.compile('^http://.*?(JPG|JPEG|PNG|GIF|jpg|jpeg|png|gif)$')
INVALID_IMG_RE = re.compile('^http://\d+.\d+.\d+.\d+/.*')

def is_valid_image(url):
    url = smart_str(url, errors="ignore")
    if bool(INVALID_IMG_RE.match(url)):
        return False
    if bool(VALID_IMG_RE.match(url)):
        return True
    return False

def makekey(url):
    return sha1('urlprop%s' % smart_str(url, errors="ignore")).hexdigest()

def check_cache_and_db(url):
    key = makekey(url)
    properties = cache.get(key)
    if not properties: # properties not in the cache
        try:
            properties = URLProperties.objects.filter(url=url).order_by('-processed')[0] # prefer processed entry
        except IndexError:
            return None
        if properties is not None:
            # properties exists, make sure we'll get a cache hit next time, either short or long depending if it's been processed
            if properties.processed:
                cache.set(key, properties, CACHE_EXPIRY) 
            else:
                cache.set(key, properties, NEGATIVE_CACHE_EXPIRY)                 
    return properties
        
def request_page_bytes(url, request):
    """ 
    # TODO: compute sizes for CSS images
    returns the page size after actually retrieving the document, 
    returns None if the document could not be retrieved
    """
    properties = check_cache_and_db(url)
    if properties is not None:
        return properties.bytes

    referer = 'http://%s/' % urlparse.urlparse(url).netloc

    try:
        response_or_redirect = getpage(url, request, referer_url=referer, allow_self_mobify=True)
    except Exception, e:  # ??
        return 0

    from jungle.website.utils import HttpRedirect    
    if isinstance(response_or_redirect, HttpRedirect):
        return 0  ## don't bother with redirects

    response = response_or_redirect
    from jungle.utils.proxy import ChooseElement
    doc = response2doc(response, ChooseElement) 

    doc_bytes = _process_doc_bytes(url, request, doc)   
    prop, created = URLProperties.objects.get_or_create(url=url) # no processing required for non-images
    prop.bytes = doc_bytes
    prop.processed = True
    cache.set(makekey(url), prop, CACHE_EXPIRY)    
    return doc_bytes
    
    
class Asset(object):
    """Helper used to remember where assets came from."""
    def __init__(self, item, src_from="src"):
        self.src = item.get(src_from)
        self.tag = item.tag
    def __str__(self):
        return self.src
    def __unicode__(self):
        return u'%s' % self.src
    

def is_safe_src(src):
    """We're only sizing assets that can be retrieved over HTTP."""
    return src.startswith("http")

def _process_doc_bytes(baseurl, request, doc):
    """
    Once a page has been retrieved, process the elements in the
    lxml document and retrieve individual sizes.  
    """
    properties = check_cache_and_db(baseurl)
    if properties is not None:
        return properties.bytes
    
    totalsize = len(ET.tostring(doc))

    # Build a list of the page's assets.
    asset_list = doc.xpath('.//link|.//script|.//img')
    asset_set = Set()
    for item in asset_list:
            
        if item.tag == 'link' and item.get('rel') in ['stylesheet', 'apple-touch-icon', 'shortcut icon']:
            asset = Asset(item, "href")
        elif item.tag == 'script':
            asset = Asset(item)
        elif item.tag == 'img':
            asset = Asset(item)
        else:
            continue 

        # Absolutize and get rid of bad assets.
        if asset.src is None:
            continue
        asset.src = urlparse.urljoin(baseurl, asset.src, allow_fragments=False)
        if not is_safe_src(asset.src):
            continue
        
        # @@@ Could we call some common function now??
        cached_object = check_cache_and_db(asset.src)
        if properties is not None:
            if properties.bytes:
                totalsize += properties.bytes
        else: 
            asset_set.add(asset)
    
    # Gather the size of the assets.
    if len(asset_set):
        tracker = run_threads(asset_set, baseurl)        
        for w_thread in tracker.completed_threads:
            content = w_thread.response.content
            asset = w_thread.asset
            size = len(content)
            totalsize += size

            if asset.tag == 'img':
                _, img_dim = _webfetch_image_properties(w_thread)
            else:
                img_dim = None            

            p, _ = URLProperties.objects.get_or_create(url=asset.src)
            if img_dim is not None:
                p.width, p.height = img_dim
            p.bytes = size
            p.processed = True
            p.save()
            cache.set(makekey(asset.src), p, CACHE_EXPIRY)

    # Create the object to remember the size of the page.
    p, _ = URLProperties.objects.get_or_create(url=baseurl)
    p.bytes = totalsize
    p.processed = True
    p.save()
    cache.set(makekey(baseurl), p, CACHE_EXPIRY)
    return totalsize        

def get_image_dimensions(url, defaults=None, process=False):
    return get_image_properties(url, 
                                defaults=defaults, 
                                process=process).size

def get_image_bytes(url, defaults=None, process=False):
    return get_image_properties(url, defaults=defaults, process=process).bytes



size_res = [
    # Double Click. # http://...sz=120x30;...
    re.compile("sz=(?P<w>\d+)x(?P<h>\d+)", re.I)

]



# @@@ With ?param images this whole function will have to be overhauled
# @@@ Otherwise we'll have thousands of same images.
def get_image_properties(url, defaults=None, process=False):
    """
    Use cache falling back on DB to guess image sizes.
    
    Strategy:
        * Don't save implied sizes. (YouTube, DoubleClick)
    """
    
    if not is_valid_image(url):
        # we're not going to bother trying to process images 
        # with funny names
        return URLProperties(url=url)
    
    properties = check_cache_and_db(url)
        
    if properties is None:
        implied_size = None  # (width, height)
        
        try:
            properties = URLProperties.objects.filter(url=url)[0]
        except IndexError:
            properties = URLProperties(url=url)
        
        if defaults is not None:
            implied_size = (defaults.get("width"), defaults.get("height"))
        else:
            for rgx in size_res:
                m = rgx.search(url)
                if m is not None:
                    params = m.groupdict()
                    try:
                        implied_size = (int(params["w"]), int(params["h"]))
                    except ValueError:
                        continue
                    break
        
        if process and implied_size is None:
            properties.process_image()
            
        if implied_size is not None:
            properties.width, properties.height = implied_size

        if not properties.id:
            properties.save() # save if this is newly created
        
        if properties.processed: # cache for longtime only if it hasn't expired
            cache.set(makekey(url), properties, CACHE_EXPIRY)
        else:
            cache.set(makekey(url), properties, NEGATIVE_CACHE_EXPIRY)
    return properties  


class ThreadTracker(object):
    def __init__(self):
        self.completed_threads = []
        self.active_threads = []


class FetchThread(threading.Thread):
    def __init__(self, asset, referer, tracker):
        super(FetchThread, self).__init__()
        self.asset = asset
        self.referer = referer
        self.tracker = tracker
        self.created_at = datetime.now()
    
    def run(self):
        try:
            if isinstance(self.asset, URLProperties):
                if not self.asset.url.startswith('http://') and not self.asset.url.startswith('https://'):
                    print "Deleting bum asset: %s" % self.asset.url
                    self.asset.delete()
                else:
                    self.asset.process_image()
                self.response = None
            else:
                self.response = http_request(self.asset.src, retries=1, 
                    referer_url=self.referer)
        except Exception, e:
            print "!! Thread exception, cleaning up anyway... %s" % str(e)
        thread_complete(self, self.tracker)
        
def thread_complete(thread, tracker):
    tracker.active_threads.remove(thread)
    tracker.completed_threads.append(thread)

def run_threads(assets, referer):
    """
    Threaded grabbing of the stuff. 
    If in DEBUG then synchronous.
    """
    tracker = ThreadTracker()

    
    def check_active (tracker):
        # remove threads that have been alive too long, 
        # unfortunately, no way to hard kill the damn things, 
        # so they get to go on in the background making our lives miserable
        for t in tracker.active_threads:
            now = datetime.now()
            if now - t.created_at > MAX_THREAD_LIFE:
                print "!! Slaying overdue thread: %s"  % str(t.asset)
                thread_complete(t, tracker)

    
    if settings.DEBUG:
        for asset in assets:
            tracker.completed_threads.append(DummyThread(asset, referer, tracker))   
    else:
        count = 0
        print_every = 50
        try:
            while True:
                # print "++ thread  <----------------"
                if len(tracker.active_threads) > MAX_THREADS:
                    time.sleep(THREADSLEEP)
                    continue
                
                check_active(tracker)
                
                asset = assets.next()
                t = FetchThread(asset, referer, tracker)
                tracker.active_threads.append(t)
                t.start()
                if count % print_every == 0:
                    print "-- Started request number %i" % count
                count += 1
        except StopIteration, e:
            print "-- finished assigning threads" 
        
        while len(tracker.active_threads) > 0:
            # print "== sleeping =="
            check_active(tracker)
            time.sleep(THREADSLEEP)

    return tracker
        
def _webfetch_image_properties(data):
    """
    Retrieve the image size in bytes, and a tuple containing dimensions (or None, if they cannot be determined)
    Input can be a string OR a webfetch_thread
    """
    # @@@ ??? Whats this all about?
    if type(data) is type(u''):        
        # size = f.headers.get("content-length")   
        uri = data
        referer = 'http://%s/' % urlparse.urlparse(uri).netloc
        http_response = http_request(uri, 
                                     retries=1, 
                                     referer_url=referer
                                     )
        imagedata = http_response.content
    else:
        imagedata = data.response.content
        
    size = len(imagedata)
    p = ImageFile.Parser()
    p.feed(imagedata)
    if p.image:
        return size, p.image.size
    return size, None



class DummyResponse(object):
    def __init__(self):
        self.content = ""

class DummyThread(object):
    def __init__(self, asset, referer, tracker):
        self.asset = asset
        self.referer = referer
        self.tracker = tracker
        try:
            self.response = http_request(self.asset.src, retries=1, 
                referer_url=self.referer, max_time=settings.HTTP_MAX_REQUEST_TIME)
        except:
            self.response = DummyResponse()


def process(expiry=DB_EXPIRY, limit=20000): 
    """Select and process all unprocessed images, expire all images past their expiry date"""
    properties = URLProperties.objects.filter(created_at__lt=(datetime.now() - expiry))[:limit]
    print "-- begin delete"
    for p in properties.iterator():
        p.delete()
        cache.delete(makekey(p.url))
    print "-- end delete"
    # properties.delete()

    # @@@ If the expiry is NOT the same as the cache expiry, 
    # @@@ should do a manual cache flush for each of these objects! 
    # @@@ if it's not flagged as processed, must be an image
    print "-- begin processing"   
    properties = URLProperties.objects.filter(processed=False)[:limit].iterator()
    tracker = run_threads(properties, '')        
