#! /usr/bin/python
# Written by Dan Mandle http://dan.mandle.me September 2012
# http://www.danmandle.com/blog/getting-gpsd-to-work-with-python/
# License: GPL 2.0
# Slightly modified by Akkana for PyTopo.

from __future__ import print_function

import os
import gps
import time
import threading


class GpsdPoller(threading.Thread):
    def __init__(self, polltime=10, callback=None):
        """Poll time is in seconds.
           Callback has one argument: a gps.gpsd object.
        """

        threading.Thread.__init__(self, name="gpsd_poller")

        self.polltime = polltime
        self.callback = callback

        self.gpsd = gps.gps(mode=gps.WATCH_ENABLE) # starting the stream of info
        self.current_value = None
        self.running = True   # setting the thread running to true

        self.start()          # Start the thread


    def run(self):
        while self.running:
            self.gpsd.next()
            if self.callback:
                self.callback(self.gpsd)

            time.sleep(self.polltime)
            # this will continue to loop and grab EACH set of gpsd info


    def stopGPS(self):
        self.running = False
        self.join() # wait for the thread to finish what it's doing


if __name__ == '__main__':
    gpsp = GpsdPoller()     # create the thread
    try:
        while True:
            # It may take a second or two to get good data

            os.system('clear')
            print()
            print(' GPS reading')
            print('----------------------------------------')
            print('latitude    ' , gpsp.gpsd.fix.latitude)
            print('longitude   ' , gpsp.gpsd.fix.longitude)
            print('time utc    ' , gpsp.gpsd.utc,' + ', gpsp.gpsd.fix.time)
            print('altitude (m)' , gpsp.gpsd.fix.altitude)
            print('eps         ' , gpsp.gpsd.fix.eps)
            print('epx         ' , gpsp.gpsd.fix.epx)
            print('epv         ' , gpsp.gpsd.fix.epv)
            print('ept         ' , gpsp.gpsd.fix.ept)
            print('speed (m/s) ' , gpsp.gpsd.fix.speed)
            print('climb       ' , gpsp.gpsd.fix.climb)
            print('track       ' , gpsp.gpsd.fix.track)
            print('gpsd status:' , gpsp.gpsd.status)
            print('mode        ' , gpsp.gpsd.fix.mode)
            print()
            print('sats        ' , gpsp.gpsd.satellites)

            time.sleep(5) # set to whatever

    except (KeyboardInterrupt, SystemExit): # when you press ctrl+c
        print("Control-C from gpsdPoller")
        gpsp.stopGPS()

    print("Done.\nExiting.")


