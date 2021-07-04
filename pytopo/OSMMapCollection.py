# Copyright (C) 2009-2016 by Akkana Peck.
# You are free to use, share or modify this program under
# the terms of the GPLv2 or, at your option, any later GPL.

"""OSMMapCollection: tiles downloaded from the OpenStreetMap project,
   one of its renderers, or any other source that uses a similar
   tile naming and zoom scheme.
"""

from __future__ import print_function

from pytopo.TiledMapCollection import TiledMapCollection
from pytopo.MapWindow import MapWindow

import os
import time
import math
import gobject


class OSMMapCollection(TiledMapCollection):

    """
    A collection of tiles downloaded from the OpenStreetMap project
    or one of its renderers, using the OSM naming scheme.
    See also http://tfischernet.wordpress.com/2009/05/04/drawing-gps-traces-on-map-tiles-from-openstreetmap/

    @ivar: zoomlevel   The current zoom level.
    @ivar: location    Where on disk the map tiles reside.
    @ivar: download_url Where to download new tiles.
    """

    def __init__(self, _name, _location, _ext,
                 _img_width, _img_height, _init_zoom,
                 _download_url=None, maxzoom=19,
                 reload_if_older=None, attribution=None):
        """
        Parameters
        ----------
        name         : str
            user-visible name of the collection
        location     : str
            directory on disk where the maps reside
        ext          : str
            filename extension including the dot, e.g. .jpg
        img_width    : int
            width of each maplet in pixels
        img_height   : int
            height of each maplet in pixels
        init_zoom    : int
            default initial zoom level
        download_url : str
            try to download missing maplets from here
        reload_if_older : bool
            if set, reload tiles older than this (in days)
        """
        TiledMapCollection.__init__(self, _name, _location,
                                    _img_width, _img_height)
        self.ext = _ext
        self.img_width = _img_width
        self.img_height = _img_height
        self.zoomlevel = _init_zoom
        self.powzoom = 2.0 ** self.zoomlevel   # to avoid re-re-calculating
        self.download_url = _download_url
        self.maxzoom = maxzoom

        self.Debug = False

        # If reload_tiles is set, it should be set to a Unix datestamp,
        # e.g. from when the program was started.
        # Any file older than that will be re-downloaded.
        # By default, never reload tiles.
        if reload_if_older:
            self.reload_tiles = time.time() - reload_if_older * 60*60*24
        else:
            self.reload_tiles = False

        if attribution:
            self.attribution = attribution
        else:
            self.attribution = ""

        self.location = os.path.expanduser(self.location)

        # Handle ~ format for location

        # If we're download-capable, we'd better have a directory
        # to download to, so make it if it's not there already:
        if self.download_url and not os.access(self.location, os.W_OK):
            # XXX wrap in a try, show user-visible error dialog!
            os.makedirs(self.location)

        # Call zoom so we set all scales appropriately:
        self.zoom(0)

    def draw_attribution(self, mapwin):
        mapwin.draw_string_scale(-10, 1, self.attribution,
                                 whichfont="attribution")
        return

    # Utilities for mapping tiles to/from degrees.
    # From http://wiki.openstreetmap.org/wiki/Slippy_map_tilenames
    def deg2num(self, lat_deg, lon_deg, zoom=None):
        """Map coordinates to tile numbers and offsets.
           @return:  (xtile, ytile, x_off, y_off)
        """
        if zoom:
            powzoom = 2.0 ** zoom
        else:
            powzoom = self.powzoom
        lat_rad = math.radians(lat_deg)
        xtilef = (lon_deg + 180.0) / 360.0 * powzoom
        ytilef = ((1.0 - math.log(math.tan(lat_rad) +
                                  (1 / math.cos(lat_rad))) / math.pi)
                  / 2.0 * powzoom)
        xtile = int(xtilef)
        ytile = int(ytilef)

        tilesize = 256
        x_off = int((xtilef - xtile) * tilesize)
        y_off = int((ytilef - ytile) * tilesize)

        return(xtile, ytile, x_off, y_off)

    def num2deg(self, xtile, ytile):
        """Map OSM tile file numbers to coordinates.
           @return:  (lat_deg, lon_deg)
        """
        lon_deg = xtile / self.powzoom * 360.0 - 180.0
        lat_rad = math.atan(math.sinh(math.pi
                                      * (1 - 2 * ytile / self.powzoom)))
        lat_deg = math.degrees(lat_rad)
        return (lat_deg, lon_deg)

    def zoom_to(self, newzoom, latitude=45):
        """Zoom to a specific zoom level, updating scales accordingly.
        Pass latitude for map collections (e.g. OSM) that cover
        large areas so scale will tend to vary with latitude.
        """
        if self.zoomlevel != newzoom:
            if newzoom > self.maxzoom:
                print("Can't zoom past level", self.maxzoom, "in", \
                    self.name, "map collections")
                return
            self.zoomlevel = newzoom
            self.powzoom = 2.0 ** self.zoomlevel

        # Get scale, in pixels / degree.
        # (2 ** zoomlevel) tiles covers the whole world.
        self.xscale = self.powzoom * 180. / 256.

        # But because of the Mercator projection,
        # yscale has to be adjusted for latitude.
        (xtile, ytile, x_off, y_off) = self.deg2num(latitude, 180)
        (lat1, lon1) = self.num2deg(xtile, ytile)
        (lat2, lon2) = self.num2deg(xtile + 1, ytile - 1)
        self.xscale = 256. / (lon2 - lon1)
        self.yscale = 256. / (lat2 - lat1)
        if self.Debug:
            print("Zoom to %d: Calculated scales: %f, %f" \
                % (self.zoomlevel, self.xscale, self.yscale))
        return

    def zoom(self, amount, latitude=45):
        """Zoom in or out by the specified amount,
        updating the scales appropriately.
        Call zoom(0) to update x/y scales without changing zoom level.
        Pass latitude for map collections (e.g. OSM) that cover
        large areas so scale will tend to vary with latitude.
        """
        self.zoom_to(self.zoomlevel + amount, latitude)

    def get_maplet(self, longitude, latitude):
        """Fetch or queue download for the maplet containing the
        specified coordinates.
        Input coordinates are in decimal degrees.
        Returns pixbuf, x_offset, y_offset, filename
        where offsets are pixels from top left of the specified coords
        and pixbuf or (less often) filename may be None.
        """

        (xtile, ytile, x_off, y_off) = self.deg2num(latitude, longitude)

        filename = os.path.join(self.location, str(self.zoomlevel),
                                str(xtile), str(ytile)) + self.ext
        pixbuf = self.fetch_or_download_maplet(filename)
        return pixbuf, x_off, y_off, filename

    # maplet size is 256. Files per dir:
    # at zoomlevel 12, 28
    # at zoomlevel 13, 53
    # at zoomlevel 14, 107
    def get_next_maplet_name(self, fullpathname, dX, dY):
        """Starting from a maplet name, get the one a set distance away."""
        fulldir, filename = os.path.split(fullpathname)
        ystr, ext = os.path.splitext(filename)
        zoomdir, xstr = os.path.split(fulldir)
        xstr = str(int(xstr) + dX)
        ystr = str(int(ystr) + dY)

        return os.path.join(zoomdir, xstr, ystr + ext)

    def get_next_maplet(self, fullpathname, dX, dY):
        """Given a maplet's pathname, get the next or previous one.
        May not work for jumps more than 1 in any direction.
        Returns pixbuf, newpath (either may be None).
        """
        newpath = self.get_next_maplet_name(fullpathname, dX, dY)
        if newpath is None:
            return None, newpath

        pixbuf = self.fetch_or_download_maplet(newpath)
        return pixbuf, newpath

    def get_maplet_difference(self, path1, path2):
        """Given two filenames, like .../10/162/395.jpg and .../10/163/396.jpg,
           return the number of tiles different, dx and dy.
           The first (upper leftmost) one should be first.
        """
        path1 = path1.split('/')[-2:]
        path1[1] = os.path.splitext(path1[-1])[0]
        # Now path1 is something like [162, 395] which is x, y
        path2 = path2.split('/')[-2:]
        path2[1] = os.path.splitext(path2[-1])[0]
        return (int(path2[0]) - int(path1[0]), int(path2[1]) - int(path1[1]))

    def url_from_path(self, path, zoomlevel=None):
        """URL we need to get the given tile file.
           URLs can be specified like
           "http://a.tile.openstreetmap.org", and we will append /zoom/x/y.ext
           or they can be specified like
           "https://tile.thunderforest.com/outdoors/{z}/{x}/{y}.png?apikey=X"
           and we will substitute {z}, {x} and {y}.
        """
        if not zoomlevel:
            zoomlevel = self.zoomlevel

        xdir, filename = os.path.split(path)
        xdir = os.path.basename(xdir)
        y, ext = os.path.splitext(filename)

        url = self.download_url.format(z=zoomlevel, x=xdir, y=y)

        if url == self.download_url:
            # Didn't replace anything, so do it old-style
            return url + '/' + str(zoomlevel) + '/' \
                + xdir + '/' + filename
        else:
            return url

    def fetch_or_download_maplet(self, path):
        """Return a pixbuf if the file is on disk, else download"""
        # Does the tile already exist on local disk?
        # Even if it does, do we need to re-download it?
        # XXX This calls os.access then os.stat. Does that mean
        # we're statting the file twice? Might be a performance issue.
        try:
            on_disk = os.access(path, os.R_OK)
            needs_download = (not on_disk) or \
                             (self.reload_tiles and
                              os.stat(path).st_mtime < self.reload_tiles)
        except OSError:
            on_disk = False
            needs_download = True

        if needs_download:
            if self.download_url:
                # path is a full path on the local filesystem, OS independent.
                # We need to turn it into a url (Unix path) with slashes.
                thedir = os.path.dirname(path)
                if not os.access(thedir, os.W_OK):
                    os.makedirs(thedir)

                if self.Debug:
                    print("Need to download", path)
                    if not on_disk:
                        print("Wasn't on disk")
                    else:
                        print(os.stat(path).st_mtime, "<", self.reload_tiles)

                self.queue_download(self.url_from_path(path), path)

            else:
                if self.Debug:
                    print("Downloads not enabled; skipping", path)

        # We've queued any needed downloads.
        # Now return the current pixbuf, if any.
        if not on_disk:
            return None

        try:
            pixbuf = MapWindow.load_image_from_file(path)
        except:
            if self.Debug:
                print("load_image_from_file(%s) failed", path)
            pixbuf = None
            # return None

        # In case something went wrong, don't keep a bad file around:
        if not pixbuf or pixbuf.get_width() <= 0 or pixbuf.get_height() <= 0:
            # This happens periodically even when a tile does eventually
            # get downloaded and shown. I'm not sure why, but the message
            # can be misleading, so restrict it to Debug:
            if self.Debug:
                print("Couldn't open pixbuf from", path)
            os.rename(path, path + ".bad")
            pixbuf = None
        # XXX Sometimes despite that check, we mysteriously get
        # GtkWarning: gdk_drawable_real_draw_pixbuf:
        #    assertion 'width >= 0 && height >= 0' failed
        # Not clear what we can do about that since we're already checking.
        # This seems to be happening a lot less often;
        # maybe a GTK bug got fixed.

        return pixbuf

    def coords_to_filename(self, longitude, latitude):
        """Given coordinates in decimal degrees, map to the closest filename"""
        return None
