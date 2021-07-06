#!/usr/bin/env python
# -*- coding: utf-8 -*-

# Copyright (C) 2009-2019 by Akkana Peck.
# You are free to use, share or modify this program under
# the terms of the GPLv2 or, at your option, any later GPL.

"""MapViewer, the main pytopo application, which controls the MapWindow.
"""

from __future__ import print_function

from pytopo.MapWindow import MapWindow
from pytopo.MapUtils import MapUtils
from pytopo.TrackPoints import TrackPoints, BoundingBox

# For version and user_agent, so the downloader can access them.
import pytopo

import sys
import os
import time
import re
import collections
import glob
import gc
import xml.parsers.expat

import gtk    # XXX any gtk calls should be moved into MapWindow
import gobject


class ArgParseException(Exception):
    pass


def strip_bracketed(s, c):
    """If s begins and ends with c, strip off c.
       c can be a single character like '"',
       or a pair of characters like '[]'.
       Also removes trailing commas.
    """
    start_char = c[0]
    if len(c) > 1:
        end_char = c[1]
    else:
        end_char = start_char

    # Strip out unneeded [ ]
    s = s.strip()
    if s.endswith(','):
        s = s[:-1].strip()
    if s.startswith(start_char):
        s = s[1:].strip()
    if s.endswith(end_char):
        s = s[:-1].strip()

    return s

quoting_regex = re.compile(r'''
'.*?' | # single quoted substring
".*?" | # double quoted substring
\S+ # all the rest
''', re.VERBOSE)

def parse_saved_site_line(line):
    """Parse lines like
       [ "Treasure Island, zoomed", -122.221287, 37.493330, humanitarian, 13]
       (enclosing brackets are optional, as are double quotes
       for strings that don't include commas).
       Clever way of avoiding needing the CSV module
    """

    line = strip_bracketed(line, '[]')

    parts = [ strip_bracketed(strip_bracketed(s, "'"), '"')
              for s in quoting_regex.findall(line)
              if s not in ',[]' ]
    return parts


class MapViewer(object):

    """A class to hold the mechanics of running the pytopo program,
    plus some important variables including Collections and KnownSites.
    """

    def __init__(self):
        self.collections = []
        self.KnownSites = []
        self.KnownTracks = []
        self.init_width = 800
        self.init_height = 600
        self.default_collection = None
        self.needs_saving = False

        if 'XDG_CONFIG_HOME' in os.environ:
            self.config_dir = os.path.join(os.environ['XDG_CONFIG_HOME'],
                                                      "pytopo")
        else:
            self.config_dir = os.path.expanduser("~/.config/pytopo",)

        self.saved_sites_filename = os.path.join(self.config_dir, "saved.sites")
        self.reload_tiles = False

        self.Debug = False


    @staticmethod
    def get_version():
        return pytopo.__version__

    @classmethod
    def Usage(cls):
        print("pytopo", MapViewer.get_version())
        print("""
Usage: pytopo
       pytopo trackfile
       pytopo known_site
       pytopo [-t trackfile] [-c collection] [-o overlay] [-r] [site_name]
       pytopo [-t trackfile] start_lat start_lon [collection]
       pytopo -p :  list known sites, collections and tracks
       pytopo -r :  re-download all map tiles that need to be shown
       pytopo -h :  print this message

Other flags:
       -k keys   : comma-separated list of fields (keys) to look for
                   when grouping polygonal regions.
       -g        : follow a GPS if available
       -d[level] : debugging mode. Defaults to 1, level 2 shows a little more.

With no arguments, will display a menu of known sites
(defined in pytopo.sites).

Map collections are defined in pytopo.sites.
Overlays are also collections, drawn translucently on top of the base map,
 and there can be more than one.

Track files may be in GPX, KML, KMZ or GeoJSON format, and may contain
track points and/or waypoints; multiple track files are allowed.
GeoJSON files may also contain polygons: use the -k option to specify
which field in the GeoJSON feature should be used for coloring groups.

Use decimal degrees for coordinates.

Set up favorite site names in ~/.config/pytopo.sites,
favorite track logs in ~/Tracks

Move around by dragging and zoom with the mousewheel, or use the keyboard:
  Left/right/up/down:  move in that direction
               +/=/-:  zoom in/out
            spacebar:  go back to last pinned location
                   m:  bring up the site selection dialog
                   q:  quit

Right-click gives a context menu.
Shift-click in the map to print the coordinates of the clicked location,
as well as distance and bearing from the last shift-clicked point,
to standard output.
""")
        sys.exit(1)

    @classmethod
    def error_out(cls, errstr):
        """Print an error and exit cleanly."""
        print("===============")
        print(errstr)
        print("===============\n")
        MapViewer.Usage()

    def append_known_site(self, site):
        """Append the given site to KnownSites."""
        self.KnownSites.append(site)
        self.needs_saving = True

    def save_sites(self):
        """Write any new KnownSites to file.
           Should only be called from graceful exit.
        """
        if not self.needs_saving:
            return

        try:
            savefile = open(self.saved_sites_filename, "w")
        except:
            print("Couldn't open save file", self.saved_sites_filename)
            return

        for site in self.KnownSites[self.first_saved_site:]:
            # KnownSites is a list of lists:
            # [ [ name, lon, lat, [collection], [zoomlevel]
            print('[ "%s", %f, %f' % (site[0], site[1], site[2]),
                  end='', file=savefile)
            if len(site) > 3:
                print(', %s' % site[3], end='', file=savefile)
            if len(site) > 4:
                print(', %d' % site[4], end='', file=savefile)
            print("]", file=savefile)

        savefile.close()

    def print_sites(self):
        """Print the list of known sites."""
        print("Known Sites:")
        for site in self.KnownSites:
            print(" ", site[0], "(", os.path.basename(site[3]), ")")
        print()

        print("Collections:")
        for collection in self.collections:
            print(collection)
        print()

        print("Known Tracks:")
        for track in self.KnownTracks:
            print(" ", track[0])
        sys.exit(0)

    def find_collection(self, collname):
        """Find a collection with the given name."""

        # Make sure collname is a MapCollection we know about:
        for coll in self.collections:
            if collname == coll.name:
                if not coll.exists():
                    self.error_out("Can't access location " + coll.location +
                                   " for collection " + collname)
                if (self.Debug):
                    print("Found the collection", coll.name)
                return coll

        return None

    def track_select(self, mapwin):
        """Show a dialog giving a choice of known tracks.
        """
        dialog = gtk.Dialog("Tracks", None, 0,
                            (gtk.STOCK_CLOSE, gtk.RESPONSE_NONE,
                             gtk.STOCK_OK, gtk.RESPONSE_OK))
        dialog.set_size_request(400, 300)

        sw = gtk.ScrolledWindow()
        sw.set_shadow_type(gtk.SHADOW_ETCHED_IN)
        sw.set_policy(gtk.POLICY_AUTOMATIC, gtk.POLICY_AUTOMATIC)

        # List store will hold Track name and Track file path
        store = gtk.ListStore(str, str)

        # Create the list
        for track in self.KnownTracks:
            store.append([track[0], track[1]])

        treeview = gtk.TreeView(store)

        renderer = gtk.CellRendererText()
        column = gtk.TreeViewColumn("Track name", renderer, text=0)
        treeview.append_column(column)

        sw.set_policy(gtk.POLICY_AUTOMATIC, gtk.POLICY_AUTOMATIC)
        sw.add(treeview)

        dialog.vbox.pack_start(sw, expand=True)

        dialog.show_all()

        response = dialog.run()
        if response == gtk.RESPONSE_OK:
            selection = treeview.get_selection()
            model, it = selection.get_selected()
            if it:
                trackfile = store.get_value(it, 1)
                mapwin.trackpoints = TrackPoints()
                mapwin.trackpoints.read_track_file(trackfile)
                # XXX Might want to handle IOError in case file doesn't exist
                dialog.destroy()
                return True
        else:
            dialog.destroy()
        return False

    def location_select(self, mapwin):
        """Bring up a dialog giving a choice of known starting locations.
        """
        dialog = gtk.Dialog("Locations", None, 0,
                            (gtk.STOCK_REMOVE, gtk.RESPONSE_APPLY,
                             gtk.STOCK_CLOSE, gtk.RESPONSE_NONE,
                             gtk.STOCK_OK, gtk.RESPONSE_OK))
        dialog.set_size_request(400, 300)

        sw = gtk.ScrolledWindow()
        sw.set_shadow_type(gtk.SHADOW_ETCHED_IN)
        sw.set_policy(gtk.POLICY_AUTOMATIC, gtk.POLICY_AUTOMATIC)

        # List store will hold name, collection-name and site object
        store = gtk.ListStore(str, str, object)

        # Create the list
        for site in self.KnownSites:
            store.append([site[0], site[3], site])

        # Make a treeview from the list:
        treeview = gtk.TreeView(store)

        renderer = gtk.CellRendererText()
        column = gtk.TreeViewColumn("Location", renderer, text=0)
        treeview.append_column(column)
        renderer = gtk.CellRendererText()
        column = gtk.TreeViewColumn("Collection", renderer, text=1)
        treeview.append_column(column)

        sw.set_policy(gtk.POLICY_AUTOMATIC, gtk.POLICY_AUTOMATIC)
        sw.add(treeview)

        dialog.vbox.pack_start(sw, expand=True)

        dialog.show_all()

        response = dialog.run()
        while response == gtk.RESPONSE_APPLY:
            selection = treeview.get_selection()
            model, it = selection.get_selected()
            if it:
                site = store.get_value(it, 2)
                self.KnownSites.remove(site)
                store.remove(it)
            response = dialog.run()

        if response == gtk.RESPONSE_OK:
            selection = treeview.get_selection()
            model, it = selection.get_selected()
            if it:
                site = store.get_value(it, 2)
                self.use_site(site, mapwin)
                dialog.destroy()
                return True
        else:
            dialog.destroy()
        return False

    def use_site(self, site, mapwin):
        """Given a starting site, center the map on it and show the map.
           Returns true for success.
        """
        if not mapwin.collection:
            if len(site) > 3 and site[3]:
                collection = self.find_collection(site[3])
            else:
                collection = self.find_collection(self.default_collection)
            if not collection:
                return False
            mapwin.collection = collection

        # site[1] and site[2] are the long and lat in deg.minutes
        mapwin.center_lon = MapUtils.deg_min2dec_deg(site[1])
        mapwin.center_lat = MapUtils.deg_min2dec_deg(site[2])
        mapwin.cur_lon = mapwin.center_lon
        mapwin.cur_lat = mapwin.center_lat
        mapwin.pin_lon = mapwin.center_lon
        mapwin.pin_lat = mapwin.center_lat

        if (self.Debug):
            print(site[0] + ":", \
                MapUtils.dec_deg2deg_min_str(mapwin.center_lon), \
                MapUtils.dec_deg2deg_min_str(mapwin.center_lat))

        return True

    def parse_args(self, mapwin, args):
        """Parse runtime arguments."""

        args = args[1:]

        mapwin.trackpoints = TrackPoints()

        while len(args) > 0:
            if args[0][0] == '-' and not args[0][1].isdigit():
                if args[0] == "-v" or args[0] == "--version":
                    print(self.get_version())
                    sys.exit(0)
                elif args[0] == "-h" or args[0] == "--help":
                    self.Usage()

                # Next clause is impossible because of the prev isdigit check:
                # if args[0] == "-15":

                #    series = 15
                elif args[0] == "-p":
                    self.print_sites()

                elif args[0] == "-g":
                    try:
                        import socket
                        from gpsdPoller import GpsdPoller
                        # mapwin.gps_poller = GpsdPoller(10, self.gps_poll)
                        mapwin.gps_poller = GpsdPoller(10, mapwin.gpsd_callback)
                    except ImportError as e:
                        print(str(e))
                        print()
                        print("Can't follow GPS: python-gps isn't installed")
                        mapwin.gps_poller = None
                    except socket.error as e:
                        print(str(e))
                        print()
                        print("Can't follow GPS: can't open GPS device")
                        mapwin.gps_poller = None

                elif args[0] == "-c":
                    # Specify a collection:
                    if len(args) < 2:
                        print("-c must specify collection")
                        self.Usage()
                    mapwin.collection = self.find_collection(args[1])
                    if mapwin.collection is None:
                        self.error_out("Can't find a map collection called "
                                        + args[1])
                    args = args[1:]

                elif args[0] == "-o":
                    # Specify an overlay collection:
                    if len(args) < 2:
                        print("-c must specify overlay collection")
                        self.Usage()
                    overlay = self.find_collection(args[1])
                    if overlay is None:
                        self.error_out("Can't find a map collection called "
                                        + args[1])
                    mapwin.add_overlay(overlay)
                    args = args[1:]

                elif args[0].startswith("-d"):
                    try:
                        debuglevel = int(args[0][2:])
                        self.Debug = debuglevel
                    except:
                        self.Debug = 1
                    print("Debugging level", self.Debug)

                elif args[0] == "-k":
                    if len(args) < 2:
                        print("-k must include a comma-separated list of field names")
                        self.Usage()
                    mapwin.trackpoints.fieldnames = args[1].split(',')
                    args = args[1:]

                elif args[0] == "-r":
                    self.reload_tiles = time.time()

                elif args[0] == "-t" and len(args) > 1:
                    if mapwin.trackpoints is None:
                        mapwin.trackpoints = TrackPoints()

                    # Is it a known track?
                    for tr in self.KnownTracks:
                        if args[1] == tr[0]:
                            if self.Debug:
                                print("Reading known track", tr[0], tr[1])
                            args[1] = tr[1]
                            break

                    try:
                        mapwin.trackpoints.read_track_file(args[1])
                    except IOError:
                        print("Can't read track file", args[1])
                    args = args[1:]

                else:
                    self.error_out("Unknown flag " + args[0])

                # Done processing this flag
                args = args[1:]
                continue

            # args[0] doesn't start with '-'. Is it a track file?
            try:
                mapwin.trackpoints.read_track_file(args[0])
                args = args[1:]
                continue

            except IOError:
                print("Can't read track file", args[0])
                args = args[1:]
                continue

            # Catch a special case for a common KML error:
            except xml.parsers.expat.ExpatError:
                print("Can't read %s: syntax error." % args[0])
                lowerarg = args[0].lower()
                if lowerarg.endswith(".kml") or \
                   lowerarg.endswith(".kmz"):
                    print("""
Is this a KML made with ArcGIS?
It may have an illegal xsi:schemaLocation.
If so, try changing xsi:schemaLocation to just schemaLocation.""")
                    args = args[1:]
                    sys.exit(1)

            except (RuntimeError, FileNotFoundError) as e:
                # It wasn't a track file; continue trying to parse it
                if self.Debug:
                    print("%s didn't work as a track file: %s" % (args[0], e))
                pass

            # Try to match a known site:
            for site in self.KnownSites:
                if args[0] == site[0]:
                    if not self.use_site(site, mapwin):
                        continue
                    break

            if mapwin.collection and mapwin.center_lon is not None \
               and mapwin.center_lat is not None:
                args = args[1:]
                continue

            # Doesn't match a known site. Maybe the args are coordinates?
            try:
                def to_coord(s):
                    if len(s) <= 0:
                        return None
                    try:
                        f = float(s)
                        return f
                    except:
                        return None

                if len(args) >= 2:
                    lat = to_coord(args[0])
                    lon = to_coord(args[1])
                    if lat is not None and lon is not None:
                        mapwin.center_lat = lat
                        mapwin.center_lon = lon

                        # Set a pin on the specified point.
                        mapwin.pin_lat = lat
                        mapwin.pin_lon = lon

                        args = args[2:]

                        # The next argument after latitude, longitude
                        # might be a collection, but it also might not.
                        # Try it and see.
                        if args:
                            coll = self.find_collection(args[0])
                            if coll:
                                mapwin.collection = coll
                                args = args[1:]

                        continue

                print("Can't make sense of argument:", args[0])
                args = args[1:]
                continue

            except ValueError:
                print("Couldn't parse coordinates")
                self.Usage()

            # If we get here, we still have an argument but it doesn't
            # match anything we know: flag, collection, site or coordinate.
            print("Problem parsing arguments. Remaining args:", args)
            self.Usage()

        # Now we've parsed all the arguments.
        # If we didn't get a collection, use the default, if any:
        if not mapwin.collection and self.default_collection:
            mapwin.collection = self.find_collection(self.default_collection)

        if not mapwin.collection:
            print("Can't find a default Map Collection!")
            print("There may be something wrong with your pytopo.sites")
            print()
            sys.exit(1)

        mapwin.collection.Debug = self.Debug

        # Decide on an appropriate center and zoom level for the content,
        # starting with the bounding box for any loaded files.
        bbox = mapwin.trackpoints.get_bounds()
        if bbox:
            # If there's a pin, use it
            if mapwin.pin_lat and mapwin.pin_lon:
                mapwin.center_lat = mapwin.pin_lat
                mapwin.center_lon = mapwin.pin_lon

                # Compute a bounding box that keeps the pin centered
                # while also including the full bounding box.
                # XXX Fudgy math, doesn't account for things like
                # the dateline or crossing over the pole.
                max_dlat = max(abs(mapwin.pin_lat - bbox.minlat),
                               abs(mapwin.pin_lat - bbox.maxlat))
                max_dlon = max(abs(mapwin.pin_lon - bbox.minlon),
                               abs(mapwin.pin_lon - bbox.maxlon))

                bbox = BoundingBox()
                bbox.add_point(mapwin.center_lat - max_dlat,
                               mapwin.center_lon - max_dlon)
                bbox.add_point(mapwin.center_lat + max_dlat,
                               mapwin.center_lon + max_dlon)

            # else use the bbox
            else:
                mapwin.center_lat, mapwin.center_lon = bbox.center()

            mapwin.collection.zoom_to_bounds(bbox)
            for ov in mapwin.overlays:
                ov.zoom_to_bounds(bbox)

        else:
            # No bounding box from the trackpoints.
            # Hopefully the center has already been set from use_site,
            # otherwise we're in trouble:
            if not (mapwin.center_lat and mapwin.center_lon):
                print("""No center coordinates!
Please specify either a site or a file containing geographic data.""")
                raise(ArgParseException)

            # There's a center but no zoom level.
            # Zoom to the collection's default zoom level, if any
            mapwin.zoom_to(mapwin.collection.zoomlevel)

        if self.reload_tiles and 'set_reload_tiles' in dir(mapwin.collection):
            mapwin.collection.set_reload_tiles(self.reload_tiles)
        elif self.reload_tiles:
            print("Collection can't re-download tiles")

        # By now, we hope we have the mapwin positioned with a collection
        # and starting coordinates:
        if mapwin.collection and \
           mapwin.center_lon is not None and mapwin.center_lat is not None:
            return

        # If we're following GPS, it's okay if we don't have center coords yet;
        # the mapwin will wait for a fix.
        if mapwin.collection and mapwin.gps_poller:
            return

        raise(ArgParseException)


# Check for a user config file named .pytopo
# in either $HOME/.config/pytopo or $HOME.
#
# Format of the user config file:
# It is a python script, which can include arbitrary python code,
# but the most useful will be KnownSites definitions,
# with coordinates specified in degrees.decimal_minutes,
# like this:
# MapHome = "/cdrom"
# KnownSites = [
#     # Death Valley
#     [ "zabriskie", 116.475, 36.245, "dv_data" ],
#     [ "badwater", 116.445, 36.125, "dv_data" ],
#     # East Mojave
#     [ "zzyzyx", 116.05, 35.08, "emj_data" ]
#     ]

    def exec_config_file(self):
        """Load the user's .pytopo config file,
        found either in $HOME/.config/pytopo/ or $HOME/pytopo.
        """
        userfile = os.path.join(self.config_dir, "pytopo.sites")
        if not os.access(userfile, os.R_OK):
            if self.Debug:
                print("Couldn't open", userfile)
            userfile = os.path.expanduser("~/.pytopo")
            if not os.access(userfile, os.R_OK):
                if self.Debug:
                    print("Couldn't open", userfile, "either")
                userfile = os.path.join(self.config_dir, "pytopo", ".pytopo")
                if not os.access(userfile, os.R_OK):
                    if self.Debug:
                        print("Couldn't open", userfile, "either")
                    userfile = self.create_initial_config()
                    if userfile is None:
                        print("Couldn't create a new pytopo config file")
                        return
                else:
                    print("Suggestion: rename", userfile, \
                          "to ~/.config/pytopo/pytopo.sites")
                    print(userfile, "may eventually be deprecated")
        if self.Debug:
            print("Found", userfile)

        # Now we'd better have a userfile

        # Now that we're in a function inside the MapViewer class, we can't
        # just execfile() and set a variable inside that file -- the file
        # can only change it inside a "locals" dictionary.
        # So set up the dictionary:
        locs = {'Collections': [3, 4],
                'KnownSites': [],
                'init_width': self.init_width,
                'init_height': self.init_height
                }
        globs = {}

        # Import the map collection classes automatically:
        execstring = '''
from pytopo import OSMMapCollection
from pytopo import Topo1MapCollection
from pytopo import Topo2MapCollection
from pytopo import GenericMapCollection
'''

        with open(userfile) as fp:
            # exec is a security problem only if you let other people
            # modify your pytopo.sites. So don't.
            execstring += fp.read()
            exec(execstring, globs, locs)

        # Then extract the changed values back out:
        # These two are mandatory.
        self.collections = locs['Collections']
        self.default_collection = locs["defaultCollection"]

        # Optional variables:
        if 'init_width' in locs:
            self.init_width = locs['init_width']
        if 'init_height' in locs:
            self.init_height = locs['init_height']

        if 'KnownSites' in locs:
            for site in locs['KnownSites']:
                self.KnownSites.append(site)

        # user_agent is special: it needs to be a class variable
        # so the downloader can access it without needing a
        # pointer to a specific object.
        if 'user_agent' in locs:
            pytopo.user_agent = locs['user_agent']

    def read_saved_sites(self):
        """Read previously saved (favorite) sites."""

        # A line typically looks like this:
        # [ "san-francisco", -121.750000, 37.400000, "openstreetmap" ]
        # or, with an extra optional zoom level and included comma,
        # [ "Treasure Island, zoomed", -122.221, 37.493, humanitarian, 13 ]
        try:
            sitesfile = open(self.saved_sites_filename, "r")
        except:
            return

        for line in sitesfile:
            site = parse_saved_site_line(line)

            site[1] = float(site[1])    # longitude
            site[2] = float(site[2])    # latitude
            if len(site) > 4:
                site[4] = int(site[4])  # zoom level

            self.KnownSites.append(site)

        sitesfile.close()

    def read_tracks(self):
        """Read in all tracks from ~/Tracks."""
        trackdir = os.path.expanduser('~/Tracks')

        if os.path.isdir(trackdir):
            for f in glob.glob(os.path.join(trackdir, '*.gpx')):
                head, gpx = os.path.split(f)
                filename = gpx.partition('.')[0]
                self.KnownTracks.append([filename, f])

    def create_initial_config(self):
        """Make an initial configuration file.
           If the user has a ~/.config, make ~/.config/pytopo/pytopo.sites.
        """
        if not os.access(self.config_dir, os.W_OK):
            os.makedirs(self.config_dir)
        userfile = os.path.join(self.config_dir, "pytopo.sites")
        fp = open(userfile, 'w')

        # Now we have fp open. Write a very basic config to it.
        print("""# Pytopo site file

# Map collections

Collections = [
    # OpenStreetMap's Tile Usage Policy is discussed at
    # https://operations.osmfoundation.org/policies/tiles/
    # and requests that apps not use tile.openstreetmap.org without permission.
    # If you choose to use it, please add a user_agent line elsewhere
    # in this file, such as
    # user_agent = "PyTopo customized by Your Name Here"
    # and use it sparingly, so OSM doesn't get upset and ban all PyTopo users.

    # Humanitarian
    OSMMapCollection( "humanitarian", "~/Maps/humanitarian",
                      ".png", 256, 256, 10,
                      "http://a.tile.openstreetmap.fr/hot/{z}/{x}/{y}.png",
                      maxzoom=15,
                      attribution="Humanitarian OSM Maps, map data © OpenStreetMap contributors"),

    # The USGS National Map provides various kinds of tiles.
    # Here's their basic Topo tile.
    # Their documentation says they support zooms to 19,
    # but in practice they give an error after zoom level 15.
    # They're a bit flaky: sometimes they don't load, or load blank tiles.
    OSMMapCollection( "USGS", "~/Maps/USGS",
                      ".jpg", 256, 256, 10,
                       "https://basemap.nationalmap.gov/arcgis/rest/services/USGSTopo/MapServer/WMTS?SERVICE=WMTS&REQUEST=GetTile&VERSION=1.0.0&LAYER=USGSTopo&STYLE=default&TILEMATRIXSET=GoogleMapsCompatible&TILEMATRIX={z}&TILEROW={y}&TILECOL={x}&FORMAT=image%2Fjpeg",
                      maxzoom=15,
                      attribution="USGS National Map"),

    # USGS also offers satellite tiles:
    OSMMapCollection( "USGS Imagery", "~/Maps/USGS-imagery",
                      ".jpg", 256, 256, 11,
                       "https://basemap.nationalmap.gov/arcgis/rest/services/USGSImageryOnly/MapServer/WMTS?SERVICE=WMTS&REQUEST=GetTile&VERSION=1.0.0&LAYER=USGSImageryOnly&STYLE=default&TILEMATRIXSET=GoogleMapsCompatible&TILEMATRIX={z}&TILEROW={y}&TILECOL={x}&FORMAT=image%2Fjpeg",
                      maxzoom=15,
                      attribution="USGS National Map"),

    # ThunderForest offers OpenCycleMap tiles and several other good styles,
    # but you'll need to sign up for an API key from http://thunderforest.com.
    # OSMMapCollection( "opencyclemap", "~/Maps/opencyclemap",
    #                   ".png", 256, 256, 13,
    #                   "https://tile.thunderforest.com/cycle/{z}/{x}/{y}.png?apikey=YOUR_API_KEY_HERE",
    #                   maxzoom=22, reload_if_older=90,  # reload if > 90 days
    #                   attribution="Maps © www.thunderforest.com, Data © www.osm.org/copyright"),
    ]

# Default to whichever MapCollection is listed first.
defaultCollection = Collections[0].name

KnownSites = [
    # Some base values to get new users started.
    # Note that these coordinates are a bit northwest of the city centers;
    # they're the coordinates of the map top left, not center.
    [ "san-francisco", -122.245, 37.471, "", 11 ],
    [ "new-york", -74.001, 40.4351, "", 11 ],
    [ "london", -0.072, 51.3098, "", 11 ],
    [ "sydney", 151.125, -33.517, "", 11 ],
    ]

user_agent = "PyTopo customized by Your Name Here"
""", file=fp)
        fp.close()

        print("""Welcome to Pytopo!
Created an initial site file in %s
You can add new sites and collections there; see the instructions at
   http://shallowsky.com/software/topo/
""" % (userfile))
        return userfile

    def main(self, pytopo_args):
        """main execution routine for pytopo."""
        self.exec_config_file()
        # Remember how many known sites we got from the config file;
        # the rest are read in from saved sites and may need to be re-saved.
        self.first_saved_site = len(self.KnownSites)

        # Now it's safe to read the saved sites.
        self.read_saved_sites()

        self.read_tracks()
        gc.enable()

        mapwin = MapWindow(self)

        try:
            self.parse_args(mapwin, pytopo_args)
        except ArgParseException:
            # Didn't match any known run mode:
            # start in selector mode to choose a location:
            if not mapwin.selection_window():
                sys.exit(0)

        # For cProfile testing, run with a dummy collection (no data needed):
        # mapwin.collection = MapCollection("dummy", "/tmp")

        # print(cProfile.__file__)
        # cProfile.run('mapwin.show_window()', 'cprof.out')
        # http://docs.python.org/library/profile.html
        # To analyze cprof.out output, do this:
        # import pstats
        # p = pstats.Stats('fooprof')
        # p.sort_stats('time').print_stats(20)

        mapwin.show_window(self.init_width, self.init_height)


def main():
    viewer = MapViewer()
    viewer.main(sys.argv)


if __name__ == "__main__":
    main()
