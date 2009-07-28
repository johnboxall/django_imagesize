import hashlib
import time
import threading
from datetime import timedelta, datetime
import ImageFile
from sets import Set
from lxml import etree as ET
from hashlib import sha1

from django.conf import settings
from django.core.cache import cache

from urlproperties.models import URLProperties


# ### Don't really think we need these...
from bloom.http import http_request
from jungle.core import urlparse
from jungle.website.pagehelpers import getpage, response2doc

# ### BUG: NO HTTP IN LIBCURL
# ### BUG: What is done about duplicate objects?
# @@@ Three seperate calls to "http_request" - gotta get it down to one!

THREADSLEEP = .001
CACHE_EXPIRY = 60 * 60 * 24 * 5 ## time in seconds before the image cache times out
DB_EXPIRY = timedelta(seconds=CACHE_EXPIRY) # DB object timeout, set to same duration as CACHE_EXPIRY by default

MAX_THREADS = 20


def makekey(url):
    return sha1('urlprop%s' % url).hexdigest()

def check_cache_and_db(url):
    key = makekey(url)
    properties = cache.get(key)
    if properties is None or not properties.processed:
        try:
            properties = URLProperties.objects.filter(url=url, processed=True)[0]
        except IndexError:
            return None
        cache.set(key, properties, CACHE_EXPIRY)            
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
    return get_image_properties(url, defaults=defaults, process=process).size

def get_image_bytes(url, defaults=None, process=False):
    return get_image_properties(url, defaults=defaults, process=process).bytes


import re
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
            properties.save()
            
        if implied_size is not None:
            properties.width, properties.height = implied_size
        else:
            properties.save()
        
        cache.set(makekey(url), properties, CACHE_EXPIRY)
    return properties  


class ThreadTracker(object):
    def __init__(self):
        self.completed_threads = []
        self.active_threads = 0


class FetchThread(threading.Thread):
    def __init__(self, asset, referer, tracker):
        super(FetchThread, self).__init__()
        self.asset = asset
        self.referer = referer
        self.tracker = tracker
    
    def run(self):
        self.response = http_request(self.asset.src, retries=1, 
            referer_url=self.referer, max_time=settings.HTTP_MAX_REQUEST_TIME)
        thread_complete(self, self.tracker)
        
def thread_complete(thread, tracker):
    tracker.active_threads -= 1
    tracker.completed_threads.append(thread)

def run_threads(assets, referer):
    """
    Threaded grabbing of the stuff. 
    If in DEBUG then synchronous.
    """
    tracker = ThreadTracker()

    if settings.DEBUG:
        for asset in assets:
            tracker.completed_threads.append(DummyThread(asset, referer, tracker))
            
    else:
        while assets:
            # print "++ thread  <----------------"
            if tracker.active_threads > MAX_THREADS:
                time.sleep(THREADSLEEP)
                continue
            asset = assets.pop()
            t = FetchThread(asset, referer, tracker)
            tracker.active_threads += 1
            t.start()
        
        while tracker.active_threads > 0:
            # print "== sleeping =="
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
        http_response = http_request(uri, retries=1, referer_url=referer, max_time=settings.HTTP_MAX_REQUEST_TIME)
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


def process(expiry=DB_EXPIRY): 
    """Select and process all unprocessed images, expire all images past their expiry date"""
    properties = URLProperties.objects.filter(created_at__lt=(datetime.now() - expiry))
    for p in properties.iterator():
        cache.delete(makekey(p.url))
    properties.delete()

    # @@@ If the expiry is NOT the same as the cache expiry, 
    # @@@ should do a manual cache flush for each of these objects! 
    # @@@ if it's not flagged as processed, must be an image
    properties = URLProperties.objects.filter(processed=False)
    for p in properties.iterator():
        p.process_image()