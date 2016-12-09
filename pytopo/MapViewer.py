#!/usr/bin/env python
# -*- coding: utf-8 -*-

# Copyright (C) 2009-2016 by Akkana Peck.
# You are free to use, share or modify this program under
# the terms of the GPLv2 or, at your option, any later GPL.

'''MapViewer, the main pytopo application, which controls the MapWindow.
'''

from pytopo.MapWindow import MapWindow
from pytopo.MapUtils import MapUtils
from pytopo.TrackPoints import TrackPoints

import sys
import os
import time
import re
import collections
import glob
import gc
import xml.parsers.expat

import gtk    # XXX any gtk calls should be factored into a MapWindow method
import gobject


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
        self.config_dir = os.path.expanduser("~/.config/pytopo",)
        self.savefilename = os.path.join(self.config_dir, "saved.sites")
        self.reload_tiles = False
        self.Debug = False

    @staticmethod
    def get_version():
        # There doesn't seem to be any good way of getting the current
        # module's version. from . import __version__ works from external
        # scripts that are importing the module, but if you try to run
        # this file's main(), it dies with
        #   ValueError: Attempted relative import in non-package
        # The only solution I've found is to import the whole module,
        # then get the version from it.
        import pytopo
        return pytopo.__version__

    @classmethod
    def Usage(cls):
        print "pytopo", MapViewer.get_version()
        print """
Usage: pytopo
       pytopo trackfile
       pytopo known_site
       pytopo [-t trackfile] [-c collection] [-r] [site_name]
       pytopo [-t trackfile] start_lat start_long collection
       pytopo -p :     list known sites and tracks
       pytopo -r :     re-download all map tiles
       pytopo -h :     print this message

With no arguments, will display a list of known sites.

Track files may be in GPX, KML, KMZ or GeoJSON format, and may contain
track points and/or waypoints; multiple track files are allowed.

Use degrees.decimal_minutes format for coordinates.
Set up favorite site names in ~/.config/pytopo.sites,
favorite track logs in ~/Tracks

Move around by dragging or using arrow keys.  q quits.
Right-click gives a context menu.
Shift-click in the map to print the coordinates of the clicked location.
"""
        sys.exit(1)

    @classmethod
    def error_out(cls, errstr):
        """Print an error and exit cleanly."""
        print "==============="
        print errstr
        print "===============\n"
        MapViewer.Usage()

    def append_known_site(self, site):
        self.KnownSites.append(site)
        self.needs_saving = True

    def save_sites(self):
        """Write any new KnownSites to file.
           Should only be called from graceful exit.
        """
        if not self.needs_saving:
            return

        try:
            savefile = open(self.savefilename, "w")
        except:
            print "Couldn't open save file", self.savefilename
            return

        for site in self.KnownSites[self.first_saved_site:]:
            # All sites have a string, two floats and another string;
            # some sites may have additional ints after that.
            print >>savefile, '[ "%s", %f, %f, "%s"' % \
                (site[0], site[1], site[2], site[3]),
            if len(site) > 4:
                print >>savefile, ', ' + ', '.join(map(str, site[4:])),
            print >>savefile, "]"
        savefile.close()

    def print_sites(self):
        """Print the list of known sites."""
        print "Known Sites:"
        for site in self.KnownSites:
            print " ", site[0], "(", os.path.basename(site[3]), ")"
        print
        print "Known Tracks:"
        for track in self.KnownTracks:
            print " ", track[0]
        sys.exit(0)

    def find_collection(self, collname):
        """Find a collection with the given name."""

        # print "Looking for a collection named", collname
        # Make sure collname is a MapCollection we know about:
        collection = None
        for coll in self.collections:
            if collname == coll.name:
                if not coll.exists():
                    self.error_out("Can't access location " + coll.location +
                                   " for collection " + collname)
                collection = coll
                if (self.Debug):
                    print "Found the collection", collection.name
                return collection
        return collection

    def track_select(self, mapwin):
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
        collection = self.find_collection(site[3])
        if not collection:
            return False
        mapwin.collection = collection

        # site[1] and site[2] are the long and lat in deg.minutes
        # print site[0], site[1], site[2]
        mapwin.center_lon = MapUtils.deg_min2dec_deg(site[1])
        mapwin.center_lat = MapUtils.deg_min2dec_deg(site[2])
        mapwin.pin_lon = mapwin.center_lon
        mapwin.pin_lat = mapwin.center_lat
        # print "Center in decimal degrees:", centerLon, centerLat
        if (self.Debug):
            print site[0] + ":", \
                MapUtils.dec_deg2deg_min_str(mapwin.center_lon), \
                MapUtils.dec_deg2deg_min_str(mapwin.center_lat)
        if len(site) > 4 and collection.zoom_to:
            collection.zoom_to(site[4])
        mapwin.draw_map()
        return True

    def parse_args(self, mapwin, args):
        """Parse runtime arguments."""

        args = args[1:]

        while len(args) > 0:
            if args[0][0] == '-' and not args[0][1].isdigit():
                if args[0] == "-v" or args[0] == "--version":
                    print self.get_version()
                    sys.exit(0)
                elif args[0] == "-h" or args[0] == "--help":
                    self.Usage()

                # Next clause is impossible because of the prev isdigit check:
                # if args[0] == "-15":
                #    series = 15
                elif args[0] == "-p":
                    self.print_sites()
                elif args[0] == "-c":
                    # Specify a collection:
                    if len(args) < 2:
                        print "-c must specify collection"
                        self.Usage()
                    mapwin.collection = self.find_collection(args[1])
                    if mapwin.collection is None:
                        self.error_out("Can't find a map collection called "
                                        + args[1])
                    # Start initially at top left, but subsequent args
                    # may change this:
                    mapwin.center_lon, mapwin.center_lat = \
                        mapwin.collection.get_top_left()
                    if (self.Debug):
                        print "Collection", mapwin.collection.name,
                        print "Starting at", \
                            MapUtils.dec_deg2deg_min_str(mapwin.center_lon), \
                            ", ", \
                            MapUtils.dec_deg2deg_min_str(mapwin.center_lat)
                    args = args[1:]

                elif args[0] == "-d":
                    self.Debug = True
                elif args[0] == "-r":
                    self.reload_tiles = time.time()
                elif args[0] == "-t" and len(args) > 1:
                    if mapwin.trackpoints is None:
                        mapwin.trackpoints = TrackPoints()

                    # Is it a known track?
                    for tr in self.KnownTracks:
                        if args[1] == tr[0]:
                            if self.Debug:
                                print "Reading known track", tr[0], tr[1]
                            args[1] = tr[1]
                            break

                    try:
                        mapwin.trackpoints.read_track_file(args[1])
                    except IOError:
                        print "Can't read track file", args[1]
                    args = args[1:]
                else:
                    self.error_out("Unknown flag " + args[0])

                # Done processing this flag
                args = args[1:]
                continue

            # args[0] doesn't start with '-'. Is it a track file?
            if args[0].endswith(".gpx") \
               or args[0].endswith(".kml") \
               or args[0].endswith(".kmz") \
               or args[0].endswith("json"):
                try:
                    if mapwin.trackpoints:
                        mapwin.trackpoints.read_track_file(args[0])
                    else:
                        trackpoints = TrackPoints()
                        trackpoints.read_track_file(args[0])
                        mapwin.trackpoints = trackpoints
                except IOError:
                    print "Can't read track file", args[0]
                except xml.parsers.expat.ExpatError:
                    print "Can't read %s: syntax error." % args[0]
                    if args[0].lower().endswith(".kml") or \
                       args[0].lower().endswith(".kmz"):
                        print """
Is this a KML made with ArcGIS?
It may have an illegal xsi:schemaLocation.
If so, try changing xsi:schemaLocation to just schemaLocation."""
                args = args[1:]
                continue

            # Try to match a known site:
            for site in self.KnownSites:
                if args[0] == site[0]:
                    if not self.use_site(site, mapwin):
                        continue
                    break

            if mapwin.collection and mapwin.center_lon and mapwin.center_lat:
                args = args[1:]
                continue

            # Doesn't match a known site. Maybe the args are coordinates?
            try:
                if len(args) >= 2 and \
                   len(args[0]) > 1 and args[0][1].isdigit() and \
                   len(args[1]) > 1 and args[1][1].isdigit():
                    mapwin.center_lon = MapUtils.deg_min2dec_deg(float(args[0]))
                    mapwin.center_lat = MapUtils.deg_min2dec_deg(float(args[2]))
                    mapwin.collection = self.find_collection(args[3])
                    args = args[2:]
                    continue
                print "Can't make sense of argument:", args[0]
                self.Usage()

            except ValueError:
                print "Couldn't parse coordinates"
                self.Usage()

            # If we get here, we still have an argument but it doesn't
            # match anything we know: flag, collection, site or coordinate.
            print "Problem parsing arguments. Remaining args:", args
            self.Usage()

        # Now we've parsed all the arguments.
        # If we didn't get a collection, use the default, if any:
        if not mapwin.collection and self.default_collection:
            mapwin.collection = self.find_collection(self.default_collection)

        # If we have a collection and a track but no center point,
        # center it on the trackpoints, and set scale appropriately:
        if mapwin.trackpoints is not None and mapwin.collection is not None \
                and not (mapwin.center_lat and mapwin.center_lon):
            minlon, minlat, maxlon, maxlat = mapwin.trackpoints.get_bounds()
            mapwin.center_lon = (maxlon + minlon) / 2
            mapwin.center_lat = (maxlat + minlat) / 2
            mapwin.collection.zoom_to_bounds(minlon, minlat, maxlon, maxlat)

        if self.reload_tiles and 'set_reload_tiles' in dir(mapwin.collection):
            mapwin.collection.set_reload_tiles(self.reload_tiles)
        elif self.reload_tiles:
            print "Collection can't re-download tiles"

        # By now, we hope we have the mapwin positioned with a collection
        # and starting coordinates:
        if mapwin.collection and mapwin.center_lon and mapwin.center_lat:
            return

        # Didn't match any known run mode:
        # start in GUI mode choosing a location:
        if not mapwin.selection_window():
            sys.exit(0)

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
                print "Couldn't open", userfile
            userfile = os.path.expanduser("~/.pytopo")
            if not os.access(userfile, os.R_OK):
                if self.Debug:
                    print "Couldn't open", userfile, "either"
                userfile = os.path.join(self.config_dir, "pytopo", ".pytopo")
                if not os.access(userfile, os.R_OK):
                    if self.Debug:
                        print "Couldn't open", userfile, "either"
                    userfile = self.create_initial_config()
                    if userfile is None:
                        print "Couldn't create a new pytopo config file"
                        return
                else:
                    print "Suggestion: rename", userfile, \
                          "to ~/.config/pytopo/pytopo.sites"
                    print userfile, "may eventually be deprecated"
        if self.Debug:
            print "Found", userfile

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
            execstring += fp.read()
            exec(execstring, globs, locs)

        # Then extract the changed values back out:
        self.collections = locs['Collections']
        self.KnownSites = locs['KnownSites']
        self.init_width = locs["init_width"]
        self.init_height = locs["init_height"]
        self.default_collection = locs["defaultCollection"]

    def read_saved_sites(self):
        """Read previously saved (favorite) sites."""
        try:
            savefile = open(self.savefilename, "r")
        except:
            return

        # A line typically looks like this:
        # [ "san-francisco", -121.750000, 37.400000, "openstreetmap" ]
        # or, with an extra optional zoom level,
        # [ "san-francisco", -121.750000, 37.400000, "openstreetmap", 11 ]

        r = re.compile('\["([^"]*)",([-0-9\.]*),([-0-9\.]*),"([^"]*)",?([0-9]+)?\]')
        for line in savefile:
            # First remove all whitespace:
            line = re.sub(r'\s', '', line)
            match = r.search(line)
            if match:
                matches = match.groups()
                # Convert from strings to numbers
                site = [matches[0], float(matches[1]), float(matches[2]),
                        matches[3]]
                if len(matches) == 5 and matches[4] is not None:
                    site.append(int(matches[4]))
                if self.Debug:
                    print "Adding", site[0], "to KnownSites"
                self.KnownSites.append(site)

        savefile.close()

    def read_tracks(self):
        trackdir = os.path.expanduser('~/Tracks')

        if os.path.isdir(trackdir):
            for f in glob.glob(os.path.join(trackdir, '*.gpx')):
                head, gpx = os.path.split(f)
                filename = gpx.partition('.')[0]
                self.KnownTracks.append([filename, f])

    def create_initial_config(self):
        """Make an initial configuration file.
           If the user has a ~/.config, make ~/.config/pytopo/pytopo.sites
           else fall back on ~/.pytopo.
        """
        confdir = os.path.expanduser("~/.config/pytopo")
        try:
            if not os.access(confdir, os.W_OK):
                os.mkdir(confdir)
            userfile = os.path.join(confdir, "pytopo.sites")
            fp = open(userfile, 'w')
        except:
            fp = None
        if not fp:
            userfile = os.path.expanduser("~/.pytopo")
            try:
                fp = open(userfile, 'w')
            except:
                return None

        # Now we have fp open. Write a very basic config to it.
        print >>fp, """# Pytopo site file

# Map collections

Collections = [
    OSMMapCollection( "openstreetmap", "~/Maps/openstreetmap",
                      ".png", 256, 256, 10,
                      "http://a.tile.openstreetmap.org" ),

    # You will need an API key to get the excellent OpenCycleMap tiles
    # from http://thunderforest.com.
    # OSMMapCollection( "opencyclemap", "~/Maps/opencyclemap",
    #                   ".png", 256, 256, 13,
    #                   "https://tile.thunderforest.com/cycle/{z}/{x}/{y}.png?apikey=YOUR_API_KEY_HERE",
    #                   maxzoom=22, reload_if_older=90,  # reload if > 90 days
    #                   attribution="Maps © www.thunderforest.com, Data © www.osm.org/copyright"),
    ]

defaultCollection = "openstreetmap"

KnownSites = [
    # Some base values to get new users started.
    # Note that these coordinates are a bit northwest of the city centers;
    # they're the coordinates of the map top left, not center.
    [ "san-francisco", -121.75, 37.4, "openstreetmap" ],
    [ "new-york", -73.466, 40.392, "openstreetmap" ],
    [ "london", 0.1, 51.266, "openstreetmap" ],
    [ "sydney", 151.0, -33.5, "openstreetmap" ],
    ]
"""
        fp.close()

        print """Welcome to Pytopo!
Created an initial site file in %s
You can add new sites and collections there; see the instructions at
   http://shallowsky.com/software/topo/
""" % (userfile)
        return userfile

    def main(self, pytopo_args):
        """main execution routine for pytopo."""
        self.exec_config_file()
        # Remember how many known sites we got from the config file;
        # the rest are read in from saved sites and may need to be re-saved.
        self.first_saved_site = len(self.KnownSites)
        self.read_saved_sites()
        self.read_tracks()
        gc.enable()

        mapwin = MapWindow(self)

        self.parse_args(mapwin, pytopo_args)

        # For cProfile testing, run with a dummy collection (no data needed):
        # mapwin.collection = MapCollection("dummy", "/tmp")

        # print cProfile.__file__
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
