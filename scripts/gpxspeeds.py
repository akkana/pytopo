#!/usr/bin/env python3

"""Examine the max speed in a collection of GPX files.
"""

from pytopo import trackstats
from pytopo.TrackPoints import TrackPoints


def speedrange(gpxfile):
    trackpoints = TrackPoints()
    trackpoints.read_track_file(gpxfile)
    halfwin = 0
    beta = 2
    metric = False
    return trackstats.statistics(trackpoints, halfwin, beta, metric)


if __name__ == '__main__':
    import sys, os

    maxmax = 0
    maxsum = 0
    nfiles = 0

    results = []

    bins = [0] * 40

    try:
        for f in sys.argv[1:]:
            try:
                stats = speedrange(f)
                maxspeed = stats['Max speed']
                # print("%42s  %5.2f" % (os.path.basename(f), maxspeed))
                maxmax = max(maxspeed, maxmax)
                maxsum += maxspeed
                nfiles += 1
                results.append((maxspeed, os.path.basename(f)))
                bins[int(maxspeed)] += 1
            except RuntimeError:
                pass

        results.sort()
        for r in results:
            print("%5.2f    %-42s" % r)

        print("\nHighest speed:", maxmax)
        print("Average max speed:", maxsum / nfiles)

        # Cut off the bins after the last nonzero value
        for i in range(len(bins)-1, 0, -1):
            if bins[i]:
                break
        # now i is the last index that has a value
        bins = bins[:i+1]
        print()
        for i, bin in enumerate(bins):
            print('%3d %s' % (i, '*' * bin))

    except KeyboardInterrupt:
        print("Bye")

