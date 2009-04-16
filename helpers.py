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


cache_timeout = 60 * 60 * 24  ## time in seconds before the image cache times out
db_expiry = timedelta(seconds=cache_timeout) # DB object timeout, set to same duration as cache_timeout by default

def request_page_bytes(url, request):
    """ 
    # TODO: compute sizes for CSS images
    returns the page size after actually retrieving the document, returns None if the document could not be retrieved
    """

    ## first check cache
    cached_obj = cache.get(url)
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
    _, created = URLProperties.objects.get_or_create(url=url, bytes=doc_bytes, processed=True) # no processing required for non-images
    cache.set(url, (doc_bytes, None), cache_timeout)    
    return doc_bytes
    
def _process_doc_bytes(baseurl, request, doc):
    """
    Once a page has been retrieved, process the elements in the page lxml document and retrieve individual sizes.  
    Use the memcache to cache requests, also, stick object sizes in the database for level 2 caching.  
    """
    
    ## first check cache
    cached_obj = cache.get(baseurl)
    if cached_obj:
        return cached_obj[0] ## W00t!
    
    totalsize = len(ET.tostring(doc))

    css_list = doc.findall('.//link')
    js_list = doc.findall('.//script')    
    for item in css_list + js_list:
        if item.tag == 'link':
            res_url = item.get('href')
        elif item.tag == 'script':
            res_url = item.get('src')
        else:
            continue ## ignore unrecognized tags        

        if res_url:
            res_url = urlparse.urljoin(baseurl, res_url, allow_fragments=False) # make relative url's absolute
            cached_object = cache.get(res_url)
            if cached_object is None:
                response = getpage(res_url, request, referer_url=baseurl)
                size = len(response.content)
                _, created = URLProperties.objects.get_or_create(url=res_url, bytes=size, processed=True) # no processing required for non-images
                cache.set(res_url, (size, None), cache_timeout)
                totalsize += size
            else: 
                totalsize += cached_object[0]
    
    img_list = doc.findall('.//img')
    for img_url in img_list:
        img_src = img_url.get('src')
        if img_src:
            totalsize += get_image_bytes(img_src, defaults=None, process=True)
            
    _, created = URLProperties.objects.get_or_create(url=baseurl, bytes=totalsize, processed=True) # no processing required for non-images
    cache.set(baseurl, (totalsize, None), cache_timeout)    
    return totalsize

def get_image_dimensions(url, defaults=None, process=False):
    return get_image_properties(url, defaults=defaults, process=process)[1]

def get_image_bytes(url, defaults=None, process=False):
    return get_image_properties(url, defaults=defaults, process=process)[0]

def get_image_properties(url, defaults=None, process=False):
    "Uses cache and the DB to get image sizes."
    img_data = cache.get(url)
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
    
def _webfetch_image_properties(uri):
    """
    Retrieve the image size in bytes, and a tuple containing dimensions (or None, if they cannot be determined)
    """
    #size = f.headers.get("content-length")   
    referer = 'http://%s/' % urlparse.urlparse(uri).netloc
    http_response = http.http_request(uri, retries=1, referer_url=referer)
    imagedata = http_response.content
    size = len(imagedata)
    p = ImageFile.Parser()
    p.feed(imagedata)
    if p.image:
        return size, p.image.size
    return size, None


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
    
        
    