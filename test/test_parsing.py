#!/usr/bin/env python3

from __future__ import print_function

import unittest
import sys, os

sys.path.insert(0, '..')

from .utils import assertCloseEnough, create_kmz
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

    def verify_otowi(self, trackpoints, trackname, track_times, track_eles):
        self.assertEqual(len(trackpoints.points), 1265)

        # Check points, the first label and the first real point
        self.assertEqual(len(trackpoints.points), 1265)

        self.assertIsInstance(trackpoints.points[0], str)
        self.assertEqual(trackpoints.points[0], trackname)

        self.assertIsInstance(trackpoints.points[1], GeoPoint)
        if track_eles:
            assertCloseEnough(float(trackpoints.points[1].ele), 2108.0)
        if track_times:
            self.assertEqual(trackpoints.points[1].timestamp,
                             '2016-03-02T17:28:45Z')

        self.assertEqual(len(trackpoints.waypoints), 2)
        lastpt = trackpoints.waypoints[-1]
        self.assertEqual(lastpt.name, 'Arches')
        assertCloseEnough(lastpt.lat, 35.8872124)
        assertCloseEnough(lastpt.lon, -106.2297864)

    def test_read_gpx(self):
        trackpoints = TrackPoints()
        trackpoints.read_track_file('test/files/otowi-mesa-arch.gpx')
        self.verify_otowi(trackpoints, 'otowi-mesa-arch.gpx',
                          track_times=True, track_eles=True)

        # GPX specifies region boundaries, but not all formats do.
        bounds = trackpoints.get_bounds()
        assertCloseEnough(trackpoints.get_bounds().as_tuple(),
                          (-106.2534204, 35.8849806,
                           -106.2283611, 35.895508))

    def test_read_kml(self):
        trackpoints = TrackPoints()
        trackpoints.read_track_file('test/files/otowi-mesa-arch.kml')
        self.verify_otowi(trackpoints, 'Otowi Mesa Trail',
                          track_times=False, track_eles=False)

    def test_read_kmz(self):
        kmzfile = create_kmz('test/files/otowi-mesa-arch')

        trackpoints = TrackPoints()
        trackpoints.read_track_file(kmzfile)
        self.verify_otowi(trackpoints, 'Otowi Mesa Trail',
                          track_times=False, track_eles=False)

        os.unlink(kmzfile)

    def test_read_geojson(self):
        trackpoints = TrackPoints()
        trackpoints.read_track_file('test/files/otowi-mesa-arch.geojson')
        trackpoints2 = TrackPoints()
        trackpoints2.read_track_file('test/files/otowi-mesa-arch.gpx')

        for i, pt in enumerate(trackpoints.points):
            if not trackpoints.is_start(trackpoints.points[i]) and \
               not trackpoints.is_start(trackpoints2.points[i]):
                assertCloseEnough(trackpoints.points[i].lat,
                                  trackpoints2.points[i].lat)
                assertCloseEnough(trackpoints.points[i].lon,
                                  trackpoints2.points[i].lon)

        self.verify_otowi(trackpoints, 'unnamed',
                          track_times=False, track_eles=True)

