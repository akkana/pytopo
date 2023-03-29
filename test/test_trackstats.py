#!/usr/bin/env python3

from __future__ import print_function

import unittest
import sys

sys.path.insert(0, '..')

import pytopo.TrackPoints
import pytopo.trackstats

class TestTrackStats(unittest.TestCase):

    # executed prior to each test
    def setUp(self):
        pass

    # executed after each test
    def tearDown(self):
        pass

    def test_track_stats(self):
        # Require numpy for unit tests, to ensure complete testing coverage.
        # This will raise ModuleNotFoundError: No module named 'numpy'
        # if it's not there.
        import numpy

        halfwin = 0
        beta = 2
        metric = False

        trackpoints = pytopo.TrackPoints()
        trackpoints.read_track_file('test/files/otowi-mesa-arch.gpx')

        stats = pytopo.trackstats.statistics(trackpoints, halfwin, beta, metric)

        self.assertAlmostEqual(stats['Total distance'], 3.5755, places=4)
        self.assertAlmostEqual(stats['Raw total climb'], 1164.68, places=4)
        self.assertAlmostEqual(stats['Smoothed total climb'], 781.1629,
                               places=4)
        self.assertAlmostEqual(stats['Lowest'], 6698.2772, places=4)
        self.assertAlmostEqual(stats['Highest'], 7070.2771, places=4)
        self.assertAlmostEqual(stats['Moving time'], 13126)
        self.assertAlmostEqual(stats['Stopped time'], 9920)
        self.assertAlmostEqual(stats['Average moving speed'], 0.9806,
                               places=4)
        self.assertEqual(len(stats['Distances']), 1263)

        trackpoints.read_track_file('test/files/otowi-mesa-arch.gpx')

        trackpoints = pytopo.TrackPoints()
        trackpoints.read_track_file('test/files/potrillo-cyn-loop.gpx')

        stats = pytopo.trackstats.statistics(trackpoints, halfwin, beta, metric)

        from pprint import pprint
        self.assertAlmostEqual(stats['Total distance'], 4.2699, places=4)
        self.assertAlmostEqual(stats['Raw total climb'], 1752.9500, places=4)
        self.assertAlmostEqual(stats['Smoothed total climb'], 202.5349,
                               places=4)
        self.assertAlmostEqual(stats['Lowest'], 6236.3346, places=4)
        self.assertAlmostEqual(stats['Highest'], 6443.9083, places=4)
        self.assertAlmostEqual(stats['Moving time'], 2849)
        self.assertAlmostEqual(stats['Stopped time'], 9506)
        self.assertAlmostEqual(stats['Average moving speed'], 5.3954,
                               places=4)
        self.assertEqual(len(stats['Distances']), 710)
