#!/usr/bin/env python3

import unittest
import sys, os
import shutil
import math

sys.path.insert(0, '..')

from pytopo import MapViewer, MapWindow


class ArgparseTests(unittest.TestCase):

    # executed prior to each test
    def setUp(self):
        self.configdir = 'test/files/config'
        os.environ['XDG_CONFIG_HOME'] = self.configdir
        try:
            os.mkdir(self.configdir)
        except FileExistsError:
            pass

        # A lot of this code mimcs MapViewer.main()
        self.viewer = MapViewer()
        self.viewer.exec_config_file()

        self.viewer.first_saved_site = len(self.viewer.KnownSites)
        self.viewer.read_saved_sites()
        self.viewer.read_tracks()
        # gc.enable()


    # executed after each test
    def tearDown(self):
        shutil.rmtree(self.configdir)
        self.configdir = None


    # unittest almostEqual requires more closeness than there is between
    # gpx and kml.
    def assertClose(self, a, b, tolerance=1e-5):
        if not math.isclose(a, b, rel_tol=tolerance):
            raise AssertionError('%f not close enough to %f' % (a, b))


    def test_gpx_arg(self):
        args = [ 'pytopo', 'test/files/otowi-mesa-arch.gpx' ]

        mapwin =  MapWindow(self.viewer)
        self.viewer.parse_args(mapwin, args)

        self.assertEqual(len(mapwin.trackpoints.points), 1265)
        self.assertEqual(len(mapwin.trackpoints.waypoints), 2)
        self.assertClose(mapwin.center_lon, -106.24089075)
        print("center lat", mapwin.center_lat)
        self.assertClose(mapwin.center_lat, 35.890244)


    def test_gpx_and_kml_arg(self):
        args = [ 'pytopo', 'test/files/otowi-mesa-arch.gpx',
                 'test/files/otowi-mesa-arch.kml' ]

        mapwin =  MapWindow(self.viewer)
        self.viewer.parse_args(mapwin, args)

        self.assertEqual(len(mapwin.trackpoints.points), 2530)
        self.assertEqual(len(mapwin.trackpoints.waypoints), 4)
        self.assertClose(mapwin.center_lon, -106.24089075)
        self.assertClose(mapwin.center_lat, 35.890244)


    def test_known_site(self):
        args = [ 'pytopo', 'san-francisco' ]

        with open(os.path.join(self.configdir, 'pytopo.sites'), "w") as cfp:
            cfp.write('''KnownSites = [
    [ "san-francisco", -122.245, 37.471, "", 11 ],
    ]''')

        mapwin =  MapWindow(self.viewer)
        self.viewer.parse_args(mapwin, args)

        self.assertEqual(len(mapwin.trackpoints.points), 0)
        self.assertEqual(len(mapwin.trackpoints.waypoints), 0)
        # XXX The default san-francisco coordinates are 37.471, -122.245
        # so it's not entirely clear why that isn't the center location.
        # Investigate this.
        self.assertClose(mapwin.center_lon, -122.4083)
        self.assertClose(mapwin.center_lat, 37.7850)
