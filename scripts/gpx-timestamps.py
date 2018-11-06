#!/usr/bin/env python

# Add bogus timestamps to all paths in a GPX file,
# as required to import a path into OpenStreetMap.

import sys

from pytopo.TrackPoints import TrackPoints

def add_gpx_timestamps(infile, outfile):
    trackpoints = TrackPoints()
    trackpoints.read_track_file(infile)

    trackpoints.add_bogus_timestamps()

    trackpoints.save_GPX(outfile)
    print "Saved to", outfile

if __name__ == '__main__':
    add_gpx_timestamps(sys.argv[1], sys.argv[2])

