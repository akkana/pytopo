#!/usr/bin/env python3

from __future__ import print_function

import unittest
import sys

sys.path.insert(0, '..')

import pytopo.TrackPoints
import pytopo.trackstats

class ParseTests(unittest.TestCase):

    # executed prior to each test
    def setUp(self):
        pass

    # executed after each test
    def tearDown(self):
        pass

    def test_track_stats(self):
        trackpoints = pytopo.TrackPoints()
        trackpoints.read_track_file('test/files/otowi-mesa-arch.gpx')

        # Require numpy for unit tests, to ensure complete testing coverage.
        # This will raise ModuleNotFoundError: No module named 'numpy'
        # if it's not there.
        import numpy

        halfwin = 0
        beta = 2
        metric = False

        stats = pytopo.trackstats.statistics(trackpoints, halfwin, beta, metric)

        self.assertAlmostEqual(stats['Total distance'], 5.150545737380824)
        self.assertAlmostEqual(stats['Raw total climb'], 1345.1099999999979)
        self.assertAlmostEqual(stats['Smoothed total climb'], 781.1629205918334)
        self.assertAlmostEqual(stats['Lowest'], 6698.2771590538805)
        self.assertAlmostEqual(stats['Highest'], 7070.277109582933)
        self.assertAlmostEqual(stats['Moving time'], 13126)
        self.assertAlmostEqual(stats['Stopped time'], 40656)
        self.assertAlmostEqual(stats['Average moving speed'], 1.412613488844352)
        self.assertEqual(len(stats['Distances']), 1263)
