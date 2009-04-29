import hashlib
from StringIO import StringIO
import Image
from bloom import http
import ImageFile
from django.core.cache import cache
from urlproperties.models import URLProperties
from jungle.core import urlparse
from jungle.website.pagehelpers import getpage, response2doc
from lxml import etree as ET
from datetime import timedelta, datetime
import threading
import time
from django.core.exceptions import ObjectDoesNotExist
from sets import Set


THREADSLEEP = .001
cache_timeout = 60 * 60 * 24  ## time in seconds before the image cache times out
db_expiry = timedelta(seconds=cache_timeout) # DB object timeout, set to same duration as cache_timeout by default

max_threads = 20

def check_cache_and_db(url):
    result = cache.get(url)
    if result is None:
        try:
            result_obj = URLProperties.objects.get(url=url)
            img_dim = None
            if result_obj.width and result_obj.height: 
                img_dim = (result_obj.width, result_obj.height)
            result = (result_obj.bytes, img_dim)
        except ObjectDoesNotExist:
            return None
    return result
        
def request_page_bytes(url, request):
    """ 
    # TODO: compute sizes for CSS images
    returns the page size after actually retrieving the document, returns None if the document could not be retrieved
    """

    ## first check cache
    cached_obj = check_cache_and_db(url)
    if cached_obj:
        return cached_obj[0] ## W00t!
    
    try:         
        response_or_redirect = getpage(url, request, referer_url='http://%s/' % urlparse.urlparse(url).netloc)
    except Exception, e: 
        return None
    from jungle.website.utils import HttpRedirect    
    if isinstance(response_or_redirect, HttpRedirect):
        redirect = response_or_redirect
        return None  ## don't bother with redirects

    response = response_or_redirect
    from jungle.utils.proxy import ChooseElement
    doc = response2doc(response, ChooseElement) 

    doc_bytes = _process_doc_bytes(url, request, doc)   
    prop, created = URLProperties.objects.get_or_create(url=url) # no processing required for non-images
    prop.bytes = doc_bytes
    prop.processed = True
    cache.set(url, (doc_bytes, None), cache_timeout)    
    return doc_bytes
    
def _process_doc_bytes(baseurl, request, doc):
    """
    Once a page has been retrieved, process the elements in the page lxml document and retrieve individual sizes.  
    Use the memcache to cache requests, also, stick object sizes in the database for level 2 caching.  
    """
    ## first check cache
    cached_obj = check_cache_and_db(baseurl)
    if cached_obj:
        return cached_obj[0] ## W00t!
    
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
            
        if item.tag == 'link':
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
        if cached_object is not None and None not in cached_object:   
            totalsize += cached_object[0]
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
            cache.set(res_url.in_str, (size, img_dim), cache_timeout)

    prop, created = URLProperties.objects.get_or_create(url=baseurl) # no processing required for non-images
    prop.bytes = totalsize
    prop.processed = True
    prop.save()
    cache.set(baseurl, (totalsize, None), cache_timeout)    
    
    return totalsize        

def get_image_dimensions(url, defaults=None, process=False):
    return get_image_properties(url, defaults=defaults, process=process)[1]

def get_image_bytes(url, defaults=None, process=False):
    return get_image_properties(url, defaults=defaults, process=process)[0]

def get_image_properties(url, defaults=None, process=False):
    "Uses cache and the DB to get image sizes."
    img_data = check_cache_and_db(url)
    if img_data is None:
        url_properties, created = URLProperties.objects.get_or_create(url=url)
        if process:
            url_properties.process_image() # fetch and store properties
            url_properties.save()
            img_bytes = url_properties.bytes
            img_dim = url_properties.size            
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
            url_properties.width = img_width
            url_properties.height = img_height
            url_properties.bytes = img_bytes
            url_properties.save()
        cache.set(url, (img_bytes, img_dim), cache_timeout)
        img_data = (img_bytes, img_dim)
    return img_data  ## (bytes, (width, height))

class _webfetch_thread(threading.Thread):
    def __init__(self, url, referer, tracker):
        super(_webfetch_thread, self).__init__()
        self.url = url
        self.referer = referer
        self.tracker = tracker
    
    def run (self):
        self.response = http.http_request(self.url.in_str, retries=1, referer_url=self.referer)
        thread_complete(self, self.tracker)
        
def thread_complete(w_thread, tracker):
    tracker.active_threads -= 1
    tracker.completed_threads.append(w_thread)

def run_threads(urls, referer):
    tracker = Thread_tracker()
    while urls:
        # print "++ thread  <----------------"
        if tracker.active_threads > max_threads:
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
    if type(data) is type(''):        
        # size = f.headers.get("content-length")   
        uri = data
        referer = 'http://%s/' % urlparse.urlparse(uri).netloc
        http_response = http.http_request(uri, retries=1, referer_url=referer)
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

def process(expiry=db_expiry): 
    """
    Select and process all unprocessed images, expire all images past their expiry date
    """
    for prop in URLProperties.objects.filter(created_at__lt=(datetime.now() - expiry)):
        cache.delete(prop.url)
        prop.delete()
    ## If the expiry is NOT the same as the cache expiry, should do a manual cache flush for each of these objects! 
    for prop in URLProperties.objects.filter(processed=False):  ## if it's not flagged as processed, must be an image
        prop.process_image()
    
        
    