# Copyright (C) 2009-2016 by Akkana Peck.
# You are free to use, share or modify this program under
# the terms of the GPLv2 or, at your option, any later GPL.

'''MapCollection: the base class for all pytopo map collections.
'''

from __future__ import print_function

import os
import math


class MapCollection (object):

    """A MapCollection is a set of maplet tiles on disk,
combined with knowledge about the geographic coordinates
and scale of those tiles so they can be drawn in a map window.

Child classes implementing MapCollection must define functions
__init__, get_maplet, draw_map, and get_top_left.
Get_top_left() is only for debugging, when you're trying to figure out
map coordinates and need a starting place. Should probably remove it.
"""

    def __init__(self, _name, _location):
        self.name = _name
        self.location = _location

        # Set some defaults so that we can test pytopo with a null collection:
        self.img_width = 100
        self.img_height = 100
        self.xscale = 100.
        self.yscale = 100.

        # Child classes must set maxzoom:
        self.maxzoom = None

        self.Debug = False

    def get_maplet(self, longitude, latitude):
        """Returns pixbuf, x_offset, y_offset:

         - the pixbuf for the maplet image (or null)
         - the offset in pixels into the image for the given coordinates,
           from top left.
        """
        return None, 0, 0

    def draw_map(self, center_lon, center_lat, drawwin):
        """Draw a map in a window, centered around the specified coordinates.
        drawwin is a DrawWin object.
        """
        return

    def draw_attribution(self, drawwin):
        """Draw attribution/copyright for the map tiles used in this collection.
        """
        return

    def get_top_left(self):
        """A way to display some part of a map collection even if we're fuzzy
        on the coordinates -- get the coordinate of the first maplet
        and return as longitude, latitude."""
        return 0, 0

    def zoom(self, amount, latitude=45):
        """Zoom by the given number of steps (positive to zoom in,
        negative to zoom out). Pass amount=0 to recalculate/redraw.
        Some map collections need to know latitude to determine scale.
        """
        return

    def zoom_to(self, newzoom, latitude=45):
        """Zoom to a specific zoom level and recalculate scales.
        Some map collections need to know latitude to determine scale.
        """
        return

    def exists(self):
        """Does the collection have its map files in place?"""
        self.location = os.path.expanduser(self.location)
        return os.access(self.location, os.X_OK)

    # Spherical Mercator code,
    # from http://wiki.openstreetmap.org/wiki/Mercator#Python
    def y2lat(self, a):
        return (180.0 / math.pi
                * (2.0 * math.atan(math.exp(a * math.pi / 180.0))
                   - math.pi / 2.0))

    def lat2y(self, a):
        return (180.0 / math.pi
                * math.log(math.tan(math.pi / 4.0
                                    + a * (math.pi / 180.0) / 2.0)))

    def zoom_to_bounds(self, minlon, minlat, maxlon, maxlat):
        # http://gis.stackexchange.com/questions/19632/how-to-calculate-the-optimal-zoom-level-to-display-two-or-more-points-on-a-map
        # Find spherical Mercator distances:
        xdist = maxlon - minlon
        ydist = self.lat2y(maxlat) - self.lat2y(minlat)
        # The equator is about 40m meters long projected and tiles are
        # 256 pixels wide, so the pixel length of that map at a given
        # zoom level is about 256 * distance/40000000 * 2^zoom.
        # But it needs another factor of 100000, determined empirically.
        mult = 256. * 100000. / 40000000.
        z = 0

        # Handle the case of a single point
        if xdist == 0 or ydist == 0:
            print("Single point! Zooming to maxzoom", self.maxzoom)
            self.zoom_to(self.maxzoom)
            return

        while z <= self.maxzoom:
            powz = pow(2, z)
            w = xdist * mult * powz
            h = ydist * mult * powz
            # print z, ": Size", w, "x", h
            if w > 800 or h > 600:
                self.zoom_to(z-1)
                return
            z += 1
        print("Couldn't fit bounding box; using maximum zoom")
        self.zoom_to(self.maxzoom)
