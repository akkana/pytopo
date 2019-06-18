# Copyright (C) 2009-2016 by Akkana Peck.
# You are free to use, share or modify this program under
# the terms of the GPLv2 or, at your option, any later GPL.

'''TiledMapCollection: a pytopo map collection that can download tiles.

   A base class for more specific downloaders.
'''

from __future__ import print_function

from pytopo.MapCollection import MapCollection
from pytopo.MapWindow import MapWindow
from pytopo.MapUtils import MapUtils
from pytopo.DownloadTileQueue import DownloadTileQueue

import os
import glib
import gobject
import gc


class TiledMapCollection(MapCollection):

    """Code common to map collections that have raster tiles of a fixed size.
TiledMapCollection classes must implement:

  (pixbuf, x_off, y_off, pathname) = get_maplet(curlon, curlat)
  (pixbuf, newpath) = get_next_maplet(oldpath, dX, dY)
  deg2num(self, lat_deg, lon_deg, zoom=None)
  num2deg(self, xtile, ytile)
  deg2num
"""

    def __init__(self, _name, _location, _tile_w, _tile_h):
        MapCollection.__init__(self, _name, _location)
        self.img_width = _tile_w
        self.img_height = _tile_h

        # For collections that support downloading new tiles,
        # keep a list of tiles that still need downloading:
        self.download_tiles = DownloadTileQueue()
        self.download_func = None
        self.download_failures = 0

        # We need to keep a pointer to the map window for redrawing
        # when downloaded tiles come in.
        self.mapwin = None

    def set_reload_tiles(self, p):
        if p:
            if 'download_url' in dir(self) and self.download_url:
                print("Will re-download all map tiles")
                self.reload_tiles = p
            else:
                print("Error: can't reload tiles without a download URL")
                self.reload_tiles = False
        else:
            self.reload_tiles = False

    def draw_map(self, center_lon, center_lat, mapwin):
        """Draw maplets at the specified coordinates, to fill the mapwin."""

        self.mapwin = mapwin

        # Get the current window size:
        win_width, win_height = mapwin.get_size()
        if (self.Debug):
            print("Window is", win_width, "x", win_height)

        # Now that we have a latitude, call zoom so we can finally
        # set the x and y scales accurately.
        self.zoom(0, center_lat)

        # Find the coordinate boundaries for the set of maps to draw.
        # This may (indeed, usually will) include maps partly off the screen,
        # so the coordinates will span a greater area than the visible window.
        if (self.Debug):
            print("Calculating boundaries: min =", \
                MapUtils.dec_deg2deg_min_str(center_lon), \
                center_lon, "+/-", win_width, \
                "/", self.xscale, "/ 2")
        min_lon = center_lon - win_width / self.xscale / 2
        max_lon = center_lon + win_width / self.xscale / 2
        min_lat = center_lat - win_height / self.yscale / 2
        max_lat = center_lat + win_height / self.yscale / 2

        if (self.Debug):
            print("Map from", min_lon, MapUtils.dec_deg2deg_min_str(min_lon), \
                MapUtils.dec_deg2deg_min_str(min_lat), \
                "to", MapUtils.dec_deg2deg_min_str(max_lon), \
                MapUtils.dec_deg2deg_min_str(max_lat))

        # Start from the upper left: min_lon, max_lat

        # pdb.set_trace()
        curlat = max_lat
        cur_y = 0
        y_maplet_name = None
        initial_x_off = None
        while cur_y < win_height:
            curlon = min_lon
            cur_x = 0
            x_maplet_name = None
            while cur_x < win_width:

                # Reset the expected image size:
                w = self.img_width
                h = self.img_height

                # Is it the first maplet in this row?
                if x_maplet_name is None:

                    # Is it the first maplet in the map --
                    # usually the one in the upper left corner?
                    # Then we need to specify coordinates.
                    if y_maplet_name is None:
                        pixbuf, x_off, y_off, x_maplet_name = \
                            self.get_maplet(curlon, curlat)

                        # Save the x offset: we'll need it for the
                        # beginning of each subsequent row.
                        initial_x_off = x_off

                    # Not upper left corner --
                    # must be the beginning of a new row.
                    # Get the maplet below the beginning of the last row.
                    else:
                        pixbuf, x_maplet_name = \
                            self.get_next_maplet(y_maplet_name, 0, 1)
                        x_off = initial_x_off
                        y_off = 0

                    # Either way, whether or not we got a pixbuf,
                    # if we're at the beginning of a row, save the
                    # beginning-of-row maplet name and the offset:
                    if cur_x == 0:
                        y_maplet_name = x_maplet_name

                # Continuing an existing row.
                # Get the maplet to the right of the last one.
                else:
                    pixbuf, x_maplet_name = self.get_next_maplet(x_maplet_name,
                                                                 1, 0)
                    x_off = 0

                if self.Debug:
                    print("    ", x_maplet_name)

                x = cur_x
                y = cur_y

                w, h = self.draw_tile_at_position(pixbuf, mapwin,
                                                  x, y, x_off, y_off)
                # You may ask, why not just do this subtraction before
                # draw_pixbuf so we don't have to subtract w and h twice?
                # Alas, we may not have the real w and h until we've done
                # pixbuf.get_width(), so we'd be subtracting the wrong thing.
                # XXX Not really true any more, since we're assuming fixed
                # XXX tile size. Revisit this!
                cur_x += w
                curlon += float(w) / self.xscale

            if (self.Debug):
                print(" ")
                print("New row: adding y =", h, end=' ')
                print("Subtracting lat", float(h) / self.yscale)

            cur_y += h
            curlat -= float(h) / self.yscale
            # curlat -= float(self.img_height) / self.yscale

        # Free all pixbuf data. Just letting pixbuf go out of scope
        # isn't enough; it's necessary to force garbage collection
        # otherwise Python will let the process grow until it
        # fills all of memory.
        # http://www.daa.com.au/pipermail/pygtk/2003-December/006499.html
        # (At this indentation level, we free after drawing the whole map.)
        gc.collect()

        # If we queued any downloads and aren't currently downloading,
        # schedule a function to take care of that:
        if len(self.download_tiles) > 0 and self.download_func is None:
            gobject.timeout_add(300, self.download_more)

    def get_next_maplet_name(self, fullpathname, dX, dY):
        """Starting from a maplet name, get the one a set distance away."""
        return

    def get_next_maplet(self, fullpathname, dX, dY):
        """Given a maplet's pathname, get the next or previous one.
        May not work for jumps more than 1 in any direction.
        Returns pixbuf, newpath (either may be None).
        """
        return

    def draw_tile_at_position(self, pixbuf, mapwin, x, y, x_off, y_off):
        """Draw a single tile, perhaps after downloading it,
           at a specified location.
        """
        if pixbuf is not None:
            w = pixbuf.get_width() - x_off
            h = pixbuf.get_height() - y_off
            if (self.Debug):
                print("img size:", pixbuf.get_width(), \
                      pixbuf.get_height())

            # If the image won't completely fill the grid space,
            # fill the whole rectangle first with black.
            # Note: this may not guard against images with
            # transparent areas. Don't do that.
            if (pixbuf.get_width() < self.img_width or
                    pixbuf.get_height() < self.img_height):
                mapwin.set_bg_color()
                mapwin.draw_rectangle(1, x, y,
                                      self.img_width, self.img_height)
                if (self.Debug):
                    print("Filling in background:", x, y, end=' ')
                    print(self.img_width, self.img_height)

            # if (self.Debug):
            #     print("Drawing maplet for", end='')
            #     print(MapUtils.dec_deg2deg_min_str(curlon), end='')
            #     print(MapUtils.dec_deg2deg_min_str(curlat), end='')
            #     print("at", x, y, "offset", x_off, y_off, end='')
            #     print("size", w, h)

            mapwin.draw_pixbuf(pixbuf, x_off, y_off, x, y, w, h)

            # Make sure the pixbuf goes out of scope properly:
            pixbuf = 0
        else:
            # if (self.Debug):
            #     print("No maplet for", curlon, curlat, end='')
            #     print("at", x, y, "offset", x_off, y_off)
            mapwin.set_bg_color()
            w = self.img_width - x_off
            h = self.img_height - y_off
            mapwin.draw_rectangle(1, x, y, w, h)

        # Useful when testing:
        if (self.Debug > 1):
            mapwin.set_color(mapwin.grid_color)
            mapwin.draw_rectangle(0, x, y, w, h)
            mapwin.draw_line(x, y, x + w, y + h)
            mapwin.set_bg_color()

        return w, h

    # Utilities for mapping tiles to/from degrees.
    # From http://wiki.openstreetmap.org/wiki/Slippy_map_tilenames
    def deg2num(self, lat_deg, lon_deg, zoom=None):
        raise RuntimeError("TiledMapCollection subclasses must define deg2num")

    def num2deg(self, xtile, ytile):
        raise RuntimeError("TiledMapCollection subclasses must define num2deg")

    def draw_single_tile(self, path, mapwin):
        '''After a new tile is downloaded, fetch its pixbuf and draw it
           in the right place for our currently displayed map.
        '''
        # Calculate x, y, x_offset, y_offset from the tile name.
        # Make sure it's even still visible.
        # Tile name is /path/to/zoom/x/y.ext
        head, tiley = os.path.split(path)
        tiley = os.path.splitext(tiley)[0]
        head, tilex = os.path.split(head)
        head, tilezoom = os.path.split(head)
        try:
            tiley = int(tiley)
            tilex = int(tilex)
        except ValueError:
            print("Bad tile filename", path)
            return
        # Now we need to turn tilex and tiley into x, y, x_off, y_off
        # for the MapWindow's current position.
        lat_deg, lon_deg = self.num2deg(tilex, tiley)

        # Where on the map window should this lat and lon appear?
        min_lon = mapwin.center_lon - mapwin.win_width / self.xscale / 2
        max_lat = mapwin.center_lat + mapwin.win_height / self.yscale / 2
        mapx = int((lon_deg - min_lon) * self.xscale)
        mapy = int((max_lat - lat_deg) * self.yscale)

        if mapx < 0:
            x_off = -mapx
            mapx = 0
        else:
            x_off = 0
        if mapy < 0:
            y_off = -mapy
            mapy = 0
        else:
            y_off = 0

        try:
            pixbuf = MapWindow.load_image_from_file(path)
            self.draw_tile_at_position(pixbuf, mapwin, mapx, mapy,
                                       x_off, y_off)
        except glib.GError as e:
            print("Couldn't draw tile:", e, end=' ')
            if not self.Debug:
                print("... deleting")
            else:
                print("")
            print("")
            if os.path.exists(path) and not self.Debug:
                os.unlink(path)
            self.download_failures += 1
            # Usually this means OSM gave us a text file containing
            # a string like "Tile Not Available"
        except Exception as e:
            print("Error drawing tile:", e)
            self.download_failures += 1

        # Redraw any trackpoints, zoom controls, and anything else that
        # has to draw over the tiles, since they might have been overwritten.
        # XXX should schedule this after a delay, so we're not constantly
        # redrawing large sets of trackpoints each time a new tile comes in.
        mapwin.draw_overlays()

    def download_finished(self, path):
        """Callback when a tile finishes downloading.
           The path argument is either the local file path just downloaded,
           or an exception, e.g. IOError.
        """

        # If we got too many failures -- usually IOError,
        # perhaps we're offline -- path will be None here.
        # In that case, just give up on downloading.
        if path is None:
            self.download_failures += 1
            if self.download_failures > 10:
                print("\nDownload failed; giving up")
                self.download_func = None
                # Clear self.download_tiles, so that if the net returns
                # we'll start on new stuff, not old stuff.
                # Not clear if this is the right thing to do or not.
                self.download_tiles = DownloadTileQueue()
                self.download_failures = 0
            # We can't draw this tile, so return.
            return

        # Otherwise, we got a path for a successful tile download.
        # Reset the failure counter:
        # self.download_failures = 0

        self.download_tiles.pop()   # Throw away url, path popped
        # Calling draw_single_tile from idle_add makes the GTK3 window
        # redraw much more promptly (didn't matter under GTK2).
        # self.draw_single_tile(path, self.mapwin)
        glib.idle_add(self.draw_single_tile, path, self.mapwin)

        # It's okay to start a new download now:
        self.download_func = None

        # Anything more to download?
        if len(self.download_tiles) > 0:
            self.download_more()

    def download_more(self):
        """Idle/timeout proc to download any pending tiles.
           Should always return False so it won't get rescheduled.
           Eventually this should download in a separate thread.
        """

        # If we already have a download going, don't start another one
        # (eventually we'll want to run several in parallel).
        if self.download_func is not None:
            if self.Debug:
                print("There's already a download going; not downloading more")
            return False

        # If there are no more tiles to download, we're done:
        if len(self.download_tiles) == 0:
            self.download_func = None
            return False

        url, path = self.download_tiles.peek()
        # Don't actually pop() it until it has downloaded.
        # urllib.urlretrieve(url, path)
        self.download_func = \
            DownloadTileQueue.start_job(DownloadTileQueue.download_job(url,
                                                                       path,
                                                     self.download_finished))
        if self.Debug:
            print("Started download %s to %s" % (url, path))

        return False
