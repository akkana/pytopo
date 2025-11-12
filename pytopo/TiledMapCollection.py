# Copyright (C) 2009-2016 by Akkana Peck.
# You are free to use, share or modify this program under
# the terms of the GPLv2 or, at your option, any later GPL.

"""TiledMapCollection: a pytopo map collection that can download tiles.

   A base class for more specific downloaders.
"""

from pytopo.MapCollection import MapCollection
from pytopo.MapWindow import MapWindow
from pytopo import MapUtils

# For downloading tiles:
from requests_futures.sessions import FuturesSession
from concurrent.futures import ThreadPoolExecutor
# import threading

import time
import math

import os

from gi.repository import GLib

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

    def find_tile_window_geometry(self, mapwin):
        """
           For given center coordinates and the current zoom level and
           window size, calculate the tile X and Y for the center,
           the offset at which to draw the tiles,
           and the number of tiles spanned in each direction.
           Return: center_tile_x, center_tile_y,
                   tile_offset_x, tile_offset_y,
                   tiles_left, tiles_right, tiles_up, tiles_down
        """
        # Find the tile that contains the center
        center_tile_x = int(self.powzoom * (mapwin.center_lon + 180) / 360)
        center_lat_rad = math.radians(mapwin.center_lat)
        center_tile_y = int(self.powzoom * (
            1 - math.log(math.tan(center_lat_rad)
                         + 1/math.cos(center_lat_rad)) / math.pi) / 2)

        # Convert center to Mercator and then to tile coordinates
        center_merc_x, center_merc_y = MapUtils.latlon_to_mercator(
            mapwin.center_lat, mapwin.center_lon)

        # Get Mercator coords of the center tile's top-left corner
        tile_lon = center_tile_x / self.powzoom * 360 - 180
        tile_y_rad = math.atan(math.sinh(
            math.pi * (1 - 2 * center_tile_y / self.powzoom)))
        tile_lat = math.degrees(tile_y_rad)
        tile_merc_x, tile_merc_y = MapUtils.latlon_to_mercator(tile_lat, tile_lon)

        # Calculate resolution (meters per pixel)
        resolution = 2 * math.pi * 6378137.0 / 256.0 / self.powzoom

        # Offset of the center point from the top, left of its tile (pixels)
        tile_offset_x = int((center_merc_x - tile_merc_x) / resolution)
        tile_offset_y = int((tile_merc_y - center_merc_y) / resolution)

        center_tile_draw_x = mapwin.win_width / 2 - tile_offset_x
        center_tile_draw_y = mapwin.win_height / 2 - tile_offset_y

        # Determine range of tiles needed
        tiles_left = int(math.ceil(-center_tile_draw_x / self.img_width)) - 1
        tiles_right = int(math.ceil((mapwin.win_width - center_tile_draw_x)
                                    / self.img_width))
        tiles_up = int(math.ceil(-center_tile_draw_y / self.img_height)) - 1
        tiles_down = int(math.ceil((mapwin.win_height - center_tile_draw_y)
                                   / self.img_height))

        # print("find_tile_window_geometry: Returning",
        #       center_tile_x, center_tile_y,
        #       tile_offset_x, tile_offset_y,
        #       tiles_left, tiles_right, tiles_up, tiles_down)
        return (center_tile_x, center_tile_y,
                tile_offset_x, tile_offset_y,
                tiles_left, tiles_right, tiles_up, tiles_down)

    def draw_map(self, center_lon, center_lat, mapwin):
        # In case the mapwin hasn't been initialized yet:
        self.mapwin = mapwin

        # Call zoom to set the x and y scales accurately for this latitude.
        self.zoom_to(self.zoomlevel, center_lat)

        (center_tile_x, center_tile_y,
         center_offset_x, center_offset_y,
         tiles_left, tiles_right, tiles_up, tiles_down) = \
             self.find_tile_window_geometry(mapwin)

        # Where to draw the center tile so the center pt appears at window center
        center_tile_draw_x = mapwin.win_width / 2 - center_offset_x
        center_tile_draw_y = mapwin.win_height / 2 - center_offset_y

        if self.mapwin.controller.Debug > 1:
            print("tiles left, right, up, down:",
                  tiles_left, tiles_right, tiles_up, tiles_down)

        tiles = []
        for dy in range(tiles_up, tiles_down):
            for dx in range(tiles_left, tiles_right):
                tile_x = center_tile_x + dx
                tile_y = center_tile_y + dy

                # Wrap around in longitude, but not in latitude
                # because that doesn't work in a Mercator projection
                if tile_x < 0:
                    tile_x = int(tile_x + self.powzoom)
                if tile_x >= self.powzoom:
                    tile_x = tile_x % self.powzoom

                # Skip tiles outside valid Y range
                # (though that shouldn't happen)
                if tile_y < 0 or tile_y >= self.powzoom:
                    print("Skipping tile %d, %d" % (tile_x, tile_y))
                    continue

                draw_x = int(center_tile_draw_x + dx * self.img_width)
                draw_y = int(center_tile_draw_y + dy * self.img_height)

                if self.mapwin.controller.Debug:
                    print(f"Tile ({tile_x}, {tile_y}) -> draw at"
                          f"({draw_x}, {draw_y})")
                pixbuf, filename = self.get_maplet_by_number(tile_x, tile_y)
                x_off, y_off = 0, 0
                self.draw_tile_at_position(pixbuf, mapwin,
                                           draw_x, draw_y, x_off, y_off)

        # Free all pixbuf data after drawing the whole map.
        # Just letting pixbuf go out of scope # isn't enough;
        # it's necessary to force garbage collection
        # otherwise Python will let the process grow until it
        # fills all of memory.
        # http://www.daa.com.au/pipermail/pygtk/2003-December/006499.html
        gc.collect()

    def get_next_maplet_name(self, fullpathname, dX, dY):
        """Starting from a maplet name, get the one a set distance away.
           This needs to be overridden by child classes.
        """
        return

    def get_next_maplet(self, fullpathname, dX, dY):
        """Given a maplet's pathname, get the next or previous one.
           May not work for jumps more than 1 in any direction.
           Returns pixbuf, newpath (either may be None).
           This needs to be overridden by child classes.
        """
        return

    def draw_tile_at_position(self, pixbuf, mapwin, x, y, x_off, y_off):
        """Draw a single tile at a specified location,
           starting at offset x_off, y_off into the tile.
           Return width, height of how much was drawn of the tile.
        """
        if pixbuf is None:
            if self.mapwin.controller.Debug:
                print("Can't draw_tile_at_position: no pixbuf for",
                      x, y, "offset", x_off, y_off)
            return

        if x < 0:
            x_off += -x
            x = 0
        if y < 0:
            y_off += -y
            y = 0

        if self.mapwin.controller.Debug >= 2:
            print("draw_tile_at_position", x, y, x_off, y_off)

        w = pixbuf.get_width() - x_off
        h = pixbuf.get_height() - y_off

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
        if self.mapwin.controller.Debug > 1:
            mapwin.set_color(mapwin.grid_color)
            mapwin.draw_rectangle(0, x, y, w, h)
            mapwin.draw_line(x, y, x + w, y + h)
            mapwin.set_bg_color()

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
            if self.mapwin.controller.Debug:
                print("Scheduling full redraw rather than drawing single tile")
            self.mapwin.schedule_redraw()
            return

        # Calculate x, y, x_offset, y_offset from the tile name.
        # Make sure it's even still visible.
        # Tile name is /path/to/zoom/x/y.ext
        try:
            head, tileynum = os.path.split(path)
            tileynum = os.path.splitext(tileynum)[0]
            head, tilexnum = os.path.split(head)
            head, tilezoom = os.path.split(head)
            tileynum = int(tileynum)
            tilexnum = int(tilexnum)
        except ValueError:
            print("Bad tile filename", path)
            return

        (center_tile_xnum, center_tile_ynum,
         tile_offset_x, tile_offset_y,
         tiles_left, tiles_right, tiles_up, tiles_down) = \
             self.find_tile_window_geometry(mapwin)

        try:
            pixbuf = MapWindow.load_image_from_file(path)

        except Exception as e:
            # This used to look for glib.GError, but I don't know what
            # errors the GTK3 load_image_from_file might raise.
            print("Error loading image from file", e)
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
                if self.mapwin.controller.Debug:
                    print("RENAMING", path)

            self.num_failed_downloads += 1
            return

        except Exception as e:
            print("Error drawing tile:", e)
            self.num_failed_downloads += 1
            return

        # Calculate the X and Y coordinates of the tile in the map window.
        if tilexnum == 0:
            mapx = 0
            x_off = tile_offset_x
        else:
            mapx = tilexnum * self.img_width - tile_offset_x
            x_off = 0
        if tileynum == 0:
            mapy = 0
            y_off = tile_offset_y
        else:
            mapy = tileynum * self.img_height - tile_offset_y
            y_off = 0
        if self.mapwin.controller.Debug:
            print("Drawing single tile at", mapx, mapy, x_off, y_off)
        self.draw_tile_at_position(pixbuf, mapwin, mapx, mapy, x_off, y_off)

    def queue_download(self, url, path):
        """Add a URL to the FuturesSession downloader queue,
           and keep a record of what file path it should use.
        """
        if self.mapwin.controller.Debug:
            print("queue_download", url, path)
        now = time.time()
        if self.num_failed_downloads > self.MAX_FAILED_DOWNLOADS:
            if self.last_failed_download_time \
               and now - self.last_failed_download_time \
                    < self.RETRY_DOWNLOADS_AFTER:
                # too many failed downloads, too recently
                if self.mapwin.controller.Debug:
                    print("Too many failed downloads, skipping", url)
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
        if self.mapwin.controller.Debug:
            print("Appending", url, "to download queue")
        self.urls_queued.append(url)

        self.downloader.get(url)

    def response_hook(self, response, *args, **kwargs):
        """When the FuturesSession completes downloading a tile,
           draw it on the map when possible.
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
                print("Yikes, downloaded a URL not in the queue:",
                      response.url)

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
                GLib.idle_add(self.mapwin.draw_map)
            # elif self.mapwin.controller.Debug:
            #     print("downloaded", tilepath, "but still tiles to download")
        else:
            if self.mapwin.controller.Debug > 1:
                print("Schedule drawing of single tile", tilepath)
            GLib.idle_add(self.draw_single_tile, tilepath, self.mapwin)
