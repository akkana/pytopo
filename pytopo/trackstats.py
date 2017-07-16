# Copyright (C) 2009-2016 by Akkana Peck.
# You are free to use, share or modify this program under
# the terms of the GPLv2 or, at your option, any later GPL.

'''Statistics on track logs,
   such as total distance, average speed, and total climb.
'''

import argparse
import math
import datetime
import numpy


# Variables that need to be global, because statistics() and
# accumulate_climb() need to share them, and python 2.7 doesn't
# have nonlocal.
total_climb = 0
this_climb = 0
this_climb_start = 0
lastele = -1

CLIMB_THRESHOLD = 8

# How fast do we have to be moving to count
# toward the moving average speed?
# This is in miles/hour.
SPEED_THRESHOLD = .5


def statistics(trackpoints, halfwin, beta, metric):
    '''Accumulate statistics like mileage and total climb.
       Return a dictionary of stats collected.
    '''
    global total_climb, this_climb, this_climb_start, lastele

    # The variables we're going to plot:
    eles = [ ]
    distances = [ ]

    # Accumulators:
    lastlat = 0
    lastlon = 0
    total_dist = 0

    lasttime = None
    moving_time = datetime.timedelta(0)
    stopped_time = datetime.timedelta(0)

    def accumulate_climb(ele):
        global total_climb, this_climb, this_climb_start, lastele

        if lastele >= 0:             # Not the first call
            if ele > lastele:        # Climbed since last step
                if this_climb == 0:
                    this_climb_start = lastele
                this_climb = this_climb + ele - lastele
            else:
                if this_climb > CLIMB_THRESHOLD:
                    total_climb = total_climb + this_climb
                    this_climb = 0
                elif ele <= this_climb_start:
                    # We got a little hump but not big enough to count;
                    # probably an artifact like taking the GPS out of its
                    # case or getting off the bike or something. Reset.
                    this_climb = 0
        lastele = ele

    for pt in trackpoints.points:
        if trackpoints.is_start(pt):
            lastlat = 0
            lastlon = 0
            lastele = -1
            continue

        lat, lon, ele, t = pt
        # We're requiring that trackpoints have a time attached.
        # Should we try to handle tracks that don't have timestamps?
        t = datetime.datetime.strptime(t['time'], '%Y-%m-%dT%H:%M:%SZ')
        lat =  float(lat)
        lon = float(lon)
        if not metric:
            ele = round(float(ele) * 3.2808399, 2)    # convert meters->feet
        else: 
            ele = round(float(ele),2)

        if lastlat != 0 and lastlon != 0:
            if not metric:
                dist = math.sqrt((lat - lastlat)**2 + (lon - lastlon)**2) \
                    * 69.046767              # 69.046767 converts nautical miles (arcminutes) to miles
            else:
                dist = math.sqrt((lat - lastlat)**2 + (lon - lastlon)**2) \
                    * 69.046767 * 1.60934
            
            total_dist += dist

            delta_t = t - lasttime   # a datetime.timedelta object
            speed = dist / delta_t.seconds * 60 * 60    # miles/hour
            if speed > SPEED_THRESHOLD:
                moving_time += delta_t
                #print "moving\t",
            else:
                stopped_time += delta_t
                #print "stopped\t",

        lasttime = t

        accumulate_climb(ele)

        lastlat = lat
        lastlon = lon

        # print total_dist, ele, "\t", time, lat, lon, "\t", total_climb
        # print total_dist, ele, "\t", time, total_climb

        distances.append(total_dist)
        eles.append(ele)

    smoothed_eles = smooth(eles, halfwin, beta)

    out = {}
    out['Total distance'] = total_dist
    out['Raw total climb'] = total_climb
    out['Smoothed total climb'] = tot_climb(smoothed_eles)
    out['Moving time'] = moving_time.seconds
    out['Stopped time'] = stopped_time.seconds
    out['Average moving speed'] = total_dist * 60 * 60 / moving_time.seconds
    out['Distances'] = distances
    out['Elevations'] = eles
    out['Smoothed elevations'] = smoothed_eles

    return out

def tot_climb(arr):
    global this_climb, this_climb_start

    tot = 0
    lastel = -1
    this_climb = 0
    this_climb_start = 0
    for el in arr:
        if lastel > 0:
            if el > lastel:
                if this_climb == 0:
                    this_climb_start = lastel
                this_climb += el - lastel
            elif el < lastel:
                if this_climb > CLIMB_THRESHOLD:
                    tot += this_climb
                    this_climb = 0
                elif el <= this_climb_start:
                    this_climb = 0

        lastel = el

    return tot

def smooth(x, halfwin, beta):
    """ Kaiser window smoothing.
        Unfortunately, this only smooths by a tiny bit,
        and changing beta doesn't affect that much.
    """
    window_len = 2 * halfwin + 1
    # extending the data at beginning and at the end
    # to apply the window at the borders
    s = numpy.r_[x[window_len-1:0:-1],x,x[-1:-window_len:-1]]
    w = numpy.kaiser(window_len,beta)
    y = numpy.convolve(w/w.sum(),s,mode='valid')
    return y[halfwin:len(y)-halfwin]

#
# main() to gather stats from a file passed in on the commandline
# and graph them if possible, else just print them.
#
def main():
    import sys
    import os
    import pytopo.TrackPoints

    try:
        import pylab
        have_pylab = True
    except ImportError:
        have_pylab = False
        print "pylab isn't installed; will print stats only, no plotting"

    parser = argparse.ArgumentParser(description='This parses track log files, in gpx format, and gives you a graph and a few statistics. ')
    parser.add_argument('--version', action='version', version=pytopo.__version__)
    parser.add_argument('-m', action="store_true", default=False, dest="metric", help='Use metric rather than standard units')
    parser.add_argument('-b', action="store", default=2, dest="beta", type=int, help='Kaiser window smoothing beta parameter (default = 2)')
    parser.add_argument('-w', action="store", default=15, dest="halfwin", type=int, help='Kaiser window smoothing halfwidth parameter (default = 15)')
    parser.add_argument('track_file', nargs='+')

    results = parser.parse_args()
    beta = results.beta
    halfwin = results.halfwin
    metric = results.metric
    track_file = results.track_file[0]


    #
    # Read the trackpoints file:
    #
    trackpoints = pytopo.TrackPoints()
    try:
        #trackpoints.read_track_file(args[0])
        trackpoints.read_track_file(results.track_file[0])
    except IOError, e:
        print e
        #print dir(e)
        return e.errno

    out = statistics(trackpoints, halfwin, beta, metric)

    #
    # Print and plot the results:
    #
    if not metric:
        print "%.1f miles. Raw total climb: %d'" % (out['Total distance'],
                                                    int(out['Raw total climb']))
        print "Smoothed climb: %d'" % out['Smoothed total climb']
        print "Average speed moving: %.1f mph" % out['Average moving speed']
    else:
        print "%.1f km. Raw total climb: %d m" % (out['Total distance'],
                                                    int(out['Raw total climb']))
        print "Smoothed climb: %d m" % out['Smoothed total climb']
        print "Average speed moving: %.1f kph" % out['Average moving speed']
    print "%d minutes moving, %d stopped" % (int(out['Moving time'] / 60),
                                             int(out['Stopped time'] / 60))

    if not have_pylab:
        return 0

    pylab.plot(out['Distances'], out['Elevations'],
               label="GPS elevation data", color="gray")
    pylab.plot(out['Distances'], out['Smoothed elevations'],
               color="red", label="smoothed (b=%.1f, hw=%d)" % (beta, halfwin))

    if not metric:
        title_string = "Elevation profile (" + str(round(out['Distances'][-1], 1)) \
                       + " miles, " + str(int(out['Smoothed total climb'])) \
                       + "' climb)"
    else:
        title_string = "Elevation profile (" + str(round(out['Distances'][-1], 1)) \
                       + " km, " + str(int(out['Smoothed total climb'])) \
                       + "' climb)"
    pylab.title(title_string)

    # Set the window titlebar to something other than "Figure 1"
    pylab.gcf().canvas.set_window_title("Ellie: " + track_file)
    if not metric:
        pylab.xlabel("miles")
        pylab.ylabel("feet")
    else:
        pylab.xlabel("km")
        pylab.ylabel("m")

    pylab.grid(True)
    pylab.legend()
    pylab.show()

if __name__ == '__main__':
    main()
