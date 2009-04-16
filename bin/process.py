"""
Run as a cron job to update the sizes of all unprocessed images.
"""
from urlproperties.helpers import process
process()