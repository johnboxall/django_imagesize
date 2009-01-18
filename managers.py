from django.db import models

class ImageSizeManager(models.Manager):
    def get_or_create(self, *args, **kwargs):
        "Delete url and switch it for a hash - put url in the defaults"
        if 'url' in kwargs:
            from imagesize.helpers import url_hash
            kwargs['digest'] = url_hash(kwargs['url'])
            # Put `url` into defaults.
            if isinstance(kwargs.get('defaults'), dict):
                kwargs['defaults']['url'] = kwargs['url']
                if 'width' in kwargs['defaults'] and 'height' in kwargs['defaults']:
                    kwargs['defaults']['processed'] = True             
            else:
                kwargs['defaults'] = {'url':kwargs['url']}
            del kwargs['url']
        return super(ImageSizeManager, self).get_or_create(*args, **kwargs)