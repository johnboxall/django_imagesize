from django.core.cache import cache

from urlproperties.models import URLProperties


# Time in seconds before the image cache times out. 30 days.
CACHE_EXPIRY = 60 * 60 * 24 * 30 


def get_image_dimensions(url, defaults=None, process=False):
    return get_image_properties(url, defaults, process).size

def get_image_properties(url, defaults=None, process=False):
    cachekey = URLProperties.getcachekey(url)
    u = cache.get(cachekey)
    if u is None:
        # Prefer processed entries.
        try:
            u = URLProperties.objects.filter(url=url).order_by('-processed')[0]
        except IndexError:
            u = URLProperties(url=url)
        
        if u.id is None:
            if defaults is not None:
                u.width, u.height = (defaults.get("width"), defaults.get("height"))
            elif process:
                u.process()
            
            u.save()
        
        cache.set(cachekey, u, CACHE_EXPIRY)
    return u