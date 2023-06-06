#!/usr/bin/env python3

import unittest
import sys, os

sys.path.insert(0, '..')

import pytopo.configfile as configfile

from .testutils import assertCloseEnough, create_kmz
from pytopo.TrackPoints import TrackPoints, GeoPoint


class ConfigFileTests(unittest.TestCase):

    # executed prior to each test
    def setUp(self):
        pass

    # executed after each test
    def tearDown(self):
        pass

    def check_site_equal(self, site1, site2):
        self.assertEqual(len(site1), len(site2))
        self.assertEqual(site1[0], site2[0])

        assertCloseEnough(site1[1], site2[1])
        assertCloseEnough(site1[2], site2[2])

        for i, val in enumerate(site1[3:]):
            self.assertEqual(site1[i+3], site2[i+3])

    def test_parse_saved_sites(self):
        configfile.CONFIG_DIR = "./test/files"

        # The correct decimal degree values, for verification
        dd_values = [
            ['PEEC', -106.3062492, 35.8848105, 'openstreetmap', 18],
            ['paria-ranger', -111.912, 37.10583, 'openstreetmap']
        ]

        # test site lines using DM coordinates
        dm_sites = """
[ 'PEEC',         -106.1837, 35.5309, 'openstreetmap', 18 ]
[ 'paria-ranger', -111.5472, 37.0636, "openstreetmap" ]
"""
        # print("******* DM test")
        filename = "test/files/dm.sites"
        with open(filename, "w") as fp:
            fp.write(dm_sites)

        sites = configfile.read_saved_sites(filename)
        for i, site in enumerate(sites):
            self.check_site_equal(site, dd_values[i])

        os.unlink(filename)

        # test site lines using DMS coordinates
        # print("******* DMS test")
        dms_sites = """
# FORMAT=DMS
[ 'PEEC',            -106.182250,           35.530532,  'openstreetmap', 18 ]
[ 'paria-ranger', '''-111° 54' 43.2"''', '''37° 6' 20.99"''', "openstreetmap" ]
"""
        filename = "test/files/dms.sites"
        with open(filename, "w") as fp:
            fp.write(dms_sites)

        sites = configfile.read_saved_sites(filename)
        for i, site in enumerate(sites):
            self.check_site_equal(site, dd_values[i])

        os.unlink(filename)

        # test site lines using DD coordinates
        # print("******* DD test")
        dd_sites = """
# FORMAT=DD
[ 'PEEC',         -106.3062492, 35.8848105, 'openstreetmap', 18 ]
[ 'paria-ranger', -111.912,     37.10583,     "openstreetmap" ]
"""

        filename = "test/files/dd.sites"
        with open(filename, "w") as fp:
            fp.write(dd_sites)
            # print("Saved DD test to", filename)

        sites = configfile.read_saved_sites(filename)
        for i, site in enumerate(sites):
            self.check_site_equal(site, dd_values[i])

        os.unlink(filename)

        # print("saved sites filename:", configfile.saved_sites_filename())

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

