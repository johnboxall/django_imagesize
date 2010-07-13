#!/bin/bash

RUNNING=`ps aux | grep -i /services/mobify/lib/python2.6/site-packages/urlproperties/bin/process.py | grep -v grep | awk -F" " '{ print $2 }'`

while [[ $RUNNING -ne " " ]]; do
    kill -9 $RUNNING
    sleep 1
    RUNNING=`ps aux | grep -i /services/mobify/lib/python2.6/site-packages/urlproperties/bin/process.py | grep -v grep | awk -F" " '{ print $2 }'`
    echo "running is now: '" ${RUNNING} "'"
done

# cleaning up the thread handler files
rm -f /services/mobify/*MainThread*

# run the process command
BINDIR=/services/mobify/lib/python2.6/site-packages/urlproperties/bin

cd /services/mobify; source bin/activate; export DJANGO_SETTINGS_MODULE=jungle.settings; python -Wignore $BINDIR/process.py 
