"""
Run as a cron job to update the sizes of all unprocessed images.
"""
from imagesize.helpers import process
process()