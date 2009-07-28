import hashlib, time, threading
from datetime import timedelta, datetime
import ImageFile
from sets import Set
from lxml import etree as ET
from hashlib import sha1

from django.conf import settings
from django.core.cache import cache

from urlproperties.models import URLProperties


# ### Don't really think we need these...
from bloom import http
from jungle.core import urlparse
from jungle.website.pagehelpers import getpage, response2doc

# ### BUG: NO HTTP IN LIBCURL
# ### BUG: What is done about duplicate objects?

THREADSLEEP = .001
CACHE_EXPIRY = 60 * 60 * 24 * 5 ## time in seconds before the image cache times out
DB_EXPIRY = timedelta(seconds=CACHE_EXPIRY) # DB object timeout, set to same duration as CACHE_EXPIRY by default

MAX_THREADS = 20


def makekey(url):
    return sha1('urlprop%s' % url).hexdigest()

# ### Need to return something consistant ...
def check_cache_and_db(url):
    key = makekey(url)
    properties = cache.get(key)
    if properties is None or not properties.processed:
        properties = URLProperties.objects.filter(url=url, processed=True) 
        if len(properties) >= 1:
            properties = properties[0]
        else:
            return None
        cache.set(key, properties, CACHE_EXPIRY) # found it in the DB, update cache            
            
    return properties
        
def request_page_bytes(url, request):
    """ 
    # TODO: compute sizes for CSS images
    returns the page size after actually retrieving the document, returns None if the document could not be retrieved
    """
    properties = check_cache_and_db(url)
    if properties is not None:
        return properties.bytes

    try:
        response_or_redirect = getpage(url, request, referer_url='http://%s/' % urlparse.urlparse(url).netloc, allow_self_mobify=True)
    except Exception, e: 
        return 0
    from jungle.website.utils import HttpRedirect    
    if isinstance(response_or_redirect, HttpRedirect):
        redirect = response_or_redirect
        return 0  ## don't bother with redirects

    response = response_or_redirect
    from jungle.utils.proxy import ChooseElement
    doc = response2doc(response, ChooseElement) 

    # ### This is really always create at this point isn't it???
    doc_bytes = _process_doc_bytes(url, request, doc)   
    prop, created = URLProperties.objects.get_or_create(url=url) # no processing required for non-images
    prop.bytes = doc_bytes
    prop.processed = True
    cache.set(makekey(url), prop, CACHE_EXPIRY)    
    return doc_bytes
    
def _process_doc_bytes(baseurl, request, doc):
    """
    Once a page has been retrieved, process the elements in the page lxml document and retrieve individual sizes.  
    Use the memcache to cache requests, also, stick object sizes in the database for level 2 caching.  

    """
    ## first check cache
    properties = check_cache_and_db(baseurl)
    if properties is not None:
        return properties.bytes ## W00t!
    
    totalsize = len(ET.tostring(doc))

    css_list = doc.findall('.//link')
    js_list = doc.findall('.//script')    
    img_list = doc.findall('.//img')

    res_url_set = Set()
    for item in css_list + js_list + img_list:
        class faux_str(object):
            def __init__(self, in_str, t=None):
                self.in_str = in_str
                self.t = t
            def __str__(self):
                return self.in_str
            def __unicode__(self):
                return u'%s' % self.in_str
            
        if item.tag == 'link' and item.get('rel') in ['stylesheet', 'apple-touch-icon', 'shortcut icon']:
            res_url = faux_str(item.get('href'))
        elif item.tag == 'script':
            res_url = faux_str(item.get('src'))
        elif item.tag == 'img':
            res_url = faux_str(item.get('src'), t='img')
        else:
            continue ## ignore unrecognized tags        
        if res_url.in_str is None:
            continue 
        res_url.in_str = urlparse.urljoin(baseurl, res_url.in_str, allow_fragments=False) # make relative urls absolute
        
        cached_object = check_cache_and_db(res_url.in_str)
        if cached_object is not None: # and len(cached_object):  
            if cached_object.bytes:
                totalsize += cached_object.bytes #[0]
        else: 
            res_url_set.add(res_url)
    
    if res_url_set:
        tracker = run_threads(res_url_set, baseurl)        
        for w_thread in tracker.completed_threads:
            content = w_thread.response.content
            res_url = w_thread.url
            size = len(content)
            totalsize += size
            
            # print "%i %s" % (size, res_url.in_str)
            
            ## cache for future use
            if res_url.t == 'img':
                # image
                _, img_dim = _webfetch_image_properties(w_thread)
            else:
                img_dim = None            

            prop, created = URLProperties.objects.get_or_create(url=res_url.in_str)
            if img_dim:
                prop.width=img_dim[0]
                prop.height=img_dim[1]
                prop.bytes=size
                prop.processed=True # no processing required for non-images            
            else:
                prop.bytes=size
                prop.processed=True # no processing required for non-images                            
            prop.save()
            cache.set(makekey(res_url.in_str), prop, CACHE_EXPIRY)

    prop, created = URLProperties.objects.get_or_create(url=baseurl) # no processing required for non-images
    prop.bytes = totalsize
    prop.processed = True
    prop.save()
    cache.set(makekey(baseurl), prop, CACHE_EXPIRY)    
    
    return totalsize        

def get_image_dimensions(url, defaults=None, process=False):
    return get_image_properties(url, defaults=defaults, process=process).size

def get_image_bytes(url, defaults=None, process=False):
    return get_image_properties(url, defaults=defaults, process=process).bytes

def get_image_properties(url, defaults=None, process=False):
    """Uses cache and the DB to get image sizes."""
    properties = check_cache_and_db(url)
    if properties is None:
        # ### This is always get at this point...
        properties, _ = URLProperties.objects.get_or_create(url=url)
        if process:
            properties.process_image() # fetch and store properties
            properties.save()
            img_bytes = properties.bytes
            img_dim = properties.size            
        else:
            if defaults: 
                img_width = defaults.get('width')
                img_height = defaults.get('height')
            else: 
                img_width = None
                img_height = None
            
            if img_width is None or img_height is None:
                img_dim = None
            else:
                img_dim = (img_width, img_height)            
                
            img_bytes = None
            properties.width = img_width
            properties.height = img_height
            properties.bytes = img_bytes
            properties.save()
        cache.set(makekey(url), properties, CACHE_EXPIRY)
    return properties  

class _webfetch_thread(threading.Thread):
    def __init__(self, url, referer, tracker):
        super(_webfetch_thread, self).__init__()
        self.url = url
        self.referer = referer
        self.tracker = tracker
    
    def run(self):
        self.response = http.http_request(self.url.in_str, retries=1, referer_url=self.referer, max_time=settings.HTTP_MAX_REQUEST_TIME)
        thread_complete(self, self.tracker)
        
def thread_complete(w_thread, tracker):
    tracker.active_threads -= 1
    tracker.completed_threads.append(w_thread)

def run_threads(urls, referer):
    """Threaded grabbing of the stuff. If in DEBUG then synchronous."""
    # ### Need to check for dupe URLS before we get here.    
    tracker = Thread_tracker()

    if settings.DEBUG:
        for url in urls:
            tracker.completed_threads.append(DummyThread(url, referer, tracker))
    else:
        while urls:
            # print "++ thread  <----------------"
            if tracker.active_threads > MAX_THREADS:
                time.sleep(THREADSLEEP)
                continue
            url = urls.pop()
            t = _webfetch_thread(url, referer, tracker)
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
    if type(data) is type(u''):        
        # size = f.headers.get("content-length")   
        uri = data
        referer = 'http://%s/' % urlparse.urlparse(uri).netloc
        http_response = http.http_request(uri, retries=1, referer_url=referer, max_time=settings.HTTP_MAX_REQUEST_TIME)
        imagedata = http_response.content
    else:
        imagedata = data.response.content
        
    size = len(imagedata)
    p = ImageFile.Parser()
    p.feed(imagedata)
    if p.image:
        return size, p.image.size
    return size, None


class Thread_tracker(object):
    def __init__(self):
        self.completed_threads = []
        self.active_threads = 0

class DummyResponse(object):
    def __init__(self):
        self.content = ""

class DummyThread(object):
    def __init__(self, url, referer, tracker):
        self.url = url
        self.referer = referer
        self.tracker = tracker
        try:
            self.response = http.http_request(self.url.in_str, retries=1, referer_url=self.referer, max_time=settings.HTTP_MAX_REQUEST_TIME)
        except:
            self.response = DummyResponse()


def process(expiry=DB_EXPIRY): 
    """Select and process all unprocessed images, expire all images past their expiry date"""
    qs = URLProperties.objects.filter(created_at__lt=(datetime.now() - expiry))
    for properties in URLProperties.objects.filter(created_at__lt=(datetime.now() - expiry)):
        cache.delete(makekey(properties.url))
    qs.delete()

    ## If the expiry is NOT the same as the cache expiry, should do a manual cache flush for each of these objects! 
    for properties in URLProperties.objects.filter(processed=False):  ## if it's not flagged as processed, must be an image
        properties.process_image()
    
        
    