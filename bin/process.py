"""
Run me in a cron job to walk through all the images and process them!

@@@ Where does file lock store the lockfile by default?

"""
import time
import logging
from lockfile import FileLock, AlreadyLocked, LockTimeout
from urlproperties.helpers import process


def locked_job(callback, name="job"):
    lock = FileLock(name)
    
    logging.debug("acquiring lock...")
    
    try:
        lock.acquire(-1)
    except AlreadyLocked:
        logging.debug("lock already in place. quitting.")
        return
    except LockTimeout:
        logging.debug("waiting for the lock timed out. quitting.")
        return
    logging.debug("acquired.")
    
    start_time = time.time()
    
    try:
        callback()
    finally:
        logging.debug("releasing lock...")
        lock.release()
        logging.debug("released.")
    
    logging.info("")
    logging.info("one in %.2f seconds" % (time.time() - start_time))

locked_job(process, "urlproperties")