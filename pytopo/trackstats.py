#!/usr/bin/env python

# Copyright (C) 2009-2026 by Akkana Peck.
# You are free to use, share or modify this program under
# the terms of the GPLv2 or, at your option, any later GPL.

"""Statistics on track logs,
   such as total distance, average speed, and total climb.
"""

from __future__ import print_function

import argparse

import math
import datetime
import sys, os

try:
    import numpy
except ImportError:
    pass

from pytopo import MapUtils, __version__

from pytopo.TrackPoints import TrackPoints


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
    eles = []
    sparse_eles = []
    distances = []
    speeds = []
    calcspeeds = []

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

        # This speed and distance calculation isn't terribly accurate,
        # since small position errors accumulate.
        # If there's a GPS speed recorded, use that and the
        # time interval for distance calculations,
        # but also try calculating the speed, to see how close they are.
        calcdist = MapUtils.haversine_distance(lat, lon,
                                               lastlat, lastlon, metric)
        dist = 0
        if delta_t:
            calcspeed = calcdist * 3600 / delta_t.total_seconds()
            calcspeeds.append(calcspeed)
        else:
            calcspeeds.append(0)

        if pt.attrs and 'speed' in pt.attrs:
            speed = float(pt.attrs['speed'])    # in m/s

            # This is in meters/s. Convert to mi/hr or km/hr
            if metric:
                speed *= 3.6
                # dist /= 1000.
            else:
                speed *= 2.2369363
                # dist /= 1609.344

            if delta_t:
                dist = speed * delta_t.seconds
        else:
            dist = calcdist
            if delta_t:
                speed = dist / delta_t.seconds * 60 * 60   # miles (or km) / hr
            else:
                speed = 0

        if not dist:
            dist = calcdist

        speeds.append(speed)

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

        # print(total_dist, ele, "\t", time, lat, lon, "\t", total_climb)
        # print(total_dist, ele, "\t", time, total_climb)

        distances.append(total_dist)

        eles.append(ele)
        if ele:
            sparse_eles.append(ele)

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

    # if missing_times:
    #     print("Some points don't have times! Can't calculate speed")

    out = {}
    out['Total distance'] = total_dist
    if len(eles):
        out['Raw total climb'] = total_climb

        # Display smoothed climb if available.
        # numpy (used for smoothing) can't just consider an array to be truthy:
        # "The truth value of an array with more than one element is ambiguous".
        if sparse_eles:
            if (smoothed_eles is not None) and len(smoothed_eles):
                out['Smoothed total climb'], out['Lowest'], out['Highest'] \
                    = tot_climb(smoothed_eles)
                out['High'] = smoothed_eles.max()
                out['Low'] = smoothed_eles.min()
            else:
                out['High'] = max(sparse_eles)
                out['Low'] = min(sparse_eles)

    out['Moving time'] = moving_time.seconds
    out['Stopped time'] = stopped_time.seconds
    if moving_time:
        out['Average moving speed'] = total_dist * 60 * 60 / moving_time.seconds
    out['Distances'] = distances
    if eles:
        out['Elevations'] = eles
        if smoothed_eles is not None and len(smoothed_eles):
            out['Smoothed elevations'] = smoothed_eles
    if sum(speeds):
        out['Speeds'] = speeds
    if sum(calcspeeds):
        out['Calculated Speeds'] = calcspeeds

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


def hr_series(points):
    """Extract (local_time, hr) pairs for points that have hr data."""
    times = []
    hrs = []
    for p in points:
        try:
            hr = p.extensions.get("hr")
        except:
            continue
        if hr is None:
            continue
        utc_dt = datetime.datetime.strptime(p.timestamp,
                                            "%Y-%m-%dT%H:%M:%SZ").replace(
                                                tzinfo=datetime.timezone.utc
        )
        local_dt = utc_dt.astimezone()  # converts to system-local timezone
        times.append(local_dt)
        hrs.append(int(hr))
    return times, hrs


def plot_hr(points):
    try:
        import matplotlib.pyplot as plt
        import matplotlib.dates as mdates
    except:
        print("Couldn't import matplotlib, can't plot heart rate",
              file=sys.stderr)

    times, hrs = hr_series(points)

    fig, ax = plt.subplots(figsize=(12, 5))
    ax.bar(times, hrs, width=0.0005, color="crimson")  # width in days (matplotlib date units)

    ax.set_xlabel("Time")
    ax.set_ylabel("Heart Rate (bpm)")
    ax.set_title("Heart Rate")

    # Format x-axis as HH:MM in local time
    local_tz = datetime.datetime.now().astimezone().tzinfo  # get system local tz
    ax.xaxis.set_major_formatter(mdates.DateFormatter("%H:%M", tz=local_tz))
    fig.autofmt_xdate()

    plt.tight_layout()
    plt.show(block=False)
    plt.pause(0.1)  # lets the GUI event loop actually draw the window


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
# main() to gather stats from a file passed in on the commandline.
#
def analyze_track(trackfile, args):

    progname = os.path.basename(trackfile)
    beta = args.beta
    halfwin = args.halfwin
    metric = args.metric

    #
    # Read the trackpoints file:
    #
    trackpoints = TrackPoints()
    try:
        trackpoints.read_track_file(trackfile)
        # XXX Read more than one file
    except IOError as e:
        print(e)
        #print(dir(e))
        return e.errno

    out = statistics(trackpoints, halfwin, beta, metric)

    #
    # Print and plot the results:
    #
    print("\n====", trackfile)
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

    # print("======= Distances", type(out['Distances']))
    # print(out['Distances'])
    # print("\n\n======= Elevations", type(out['Elevations']))
    # print(out['Elevations'])

    return out


def parse_trackstat_args(cmdlineargs):
    parser = argparse.ArgumentParser(
        description='This parses track log files, in gpx format, '
                     'and gives you a graph and a few statistics. ')
    parser.add_argument('--version', action='version',
                        version=__version__)
    parser.add_argument('-m', action="store_true", default=False,
                        dest="metric",
                        help='Use metric rather than US units')
    parser.add_argument('-b', action="store", default=2, dest="beta", type=int,
                        help='Kaiser window smoothing beta parameter (default: 2)')
    parser.add_argument('-w', action="store", default=0, dest="halfwin",
                        type=int,
                        help='Kaiser window smoothing halfwidth parameter '
                             '(default: will try to guess a reasonable value)')
    parser.add_argument('track_files', nargs='+')

    return parser.parse_args(cmdlineargs[1:])


if __name__ == '__main__':
    args = parse_trackstat_args(sys.argv)

    for trackfile in args.track_files:
        analyze_track(trackfile, args)
