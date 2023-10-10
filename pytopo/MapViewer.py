#!/usr/bin/env python
# -*- coding: utf-8 -*-

# Copyright (C) 2009-2023 by Akkana Peck.
# You are free to use, share or modify this program under
# the terms of the GPLv2 or, at your option, any later GPL.

"""MapViewer, the main pytopo application, which controls the MapWindow.
"""

from __future__ import print_function

from pytopo.MapWindow import MapWindow
from pytopo import MapUtils
from pytopo.TrackPoints import TrackPoints, BoundingBox

import pytopo.configfile as configfile

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
       pytopo -m :  show a menu of known sites
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
        configfile.save_sites(self.KnownSites[self.first_saved_site:])

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
            elif self.Debug:
                print(f"'{collname}' Didn't match '{coll.name}'")

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

    def use_coordinates(self, lat, lon, mapwin):
        """Center the map on the given coordinates"""
        if not mapwin.collection:
            collection = self.find_collection(self.default_collection)
            # mapwin.change_collection(collection)
            mapwin.collection = collection
        mapwin.center_lat = lat
        mapwin.center_lon = lon
        mapwin.pin_lat = lat
        mapwin.pin_lon = lon
        # mapwin.draw_map()

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

        # site[1] and site[2] are the long and lat in decimal degrees
        mapwin.center_lon = site[1]
        mapwin.center_lat = site[2]
        mapwin.cur_lon = mapwin.center_lon
        mapwin.cur_lat = mapwin.center_lat
        mapwin.pin_lon = mapwin.center_lon
        mapwin.pin_lat = mapwin.center_lat
        if len(site) >= 5:
            mapwin.zoom_to(site[4])

        if (self.Debug):
            print(site[0] + ":", mapwin.center_lon
                  , mapwin.center_lat)

        return True

    def parse_args(self, mapwin, args):
        """Parse runtime arguments."""

        args = args[1:]

        if not args:
            raise(ArgParseException)

        mapwin.trackpoints = TrackPoints()
        files_bbox = BoundingBox()

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

                elif args[0] == "-m":
                    raise ArgParseException

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
                    window.add_title(args[1])
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
                    window.add_title("(%s)" % args[1])
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

                    # Is it the name of a track file?
                    try:
                        bbox = mapwin.trackpoints.read_track_file(args[1])
                        files_bbox.union(bbox)
                        mapwin.add_title(args[1])
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
                bbox = mapwin.trackpoints.read_track_file(args[0])
                files_bbox.union(bbox)
                mapwin.add_title(args[0])
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
                    mapwin.add_title(args[0])
                    if not self.use_site(site, mapwin):
                        continue
                    break

            if mapwin.collection and mapwin.center_lon is not None \
               and mapwin.center_lat is not None:
                args = args[1:]
                continue

            # Doesn't match a known site. Maybe the args are coordinates?
            try:
                if len(args) == 1:
                    lat, lon = MapUtils.parse_full_coords(args[0], "DD")
                elif len(args) >= 2:
                    lat = MapUtils.to_decimal_degrees(args[0], "DD")
                    lon = MapUtils.to_decimal_degrees(args[1], "DD")
                else:
                    raise(RuntimeError("Can't make sense of arguments: %s"
                                       % str(args)))
                if abs(lat) > 90:
                    print("Guessing", lat,
                          "is a longitude. Please specify latitude first")
                    lat, lon = lon, lat
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
        # starting with any bounding box that comes from the trackpoints.
        bbox = mapwin.trackpoints.get_bounds()

        # Is there a pin?
        if mapwin.pin_lat and mapwin.pin_lon:
            # If there's both a pin and a bbox, compute a bounding box
            # that keeps the pin centered while also including the full bbox.
            # XXX Fudgy math, doesn't account for things like
            # the dateline or crossing over the pole.
            if bbox:
                max_dlat = max(abs(mapwin.pin_lat - bbox.minlat),
                               abs(mapwin.pin_lat - bbox.maxlat))
                max_dlon = max(abs(mapwin.pin_lon - bbox.minlon),
                               abs(mapwin.pin_lon - bbox.maxlon))

                bbox = BoundingBox()
                bbox.add_point(mapwin.center_lat - max_dlat,
                               mapwin.center_lon - max_dlon)
                bbox.add_point(mapwin.center_lat + max_dlat,
                               mapwin.center_lon + max_dlon)

            # If there's no bbox, center on the pin
            else:
                mapwin.center_lat = mapwin.pin_lat
                mapwin.center_lon = mapwin.pin_lon

        # If there's no center yet, but there is a bbox, center on it.
        # The current bbox is for "normal" track/waypoint files read in;
        # files_bbox includes those but also includes GeoJSON overlays,
        # which are only used as a last resort since they're likely
        # to cover a wide area, like a whole state.
        if not bbox:
            bbox = files_bbox

        if not mapwin.center_lat or not mapwin.center_lon:
            if not bbox:
                print("""No center coordinates!
Please specify either a site or a file containing geographic data.""")
                raise(ArgParseException)

            mapwin.center_lat, mapwin.center_lon = bbox.center()

        if bbox:
            mapwin.collection.zoom_to_bounds(bbox)
            for ov in mapwin.overlays:
                ov.zoom_to_bounds(bbox)

        else:
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


    def exec_config_file(self):
        settings = configfile.exec_config_file(self.init_width,
                                               self.init_height)
        # Then extract the changed values back out:
        # Collections is mandatory:
        self.collections = settings['Collections']

        # Optional variables:
        if "defaultCollection" in settings:
            self.default_collection = settings["defaultCollection"]
        else:
            self.default_collection = settings["Collections"][0].name

        if 'init_width' in settings:
            self.init_width = settings['init_width']
        if 'init_height' in settings:
            self.init_height = settings['init_height']

        if 'KnownSites' in settings:
            for site in settings['KnownSites']:
                self.KnownSites.append(site)
        if 'KnownSitesFormat' in settings:
            self.KnownSitesFormat = settings['KnownSitesFormat']

        # user_agent is special: it needs to be a class variable
        # so the downloader can access it without needing a
        # pointer to a specific object.
        if 'user_agent' in settings:
            pytopo.user_agent = settings['user_agent']


    def main(self, pytopo_args):
        """The main execution routine for the pytopo GUI app."""
        self.exec_config_file()

        # Remember how many known sites we got from the config file;
        # the rest are read in from saved sites and may need to be re-saved.
        self.first_saved_site = len(self.KnownSites)

        # Now it's safe to read the saved sites.
        self.KnownSites += configfile.read_saved_sites()

        # XXX Uncomment this when the migration code in configfile.py is ready
        # if not self.KnownSitesFormat:
        #     self.migrate_sites_dms_dd()
        #     print("Would migrate KnownSites")
        # else:
        #     print("KnownSitesFormat =", self.KnownSitesFormat)

        # And saved tracks
        self.KnownTracks += configfile.read_tracks()

        gc.enable()

        mapwin = MapWindow(self)

        try:
            self.parse_args(mapwin, pytopo_args)
        except ArgParseException:
            # Didn't match any known run mode:
            # start in selector mode to choose a location:
            if not mapwin.selection_window():
                sys.exit(0)

        # Fork and run in the background.
        rc = os.fork()
        if rc:
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
