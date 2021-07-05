#!/usr/bin/env python

# Copyright (C) 2009-2018 by Akkana Peck.
# You are free to use, share or modify this program under
# the terms of the GPLv2 or, at your option, any later GPL.

"""Statistics on track logs,
   such as total distance, average speed, and total climb.
"""

from __future__ import print_function

import math
import datetime
import argparse
import sys

try:
    import numpy
except ImportError:
    pass

from pytopo.MapUtils import MapUtils


CLIMB_THRESHOLD = 8

# How fast do we have to be moving, in miles/hour,
# to count toward the total distance and the moving average speed?
SPEED_THRESHOLD = .2

# Variables that need to be global, because statistics() and
# accumulate_climb() need to share them, and python 2.7 doesn't
# have nonlocal.
total_climb = 0
this_climb = 0
this_climb_start = 0
lastele = -1


def statistics(trackpoints, halfwin, beta, metric, startpt=0, onetrack=False):
    """Accumulate statistics like mileage and total climb.
       Return a dictionary of stats collected.
       If startpt is provided, start from a sub-track.
       If onetrack is True, only analyze one track segment.
    """
    global total_climb, this_climb, this_climb_start, lastele

    # The variables we're going to plot:
    eles = [ ]
    distances = [ ]

    missing_times = False

    # Accumulators:
    lastlat = 0
    lastlon = 0
    total_dist = 0

    lasttime = None
    moving_time = datetime.timedelta(0)
    stopped_time = datetime.timedelta(0)

    def accumulate_climb(ele):
        global total_climb, this_climb, this_climb_start, lastele

        if lastele and lastele >= 0:             # Not the first call
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

    for pt in trackpoints.points[startpt:]:
        if trackpoints.is_start(pt):
            lastlat = 0
            lastlon = 0
            lastele = -1
            if onetrack and total_dist:
                break
            else:
                continue

        lat, lon, ele, t = pt.lat, pt.lon, pt.ele, pt.timestamp

        try:
            t = datetime.datetime.strptime(t, '%Y-%m-%dT%H:%M:%SZ')
        except:
            t = None
            missing_times = True

        lat =  float(lat)
        lon = float(lon)
        if ele:
            if metric:
                ele = round(float(ele),2)
            else:
                ele = round(float(ele) * 3.2808399, 2)    # convert meters->feet

        if not lastlat or not lastlon:
            lastlat = lat
            lastlon = lon
            lasttime = t
            continue

        if t:
            delta_t = t - lasttime   # a datetime.timedelta object
        else:
            delta_t = datetime.timedelta(0)

        speed = 0
        dist = 0

        # This speed and distance calculation isn't terribly accurate.
        # If there's a GPS speed recorded, use that and the
        # time interval for distance calculations.
        if pt.attrs and 'speed' in pt.attrs:
            speed = float(pt.attrs['speed'])    # in m/s
            if delta_t:
                dist = speed * delta_t.seconds
                # This is in meters/s. Convert to mi/hr or km/hr.
                if metric:
                    dist /= 1000.
                    speed *= 3.6
                else:
                    dist /= 1609.344
                    speed *= 2.2369363

        if dist == 0:
            dist = MapUtils.haversine_distance(lat, lon,
                                               lastlat, lastlon, metric)
            if delta_t:
                speed = dist / delta_t.seconds * 60 * 60   # miles (or km) / hr

        if speed > SPEED_THRESHOLD or not delta_t:
            total_dist += dist
            moving_time += delta_t

            lasttime = t
            lastlat = lat
            lastlon = lon

            accumulate_climb(ele)

        else:
            # If we're considered stopped, don't update lastlat/lastlon.
            # We'll calculate distance from the first stopped point.
            stopped_time += delta_t
            #print("stopped\t")

        # print(total_dist, ele, "\t", time, lat, lon, "\t", total_climb)
        # print(total_dist, ele, "\t", time, total_climb)

        distances.append(total_dist)
        eles.append(ele)

    # If halfwin wasn't supplied, try to guess a good value.
    # XXX TO DO: figure out a way to guess.
    if not halfwin:
        # print(len(eles), "points", ", average distance per step", total_dist / len(eles))
        halfwin = 15

    # Smoothing eles will fail if there are no eles.
    try:
        smoothed_eles = smooth(eles, halfwin, beta)
    except TypeError:
        smoothed_eles = []

    if missing_times:
        print("Some points don't have times! Can't calculate speed")

    out = {}
    out['Total distance'] = total_dist
    if len(eles):
        out['Raw total climb'] = total_climb

        # Display smoothed climb if available.
        # numpy (used for smoothing) can't just consider an array to be truthy:
        # "The truth value of an array with more than one element is ambiguous".
        if (smoothed_eles is not None) and len(smoothed_eles):
            out['Smoothed total climb'], out['Lowest'], out['Highest'] \
                = tot_climb(smoothed_eles)
            out['High'] = smoothed_eles.max()
            out['Low'] = smoothed_eles.min()
        else:
            out['High'] = max(eles)
            out['Low'] = min(eles)
    out['Moving time'] = moving_time.seconds
    out['Stopped time'] = stopped_time.seconds
    if moving_time:
        out['Average moving speed'] = total_dist * 60 * 60 / moving_time.seconds
    out['Distances'] = distances
    if eles:
        out['Elevations'] = eles
        if smoothed_eles is not None and len(smoothed_eles):
            out['Smoothed elevations'] = smoothed_eles

    return out


def tot_climb(arr):
    global this_climb, this_climb_start

    tot = 0.
    lastel = -1
    this_climb = 0.
    this_climb_start = 0.
    lowest = 30000.
    highest = -30000.
    for el in arr:
        if lastel >= 0:
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

        if el > highest:
            highest = el
        if el < lowest:
            lowest = el
        lastel = el

    if this_climb > 0:
        tot += this_climb

    return tot, lowest, highest

def smooth(vals, halfwin, beta):
    """ Kaiser window smoothing."""

    # Smoothing requires numpy
    if 'numpy' not in sys.modules:
        return None

    window_len = 2 * halfwin + 1
    # extending the data at beginning and at the end
    # to apply the window at the borders
    s = numpy.r_[vals[window_len-1:0:-1], vals, vals[-1:-window_len:-1]]
    w = numpy.kaiser(window_len, beta)
    smoothed = numpy.convolve(w/w.sum(), s, mode='valid')
    return smoothed[halfwin:len(smoothed) - halfwin]

#
# main() to gather stats from a file passed in on the commandline
# and graph them if possible, else just print them.
#
def main():
    import sys
    import os
    import pytopo.TrackPoints

    try:
        import pylab as plt
        have_plt = True
    except ImportError:
        have_plt = False
        print("plt (matplotlib) isn't installed; "
              "will print stats only, no plotting")

    if 'numpy' not in sys.modules:
        print("Ellie requires the numpy module")
        sys.exit(1)

    progname = os.path.basename(sys.argv[0])

    parser = argparse.ArgumentParser(description='This parses track log files, in gpx format, and gives you a graph and a few statistics. ')
    parser.add_argument('--version', action='version',
                        version=pytopo.__version__)
    parser.add_argument('-m', action="store_true", default=False,
                        dest="metric",
                        help='Use metric rather than US units')
    parser.add_argument('-b', action="store", default=2, dest="beta", type=int,
                        help='Kaiser window smoothing beta parameter (default: 2)')
    parser.add_argument('-w', action="store", default=0, dest="halfwin",
                        type=int, help='Kaiser window smoothing halfwidth parameter (default: will try to guess a reasonable value)')
    parser.add_argument('track_file', nargs='+')

    results = parser.parse_args()
    beta = results.beta
    halfwin = results.halfwin
    metric = results.metric
    track_files = results.track_file

    #
    # Read the trackpoints file:
    #
    trackpoints = pytopo.TrackPoints()
    try:
        trackpoints.read_track_file(track_files[0])
        # XXX Read more than one file
    except IOError as e:
        print(e)
        #print(dir(e))
        return e.errno

    out = statistics(trackpoints, halfwin, beta, metric)

    #
    # Print and plot the results:
    #
    climb_units = 'm' if metric else "'"
    dist_units = 'km' if metric else 'mi'
    print("%.1f %s" % (out['Total distance'], dist_units))
    if 'Raw total climb' in out:
        print("Raw total climb: %d%s" % (int(out['Raw total climb']),
                                         climb_units))
    if 'Smoothed total climb' in out:
        print("Smoothed climb: %d%s" % (out['Smoothed total climb'],
                                        climb_units))
    if 'Lowest' in out and 'Highest' in out:
        print("  from %d to %d" % (out['Lowest'], out['Highest']))
    if 'Moving time' in out and 'Stopped time' in out:
        print("%d minutes moving, %d stopped" % (int(out['Moving time'] / 60),
                                                 int(out['Stopped time'] / 60)))
    if 'Average moving speed' in out:
        print("Average speed moving: %.1f %s/h" % (out['Average moving speed'],
                                                   dist_units))
    if not have_plt:
        return 0

    # print("======= Distances", type(out['Distances']))
    # print(out['Distances'])
    # print("\n\n======= Elevations", type(out['Elevations']))
    # print(out['Elevations'])

    plt.plot(out['Distances'], out['Elevations'],
               label="GPS elevation data", color="gray")
    plt.plot(out['Distances'], out['Smoothed elevations'],
               color="red", label="smoothed (b=%.1f, hw=%d)" % (beta, halfwin))

    title_string = "Elevation profile (%.1f %s, %d%s climb)" \
                   % (out['Distances'][-1], dist_units,
                      out['Smoothed total climb'], climb_units)
    plt.title(title_string)

    # Set the window titlebar to something other than "Figure 1"
    plt.gcf().canvas.set_window_title("%s: %s" % (progname, track_files[0]))

    plt.xlabel("miles")
#    plt.get_current_fig_manager().get_window().set_title(os.path.basename(args[0] + ": " + title_string))
    plt.ylabel("feet")
    plt.grid(True)
    plt.legend()

    # Exit on key q
    plt.figure(1).canvas.mpl_connect('key_press_event',
                                     lambda e:
                                         sys.exit(0) if e.key == 'ctrl+q'
                                         else None)

    plt.show()

if __name__ == '__main__':
    main()
