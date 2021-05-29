#!/usr/bin/env python3

import unittest
import sys, os
import shutil

sys.path.insert(0, '..')

from .utils import assertCloseEnough, create_kmz
from pytopo import MapViewer, MapWindow, ArgParseException
from pytopo.MapUtils import MapUtils


def create_config_file(configdir):
    with open(os.path.join(configdir, 'pytopo', 'pytopo.sites'),
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
        # The site file uses dd.mmss but everything else wants DD
        return ("san-francisco",
                MapUtils.deg_min2dec_deg(-122.245),
                MapUtils.deg_min2dec_deg(37.471))

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
        self.assertEqual(len(mapwin.trackpoints.polygons), 21878)
        assertCloseEnough(mapwin.center_lon, -106.24089075)
        assertCloseEnough(mapwin.center_lat, 35.890244)
        assertCloseEnough(mapwin.trackpoints.bbox.as_tuple(),
                               (-106.2534204, 35.8849806,
                                -106.2283611, 35.895508))

    def test_explicit_coords(self):
        args = [ 'pytopo', '37.537', '-122.37' ]

        mapwin =  MapWindow(self.viewer)
        self.viewer.parse_args(mapwin, args)

        assertCloseEnough(mapwin.center_lon, -122.37)
        assertCloseEnough(mapwin.center_lat, 37.537)

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
        sitename, sitelon, sitelat = create_config_file(self.configdir)
        args = [ 'pytopo', sitename ]

        mapwin =  MapWindow(self.viewer)
        self.viewer.parse_args(mapwin, args)

        self.assertEqual(len(mapwin.trackpoints.points), 0)
        self.assertEqual(len(mapwin.trackpoints.waypoints), 0)

        assertCloseEnough(mapwin.center_lon, sitelon)
        assertCloseEnough(mapwin.center_lat, sitelat)

    def test_known_site_plus_overlay(self):
        sitename, sitelon, sitelat = create_config_file(self.configdir)
        args = [ 'pytopo', '-k', 'own',
                 'test/files/Surface_Ownership_10_14_2015.geojson',
                 sitename ]

        mapwin =  MapWindow(self.viewer)
        self.viewer.parse_args(mapwin, args)

        self.assertEqual(len(mapwin.trackpoints.points), 0)
        self.assertEqual(len(mapwin.trackpoints.waypoints), 0)

        assertCloseEnough(mapwin.center_lon, sitelon)
        assertCloseEnough(mapwin.center_lat, sitelat)
