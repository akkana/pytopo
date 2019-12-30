# Copyright (C) 2009-2016 by Akkana Peck.
# You are free to use, share or modify this program under
# the terms of the GPLv2 or, at your option, any later GPL.

"""TopoMapCollection: a pytopo map collection using Topo!
   commercial map datasets.
"""

from __future__ import print_function

from pytopo.TiledMapCollection import TiledMapCollection
from pytopo.MapUtils import MapUtils
from pytopo.MapWindow import MapWindow

import os


class TopoMapCollection(TiledMapCollection):

    """TiledMapCollections using the Topo! map datasets.
    Filenames are named according to a fairly strict convention.
    Some variants can toggle between more than one scale (series).
    """

    def __init__(self, _name, _location, _series, _tile_w, _tile_h,
                 _ser7prefix="012t", _ser15prefix="024t", _img_ext=".gif"):
        """arguments:
        name        -- user-visible name of the collection
        location    -- directory on disk where the maps reside
        series      -- initial series to use, 7.5 or 15 minutes of arc.
        tile_w      -- width of each maplet in pixels
        tile_h      -- height of each maplet in pixels
        img_ext     -- filename extension including the dot, e.g. .jpg
        ser7prefix  -- prefix for tile files implementing the 7.5-min series
        ser15prefix -- prefix for tile files implementing the 15-min series
        """

        TiledMapCollection.__init__(self, _name, _location, _tile_w, _tile_h)
        self.set_series(_series)
        self.ser7prefix = _ser7prefix
        self.ser15prefix = _ser15prefix
        self.img_ext = _img_ext

        # _correction because Topo1 maps aren't in WGS 84.
        # Right now these numbers are EMPIRICAL and inaccurate.
        # Need to do them right!
        # http://www.ngs.noaa.gov/cgi-bin/nadcon.prl says the correction
        # in the Mojave area from NAD27 to NAD84 (nobody converts to
        # WGS84, alas) should be -0.05463', 2.99014' (-1.684m, 75.554m)
        self.lon_correction = 0  # 0.032778 / 1000
        self.lat_correction = 0  # -1.794084 / 1000

    def set_series(self, _series):
        """Set the series to either 7.5 or 15 minutes."""

        # traceback.print_stack()
        self.series = _series
        self.xscale = self.img_width * 600.0 / self.series
        self.yscale = self.img_height * 600.0 / self.series
        if (self.Debug):
            print("set series to", self.series)
        # 600 is minutes/degree * maplets/minute

        # The fraction of a degree that each maplet spans:
        self.frac = float(self.img_width) / self.xscale
        if (self.Debug):
            if self.frac != float(self.img_height) / self.yscale:
                print("x and y fractions not equal!", end=' ')
                print(self.frac, float(self.img_height) / self.yscale)

    def get_maplet(self, longitude, latitude):
        """Get the maplet containing the specified coordinates.
        Returns pixbuf, x_offset, y_offset, filename
        where offsets are pixels from top left of the specified coords
        and pixbuf or (less often) filename may be None.
        """

        filename = self.coords_to_filename(longitude - self.lon_correction,
                                           latitude - self.lat_correction)
        if (self.Debug):
            print("T1MC get_maplet(", MapUtils.dec_deg2deg_min_str(longitude), end=' ')
            print(",", MapUtils.dec_deg2deg_min_str(latitude), "):", filename)

        # Calculate offsets.
        # Maplets are self.series minutes wide and tall,
        # so any offset from that is an offset into the maplet:
        # the number of pixels in X and Y that have to be added
        # to get from the maplet's upper left corner to the
        # indicated coordinates.
        # But then we have to correct to get to WGS84 coordinates.
        # XXX the WGS84 part doesn't work right yet.

        # longitude increases rightward:
        x_off = int((longitude - MapUtils.truncate2frac(longitude, self.frac)
                     - self.lon_correction) * self.xscale)
        if (self.Debug):
            print("truncated", MapUtils.dec_deg2deg_min_str(longitude), "to", end=' ')
            print(MapUtils.dec_deg2deg_min_str(MapUtils.truncate2frac(longitude,
                                                                     self.frac)))

        # Latitude decreases downward:
        y_off = int((MapUtils.truncate2frac(latitude, self.frac) +
                     self.frac - latitude - self.lat_correction) * self.yscale)

        if (self.Debug):
            print("truncated", MapUtils.dec_deg2deg_min_str(latitude), "to", end=' ')
            print(MapUtils.dec_deg2deg_min_str(MapUtils.truncate2frac(latitude,
                                                                     self.frac)))
            print("y_off is", y_off)

        if not os.access(filename, os.R_OK):
            return None, x_off, y_off, filename
        pixbuf = MapWindow.load_image_from_file(filename)

        return pixbuf, x_off, y_off, filename

    def get_next_maplet(self, fullpathname, dX, dY):
        """Given a maplet's pathname, get the next or previous one.
        Does not currently work for jumps more than 1 in any direction.
        Returns pixbuf, newpath (either may be None).
        """

        if (self.Debug):
            print("get_next_maplet:", fullpathname, dX, dY)
        pathname, filename = os.path.split(fullpathname)
        collecdir, mapdir = os.path.split(pathname)
        maplat = int(mapdir[1:3])
        maplon = int(mapdir[3:6])
        name, ext = os.path.splitext(filename)
        xdir = int(mapdir[-1])
        ydir = ord(mapdir[-2]) - ord('a')     # convert from letter a-h
        if self.series == 7.5:
            serstr = self.ser7prefix
            grid = 10
        else:
            serstr = self.ser15prefix
            grid = 5

        x = int(name[-4:-2]) + dX
        y = int(name[-2:]) + dY

        if x < 1:
            x = grid
            xdir = xdir + 1
            if xdir > 8:
                xdir = 1
                if self.Debug:
                    print(mapdir, name, ": wrapping mapdir coordinates -x", end=' ')
                    print(maplon)
                maplon = str(int(maplon) + 1)
        if x > grid:
            x = 1
            xdir = xdir - 1
            if xdir < 1:
                xdir = 8
                if self.Debug:
                    print(mapdir, name, ": wrapping mapdir coordinates +x", end=' ')
                    print(maplon)
                maplon = str(int(maplon) - 1)

        if y > grid:
            y = 1
            ydir = ydir - 1
            if ydir < 0:
                ydir = 7
                if self.Debug:
                    print(mapdir, name, ": wrapping mapdir coordinates +y", end=' ')
                    print(maplat)
                maplat = str(int(maplat) - 1)

        if y < 1:
            y = grid
            ydir = ydir + 1
            if ydir > 7:
                ydir = 0
                if self.Debug:
                    print(mapdir, name, ": wrapping mapdir coordinates -y", end=' ')
                    print(maplat)
                maplat = str(int(maplat) + 1)

        # We're ready to piece the filename back together!
        newpath = os.path.join(collecdir,
                               "q" + MapUtils.ohstring(maplat, 2)
                                   + MapUtils.ohstring(maplon, 3)
                                   + chr(ydir + ord('a')) + str(xdir),
                               serstr + MapUtils.ohstring(x, 2)
                                   + MapUtils.ohstring(y, 2) + ext)
        if not os.access(newpath, os.R_OK):
            if self.Debug:
                print("get_next_maplet(", fullpathname, dX, dY, ")")
                print("  Can't open", newpath)
            return None, newpath

        pixbuf = MapWindow.load_image_from_file(newpath)
        return pixbuf, newpath

    #
    # Quirk: Topo1 collections are numbered with WEST longitude --
    # i.e. longitude is written as positive but it's actually negative.
    #
    # Second quirk: Topo1 collections aren't in the WGS 84 coordinate
    # system used by GPS receivers, and need to be translated.
    # http://en.wikipedia.org/wiki/Geographic_coordinate_system
    # http://en.wikipedia.org/wiki/Geodetic_system
    #
    def coords_to_filename(self, longitude, latitude):
        """Given a pair of coordinates in deg.mmss, map to the
        containing filename, e.g. q37122c2/012t0501.gif.
        """

        latDeg = MapUtils.int_trunc(latitude)
        longDeg = MapUtils.int_trunc(-longitude)
        latMin = (latitude - latDeg) * 60.
        longMin = (-longitude - longDeg) * 60.

        # The 7.5 here is because of the 7.5 in the directory names above
        # (we're getting the offset of this image from the origin of
        # the 7.5-series map covered by the directory),
        # not the map series we're actually plotting now.
        longMinOrd = MapUtils.int_trunc(longMin / 7.5)
        latMinOrd = MapUtils.int_trunc(latMin / 7.5)

        dirname = "q" + MapUtils.ohstring(latDeg, 2) \
            + MapUtils.ohstring(longDeg, 3) \
            + chr(ord('a') + latMinOrd) + str(longMinOrd + 1)

        # Find the difference between our desired coordinates
        # and the origin of the map this directory represents.
        # The 7.5 here is because of the 7.5 in the directory names above.
        latMinDiff = latMin - (latMinOrd * 7.5)
        longMinDiff = longMin - (longMinOrd * 7.5)

        latOffset = MapUtils.int_trunc(latMinDiff * 10 / self.series)
        longOffset = MapUtils.int_trunc(longMinDiff * 10 / self.series)

        # Now calculate the current filename.
        # Note that series is either 7.5 or 15
        if (self.series > 13):
            fileprefix = "024t"
            numcharts = 5
        else:
            fileprefix = "012t"
            numcharts = 10
        filename = fileprefix + MapUtils.ohstring(numcharts - longOffset, 2) \
                   + MapUtils.ohstring(numcharts - latOffset, 2) + self.img_ext

        return self.location + "/" + dirname + "/" + filename

    def dir_to_latlong(self, qdir):
        """Given a directory, figure out the corresponding coords."""
        letter = ord(qdir[6]) - ord('a')
        digit = int(qdir[7]) - 1
        thislon = -int(qdir[3:6]) + (digit * 7.5 * 1.5 / 60)
        # thislon += self.lon_correction
        thislat = int(qdir[1:3]) + (letter * 7.5 * 1.5 / 60)
        # thislat += self.lat_correction
        return thislon, thislat

    def get_top_left(self):
        """Get the coordinates of the top left corner of the map."""
        minlong = 181
        maxlat = -91
        topleftdir = None

        mapdirs = os.listdir(self.location)
        # mapdirs.sort()
        for mapdir in mapdirs:
            if mapdir[0] == 'q':
                # Now first_mapdir is some name like "qAAABBcD" ... decode it.
                thislong, thislat = self.dir_to_latlong(mapdir)
                # if thislong < minlong and thislat > maxlat:
                if thislong < minlong:
                    minlong = thislong
                    if thislat > maxlat:
                        maxlat = thislat
                        topleftdir = mapdir
        if maxlat < -90 or minlong > 180:
            return 0, 0    # shouldn't happen

        # Now we have the top left directory. Still need the top left file:
        files = os.listdir(os.path.join(self.location, topleftdir))

        return minlong, maxlat

# End of TopoMapCollection class


class Topo1MapCollection(TopoMapCollection):

    """
Topo1MapCollection: data from local-area Topo! packages,
  the kind that have 7.5 minute and 15 minute varieties included.
   (self, _name, _location, _series, tile_w, tile_h):
    """

    def __init__(self, _name, _location, _series, _tile_w, _tile_h):
        TopoMapCollection.__init__(self, _name, _location, _series,
                                   _tile_w, _tile_h,
                                   _ser7prefix="012t", _ser15prefix="024t",
                                   _img_ext=".gif")

    def zoom(self, amount, latitude=45):
        if self.series == 7.5 and amount < 0:
            self.set_series(15)
        elif self.series == 15 and amount > 0:
            self.set_series(7.5)

# A Topo2MapCollection is just a Topo1MapCollection that has only
# 7.5-series and has a different file prefix.
# On North Palisade 7.5 (q37118a5) we get 410x256 pixel images.


class Topo2MapCollection(TopoMapCollection):

    """
Topo2MapCollection: data from local-area Topo! packages that
  have only the 7.5-minute series and use jpg instead of gif.
   (collection_name, directory_path, file_prefix, tile_w, tile_h):
    """

    def __init__(self, _name, _location, _prefix, _tile_w, _tile_h):
        TopoMapCollection.__init__(self, _name, _location, 7.5,
                                   _tile_w, _tile_h,
                                   _ser7prefix=_prefix, _ser15prefix=None,
                                   _img_ext=".jpg")
