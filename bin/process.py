# Run me in a cron job to walk through all the images and process them!
import datetime
from urlproperties.processor import process

print "process_image: Started at %s" % datetime.datetime.now()
process()
print "process_image: Ended at %s" % datetime.datetime.now()