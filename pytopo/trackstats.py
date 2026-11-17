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
    import numpy as np
    from numpy.lib.stride_tricks import sliding_window_view
except ImportError:
    pass

from pytopo import MapUtils, __version__

from pytopo.TrackPoints import TrackPoints


CLIMB_THRESHOLD = 8

# How fast do we have to be moving, in miles/hour,
# to count toward the total distance and the moving average speed?
SPEED_THRESHOLD = .3

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
    gpxspeeds = []
    calcspeeds = []

    missing_times = False

    # Accumulators:
    lastlat = 0
    lastlon = 0
    total_dist = 0

    start_time = None
    end_time = None

    lasttime = None
    moving_time = datetime.timedelta(0)
    stopped_time = datetime.timedelta(0)
    tot_time = datetime.timedelta(0)

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

            if not start_time:
                start_time = t
            end_time = t
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

        # First point with coordinates?
        if not lastlat or not lastlon or not lasttime:
            lastlat = lat
            lastlon = lon
            lasttime = t
            continue

        if t:
            delta_t = t - lasttime   # a datetime.timedelta object
        else:
            delta_t = datetime.timedelta(0)

        tot_time += delta_t

        # This speed and distance calculation isn't terribly accurate,
        # since small position errors accumulate.
        # If there's a GPS speed recorded, use that and the
        # time interval for distance calculations,
        # but also try calculating the speed, to see how close they are.
        # Sometimes they're way off.
        dist = 0
        calcdist = MapUtils.haversine_distance(lat, lon,
                                               lastlat, lastlon, metric)
        if delta_t:
            calcspeed = calcdist * 3600 / delta_t.total_seconds()
            calcspeeds.append(calcspeed)
        else:
            calcspeeds.append(0)

        '''
        XXX
        A maybe better way of estimating speed from positions:
def speed_from_positions(t, lat, lon, k=2):
    """Central-difference speed over points i-k..i+k. t in seconds (float array)."""
    R = 3958.8  # miles; use 6371.0 for km
    lat_r, lon_r = np.radians(lat), np.radians(lon)
    i0 = np.clip(np.arange(len(t)) - k, 0, len(t) - 1)
    i1 = np.clip(np.arange(len(t)) + k, 0, len(t) - 1)
    dlat = lat_r[i1] - lat_r[i0]
    dlon = lon_r[i1] - lon_r[i0]
    a = np.sin(dlat/2)**2 + np.cos(lat_r[i0]) * np.cos(lat_r[i1]) * np.sin(dlon/2)**2
    dist = 2 * R * np.arcsin(np.sqrt(a))
    dt = t[i1] - t[i0]
    return np.where(dt > 0, dist / dt * 3600, np.nan)  # mi/hr
        '''

        if pt.speed:
            speed = float(pt.speed)    # in m/s

            # This is in meters/s. Convert to mi/hr or km/hr
            if metric:
                speed *= 3.6
                # dist /= 1000.
            else:
                speed *= 2.2369363
                # dist /= 1609.344

            # print("Speed %.2f calculated (%.2f/%.2f sec), %.2f in GPX"
            #       % (calcspeed, calcdist, delta_t.total_seconds(), speed))

            gpxspeeds.append(speed)

            if delta_t:
                # speed is in mi/hr or km/hr, so convert from seconds
                dist = speed * delta_t.seconds/3600

        else:
            # It looks like places where the GPX speed disappears are mostly
            # places where the speed went to zero or near-zero; at least,
            # they coincide with places where the calculated speed is zero.
            # If that turns out not to be true, maybe use np.nan
            # though that will require changes in algorithms like hampel_despike.
            gpxspeeds.append(0)
            dist = calcdist
            if delta_t:
                speed = calcspeed   # miles (or km) / hr
            else:
                speed = 0

        if not dist:
            dist = calcdist

        if delta_t:
            if speed > SPEED_THRESHOLD:
                total_dist += dist
                moving_time += delta_t

                lastlat = lat
                lastlon = lon

                accumulate_climb(ele)

            else:
                # If we're considered stopped, don't update lastlat/lastlon.
                # We'll calculate distance from the first stopped point.
                stopped_time += delta_t

        lasttime = t

        # print(total_dist, ele, "\t", time, lat, lon, "\t", total_climb)
        # print(total_dist, ele, "\t", time, total_climb)

        distances.append(total_dist)

        eles.append(ele)
        if ele:
            sparse_eles.append(ele)

    # If halfwin wasn't supplied, try to guess a good value.
    # XXX TO DO: figure out a way to guess.
    if not halfwin:
        # print(len(eles), "points", ", average distance per step",
        #       total_dist / len(eles))
        halfwin = 15

    # Smoothing eles will fail if there are no eles or if numpy isn't there.
    try:
        smoothed_eles = smooth(eles, halfwin, beta)
    except (TypeError, NameError):
        smoothed_eles = []

    # if missing_times:
    #     print("Some points don't have times! Can't calculate speed")

    out = {}
    if start_time:
        out['Start time'] = start_time
    if end_time:
        out['End time'] = end_time
    if tot_time:
        out['Total time'] = tot_time
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

    if sum(gpxspeeds):
        try:
            out['GPS Speeds'], mask = hampel_despike(gpxspeeds)
            out['Max speed'] = max(out['GPS Speeds'])
        except NameError:
            # Will print an error later when failing to despike calc speeds
            pass
    else:
        print("No GPX speeds")

    if sum(calcspeeds):
        # Calculated speeds need to be smoothed: they're prone to
        # outlandish spikes.
        # A halfwin of 1 gives a much closer fit to the GPX data
        # than the 15 used for elevation,
        # though it makes the smoothed calcspeeds lag significantly
        # behind the GPX speeds. Beta doesn't seem to make much difference,
        # at least between 1 and 50.
        try:
            out['Calculated Speeds'], mask = hampel_despike(calcspeeds)
            good = ~mask
            out['Calculated Speeds'] = np.interp(
                np.arange(len(out['Calculated Speeds'])),
                np.flatnonzero(good), out['Calculated Speeds'][good])
        except:
            print("Couldn't despike speed data, maybe numpy is missing?",
                  file=sys.stderr)

        # Save the raw, non-despiked speeds too
        out['Calculated Speeds (raw)'] = calcspeeds
        out['GPS Speeds (raw)'] = gpxspeeds

        # Only set the max speed to a calculated value if there
        # were no GPX speeds
        if 'Max speed' not in out:
            try:
                out['Max speed'] = max(out['Calculated Speeds'])
            except KeyError:
                try:
                    out['Max speed'] = max(out['Calculated Speeds (raw)'])
                except:
                    pass

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
    window_len = 2 * halfwin + 1
    # extending the data at beginning and at the end
    # to apply the window at the borders
    s = np.r_[vals[window_len-1:0:-1], vals, vals[-1:-window_len:-1]]
    w = np.kaiser(window_len, beta)
    smoothed = np.convolve(w/w.sum(), s, mode='valid')
    return smoothed[halfwin:len(smoothed) - halfwin]


def hampel_despike(x, half_window=3, n_sigmas=3.0, min_dev=0.0):
    """Replace spikes with the local median; leave everything else untouched.

       x            : 1-D array of speeds
       half_window  : neighbors on each side (window = 2*half_window + 1)
       n_sigmas     : threshold in robust standard deviations
       min_dev      : absolute floor on the threshold (same units as x)
       Returns (cleaned, mask_of_replaced_points)
    """
    x = np.asarray(x, dtype=float)
    w = 2 * half_window + 1
    padded = np.pad(x, half_window, mode='reflect')
    win = sliding_window_view(padded, w)
    med = np.median(win, axis=1)
    mad = 1.4826 * np.median(np.abs(win - med[:, None]), axis=1)
    thresh = np.maximum(n_sigmas * mad, min_dev)
    mask = np.abs(x - med) > thresh
    return np.where(mask, med, x), mask


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
    trackpoints.read_track_file(trackfile)    # Might raise IOError

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
    if 'Start time' in out:
        print("Start time:", out['Start time'])
    if 'End time' in out:
        print("End time:", out['End time'])
    if 'Start time' in out and 'End time' in out:
        tot_time = out['End time'] - out['Start time']
        print("Total time:", tot_time, "(%d minutes)" % (tot_time.seconds / 60))

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
    parser.add_argument('-b', action="store", default=80, dest="beta", type=int,
                        help='Kaiser window smoothing beta parameter (default: 80)')
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
