from django.core.cache import cache

from urlproperties.models import URLProperties


def get_image_dimensions(url, defaults=None):
    return get_image_properties(url, defaults).size

def get_image_properties(url, defaults=None):
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
            u.save()
        u.cache()
    return u