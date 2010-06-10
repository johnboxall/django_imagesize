import Queue
import threading
import datetime

from django.conf import settings
from django.core.cache import cache
from django.utils.functional import curry

from urlproperties.models import URLProperties


# Time in seconds before the image cache times out. 30 days.
CACHE_EXPIRY = 60 * 60 * 24 * 30 

# Number of threads.
WORKERS = 1


def process(expiry=CACHE_EXPIRY, limit=5):
    # Expire stinker images and process new images.
    created_before = datetime.datetime.now() - datetime.timedelta(seconds=expiry)
    qs = URLProperties.objects.filter(created_at__lt=created_before)[:limit]

    # You can't limit a DELETE in DJ which is a bit silly.
    # cache.delete_many([makekey(p.url) for p in qs.iterator()])
    # qs.delete()
    
    for u in qs.iterator():
        cache.delete(u.cachekey)
        u.delete()
    
    qs = URLProperties.objects.filter(processed=False, broken=False)[:limit]
    processor = Processor(qs)
    processor.process()


class Processor(object):
    def __init__(self, queryset):
        self.queryset = queryset
    
    def process(self):
        q = Queue.Queue()
        for i in range(WORKERS):
            t = threading.Thread(target=curry(worker, q))
            t.setDaemon(True)
            t.start()
        
        for u in self.queryset:
            q.put(u)
        
        q.join()


def worker(queue):
    while True:
        u = queue.get()
        u.process()
        queue.task_done()