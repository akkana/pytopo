#!/usr/bin/env python3

import unittest
import sys, os
import shutil

sys.path.insert(0, '..')

from .testutils import assertCloseEnough, create_kmz
from pytopo import MapViewer, MapWindow, ArgParseException, configfile
from pytopo import MapUtils


class ArgparseTests(unittest.TestCase):

    # executed prior to each test
    def setUp(self):
        self.configparent = os.path.join('test', 'files', 'config')
        self.assertNotEqual(self.configparent, '')
        self.configdir = os.path.join(self.configparent, 'pytopo')
        configfile.CONFIG_DIR = self.configdir
        self.assertNotEqual(self.configdir, '')
        os.environ['XDG_CONFIG_HOME'] = self.configdir
        self.sitefile = None

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
        self.viewer.KnownSites += configfile.read_saved_sites()
        self.viewer.KnownTracks += configfile.read_tracks()
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

        if self.sitefile and os.path.exists(self.sitefile):
            os.unlink(self.sitefile)

    def create_config_file(self):
        self.sitefile = os.path.join(self.configdir, 'pytopo.sites')
        with open(self.sitefile, "w") as cfp:
            cfp.write('''Collections = [
    OSMMapCollection( "humanitarian", "~/Maps/humanitarian",
                      ".png", 256, 256, 13,
                      "http://a.tile.openstreetmap.fr/hot/{z}/{x}/{y}.png",
                      maxzoom=15,
                      attribution="Humanitarian OSM Maps, map data © OpenStreetMap contributors"),
    ]

    KnownSites = [
         "san-francisco", -122.4276, 37.7807, "USGS" ],
    ]''')
            # The site file uses dd.mmss but everything else wants DD
            return ("san-francisco", -122.4276, 37.7807)

    def test_gpx_arg(self):
        args = [ 'pytopo', 'test/files/otowi-mesa-arch.gpx' ]

        mapwin =  MapWindow(self.viewer)
        self.viewer.parse_args(mapwin, args)

        self.assertEqual(len(mapwin.trackpoints.points), 1265)
        self.assertEqual(len(mapwin.trackpoints.waypoints), 2)
        assertCloseEnough(mapwin.center_lon, -106.24089075)
        assertCloseEnough(mapwin.center_lat, 35.890244)
        assertCloseEnough(mapwin.trackpoints.bbox.as_tuple(),
                          (-106.2534204, 35.8849806,
                           -106.2283611, 35.895508))

    def test_kml_arg(self):
        args = [ 'pytopo', 'test/files/otowi-mesa-arch.kml' ]

        mapwin =  MapWindow(self.viewer)
        self.viewer.parse_args(mapwin, args)

        self.assertEqual(len(mapwin.trackpoints.points), 1265)
        self.assertEqual(len(mapwin.trackpoints.waypoints), 2)
        assertCloseEnough(mapwin.center_lon, -106.24089075)
        assertCloseEnough(mapwin.center_lat, 35.890244)
        assertCloseEnough(mapwin.trackpoints.bbox.as_tuple(),
                               (-106.2534204, 35.8849806,
                                -106.2283611, 35.895508))

    def test_kmz_arg(self):
        kmzfile = create_kmz('test/files/otowi-mesa-arch')

        args = [ 'pytopo', kmzfile ]

        mapwin =  MapWindow(self.viewer)
        self.viewer.parse_args(mapwin, args)

        self.assertEqual(len(mapwin.trackpoints.points), 1265)
        self.assertEqual(len(mapwin.trackpoints.waypoints), 2)
        assertCloseEnough(mapwin.center_lon, -106.24089075)
        assertCloseEnough(mapwin.center_lat, 35.890244)
        assertCloseEnough(mapwin.trackpoints.bbox.as_tuple(),
                               (-106.2534204, 35.8849806,
                                -106.2283611, 35.895508))

        os.unlink(kmzfile)

    def test_gpx_plus_overlay(self):
        args = [ 'pytopo', '-k', 'own',
                 'test/files/Surface_Ownership_10_14_2015.geojson',
                 'test/files/otowi-mesa-arch.gpx' ]

        mapwin =  MapWindow(self.viewer)
        self.viewer.parse_args(mapwin, args)

        self.assertEqual(len(mapwin.trackpoints.points), 1265)
        self.assertEqual(len(mapwin.trackpoints.waypoints), 2)
        self.assertEqual(len(mapwin.trackpoints.polygons), 27711)
        assertCloseEnough(mapwin.center_lon, -106.24089075)
        assertCloseEnough(mapwin.center_lat, 35.890244)
        assertCloseEnough(mapwin.trackpoints.bbox.as_tuple(),
                               (-106.2534204, 35.8849806,
                                -106.2283611, 35.895508))

    def test_explicit_coords(self):
        argslists = [
            # Several syntax variants for the same location:
            # decimal degrees syntax
            ( [ 'pytopo', '37.537', '-122.37' ],
              [ 37.537, -122.37] ),
            # exiftool (and most normal humans) syntax
            ( [ 'pytopo',
                '37 deg 32\' 13.12" N', '122° 22\' 12.0" W' ],
              [ 37.537, -122.37] ),
            # jhead syntax
            ( [ 'pytopo', 'N 37d 32m 13.12s', 'W 122d 22m 12.0s' ],
              [ 37.537, -122.37] ),

            # east and south
            ( [ 'pytopo',
                '37 deg 32\' 13.12" S', '122° 22\' 12.0" E' ],
              [ -37.537, 122.37] ),
            # negative signs
            ( [ 'pytopo',
                '-37 deg 32\' 13.12"', '-122° 22\' 12.0" E' ],
              [ -37.537, -122.37] ),

            # Coordinates together in one string, like exiftool
            ( [ 'pytopo',
                '-37 deg 32\' 13.12" -122° 22\' 12.0" E' ],
              [ -37.537, -122.37] ),
            # Coordinates together in one string, like jhead
            ( [ 'pytopo',
                '37 deg 32\' 13.12" N 122° 22\' 12.0" W' ],
              [ 37.537, -122.37] ),
        ]

        for argtuple in argslists:
            args, realcoords = argtuple
            mapwin =  MapWindow(self.viewer)
            self.viewer.parse_args(mapwin, args)

            assertCloseEnough(mapwin.center_lat, realcoords[0])
            assertCloseEnough(mapwin.center_lon, realcoords[1])

    def test_explicit_coords_plus_gpx(self):
        args = [ 'pytopo', '35.85', '-106.4',
                 'test/files/otowi-mesa-arch.gpx' ]

        mapwin =  MapWindow(self.viewer)
        self.viewer.parse_args(mapwin, args)

        self.assertEqual(len(mapwin.trackpoints.points), 1265)
        self.assertEqual(len(mapwin.trackpoints.waypoints), 2)
        assertCloseEnough(mapwin.center_lat, 35.85)
        assertCloseEnough(mapwin.center_lon, -106.4)
        assertCloseEnough(mapwin.trackpoints.bbox.as_tuple(),
                               (-106.253, 35.885,
                                -106.228, 35.8955))

    def test_explicit_coords_plus_gpx_minus_t(self):
        args = [ 'pytopo', '35.85', '-106.4', '-t',
                 'test/files/otowi-mesa-arch.gpx' ]

        mapwin =  MapWindow(self.viewer)
        self.viewer.parse_args(mapwin, args)

        self.assertEqual(len(mapwin.trackpoints.points), 1265)
        self.assertEqual(len(mapwin.trackpoints.waypoints), 2)
        assertCloseEnough(mapwin.center_lat, 35.85)
        assertCloseEnough(mapwin.center_lon, -106.4)
        assertCloseEnough(mapwin.trackpoints.bbox.as_tuple(),
                               (-106.253, 35.885,
                                -106.228, 35.8955))

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
        sitename, sitelon, sitelat = self.create_config_file()
        args = [ 'pytopo', sitename ]

        mapwin =  MapWindow(self.viewer)
        self.viewer.parse_args(mapwin, args)

        self.assertEqual(len(mapwin.trackpoints.points), 0)
        self.assertEqual(len(mapwin.trackpoints.waypoints), 0)

        assertCloseEnough(mapwin.center_lon, sitelon)
        assertCloseEnough(mapwin.center_lat, sitelat)

    def test_known_site_plus_overlay(self):
        sitename, sitelon, sitelat = self.create_config_file()
        args = [ 'pytopo', '-k', 'own',
                 'test/files/Surface_Ownership_10_14_2015.geojson',
                 sitename ]

        mapwin =  MapWindow(self.viewer)
        self.viewer.parse_args(mapwin, args)

        self.assertEqual(len(mapwin.trackpoints.points), 0)
        self.assertEqual(len(mapwin.trackpoints.waypoints), 0)

        assertCloseEnough(mapwin.center_lon, sitelon)
        assertCloseEnough(mapwin.center_lat, sitelat)

