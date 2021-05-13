# Copyright (C) 2009-2016 by Akkana Peck.
# You are free to use, share or modify this program under
# the terms of the GPLv2 or, at your option, any later GPL.

"""GenericMapCollection: a tiled map collection that can use
   any naming scheme, suitable for home-built tiled maps
   or maps adapted from other data sources.
"""

from __future__ import print_function

import os
from pytopo.MapUtils import MapUtils
from pytopo.MapWindow import MapWindow
from pytopo.TiledMapCollection import TiledMapCollection


class GenericMapCollection(TiledMapCollection):

    """
    A GenericMapCollection is tiled, like the Topo collections,
    but uses a less specific naming scheme:
    prefix-nn-mm.ext, with or without the dashes.
    """

    def __init__(self, _name, _location, _prefix, _ext,
                 _left_long, _top_lat,
                 _img_width, _img_height, _xscale, _yscale,
                 _numdigits, _usedash, _latfirst):
        """Create a generic map collection.
        Parameters
        ----------
        name       : str
            user-visible name of the collection
        location   : str
            directory on disk where the maps reside
        prefix     : str
            initial part of each maplet filename
        ext        : str
            filename extension including the dot, e.g. .jpg
        left_long  : float
            longitude of the left edge
        top_lat    : float
            latitude of the top edge
        img_width  : int
            width of each maplet in pixels
        img_height : int
            height of each maplet in pixels
        xscale     : float
            pixels per degree longitude
        yscale     : float
            pixels per degree latitude
        numdigits  : int
            number of digits in x and y file specifiers
        usedash    : bool
            use a dash between x and y in filenames?
        latfirst   : bool
            is latitude the first of the two numbers?
        """
        TiledMapCollection.__init__(self, _name, _location,
                                    _img_width, _img_height, )
        self.prefix = _prefix
        self.numdigits = _numdigits
        self.usedash = _usedash
        self.ext = _ext
        self.latfirst = _latfirst
        self.img_width = _img_width
        self.img_height = _img_height
        self.left_longitude = _left_long    # Left of 00-00 image
        self.top_latitude = _top_lat        # Top of 00-00 image
        self.xscale = float(_xscale)        # Pixels per degree
        self.yscale = float(_yscale)        # Pixels per degree

    def get_maplet(self, longitude, latitude):
        """Get the maplet containing the specified coordinates.
        Returns pixbuf, x_offset, y_offset, filename
        where offsets are pixels from top left of the specified coords
        and pixbuf or (less often) filename may be None.
        """
        filename = self.coords_to_filename(longitude, latitude)
        if (self.Debug):
            print("Generic get_maplet", longitude, latitude, "->", filename)
        if filename is None or not os.access(filename, os.R_OK):
            # print("Can't open", filename, "for", longitude, latitude)
            return None, 0, 0, filename
        # print("Opened", filename, "for", longitude, latitude)
        pixbuf = MapWindow.load_image_from_file(filename)

        # Offsets aren't implemented yet:
        x_off = 0
        y_off = 0

        return pixbuf, x_off, y_off, filename

    def get_next_maplet(self, fullpathname, dX, dY):
        """Given a maplet's pathname, get the next or previous one.
        Does not currently work for jumps more than 1 in any direction.
        Returns pixbuf, newpath (either may be None).
        """
        pathname, filename = os.path.split(fullpathname)
        if (self.Debug):
            print("Generic get_next_maplet", filename, dX, dY)
        name, ext = os.path.splitext(filename)
        # traceback.print_stack()
        mapb = int(name[-self.numdigits:])
        if self.usedash:
            mapa = int(name[-self.numdigits * 2 - 1: -self.numdigits - 1])
        else:
            mapa = int(name[-self.numdigits * 2: -self.numdigits])
        if self.latfirst:
            newa = MapUtils.ohstring(mapa + dX, self.numdigits)
            newb = MapUtils.ohstring(mapb + dY, self.numdigits)
        else:
            newa = MapUtils.ohstring(mapa + dY, self.numdigits)
            newb = MapUtils.ohstring(mapb + dX, self.numdigits)
        if self.usedash:
            newname = self.prefix + newa + "-" + newb
        else:
            newname = self.prefix + newa + newb
        newpath = os.path.join(self.location, newname + ext)
        if filename is None or not os.access(filename, os.R_OK):
            return None, newpath
        pixbuf = MapWindow.load_image_from_file(newpath)
        return pixbuf, newpath

    def coords_to_filename(self, longitude, latitude):
        """Given coordinates in decimal degrees, map to the closest filename"""
        if self.left_longitude > longitude or self.top_latitude < latitude:
            return None
        x_grid = MapUtils.int_trunc((longitude - self.left_longitude) *
                                    self.xscale / self.img_width)
        y_grid = MapUtils.int_trunc((self.top_latitude - latitude) *
                                    self.yscale / self.img_height)
        if not self.latfirst:
            temp = x_grid
            x_grid = y_grid
            y_grid = temp
        retstr = os.path.join(self.location,
                              self.prefix + MapUtils.ohstring(x_grid,
                                                              self.numdigits))
        if self.usedash:
            retstr = retstr + "-"
        retstr = retstr + MapUtils.ohstring(y_grid, self.numdigits) + self.ext
        return retstr
