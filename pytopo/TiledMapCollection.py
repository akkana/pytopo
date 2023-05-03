# Copyright (C) 2009-2016 by Akkana Peck.
# You are free to use, share or modify this program under
# the terms of the GPLv2 or, at your option, any later GPL.

"""TiledMapCollection: a pytopo map collection that can download tiles.

   A base class for more specific downloaders.
"""

from __future__ import print_function

from pytopo.MapCollection import MapCollection
from pytopo.MapWindow import MapWindow
from pytopo import MapUtils

# For downloading tiles:
from requests_futures.sessions import FuturesSession
from concurrent.futures import ThreadPoolExecutor
# import threading
import time

import os
import glib
import gobject
import gc


class TiledMapCollection(MapCollection):

    """Code common to map collections that have raster tiles of a fixed size.
TiledMapCollection classes must implement:

  self.xscale, self.yscale (in pixels/degree)
  (pixbuf, x_off, y_off, pathname) = get_maplet(curlon, curlat)
  (pixbuf, newpath) = get_next_maplet(oldpath, dX, dY)
  (dx, dy) = get_maplet_difference(self, path1, path2)
      (number of maplets difference, which can be multipled by maplet pixel size)
  deg2num(self, lat_deg, lon_deg, zoom=None)
  num2deg(self, xtile, ytile)
  deg2num
"""

    MAX_FAILED_DOWNLOADS = 4
    RETRY_DOWNLOADS_AFTER = 300    #seconds

    def __init__(self, _name, _location, _tile_w, _tile_h):
        MapCollection.__init__(self, _name, _location)
        self.img_width = _tile_w
        self.img_height = _tile_h

        # We need to keep a pointer to the map window for redrawing
        # when downloaded tiles come in.
        self.mapwin = None

        # scale, in pixels / degree. Inherited classes must set this.
        self.xscale = None
        self.yscale = None

        self.init_downloader()
        # If it ever becomes needed to run the FuturesSession
        # tile downloader in a separate thread, do this:.
        # threading.Thread(target=self.init_downloader).start()
        # But actually this doesn't seem to be needed,
        # because FuturesSession starts its own theads anyway.

        # Keep track of how many downloads have failed.
        # Give up after a certain number -- but not forever.
        self.num_failed_downloads = 0
        self.last_failed_download_time = 0

        # Tiles downloading or downloaded but not yet drawn.
        self.urls_queued = []

        # Downloads that have failed, with the time they failed,
        # so they can be retried after a while.
        self.failed_download_urls = {}

        # Mapping between paths and URLs. Derived classes may have
        # rules for this, but TiledMapCollection only finds out when
        # queueing tile downloads.
        self.url_to_path = {}
        self.path_to_url = {}

    def init_downloader(self):
        self.downloader = \
            FuturesSession(executor=ThreadPoolExecutor(max_workers=3))
        self.downloader.hooks['response'] = self.response_hook

    def set_reload_tiles(self, p):
        """Set a flag indicating that all map tiles need to be re-downloaded,
           if the collection has a valid download location.
        """
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
        """Draw tiles at the specified coordinates, to fill the mapwin.
           Also set some win-specific variables which can be referenced later
           by draw_single_tile as downloaded tiles become available.
        """
        # In case this hasn't been initialized yet:
        self.mapwin = mapwin

        # Call zoom to set the x and y scales accurately for this latitude.
        self.zoom(0, center_lat)

        # Find the coordinate boundaries for the set of maps to draw.
        # This may (indeed, usually will) include maps partly off the screen,
        # so the coordinates will span a greater area than the visible window.
        min_lon = center_lon - mapwin.win_width / self.xscale / 2
        max_lon = center_lon + mapwin.win_width / self.xscale / 2
        min_lat = center_lat - mapwin.win_height / self.yscale / 2
        max_lat = center_lat + mapwin.win_height / self.yscale / 2

        if (self.mapwin.controller.Debug):
            print("Map from", min_lon, min_lon, min_lat, \
                  "to", max_lon, max_lat)

        # Start from the upper left: min_lon, max_lat

        # pdb.set_trace()
        curlat = max_lat
        cur_y = 0
        y_maplet_name = None
        initial_x_off = None
        while cur_y < mapwin.win_height:
            curlon = min_lon
            cur_x = 0
            x_maplet_name = None

            while cur_x < mapwin.win_width:
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

                        # Save parameters that will help draw_single_tile later.
                        # These will be reset on the first tile of
                        # each draw_map() call.
                        self.initial_x_off = x_off
                        self.initial_y_off = y_off
                        self.upper_left_maplet_name = x_maplet_name

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

                x = cur_x
                y = cur_y
                w, h = self.draw_tile_at_position(pixbuf, mapwin,
                                                  x, y, x_off, y_off)
                # You may ask, why not just do this subtraction before
                # draw_pixbuf so we don't have to subtract w and h twice?
                # Alas, we may not have the real w and h until we've done
                # pixbuf.get_width(), so we'd be subtracting the wrong thing.
                # XXX Not true in most collections, with fixed tile size.
                # XXX Could be optimized in OSMMapCollection.
                cur_x += w
                curlon += float(w) / self.xscale

            if self.mapwin.controller.Debug >= 2:
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
           Return width, height of the given tile.
        """
        if self.mapwin.controller.Debug >= 2:
            print("draw_tile_at_position", self, x, y)

        if pixbuf is not None:
            w = pixbuf.get_width() - x_off
            h = pixbuf.get_height() - y_off
        else:
            w, h = 0, 0

        if w and h:
            # If the image won't completely fill the grid space,
            # fill the whole rectangle first with black
            # (but only if this is the base layer, opacity==1).
            # This generally shouldn't happen.
            if (self.opacity == 1. and
                (pixbuf.get_width() < self.img_width or
                 pixbuf.get_height() < self.img_height)):
                mapwin.set_bg_color()
                mapwin.draw_rectangle(1, x, y,
                                      self.img_width, self.img_height)
                if self.mapwin.controller.Debug:
                    print("Filling in background:", x, y, end=' ')
                    print(self.img_width, self.img_height)

            if self.mapwin.controller.Debug >= 2:
                print(self, "draw_tile_at_position", x, y, x_off, y_off,
                      "opacity", self.opacity)
            mapwin.draw_pixbuf(pixbuf, x_off, y_off, x, y, w, h,
                               self.opacity)

            # Make sure the pixbuf goes out of scope properly
            # so it can be garbage collected:
            pixbuf = 0

        else:
            if self.mapwin.controller.Debug:
                print("No tile for", x, y, "offset", x_off, y_off)
            w = self.img_width - x_off
            h = self.img_height - y_off
            if self.opacity == 1:
                mapwin.set_bg_color()
                mapwin.draw_rectangle(1, x, y, w, h)

        # Sometimes useful when testing:
        # if (self.mapwin.controller.Debug > 1):
        #     mapwin.set_color(mapwin.grid_color)
        #     mapwin.draw_rectangle(0, x, y, w, h)
        #     mapwin.draw_line(x, y, x + w, y + h)
        #     mapwin.set_bg_color()

        return w, h

    # Utilities for mapping tiles to/from degrees.
    # From http://wiki.openstreetmap.org/wiki/Slippy_map_tilenames
    def deg2num(self, lat_deg, lon_deg, zoom=None):
        """Undefined, must be defined by subclasses"""
        raise RuntimeError("TiledMapCollection subclasses must define deg2num")

    def num2deg(self, xtile, ytile):
        """Undefined, must be defined by subclasses"""
        raise RuntimeError("TiledMapCollection subclasses must define num2deg")

    def draw_single_tile(self, path, mapwin):
        """After a new tile is downloaded, fetch its pixbuf and draw it
           in the right place for our currently displayed map.
        """
        # Finished downloading all tiles?
        # Then don't bother to draw this one; request a full
        # map redraw, so that overlays will also be drawn.
        if not self.urls_queued:
            self.mapwin.schedule_redraw()
            return

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

        # Upper left corner of the map window:
        min_lon = mapwin.center_lon - mapwin.win_width / self.xscale / 2.
        max_lat = mapwin.center_lat + mapwin.win_height / self.yscale / 2.

        # Calculate position in the window relative to the upper left maplet
        dx, dy = self.get_maplet_difference(self.upper_left_maplet_name, path)
        mapx = dx * self.img_width - self.initial_x_off
        mapy = dy * self.img_height - self.initial_y_off

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

        except glib.GError as e:
            url = self.path_to_url[path]
            if url in self.urls_queued:
                if self.mapwin.controller.Debug:
                    # I've never actually seen this message,
                    # but if it ever happens, I'd like to know.
                    print("draw_single_tile with", url, "still queued")
                return

            # XXX When the load fails with No such file or directory,
            # it seems like it could be a race condition where the
            # file got added to the queue between the load_image and
            # the urls_queued check; but it isn't, because it doesn't
            # help to check urls_queued first, and it doesn't help to
            # retry immediately. Yet when we get to the os.rename,
            # the rename works and the .bad tile is a perfectly good pixmap.
            # the tile does show up, probably in the next redraw.
            # I'm not sure what's going on.

            if os.path.exists(path):
                # The file exists, but loading the pixbuf failed.
                # Sometimes this means OSM served a text file containing
                # a string like "Tile Not Available" instead of just failing.
                # But it can also mean a partially-written file.
                # os.unlink(path)
                os.rename(path, path + ".bad")
                print("RENAMING", path)
            else:
                print("")
            self.num_failed_downloads += 1
            return

        except Exception as e:
            print("Error drawing tile:", e)
            self.num_failed_downloads += 1
            return

        self.draw_tile_at_position(pixbuf, mapwin, mapx, mapy,
                                   x_off, y_off)

    def queue_download(self, url, path):
        """Add a URL to the FuturesSession downloader queue,
           and keep a record of what file path it should use.
        """
        now = time.time()
        if self.num_failed_downloads > self.MAX_FAILED_DOWNLOADS:
            if self.last_failed_download_time \
               and now - self.last_failed_download_time \
                    < self.RETRY_DOWNLOADS_AFTER:
                # too many failed downloads, too recently
                return

            # Downloads failed a while ago, but some time has passed.
            # Try again.
            self.num_failed_downloads = 0
            self.last_failed_download_time = 0

        # Already tried to download this tile in this session?
        if url in self.urls_queued:
            if self.mapwin.controller.Debug:
                print(path, "already queued: avoiding double downloading")
            return
        try:
            # Did it fail earlier? If so, it the timespan to short to retry?
            if (now - self.failed_download_urls[url]
                < self.RETRY_DOWNLOADS_AFTER):
                if self.mapwin.controller.Debug:
                    print("Too early to retry", url)
                return
            if self.mapwin.controller.Debug:
                print("Retrying download on", url)
            del self.failed_download_urls[url]
        except KeyError:
            # Not in the list of failed tiles, go ahead and download
            pass

        self.url_to_path[url] = path
        self.path_to_url[path] = url

        # At one time, non-opaque tiles weren't kept on the download queue,
        # because downloading all the overlay tiles shouldn't trigger a
        # map redraw if the basemap tiles aren't all there yet.
        # But it's better to handle that in response_hook.
        # if self.opacity < 1.:
        self.urls_queued.append(url)

        self.downloader.get(url)

    def response_hook(self, response, *args, **kwargs):
        """When the FuturesSession completes downloading a tile,
           draw it on the map as soon as possible.
        """
        if response.status_code != 200:
            print("Error: status", response.status_code, "on", response.url)
            # XXX should check response, and maybe retry
            # in which case it shouldn't go on failed_download_urls
            self.num_failed_downloads += 1
            self.last_failed_download_time = time.time()
            self.failed_download_urls[response.url] = \
                self.last_failed_download_time
            self.urls_queued.remove(response.url)
            return

        # Is the response an image?
        try:
            if not response.headers['Content-Type'].startswith('image/'):
                if self.mapwin.controller.Debug:
                    print("%s not an image: Content-Type %s"
                          % (response.url,
                             response.headers['Content-Type']))
                self.num_failed_downloads += 1
                self.last_failed_download_time = time.time()
                return
        except:
            print("No Content-Type in headers for", response.url)
            # Perhaps that's not a problem and it's okay to continue

        # Write to disk
        self.num_failed_downloads = 0
        self.last_failed_download_time = 0
        tilepath = self.url_to_path[response.url]
        with open(tilepath, 'wb') as tilefp:
            content = response.content
            tilefp.write(content)
            if self.mapwin.controller.Debug > 1:
                debugname = '/'.join(tilepath.split('/')[-3:])
                print(debugname, "Wrote", response.url, "to", tilepath)
                # we're getting to this point, but then later finding
                # that the file isn't there.
                print(debugname, "Wrote", len(content), "bytes")

            # Remove from the download queue.
            # Don't do this until finished writing the file --
            # otherwise, another thread could see an empty queue,
            # figure it's ready to redraw, find a partially-written
            # tile that doesn't load as a pixbuf, and end up removing
            # the tile just downloaded.
            try:
                self.urls_queued.remove(response.url)
            except:
                print("Yikes, downloaded a URL not in the queue:", response.url)
                return

        # Schedule a redraw for this tile.
        # If this is the basemap (opacity=1), do this as soon as possible.
        # If it's an overlay, though, drawing immediately might draw
        # under the basemap tile. So don't redraw until all queued
        # tiles have downloaded or at least timed out.
        # The redraw has to be mapwin.draw_map, not just this collection's
        # draw_map, since some of the collection's tiles may already have
        # been drawn, and drawing over them again will double their opacity.
        if self.opacity < 1.:
            if not self.urls_queued:
                if self.mapwin.controller.Debug:
                    print("All tiles downloaded for", self,
                          ": scheduling redraw")
                glib.idle_add(self.mapwin.draw_map)
            # elif self.mapwin.controller.Debug:
            #     print("downloaded", tilepath, "but still tiles to download")
        else:
            glib.idle_add(self.draw_single_tile, tilepath, self.mapwin)
