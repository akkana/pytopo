#!/usr/bin/env python3

from __future__ import print_function

import unittest
import sys
import datetime

sys.path.insert(0, '..')

from pytopo.MapViewer import parse_saved_site_line
from pytopo.TrackPoints import TrackPoints, GeoPoint


class ParseTests(unittest.TestCase):

    # executed prior to each test
    def setUp(self):
        pass


    # executed after each test
    def tearDown(self):
        pass


    def test_parse_saved_sites(self):
        lines = [
            '"San Francisco", -122.245, 37.471',
            'sydney, 151.125, -33.517, "", 11',
            '[ "Treasure Island, zoomed", -122.221287, 37.493330, humanitarian, 13]',
        ]
        expected = [
            ['San Francisco', '-122.245', '37.471'],
            ['sydney', '151.125', '-33.517', '', '11'],
            ['Treasure Island, zoomed', '-122.221287', '37.493330',
             'humanitarian', '13'],
        ]
        for i, line in enumerate(lines):
            parsed = parse_saved_site_line(line)
            self.assertEqual(parsed, expected[i])


    def verify_otowi(self, trackpoints):
        self.assertEqual(len(trackpoints.points), 1265)
        self.assertAlmostEqual(trackpoints.minlon, -106.2534204)
        self.assertAlmostEqual(trackpoints.maxlon, -106.2283611)
        self.assertAlmostEqual(trackpoints.minlat, 35.8849806)
        self.assertAlmostEqual(trackpoints.maxlat, 35.895508)

        # Check points, the first label and the first real point
        self.assertEqual(len(trackpoints.points), 1265)

        self.assertIsInstance(trackpoints.points[0], str)
        self.assertEqual(trackpoints.points[0], 'otowi-mesa-arch.gpx')

        self.assertIsInstance(trackpoints.points[1], GeoPoint)
        self.assertAlmostEqual(float(trackpoints.points[1].ele), 2108.0)
        self.assertEqual(trackpoints.points[1].timestamp,
                         '2016-03-02T17:28:45Z')

        self.assertEqual(len(trackpoints.waypoints), 3)
        lastpt = trackpoints.waypoints[-1]
        self.assertEqual(lastpt.name, 'Arches')
        self.assertAlmostEqual(lastpt.lat, 35.8872124)
        self.assertAlmostEqual(lastpt.lon, -106.2297864)


    def test_read_gpx(self):
        trackpoints = TrackPoints()
        trackpoints.read_track_file('test/data/otowi-mesa-arch.gpx')
        self.verify_otowi(trackpoints)

