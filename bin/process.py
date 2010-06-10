"""
Run me in a cron job to walk through all the images and process them!

@@@ Where does file lock store the lockfile by default?

"""
import time
import logging
from urlproperties.helpers import process

process()