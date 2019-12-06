#!/usr/bin/env python3

import unittest
import sys, os
import shutil
import math

sys.path.insert(0, '..')

from pytopo import MapViewer, MapWindow, ArgParseException


class ArgparseTests(unittest.TestCase):

    # executed prior to each test
    def setUp(self):
        self.configparent = os.path.join('test', 'files', 'config')
        self.assertNotEqual(self.configparent, '')
        self.configdir = os.path.join(self.configparent, 'pytopo')
        self.assertNotEqual(self.configdir, '')
        os.environ['XDG_CONFIG_HOME'] = self.configdir

        try:
            shutil.rmtree(self.configdir)
        except:
            pass

        try:
            os.mkdir(self.configparent)
        except FileExistsError:
            print("====", self.configparent, "already existed")

        try:
            os.mkdir(self.configdir)
        except FileExistsError:
            print("==== setUp:", self.configdir, "already existed")

        # A lot of this code mimcs MapViewer.main()
        self.viewer = MapViewer()
        self.viewer.exec_config_file()

        self.viewer.first_saved_site = len(self.viewer.KnownSites)
        self.viewer.read_saved_sites()
        self.viewer.read_tracks()
        # gc.enable()


    # executed after each test
    def tearDown(self):
        self.assertNotEqual(self.configparent, '')
        try:
            shutil.rmtree(self.configparent)
        except:
            print("==== tearDown: Couldn't shutil.rmtree", self.configparent)

        self.configdir = None
        self.configparent = None


    # unittest almostEqual requires more closeness than there is between
    # gpx and kml.
    def assertCloseEnough(self, a, b, tolerance=1e-5):
        if not math.isclose(a, b, rel_tol=tolerance):
            raise AssertionError('%f not close enough to %f' % (a, b))


    def test_gpx_arg(self):
        args = [ 'pytopo', 'test/files/otowi-mesa-arch.gpx' ]

        mapwin =  MapWindow(self.viewer)
        self.viewer.parse_args(mapwin, args)

        self.assertEqual(len(mapwin.trackpoints.points), 1265)
        self.assertEqual(len(mapwin.trackpoints.waypoints), 2)
        self.assertCloseEnough(mapwin.center_lon, -106.24089075)
        self.assertCloseEnough(mapwin.center_lat, 35.890244)


    def test_gpx_and_kml_arg(self):
        args = [ 'pytopo', 'test/files/otowi-mesa-arch.gpx',
                 'test/files/otowi-mesa-arch.kml' ]

        mapwin =  MapWindow(self.viewer)
        self.viewer.parse_args(mapwin, args)

        self.assertEqual(len(mapwin.trackpoints.points), 2530)
        self.assertEqual(len(mapwin.trackpoints.waypoints), 4)
        self.assertCloseEnough(mapwin.center_lon, -106.24089075)
        self.assertCloseEnough(mapwin.center_lat, 35.890244)


    def test_explicit_coords(self):
        args = [ 'pytopo', '37.471', '-122.245' ]

        mapwin =  MapWindow(self.viewer)
        self.viewer.parse_args(mapwin, args)

        self.assertCloseEnough(mapwin.center_lon, -122.245)
        self.assertCloseEnough(mapwin.center_lat, 37.471)


    def test_explicit_coords_plus_gpx(self):
        args = [ 'pytopo', '35.85', '-106.4', '-t',
                 'test/files/otowi-mesa-arch.gpx' ]

        mapwin =  MapWindow(self.viewer)
        self.viewer.parse_args(mapwin, args)

        self.assertEqual(len(mapwin.trackpoints.points), 1265)
        self.assertEqual(len(mapwin.trackpoints.waypoints), 2)
        self.assertCloseEnough(mapwin.center_lon, -106.4)
        self.assertCloseEnough(mapwin.center_lat, 35.85)


    def test_bogus_args(self):
        arglists = [ [ 'pytopo', 'test/test_argparsing.py' ],
                     [ 'pytopo', 'rumplestiltskin' ],
                     [ 'pytopo', '35.0', 'xyz' ],
                   ]

        for args in arglists:
            mapwin =  MapWindow(self.viewer)

            try:
                self.viewer.parse_args(mapwin, args)
                self.assertEqual("Should have barfed on the bogus args ["
                                 + ', '.join(args) + "]", None)

            except ArgParseException:
                print("ArgParseException, good")

            except SystemExit:
                print("SystemExit, fine")


    def test_known_site(self):
        args = [ 'pytopo', 'san-francisco' ]

        with open(os.path.join(self.configdir, 'pytopo', 'pytopo.sites'),
                  "w") as cfp:
            cfp.write('''Collections = [
    OSMMapCollection( "humanitarian", "~/Maps/humanitarian",
                      ".png", 256, 256, 13,
                      "http://a.tile.openstreetmap.fr/hot/{z}/{x}/{y}.png",
                      maxzoom=15,
                      attribution="Humanitarian OSM Maps, map data © OpenStreetMap contributors"),
    ]

# Default to whichever MapCollection is listed first.
defaultCollection = Collections[0].name

KnownSites = [
    [ "san-francisco", -122.245, 37.471, "", 11 ],
    ]''')

        mapwin =  MapWindow(self.viewer)
        self.viewer.parse_args(mapwin, args)

        self.assertEqual(len(mapwin.trackpoints.points), 0)
        self.assertEqual(len(mapwin.trackpoints.waypoints), 0)
        # XXX The default san-francisco coordinates are 37.471, -122.245
        # so it's not entirely clear why that isn't the center location.
        # That's not the case in the test_explicit_coords case,
        # where the center is exactly the coordinates specified.
        # Investigate this.
        self.assertCloseEnough(mapwin.center_lon, -122.4083)
        self.assertCloseEnough(mapwin.center_lat, 37.7850)
