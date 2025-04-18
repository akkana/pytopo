# Copyright (C) 2009-2025 by Akkana Peck.
# You are free to use, share or modify this program under
# the terms of the GPLv2 or, at your option, any later GPL.

"""MapWindow: pytopo's GTK-based window for showing tiled maps.
"""

from __future__ import print_function

import gi
gi.require_version('Gtk', '3.0')
gi.require_version('Gdk', '3.0')
gi.require_version('PangoCairo', '1.0')
from gi.repository import Gtk
from gi.repository import Gdk
from gi.repository import GLib
from gi.repository import Gio
from gi.repository import GObject
from gi.repository import GdkPixbuf
from gi.repository import Pango, PangoCairo

from pytopo import MapUtils
from pytopo.TrackPoints import TrackPoints, NULL_WP_NAME
from . import trackstats

try:
    from shapely.geometry import Point
    from shapely.geometry.polygon import Polygon
except ModuleNotFoundError:
    pass

import os, sys
import re

try:
    # Python 3:
    from urllib.request import urlretrieve
except ImportError:
    # Python 2:
    from urllib import urlretrieve

import math
from collections import OrderedDict

import importlib.resources

from enum import Enum

# As of GTK3 there's no longer any HSV support, because cairo is
# solely RGB. Use colorsys instead.
import colorsys

import traceback

GPS_MARKER_RADIUS=10

# Track colorization styles
class TrackColor(Enum):
    SEPARATE_COLORS  = 1
    SPEED_COLORS     = 2
    ELEVATION_COLORS = 3


def is_color(color):
    try:
        return len(color) == 3
    except:
        return False


def colorize_by_value(val):
    """val is a float between 0 and 1.
       Return a color (a triplet of floats between 0 and 1)
       from a smooth gradient between blue (low) and red (high).
    """
    return (val, 0., 1. - val)


class MapWindow(object):

    """The pytopo UI: the map window.

This holds the GTK specific drawing code,
and is intended to be extensible into other widget libraries.
To that end, it needs to implement the following methods
that are expected by the MapCollection classes:

   win_width, win_height = get_size(), set_color(),
   draw_pixbuf(pixbuf, x_off, y_off, x, y, w, h)
   draw_rectangle(fill, x, y, width, height)
   draw_line(x, y, width, height)

(That list is very incomplete and needs to be updated, sorry.
No one has ever actually tried to adapt this code for a different toolkit,
but if you want to, contact me and I'll help you figure it out.)
    """

    TRACK_COLOR_VIEW_MENU = OrderedDict([
        ("Each track a different color", TrackColor.SEPARATE_COLORS),
        ("By Elevation", TrackColor.ELEVATION_COLORS),
        ("By Speed", TrackColor.SPEED_COLORS)
    ])

    def __init__(self, _controller):
        """Initialize variables, but don't create the window yet."""

        # Save a reference to the PyTopo object that created this window.
        # We'll need it to change locations, collections etc.
        self.controller = _controller

        # Default title, can be changed later.
        self.title = "PyTopo "

        # The current map collection being used:
        self.collection = None

        # Any overlaid collections.
        self.overlays = []

        self.center_lon = None
        self.center_lat = None
        self.cur_lon = None
        self.cur_lat = None
        self.trackpoints = None
        self.show_waypoints = True
        self.show_labels = True
        self.drawing_track = False
        self.selected_track = None
        self.selected_waypoint = None

        # By default, each track is a different colors
        self.track_colorize = TrackColor.SEPARATE_COLORS

        # No redraws initially scheduled
        self.redraw_scheduled = False

        self.path_distance = 0

        self.win_width = 0
        self.win_height = 0

        self.prompt_dialog = None
        self.traildialog = None

        # Following a GPS device? Not until one is set.
        self.gps_poller = None
        self.last_gpsd = None
        self.gps_centered = True

        # Try to find the pytopo.pin image.
        try:
            # str() is the only way I can find to turn a Path into a string
            # without making it absolute
            pinpath = str(importlib.resources.files('pytopo').joinpath(
                'resources/pytopo-pin.png'))

            self.pin = GdkPixbuf.Pixbuf.new_from_file(pinpath)
        except:
            if self.controller.Debug:
                print("Couldn't initialize the pin image")
            self.pin = None

        self.markerpath = str(
            importlib.resources.files('pytopo').joinpath(
                'resources/blue-marker.svg'))
        self.marker_svg_bytes = None

        self.pin_lon = 0
        self.pin_lat = 0
        self.pin_xoff = -4
        self.pin_yoff = -12

        # Print distances in metric?
        # This should be set externally!
        self.use_metric = False

        # Where to save generated maps. The default is fine for most people.
        # Which is a good thing since there's currently no way to change it.
        self.map_save_dir = os.path.expanduser("~/Topo/")

        # X/Gtk graphics variables we need:
        self.drawing_area = 0
        # GTK2: X GC
        self.xgc = None
        # GTK3: all drawing is done through a Cairo context, cr.
        self.cr = None

        self.click_last_long = 0
        self.click_last_lat = 0

        # Context menus don't seem to have any way of passing the location
        # initially clicked. So save x and y on right mouse down.
        self.context_x = None
        self.context_y = None

        # Flags that affect how we handle mouse events:
        # Are we in the middle of dragging the map?
        self.is_dragging = False

        # Are we making a rubber-band selection?
        # If so, is_rubberbanding may be set to a list or tuple:
        # (function to call, arguments ...)
        # indicating what to do when the rubberbanding is finished,
        # e.g. (save_GPX, outfile)
        self.is_rubberbanding = False
        # These are used to draw the rubberbanding box:
        self.x_last_drag = None
        self.y_last_drag = None

        # The timeout for long press events
        self.press_timeout = None

        self.black_color = (0., 0., 0.)
        self.white_color = (1., 1., 1.)
        self.yellow_color = (1., 1., 0.)
        self.red_color = (1., 0., 0.)
        self.blue_color = (0., 0., 1.)
        self.bg_scale_color = (1., 1., 1., .3)
        self.grid_color = (.45, .45, .45)
        self.first_track_color = (.9, 0., 1.)

        # waypoint_color is the color for waypoint *labels*.
        # We'll try to give the actual waypoints the color of their track file.
        self.waypoint_color = self.yellow_color
        self.waypoint_color_bg = self.black_color

        self.font_desc = Pango.FontDescription("Sans 9")
        self.bold_font_desc = Pango.FontDescription("Sans Bold 9")
        self.wpt_font_desc = Pango.FontDescription("Sans Italic 10")
        self.attr_font_desc = Pango.FontDescription("Sans Bold Italic 12")
        self.select_font_desc = Pango.FontDescription("Sans Bold 15")

        # For running on tablets/touchscreens
        # (not sure why GTK2 can't figure this out on its own)
        # I'm not sure how to do this in GTK3;
        # crossing fingers and hoping GTK3 is more sensible
        # so it doesn't need this.
        # settings = Gtk.settings_get_default()
        # settings.set_property("Gtk-touchscreen-mode", True)

        # Some defaults that hopefully will never be used
        self.zoom_btn_size = 25
        self.zoom_X1 = 8
        self.zoom_in_Y1 = 10
        self.zoom_out_Y1 = self.zoom_in_Y1 + self.zoom_btn_size * 2

        # Polygon drawing:
        self.polygon_opacity = .15
        self.polygon_colors = OrderedDict()

        # Text overlays with positions: currently only used for polygons.
        self.text_overlays = []

        # Remember the last folder used in GTK file chooser dialogs,
        # separately for reading and saving.
        self.file_read_folder = None
        self.file_save_folder = None

    def add_title(self, moretitle):
        self.title = "%s %s" % (self.title, os.path.basename(moretitle))

    def add_overlay(self, overlay, opacity=.4):
        overlay.opacity = opacity
        self.overlays.append(overlay)

    def show_window(self, init_width, init_height):
        """Create the initial window."""
        win = Gtk.Window()
        win.set_name(self.title)
        win.set_title(self.title)
        win.connect("destroy", self.graceful_exit)
        win.set_border_width(5)

        vbox = Gtk.VBox(spacing=3)
        win.add(vbox)

        self.drawing_area = Gtk.DrawingArea()
        # There doesn't seem to be any way to resize a window below
        # the initial size of the drawing area. So make the drawing area
        # initially tiny, then just before showing we'll resize the window.
        # self.drawing_area.size(10, 10)
        # In gtk3 the argumesn are widget, expand, fill, padding
        vbox.pack_start(self.drawing_area, True, True, 0)

        self.drawing_area.set_events(Gdk.EventMask.EXPOSURE_MASK |
                                     Gdk.EventMask.SCROLL_MASK |
                                     # Gdk.EventMask.POINTER_MOTION_MASK |
                                     Gdk.EventMask.BUTTON1_MOTION_MASK |
                                     Gdk.EventMask.POINTER_MOTION_HINT_MASK |
                                     Gdk.EventMask.BUTTON_PRESS_MASK |
                                     Gdk.EventMask.BUTTON_RELEASE_MASK)

        self.drawing_area.connect('draw', self.draw_handler)

        self.drawing_area.connect("button-press-event",   self.mousepress)
        self.drawing_area.connect("button-release-event", self.mouserelease)
        self.drawing_area.connect("scroll-event",         self.scroll_event)
        self.drawing_area.connect("motion_notify_event",  self.drag_event)
        # The default focus in/out handlers on drawing area cause
        # spurious expose events.  Trap the focus events, to block that:
        self.drawing_area.connect("focus-in-event", self.nop)
        self.drawing_area.connect("focus-out-event", self.nop)

        # Handle key presses on the drawing area.
        self.drawing_area.set_property('can-focus', True)
        self.drawing_area.connect("key-press-event", self.key_press_event)

        # Resize the window now to the desired initial size:
        win.resize(init_width, init_height)

        win.show_all()

        # So the downloader can use threads:
        if self.gps_poller:
            GObject.threads_init()

        Gtk.main()

    def force_redraw(self):
        if not self.drawing_area:
            return
        self.drawing_area.queue_draw()

    def gpsd_callback(self, gpsd):
        """Update the map given the GPS location"""
        # gpsd.fix.mode is 1 if no fix, 2 for a 2d fix, 3 for a 3d fix.
        # mentioned in passing on http://www.catb.org/gpsd/client-howto.html
        if gpsd and gpsd.fix.mode > 1:
            self.last_gpsd = gpsd
            GLib.idle_add(self.update_position_from_GPS)

    def update_position_from_GPS(self):
        """If gpsd is running, move the map to center the new GPS location."""
        if not self.last_gpsd:
            print("No last_gpsd")    # shouldn't get here
            return

        if self.gps_centered:
            self.center_lon = self.last_gpsd.fix.longitude
            self.center_lat = self.last_gpsd.fix.latitude
            self.cur_lon = self.center_lon
            self.cur_lat = self.center_lat

        self.force_redraw()

    #
    # Draw maplets to fill the window, centered at center_lon, center_lat
    #
    def draw_map(self):
        """Redraw the map, centered at center_lon, center_lat."""

        # If waiting for GPS, don't draw anything yet:

        if self.collection is None:
            print("No collection!")
            return
        if not self.drawing_area:
            # Not initialized yet, not ready to draw a map
            if self.controller.Debug:
                print("draw_map called before drawing_area is initialized")
            return

        self.cr = self.drawing_area.get_window().cairo_create()

        self.win_width, self.win_height = \
            self.drawing_area.get_window().get_geometry()[2:4]
        if self.controller.Debug:
            print("window size is", self.win_width, self.win_height)

        # If we're in follow GPS mode and don't yet have center lat, lon,
        # display a message:
        if self.gps_poller and not self.last_gpsd:
            self.draw_label("Waiting for GPS fix ...", 10, self.win_height/2,
                            color=self.black_color, dropshadow=False)
            return

        if self.controller.Debug:
            print("\n\n>>>>>>>>>>>>>>>>")
            print("window draw_map centered at", end=' ')
            print(self.center_lon, end=' ')
            print(self.center_lat)

        self.collection.draw_map(self.center_lon, self.center_lat, self)
        if self.controller.Debug and self.overlays:
            print("drawing overlay collections")
        for ov in self.overlays:
            ov.draw_map(self.center_lon, self.center_lat, self)

        if not self.is_dragging:
            self.draw_overlays()

        # Is there a selected track?
        def draw_selected_label(name, labelstring, x, y):
            tracklabel = labelstring + name
            self.draw_label(tracklabel, x, y)

        if self.selected_track is not None:
            halfwin = 0
            beta = 2
            metric = False
            stats = trackstats.statistics(self.trackpoints,
                                          halfwin, beta, metric,
                                          startpt=self.selected_track,
                                          onetrack=True)

            climb_units = 'm' if metric else "'"
            dist_units = 'km' if metric else 'mi'
            label = "Track: " + self.trackpoints.points[self.selected_track]
            if stats:
                label += "\n%.1f %s" % (stats['Total distance'], dist_units)
                if 'Smoothed total climb' in stats and \
                   stats['Smoothed total climb']:
                    label += "\nClimb: %d%s" % (stats['Smoothed total climb'],
                                                climb_units)
                # If numpy isn't installed, we won't have smoothed climb,
                # but still have Raw total climb. But that's so
                # crazily inaccurate it's not even worth showing.

                # High and low points.
                if 'High' in stats:
                    label += '\nHigh: %d%s' % (stats['High'], climb_units)
                if 'Low' in stats:
                    label += '  Low: %d%s' % (stats['Low'], climb_units)

            trackfilename = self.trackpoints.filename_for_index(
                self.selected_track)
            if trackfilename:
                label += '\n(' + trackfilename + ')'
            self.draw_label(label, -15, 15, self.yellow_color,
                            dropshadow=True)

        if self.selected_waypoint is not None and self.show_waypoints:
            self.draw_label("Waypoint: " +
                      self.trackpoints.waypoints[self.selected_waypoint].name,
                            15, 40, color=self.yellow_color)

        # Copyright info or other attribution
        self.set_color(self.grid_color)
        self.collection.draw_attribution(self)

        # draw pin
        pin_x, pin_y = self.coords2xy(self.pin_lon, self.pin_lat,
                                      self.win_width, self.win_height)

        if self.pin:
            self.draw_pixbuf(self.pin, 0, 0, pin_x + self.pin_xoff,
                             pin_y + self.pin_yoff, -1, -1)

        # draw GPS location
        if self.last_gpsd and self.last_gpsd.fix:
            gps_x, gps_y = self.coords2xy(self.last_gpsd.fix.longitude,
                                          self.last_gpsd.fix.latitude,
                                          self.win_width, self.win_height)

            self.draw_circle(True, gps_x, gps_y, GPS_MARKER_RADIUS,
                             self.blue_color)
            # self.draw_pixbuf(self.gps_marker, 0, 0,
            #                  pin_x + self.gps_marker_xoff,
            #                  pin_y + self.gps_marker_yoff,
            #                  -1, -1)

        self.draw_map_scale()

        # Most of the time it's better to keep self.cr unset,
        # so it will be created when necessary.
        self.cr = None

        self.redraw_scheduled = False

    def schedule_redraw(self):
        """Schedule a redraw after a short timeout,
           for when multiple tiles have been downloaded.
           Only keep one scheduled.
        """
        if self.redraw_scheduled:
            return
        self.redraw_scheduled = True
        GLib.timeout_add(1000, self.force_redraw)

    def contrasting_color(self, color):
        """Takes a color triplet (values between 0 and 1)
           and converts it to a similar saturation and value but different hue
        """
        if not color:
            return self.first_track_color

        h, s, v = colorsys.rgb_to_hsv(*color[:3])

        # Hue is a floating point between 0 and 1. How much should we jump?
        jump = .17

        newcolor = colorsys.hsv_to_rgb(h + jump, s, v)
        if len(color) == 3:
            return newcolor
        return (*newcolor, color[3])

    def draw_trackpoint_segment(self, start, linecolor, linewidth=2,
                                linestyle=None):
        """Draw a trackpoint segment, starting at the given index.
           Stop drawing if we reach another start string, and return the index
           of that string. Return None if we reach the end of the list.
        """
        if self.track_colorize == TrackColor.SEPARATE_COLORS and \
           is_color(linecolor):
            self.cr.set_source_rgb (*linecolor)
        elif self.track_colorize == TrackColor.SPEED_COLORS or\
             self.track_colorize == TrackColor.ELEVATION_COLORS:
            linewidth *= 2

        cur_x = None
        cur_y = None
        i = start
        if self.trackpoints.is_start(self.trackpoints.points[i]):
            # This should be true
            i += 1

        while True:
            if i >= len(self.trackpoints.points):
                return None
            pt = self.trackpoints.points[i]
            if self.trackpoints.is_start(pt):
                return i
            i += 1

            # Skip over dictionaries of attributes
            if self.trackpoints.is_attributes(pt):
                continue

            # If specified, colorize according to speed or altitude:
            try:
                if self.track_colorize == TrackColor.SPEED_COLORS:
                    speedfrac = float(pt.speed) / self.trackpoints.max_speed
                    linecolor = colorize_by_value(speedfrac)
                    self.cr.set_source_rgb (*linecolor)

                elif (self.track_colorize == TrackColor.ELEVATION_COLORS and
                      self.trackpoints.min_ele and self.trackpoints.max_ele):
                    elefrac = ((pt.ele - self.trackpoints.min_ele) /
                               (self.trackpoints.max_ele
                                - self.trackpoints.min_ele))
                    linecolor = colorize_by_value(elefrac)
                    # print("(ele)", int(elefrac * 100),
                    #       ": Setting color to (%.2f, %.2f, %.2f)"
                    #       % linecolor)
                    self.cr.set_source_rgb (*linecolor)

            except Exception as e:
                # print("can't set color:", e)
                pass

            x = int((pt.lon - self.center_lon) * self.collection.xscale
                    + self.win_width / 2)
            y = int((self.center_lat - pt.lat) * self.collection.yscale
                    + self.win_height / 2)

            # Call draw_line whether or not the point is visible;
            # even with one or both endpoints off screen, some of
            # the line might be visible.
            if cur_x and cur_y and x and y:
                self.draw_line(cur_x, cur_y, x, y, linewidth=linewidth)
            cur_x = x
            cur_y = y

    def select_track(self, trackindex):
        """Mark a track as active."""
        if self.controller.Debug:
            # Test against None specifically, else we won't be able
            # to select the first track starting at index 0.
            if trackindex is not None:
                print("Selecting track starting at", trackindex)
            else:
                print("De-selecting track")
        self.selected_track = trackindex

        if not trackindex:
            return

        # Does the selected track have attributes? If so, pop up a dialog.
        attrs = self.trackpoints.attributes(trackindex)
        if not attrs:
            return

        # Pop up a dialog showing attributes.
        attrstr = '\n'.join(["%s: %s" % (key, attrs[key]) for key in attrs])
        self.show_traildialog(attrstr)

    def show_traildialog(self, attrstr):
        """Show a dialog giving information about a selected track."""
        trailname = self.trackpoints.points[self.selected_track]
        if not self.traildialog:
            self.traildialog = Gtk.Dialog(trailname,
                                          None, 0,
                                          (Gtk.STOCK_CLOSE,
                                           Gtk.ResponseType.CANCEL))
            self.traildialog.set_size_request(400, 300)

            sw = Gtk.ScrolledWindow()
            sw.set_shadow_type(Gtk.SHADOW_ETCHED_IN)
            sw.set_policy(Gtk.PolicyType.AUTOMATIC, Gtk.PolicyType.AUTOMATIC)

            textview = Gtk.TextView()
            self.attributes_textbuffer = textview.get_buffer()
            sw.add(textview)
            sw.show()
            textview.show()
            self.traildialog.vbox.pack_start(sw, True, True, 0)
            self.traildialog.connect("response", self.hide_traildialog)

        else:
            self.traildialog.set_title(trailname)

        self.attributes_textbuffer.set_text("== %s ==\n%s" % (trailname,
                                                              attrstr))

        self.traildialog.show_all()

    def hide_traildialog(self, d, responseid=None):
        """Hide the track dialog"""
        d.hide()

    def draw_trackpoints(self):
        """Draw any trackpoints that are currently visible."""
        if not self.trackpoints:
            return

        # Now draw any trackpoints or waypoints that are visible.
        self.track_color = None

        # Store the colors we use for each named track segment,
        # so we can try to use that color for the matching waypoints.
        # But waypoints that come on their own, unassociated with a track,
        # get their own colors too.
        track_colors = {}
        wpcolor = None

        if len(self.trackpoints.points) > 0:
            cur_x = None
            cur_y = None

            nextpt = 0
            while True:
                self.track_color = self.contrasting_color(self.track_color)
                track_colors[self.trackpoints.points[nextpt]] = self.track_color
                nextpt = self.draw_trackpoint_segment(nextpt, self.track_color)
                if not nextpt:
                    break

        if self.selected_track is not None:  # None vs. trackpoint 0
            self.draw_trackpoint_segment(self.selected_track,
                                         self.red_color, linewidth=6)

        if self.show_waypoints and len(self.trackpoints.waypoints) > 0:
            for pt in self.trackpoints.waypoints:
                if self.trackpoints.is_start(pt) or \
                   self.trackpoints.is_attributes(pt):
                    if pt in track_colors:
                        wpcolor = track_colors[pt]
                    elif type(pt) is str:
                        if wpcolor:
                            wpcolor = self.contrasting_color(wpcolor)
                        else:
                            wpcolor = self.contrasting_color(self.track_color)
                    continue
                x = int((pt.lon - self.center_lon) * self.collection.xscale
                        + self.win_width / 2)
                y = int((self.center_lat - pt.lat) * self.collection.yscale
                        + self.win_height / 2)

                if x >= 0 and x < self.win_width and \
                   y >= 0 and y < self.win_height:
                    self.draw_marker(0, 0,
                                     x - 8, y - 21,
                                     # x + self.pin_xoff, y + self.pin_yoff,
                                     color=wpcolor)
                    if self.show_labels and \
                       pt.name.strip() and pt.name != NULL_WP_NAME:
                        self.draw_label(pt.name, x, y,
                                        color=self.waypoint_color,
                                        dropshadow=True,
                                        font=self.font_desc,
                                        offsets=(1, 1))


    def find_nearest_trackpoint(self, x, y):
        """Find the indeces of the nearest track,
           the nearest point on that track,
           and the nearest waypoint (if any) to a given x, y point.
           Called on mouse click.
           Any of the three can be None if nothing is sufficiently close.
           Coords x, y passed in are screen coordinates;
           if None, we'll assume exact center, as if we've already
           set center_lat and center_lon after a mouse click.
           Also check to see whether the click is inside any known polygons.

           @return: (nearest_track,      Starting point of the nearest track
                     nearest_point,      Index of nearest point on that track
                     nearest_waypoint,   Nearest waypoint
                     enclosing_polygons) Polygons containing the point, if any
        """
        nearest_track = None
        nearest_point = None
        nearest_waypoint = None
        enclosing_polygons = None

        halfwidth, halfheight = \
            [s / 2 for s in self.drawing_area.get_window().get_geometry()[2:4]]
        if x is None:
            x = halfwidth
        if y is None:
            y = halfheight
        CLOSE = 7    # pixels

        if not self.trackpoints:
            return None, None, None, None

        def closer_dist(pt, sm_dist, lastpt=None):
            """Return distance from pt to x, y --
               but only if it's smaller than sm_dist.
            """
            tx, ty = self.coords2xy(pt.lon, pt.lat,
                                    self.win_width, self.win_height)

            # if abs(x - tx) > CLOSE or abs(y - ty) > CLOSE:
            #     return None

            dist = math.sqrt((x - tx)**2 + (y - ty)**2)
            if dist < sm_dist:
                return dist

            # # Okay, it's not that close to a point. How about to a
            # # line between the point and the last point?
            # if lastpt and self.trackpoints.is_start(lastpt) and \
            #    not self.trackpoints.is_attributes(lastpt):
            #     ltx, lty = self.coords2xy(lastpt.lon, lastpt.lat,
            #                               self.win_width, self.win_height)
            #     m = float(y-lty) / float(x-ltx)
            #     y1 = m * x + lty  # Predicted position

            return None

        # Find closest waypoint
        if self.trackpoints.waypoints:
            smallest_dist = CLOSE * 8
            lastpt = None
            for i, pt in enumerate(self.trackpoints.waypoints):
                if self.trackpoints.is_start(pt) or \
                   self.trackpoints.is_attributes(pt):
                    lastpt = None
                    continue
                d = closer_dist(pt, smallest_dist, lastpt)
                if d:
                    smallest_dist = d
                    nearest_waypoint = i
                lastpt = pt

        # Find closest track and index of the closest point on the track
        if len(self.trackpoints.points) > 0:
            smallest_dist = CLOSE * 8
            for i, pt in enumerate(self.trackpoints.points):
                if self.trackpoints.is_start(pt):
                    track_start = i
                    lastx = None
                    lasty = None
                    continue

                if self.trackpoints.is_attributes(pt):
                    continue

                d = closer_dist(pt, smallest_dist)
                if d:
                    smallest_dist = d
                    nearest_point = i
                    nearest_track = track_start

        # Is the point inside a polygon?
        # This requires shapely.
        if self.trackpoints.polygons:
            if "shapely" not in sys.modules:
                print("Can't ID regions without the shapely module")
                return (nearest_track, nearest_point, nearest_waypoint,
                        enclosing_polygons)
            enclosing_polygons = []
        for poly in self.trackpoints.polygons:
            wincoords = [ self.coords2xy(*pair,
                                         self.win_width, self.win_height)
                          for pair in poly["coordinates"] ]
            point = Point(x, y)
            polygon = Polygon(wincoords)
            if polygon.contains(point):
                if "name" in poly:
                    polystring = "%s (%s)" % (poly["name"], poly["class"])
                else:
                    polystring = poly["class"]

                # Can't just call draw_label here, because
                # the whole map is about to be redrawn.
                # So the labels need to be persistent.
                self.text_overlays.append((polystring,
                                           *self.xy2coords(x, y)))
                enclosing_polygons.append(polystring)

        return (nearest_track, nearest_point, nearest_waypoint,
                enclosing_polygons)

    def draw_overlays(self):
        """Draw overlays: tile attribution, zoom control, scale,
           plus any visible trackpoints and waypoints.
        """
        # draw_overlays is sometimes called from outside draw_map,
        # so make sure there's a cairo context:
        if not self.cr:
            self.cr = self.drawing_area.get_window().cairo_create()
        self.collection.draw_attribution(self)
        self.draw_zoom_control()
        self.draw_map_scale()
        self.draw_trackpoints()

        # The rest is drawing trackpoints and polygons.
        if not self.trackpoints:
            return
        if not self.trackpoints.polygons:
            return

        def is_in_bounds(map_bounds, poly_bounds):
            """Is any part of the polygon visible on the current map?
               Order is minlon, maxlon, minlat, maxlat.
            """
            if poly_bounds[1] < map_bounds[0]:
                return False
            if poly_bounds[3] < map_bounds[2]:
                return False
            if poly_bounds[0] > map_bounds[1]:
                return False
            if poly_bounds[2] > map_bounds[3]:
                return False
            return True

        map_bounds = self.map_bounds()

        # Text overlays likely came from clicking on a region.
        # They only get cleared if the region disappears off the screen,
        # or on zoom.
        new_overlays = []
        for t_o in self.text_overlays:
            if is_in_bounds((t_o[1], t_o[1], t_o[2], t_o[2]), map_bounds):
                self.draw_label(t_o[0], *self.coords2xy(t_o[1], t_o[2]),
                                font=self.bold_font_desc)
                new_overlays.append(t_o)
        self.text_overlays = new_overlays

        for poly in self.trackpoints.polygons:
            # Is it visible on the current map?
            if not is_in_bounds(poly["bounds"], map_bounds):
                continue

            try:
                polyclass = poly["class"]
            except:
                polyclass = "other"
            try:
                color = self.polygon_colors[polyclass]
            except KeyError:
                # No color yet for this polyclass. Take the last color
                # added and make a contrasting color for it,
                # adding a transparency member.
                if self.polygon_colors:
                    # Take the color of the last polygon class added,
                    # get a contrasting color and assign that to the
                    # new polygon class
                    last_key = next(reversed(self.polygon_colors))
                    self.polygon_colors[polyclass] = \
                        self.contrasting_color(self.polygon_colors[last_key])
                else:
                    self.polygon_colors[polyclass] = \
                        list(self.first_track_color) + [self.polygon_opacity]
            self.cr.set_source_rgba(*self.polygon_colors[polyclass])
            for coords in poly["coordinates"]:
                pt = self.coords2xy(coords[0], coords[1],
                                    self.win_width, self.win_height)
                self.cr.line_to(*pt)
            self.cr.close_path()
            self.cr.fill()

    def draw_map_scale(self):
        """Draw a map scale at the bottom of the map window.
        """
        ###################################################################
        #
        # The draw_map_scale function calculates and draws a map scale
        # at the bottom of the map window created by the PyTopo
        # mapping application. Distances are calculated along the
        # surface of the geoid defined by the earth equitorial radius,
        # Req, and the square of the eccentricity of the earth, esq.
        #
        # The map scale is accurate only for the center latitude of
        # the map. The circumference of the earth at the equator is
        # 24901 miles (an upper limit on map size). USGS quadrangles
        # use NAD-27, but WGS-84 is the most recent datum, and GPS
        # uses WGS-84.
        #
        # References:
        #    http://en.wikipedia.org/wiki/Geodetic_system
        #    http://www.gmat.unsw.edu.au/snap/gps/clynch_pdfs/radiigeo.pdf
        #
        # Scale algorithm Copyright (C) 2013 Spencer A. Buckner
        #
        ###################################################################

        # Define constants
        # Req = 6.3781370e+06   # WGS-84 earth equatorial radius (meters)
        # esq = 6.694380e-03    # WGS-84 square of eccentricity of earth
        Req = 6.3782064e+06   # NAD-27 earth equatorial radius (meters)
        esq = 6.768658e-03    # NAD-27 square of eccentricity of earth

        # Calculate pixels per mile and pixels per kilometer at map center
        lat_deg = self.center_lat
        lat_rad = lat_deg * math.pi / 180
        sin_lat = math.sin(lat_rad)
        sin_lat_sq = sin_lat * sin_lat
        cos_lat = math.cos(lat_rad)
        R_meters = Req/math.sqrt(1 - esq*sin_lat_sq)             # earth radius (m)
        R_miles = R_meters/(0.0254*12*5280)                      # earth radius (miles)
        R_km = R_meters/1000	                                 # earth radius (km)
        xscale_deg = self.collection.xscale                      # pixels per degree
        xscale_mi = xscale_deg*360/(2*math.pi*R_miles*cos_lat)   # pixels per mile
        xscale_km = xscale_deg*360/(2*math.pi*R_km*cos_lat)      # pixels per km

        ##################################################

        # Calculate window width in miles and kilometers
        width_mi = self.win_width / xscale_mi   # (miles)
        width_km = self.win_width / xscale_km   # (kilometers)

        # Calculate length of map-scale bars in pixels;
        # length (pixels) <= self.win_width/2.
        log_width = math.log10(width_mi / 2)
        power_10 = math.floor(log_width)
        fraction = log_width - power_10
        log10_1 = 0
        log10_2 = math.log10(2)
        log10_5 = math.log10(5)
        log10_10 = 1
        if log10_1 <= fraction and fraction < log10_2:
            length = 1 * math.pow(10, power_10)   # (miles or kilometers)
            nticks = 6
        elif log10_2 <= fraction and fraction < log10_5:
            length = 2 * math.pow(10, power_10)   # (miles or kilometers)
            nticks = 5
        elif log10_5 <= fraction and fraction < log10_10:
            length = 5 * math.pow(10, power_10)   # (miles or kilometers)
            nticks = 6

        length_mi = xscale_mi * length   # (pixels)
        length_km = xscale_km * length   # (pixels)
        label_mi = "%g mi" % length
        label_km = "%g km" % length

        ##################################################
        # Get label lengths in pixels
        layout = self.drawing_area.create_pango_layout(label_mi)
        layout.set_font_description(self.font_desc)
        str_width_mi, str_height_mi = layout.get_pixel_size()

        layout = self.drawing_area.create_pango_layout(label_km)
        layout.set_font_description(self.font_desc)
        str_width_km, str_height_km = layout.get_pixel_size()

        box_width = max(length_mi, length_km) + \
                    max(str_width_mi, str_width_km) * 3
        box_height = max(str_height_mi, str_height_km) * 3.3
        x_center = self.win_width / 2

        # Draw a background box to contain the map scales
        boxtop = int(self.win_height - box_height)
        self.draw_rectangle(True,
                            int(x_center - box_width/2), boxtop,
                            box_width, box_height,
                            self.bg_scale_color)

        def draw_scale_bar(y, barlength, nticks, label, textwidth, textheight):
            HALFTIC = 3
            TEXTPAD = 10
            x0 = x_center - barlength/2
            self.draw_line(x0, y, x0 + barlength, y, color=self.black_color)

            # Draw ticks
            for i in range(nticks):
                x1 = x0 + int(i * barlength / (nticks - 1) + 0.5)
                self.draw_line(x1, y - HALFTIC, x1, y + HALFTIC)

            # Draw map-scale labels
            self.draw_string_scale(x0 - TEXTPAD - textwidth/4,
                                   y - textheight/2, "0")
            self.draw_string_scale(x1 + TEXTPAD, y - textheight/2, label)

        draw_scale_bar(boxtop + str_height_mi, length_mi, nticks,
                       label_mi, str_width_mi, str_height_mi)
        draw_scale_bar(self.win_height - str_height_km, length_km, nticks,
                       label_km, str_width_km, str_height_km)

    def draw_zoom_control(self):
        """Draw some large zoom controls in case we're running on a tablet
           or phone and have no keyboard to zoom or move around.
        """
        self.zoom_btn_size = int(self.win_width / 25)
        self.zoom_X1 = 8
        self.zoom_in_Y1 = 10
        self.zoom_out_Y1 = self.zoom_in_Y1 + self.zoom_btn_size * 2

        textoffset = self.zoom_btn_size / 5

        self.set_color(self.grid_color)

        # Draw the boxes
        self.draw_rectangle(False, self.zoom_X1, self.zoom_in_Y1,
                            self.zoom_btn_size, self.zoom_btn_size,
                            color=self.grid_color)
        self.draw_rectangle(False, self.zoom_X1, self.zoom_out_Y1,
                            self.zoom_btn_size, self.zoom_btn_size,
                            color=self.grid_color)

        midpointx = self.zoom_X1 + self.zoom_btn_size / 2
        # Draw the -
        midpointy = self.zoom_out_Y1 + self.zoom_btn_size / 2
        self.draw_line(self.zoom_X1 + textoffset, midpointy,
                       self.zoom_X1 + self.zoom_btn_size - textoffset,
                       midpointy)

        # Draw the +
        midpointy = self.zoom_in_Y1 + self.zoom_btn_size / 2
        self.draw_line(self.zoom_X1 + textoffset, midpointy,
                       self.zoom_X1 + self.zoom_btn_size - textoffset,
                       midpointy)
        self.draw_line(midpointx, self.zoom_in_Y1 + textoffset,
                       midpointx,
                       self.zoom_in_Y1 + self.zoom_btn_size - textoffset)

    def was_click_in_zoom(self, x, y):
        """Do the coordinates fall within the zoom in or out buttons?
        """
        if x < self.zoom_X1 or x > self.zoom_X1 + self.zoom_btn_size:
            return 0
        if y < self.zoom_in_Y1 or y > self.zoom_out_Y1 + self.zoom_btn_size:
            return 0
        if y < self.zoom_in_Y1 + self.zoom_btn_size:
            return 1
        if y > self.zoom_out_Y1:
            return -1
        # Must be between buttons
        return 0

    def was_click_in_gps(self, event_x, event_y):
        """Was the click over the blue GPS circle? True or False.
        """
        if not self.last_gpsd or not self.last_gpsd.fix:
            return False
        gps_x, gps_y = self.coords2xy(self.last_gpsd.fix.longitude,
                                      self.last_gpsd.fix.latitude,
                                      self.win_width, self.win_height)
        return (abs(event_x - gps_x) < GPS_MARKER_RADIUS and
                abs(event_y - gps_y) < GPS_MARKER_RADIUS)

    def print_location(self, widget=None):
        print()
        print("%30s  (decimal degrees, use for saved.sites)" % \
            MapUtils.coord2str_dd(self.cur_lon, self.cur_lat))

        print("%-15s   %-15s (D M S)" % \
            (MapUtils.dec_deg2dms_str(self.cur_lon),
             MapUtils.dec_deg2dms_str(self.cur_lat)))

        print("%-15s   %-15s (DD.MMMM)" % \
            (MapUtils.dec_deg2deg_min(self.cur_lon),
             MapUtils.dec_deg2deg_min(self.cur_lat)))

    def zoom_to(self, zoomlevel):
        if self.cur_lon:
            self.center_lon = self.cur_lon
        else:
            self.cur_lon = self.center_lon
        if self.cur_lat:
            self.center_lat = self.cur_lat
        else:
            self.cur_lat = self.center_lat

        self.collection.zoom_to(zoomlevel)
        for ov in self.overlays:
            ov.zoom_to(zoomlevel)

        self.text_overlays = []
        self.force_redraw()

    def zoom(self, widget=None, amount=1):
        """Zoom the map by the given amount: positive to zoom in, negative out.
           Be sure to pass amount as a named argument, amount=X
           otherwise it will be taken as the (unused) widget argument.
        """
        self.zoom_to(self.collection.zoomlevel + amount)

    def scroll_event(self, button, event):
        """Zoom in or out in response to mousewheel events."""
        if event.direction != Gdk.ScrollDirection.UP and \
           event.direction != Gdk.ScrollDirection.DOWN:
            return False

        if event.direction == Gdk.ScrollDirection.UP:
            zoom_amount = 1
        else:
            zoom_amount = -1

        # Save off the coordinates currently under the mouse,
        # so we can arrange for it to be under the mouse again after zoom.
        curmouselon, curmouselat = self.xy2coords(event.x, event.y)

        # self.zoom needs current location to be set
        self.cur_lon, self.cur_lat = curmouselon, curmouselat

        self.zoom(amount=zoom_amount)
        if self.controller.Debug and hasattr(self.collection, 'zoomlevel'):
            print("zoomed to", self.collection.zoomlevel)

        # What are the coordinates for the current mouse pos after zoom?
        newmouselon, newmouselat = self.xy2coords(event.x, event.y)

        # Shift the map over so the old point will be under the mouse.
        self.center_lon += (curmouselon - newmouselon)
        self.center_lat += (curmouselat - newmouselat)

        self.text_overlays = []

        self.force_redraw()
        return True

    def toggle_track_drawing(self, mode):
        """Toggle whether tracks are drawn."""
        if self.drawing_track:
            self.force_redraw()

        else:
            if not self.trackpoints:
                self.trackpoints = TrackPoints()

            self.trackpoints.points.append("New track")

        self.drawing_track = not self.drawing_track

    def context_menu(self, event):
        """Create a context menu. This is called anew on every right-click."""

        SEPARATOR = "---"

        # Labels for toggles, which change depending on whether
        # the toggle is currently set:
        if self.show_waypoints:
            show_waypoint_label = "Hide waypoints"
        else:
            show_waypoint_label = "Show waypoints"
        if self.show_labels:
            show_labels_label = "Hide labels"
        else:
            show_labels_label = "Show labels"
        if self.drawing_track:
            draw_track_label = "Finish drawing track"
        else:
            draw_track_label = "Draw a new track"

        contextmenu = OrderedDict([
            (MapUtils.coord2str_dd(self.cur_lon, self.cur_lat),
             self.print_location),
            ("Open track file...", self.prompt_for_track_file),
            ("My Locations...", self.mylocations),
            ("My Tracks...", self.mytracks),

            ("Pins", SEPARATOR),
            ("Go to pin...", self.set_center_to_pin),
            ("Pin this location", self.set_pin_by_mouse),
            ("Save pin location...", self.save_location),

            ("Track Editing", SEPARATOR),
            ("Add waypoint...", self.add_waypoint_by_mouse),
            ("Edit/Remove waypoint", self.edit_waypoint),
            ("Split track here", self.split_track_by_mouse),
            ("Remove points before this", self.remove_before_mouse),
            ("Remove points after this", self.remove_after_mouse),
            ("Remove point from track", self.remove_trackpoint),
            ("Undo", self.undo),
            ("Save GPX or GeoJSON...", self.save_all_tracks_as),

            ("View", SEPARATOR),
            ("Zoom here...", self.zoom),
            (draw_track_label, self.toggle_track_drawing),
            (show_waypoint_label, self.toggle_show_waypoints),
            (show_labels_label, self.toggle_show_labels),
            ("Colorize tracks", None),

            ("Rest", SEPARATOR),
            ("Download Area...", self.download_area),
            ("Change background map", self.change_collection),
            ("Quit", self.graceful_exit)
        ])

        menu = Gtk.Menu()
        for itemname in list(contextmenu.keys()):
            if contextmenu[itemname] == SEPARATOR:
                item = Gtk.SeparatorMenuItem()
                menu.append(item)
                item.show()
                continue

            item = Gtk.MenuItem(itemname)

            # Change background map gives a submenu of available collections.
            if itemname == "Change background map":
                submenu = Gtk.Menu()
                for coll in self.controller.collections:
                    subitem = Gtk.MenuItem(coll.name)
                    subitem.connect("activate", self.change_collection,
                                    coll.name)
                    submenu.append(subitem)
                    subitem.show()

                item.set_submenu(submenu)

            elif itemname == "Colorize tracks":
                submenu = Gtk.Menu()
                for name in self.TRACK_COLOR_VIEW_MENU:
                    subitem = Gtk.MenuItem(name)
                    subitem.connect("activate", self.change_track_colorize,
                                    self.TRACK_COLOR_VIEW_MENU[name])
                    submenu.append(subitem)
                    subitem.show()

                item.set_submenu(submenu)

            elif contextmenu[itemname]:
                item.connect("activate", contextmenu[itemname])

            # Would be nice to make the menu item not selectable,
            # but this greys it out and makes it hard to read.
            # else:
            #     item.set_sensitive(False)

            menu.append(item)
            item.show()

        if event:
            button = event.button
            t = event.time
        else:
            button = 3
            t = 0
            # There's no documentation on what event.time is: it's
            # "the time of the event in milliseconds" -- but since when?
            # Not since the epoch.
        menu.popup(None, None, None, None, button, t)

    def change_track_colorize(self, widget, whichcolorize):
        self.track_colorize = whichcolorize
        self.force_redraw()

    def change_collection(self, widget, name):
        if self.collection:
            savezoom = self.collection.zoomlevel
        newcoll = self.controller.find_collection(name)
        if newcoll.maxzoom and newcoll.maxzoom < savezoom:
            savezoom = newcoll.maxzoom
        if newcoll:
            self.collection = newcoll
            self.collection.Debug = self.controller.Debug
            self.zoom_to(savezoom)
            # self.force_redraw()
        else:
            print("Couldn't find a collection named '%s'" % name)

    def toggle_show_waypoints(self, widget):
        """Toggle whether waypoints are shown."""
        self.show_waypoints = not self.show_waypoints
        self.force_redraw()

    def toggle_show_labels(self, widget):
        """Toggle whether labels on waypoints are shown."""
        self.show_labels = not self.show_labels
        self.force_redraw()

    def mylocations(self, widget):
        """Show the location_select dialog"""
        self.selection_window()

    def selection_window(self):
        """Show a window that lets the user choose a known starting point.
           Returns True if the user chose a valid site, otherwise False.
        """
        dialog = Gtk.Dialog("Choose a starting point",
                            transient_for=None, flags=0)
        dialog.add_buttons(Gtk.STOCK_CLOSE, Gtk.ResponseType.CANCEL,
                           Gtk.STOCK_OK, Gtk.ResponseType.OK)

        # dialog.connect('destroy', lambda win: Gtk.main_quit())
        # Wouldn't it be nice if GTK dialogs would automatically
        # size to their contents? Sigh. Without this, the dialog
        # is wide enough for the text box but includes none of the
        # site list in the scrolled window below it.
        dialog.set_size_request(600, 400)

        sw = Gtk.ScrolledWindow()
        sw.set_shadow_type(Gtk.ShadowType.ETCHED_IN)
        sw.set_policy(Gtk.PolicyType.AUTOMATIC, Gtk.PolicyType.AUTOMATIC)

        svbox = Gtk.VBox(spacing=10)

        hbox = Gtk.HBox(spacing=6)
        svbox.pack_start(hbox, False, True, 0)

        hbox.pack_start(Gtk.Label(label="Coordinates:"), False, True, 0)

        # An entry to enter specific coordinates
        coord_entry = Gtk.Entry()
        coord_entry.set_width_chars(45)
        coord_entry.set_activates_default(True)
        hbox.pack_start(coord_entry, False, True, 0)
        dialog.coord_entry = coord_entry

        # make OK button the default, so Enter in the entry will trigger OK
        okButton = dialog.get_widget_for_response(
            response_id=Gtk.ResponseType.OK)
        okButton.set_can_default(True)
        okButton.grab_default()

        # List store will hold name, collection-name and site object
        store = Gtk.ListStore(str, str, object)

        # Create the list
        for site in self.controller.KnownSites:
            if len(site) > 3:
                coll = site[3]
            else:
                coll = ''
            store.append([site[0], coll, site])

        # http://pyGtk.org/pyGtk2tutorial/ch-TreeViewWidget.html
        # Make a treeview from the list:
        treeview = Gtk.TreeView(model=store)

        renderer = Gtk.CellRendererText()
        column = Gtk.TreeViewColumn("Location", renderer, text=0)
        # column.pack_start(renderer, True, True, True, 0)
        # column.set_resizable(True)
        treeview.append_column(column)
        renderer = Gtk.CellRendererText()
        column = Gtk.TreeViewColumn("Collection", renderer, text=1)
        # column.pack_start(renderer, False, True, 0)
        treeview.append_column(column)

        # store.set_sort_column_id(0, Gtk.SORT_ASCENDING)

        # Catch middle-mouse pastes over the treeview
        treeview.connect("button-release-event", self.accept_paste)

        sw.set_policy(Gtk.PolicyType.AUTOMATIC, Gtk.PolicyType.AUTOMATIC)
        svbox.pack_start(treeview, True, True, 0)
        # sw.add(treeview)

        sw.add(svbox)

        def submit(self, value, widget):
            # Tell the dialog to give an OK response
            dialog.response(Gtk.ResponseType.OK)

        treeview.connect("row-activated", submit)
        # treeview.connect("key-pressed", submit)

        dialog.vbox.pack_start(sw, True, True, 0)

        dialog.show_all()

        while True:
            response = dialog.run()
            if response == Gtk.ResponseType.OK:
                coordtext = coord_entry.get_text()
                if coordtext:
                    try:
                        lat, lon = MapUtils.parse_full_coords(
                            coord_entry.get_text())
                        self.controller.use_coordinates(lat, lon, self)
                    except Exception as e:
                        print("Oops", e)
                        continue
                    dialog.destroy()
                    return True

                selection = treeview.get_selection()
                model, it = selection.get_selected()
                if it:
                    # locname = store.get_value(it, 0)
                    # collname = store.get_value(it, 1)
                    site = store.get_value(it, 2)
                    self.controller.use_site(site, self)
                    dialog.destroy()
                    return True
            else:
                dialog.destroy()
                return False


    def accept_paste(self, widget, event):
        """Handle middlemouse pastes over the site selection dialog.
           Ideally this would actually submit the dialog and open up
           the MapWindow.
        """
        if event.button != 2:
            return False

        dialog = widget.get_toplevel()

        # clipboard = Gtk.Clipboard.get(Gdk.SELECTION_CLIPBOARD)
        selection = Gtk.Clipboard.get(Gdk.SELECTION_PRIMARY)
        coordstr = selection.wait_for_text()

        dialog.coord_entry.set_text(coordstr)

        '''
        # Now that the dialog's entry is filled, the goal is to
        # submit the dialog. But I haven't found any way to do that.
        # Sending a fake enter key event from the entry doesn't do it,
        # nor does sending a button press event on the dialog's OK button.
        # Better would be to send the "clicked" signal to the button,
        # but there doesn't seem to be a way to manually generate signals.
        print("Trying to send event ...")

        event = Gdk.Event(Gdk.EventType.KEY_PRESS)
        event.window = dialog.coord_entry.get_window()
        display = Gdk.Display().get_default()
        keymap = Gdk.Keymap().get_for_display(display)
        key = keymap.get_entries_for_keyval(Gdk.KEY_Return)
        event.hardware_keycode = key[1][0].keycode
        event.send_event = True
        event = Gdk.Event(Gdk.EventType.KEY_RELEASE)
        dialog.coord_entry.emit('key-release-event', event)

        ok_button = dialog.get_widget_for_response(
            response_id=Gtk.ResponseType.OK)
        event = Gdk.Event(Gdk.EventType.BUTTON_PRESS)
        event.window = dialog.get_window()
        event.button = 1
        event.send_event = True
        ok_button.emit('button-press-event', event)
        event = Gdk.Event(Gdk.EventType.BUTTON_RELEASE)
        event.window = dialog.get_window()
        event.button = 1
        event.send_event = True
        ok_button.emit('button-release-event', event)
        '''

        return True


    @staticmethod
    def ignorecasefilter(filter_info, data):
        """A GTK GtkFileFilter function that filters for
           a given set of extensions IGNORING CASE,
           which GTK, incredibly, does not offer in Gtk.FileFilter.
           The closest to documentation I could find is at
           http://www.manpagez.com/html/pyGtk/pyGtk-2.22.0/class-Gtkfilefilter.php#method-Gtkfilefilter--add-custom

           Arguments:
           data is a list of LOWERCASE file extensions,
               e.g. [".jpg", ".png"].
               Pass it in as the third argument of filter.add_custom.
           filter_info is a Gtk.FileFilterInfo object passed by the
               FileFilter -- not the 4-tuple described on the manpagez link.
               It has four parts, typically
                   filter_info.filename      full pathname of the file
                   filter_info.url           None
                   filter_info.display_name  basename of the file
                   filter_info.mime_type
               I don't know when url and mime_type might get set;
               they never have been in my tests.
        """
        for file_ext in data:
            if filter_info.display_name.lower().endswith(file_ext):
                return True
        return False

    def prompt_for_track_file(self, widget):
        dialog = Gtk.FileChooserDialog(title="Open track file",
                               action=Gtk.FileChooserAction.SAVE,
                               buttons=(Gtk.STOCK_CANCEL,
                                        Gtk.ResponseType.CANCEL,
                                        Gtk.STOCK_SAVE,
                                        Gtk.ResponseType.OK))
        if self.file_read_folder:
            dialog.set_current_folder(self.file_read_folder)

        filt = Gtk.FileFilter()
        filt.set_name("GPX, KML/KMX or GeoJSON Files")
        filt.add_custom(Gtk.FileFilterFlags.FILENAME,
                        MapWindow.ignorecasefilter,
                        [".gpx", ".json", ".geojson", ".kml", ".kmz"])
        dialog.add_filter(filt)

        response = dialog.run()

        if response != Gtk.ResponseType.OK:
                dialog.destroy()
                return

        self.file_read_folder = dialog.get_current_folder()
        infile = dialog.get_filename()
        self.trackpoints.read_track_file(infile)

        dialog.destroy()

    def save_all_tracks_as(self, widget):
        """Prompt for a filename to save all tracks and waypoints."""
        return self.save_tracks_as(widget, False)

    def save_tracks_as(self, widget, select_area=False):
        """Prompt for a filename to save all tracks and waypoints,
           then save all tracks we know about.
           (select_area was supposed to let the user drag out an area
           with the mouse, but it doesn't currently work
           and isn't called from anywhere.)
        """
        dialog = Gtk.FileChooserDialog(title="Save GPX",
                                       action=Gtk.FileChooserAction.SAVE,
                                       buttons=(Gtk.STOCK_CANCEL,
                                                Gtk.ResponseType.CANCEL,
                                                Gtk.STOCK_SAVE,
                                                Gtk.ResponseType.OK))

        if self.file_save_folder:
            dialog.set_current_folder(self.file_save_folder)

        filt = Gtk.FileFilter()
        filt.set_name("GPX/GeoJSON Files")
        filt.add_custom(Gtk.FileFilterFlags.FILENAME,
                        MapWindow.ignorecasefilter,
                        [".gpx", ".json", ".geojson"])
        dialog.add_filter(filt)

        while True:
            response = dialog.run()

            if response != Gtk.ResponseType.OK:
                dialog.destroy()
                return

            outfile = dialog.get_filename()
            self.file_save_folder = dialog.get_current_folder()
            if os.path.exists(outfile):
                d = Gtk.MessageDialog(None,
                                      Gtk.DialogFlags.MODAL,
                                      Gtk.MessageType.QUESTION,
                                      Gtk.ButtonsType.YES_NO,
                                      "File exists. Overwrite?")
                d.set_default_response(Gtk.ResponseType.YES)

                response = d.run()
                d.destroy()

                if response != Gtk.ResponseType.YES:
                    continue
                else:
                    break
            else:
                break

        # At this point we have a filename, and either it's unique
        # or we've confirmed overwriting.
        # Now save all our tracks and waypoints as a GPX file in outfile.
        dialog.destroy()
        if self.controller.Debug:
            print("Saving tracks/waypoints to", outfile)

        if select_area:
            self.draw_label("Drag out the area you want to save...", 150, 50)
            self.is_rubberbanding = (self.trackpoints.save_GPX_in_region,
                                     outfile)
            return

        try:
            loutfile = outfile.lower()
            if loutfile.endswith(".gpx"):
                self.trackpoints.save_GPX(outfile)
            elif loutfile.endswith("json"):
                self.trackpoints.save_geojson(outfile)
            else:
                print("Unknown format to save:", outfile, file=sys.stderr)
        except Exception as e:
            print("Couldn't save to", outfile, ":", e)
            print(traceback.format_exc())

    def undo(self, widget=None):
        """Undo the last change to trackpoints: for instance,
           splitting a track or deleting early or late points.
        """
        self.trackpoints.undo()
        self.force_redraw()

    def remove_before_mouse(self, widget):
        """Remove any points before the current mouse position."""
        self.mod_track_by_mouse(remove = -1)

    def remove_after_mouse(self, widget):
        """Remove any points after the current mouse position."""
        self.mod_track_by_mouse(remove = 1)

    def split_track_by_mouse(self, widget):
        """Split a track at the current mouse position."""
        self.mod_track_by_mouse(remove = 0)

    def mod_track_by_mouse(self, remove=0):
        """Split or modify a track at the current mouse location.
           If remove is negative, remove all points in the current track
           before the current one. If positive, remove all points after.
           If remove is zero, split the track into two tracks.
        """

        self.force_redraw()
        near_track, near_point, near_waypoint, polygons = \
            self.find_nearest_trackpoint(self.context_x, self.context_y)

        if near_point is not None:
            if remove > 0:
                # Remove all points after:
                self.trackpoints.remove_after(near_point)
            elif remove < 0:
                # Remove all points before:
                self.trackpoints.remove_before(near_point)
            else:
                # Split the track. Make a name for the new track segment:
                trackname = self.trackpoints.points[near_track]
                match = re.search(r'(.*) (\d+)$', trackname)
                if match:
                    trackname = "%s %d" % (match.group(1), int(match.group(2)) + 1)
                else:
                    trackname += " 2"

                # Split the track there
                self.trackpoints.points.insert(near_point, trackname)

        self.force_redraw()

    def remove_trackpoint(self, widget):
        """Remove the point nearest the mouse from its track."""

        near_track, near_point, near_waypoint, polygons = \
            self.find_nearest_trackpoint(self.context_x, self.context_y)

        if near_point is None:
            print("There's no trackpoint near the mouse")
            return

        # Nuttiness: even if you know the index, apparently the only
        # way to remove something from a list is to search through the
        # list for an exact item match.
        self.trackpoints.points.remove(self.trackpoints.points[near_point])
        self.force_redraw()

    def show_message(self, msg):
        """Show a message only briefly.
           It will disappear as soon as the map is moved or zoomed.
        """
        self.draw_label(msg, 10, self.win_height/2,
                        color=self.black_color, dropshadow=False)

    def edit_waypoint(self, widget):
        """Remove the point nearest the mouse from its track."""

        near_track, near_point, near_waypoint, polygons = \
            self.find_nearest_trackpoint(self.context_x, self.context_y)

        if near_waypoint is None:
            # XXX This label and X are getting overwritten
            # by maplets, even before any move or zoom.
            # Looks like we'll need to store current-message and current-point.

            self.show_message("There's no waypoint near the mouse")

            # Draw an X at the mouse-click spot.
            exsize = 7
            self.draw_line(self.context_x - exsize, self.context_y - exsize,
                           self.context_x + exsize, self.context_y + exsize)
            self.draw_line(self.context_x - exsize, self.context_y + exsize,
                           self.context_x + exsize, self.context_y -exsize)
            return

        newname, delete = self.prompt(
            "Edit or Delete Waypoint",
            name=self.trackpoints.waypoints[near_waypoint].name,
            show_delete=True)

        # Nuttiness: even if you know the index, apparently the only
        # way to remove something from a list is to search through the
        # list for an exact item match.
        if delete:
            self.trackpoints.waypoints.remove(
                self.trackpoints.waypoints[near_waypoint])
        else:
            self.trackpoints.waypoints[near_waypoint].name = newname
        self.force_redraw()

    def add_waypoint_by_mouse(self, widget):
        """Set a new waypoint at the current mouse location"""
        # Prompt for a name for the waypoint
        wpname = self.prompt("New waypoint", name="*")
        if wpname == None:
            return
        if wpname:
            wpname = wpname.strip()
        else:
            wpname = "WP"

        if not self.trackpoints:
            self.trackpoints = TrackPoints()

        # XXX Might want to add a start string to the waypoint list to
        # differentiate this point from previous points that might
        # have been read in from GPX files.

        self.trackpoints.handle_track_point(self.cur_lat, self.cur_lon,
                                            waypoint_name=wpname)
        self.force_redraw()

    def set_pin_by_mouse(self, widget):
        """Set the pin at the current mouse location"""
        self.pin_lon, self.pin_lat = self.cur_lon, self.cur_lat
        self.force_redraw()

    def set_center_to_pin(self, widget):
        """Set the center at the current pin point"""
        self.center_lon, self.center_lat = self.pin_lon, self.pin_lat
        self.force_redraw()

    def prompt(self, prompt, comment="", name="", show_delete=False):
        """Prompt the user for a string, returning the string.
           Returns None if the user presses CANCEL instead
           (as opposed to an empty string, which means the
           user didn't type anything but hit OK).
           If show_delete is True, also show a Delete toggle button,
           and return a tuple where the second item is the state of the button.
        """
        if not self.prompt_dialog:
            self.prompt_dialog = Gtk.Dialog("PyTopo: %s" % prompt, None, 0,
                                            (Gtk.STOCK_CANCEL,
                                               Gtk.ResponseType.CANCEL,
                                             Gtk.STOCK_OK,
                                               Gtk.ResponseType.OK))
            self.prompt_dialog.set_size_request(200, 150)
            self.prompt_dialog.vbox.set_spacing(10)

            self.prompt_dialog_prompt = Gtk.Label(prompt)
            self.prompt_dialog.vbox.pack_start(self.prompt_dialog_prompt,
                                               False, True, 0)

            self.prompt_dialog_del_btn = Gtk.ToggleButton("Delete")
            self.prompt_dialog.vbox.pack_start(self.prompt_dialog_del_btn,
                                               False, True, 0)

            self.prompt_dialog_text = Gtk.Entry()
            self.prompt_dialog_text.set_activates_default(True)
            self.prompt_dialog.vbox.pack_start(self.prompt_dialog_text,
                                               True, True, 0)

            self.prompt_dialog_comment = Gtk.Label("")
            self.prompt_dialog.vbox.pack_start(self.prompt_dialog_comment,
                                               False, True, 0)

            self.prompt_dialog.show_all()

        else:
            self.prompt_dialog_comment.set_text(comment)
            self.prompt_dialog_prompt.set_text(prompt)

        self.prompt_dialog_del_btn.set_active(False)

        if show_delete:
            self.prompt_dialog_del_btn.show()
        else:
            self.prompt_dialog_del_btn.hide()

        self.prompt_dialog.set_default_response(Gtk.ResponseType.OK)
        self.prompt_dialog_text.set_text(name)
        if name:
            self.prompt_dialog_text.select_region(0, len(name))
        self.prompt_dialog_text.grab_focus()
        self.prompt_dialog.show()

        response = self.prompt_dialog.run()
        if response == Gtk.ResponseType.OK:
            self.prompt_dialog.hide()
            retval = self.prompt_dialog_text.get_text()
        else:
            self.prompt_dialog.hide()
            retval = None

        if show_delete:
            return retval, self.prompt_dialog_del_btn.get_active()
        else:
            return retval

    def save_location(self, widget):
        """Save the pinned location.
        """
        comment = ""
        while True:
            name = self.prompt("Save location", comment)
            # name was empty; repeat the prompt dialog
            if name == None:
                return
            name = name.strip()

            # If there was a name, break out of the loop and
            # add the point to Known Sites.
            if name:
                break

            # name was empty; repeat the prompt dialog
            comment = "Name can't be empty"

        # Add to KnownSites
        self.controller.append_known_site([name, self.pin_lon, self.pin_lat,
                                           self.collection.name,
                                           self.collection.zoomlevel])

        self.controller.save_sites()

    def mytracks(self, widget):
        """Try to center the loaded trackpoints in the window
           and show the map.
        """
        self.controller.track_select(self)
        if self.trackpoints is not None:
            self.trackpoints_center()
        self.force_redraw()

    def trackpoints_center(self):
        """Try to center the loaded trackpoints in the window"""
        minlon, minlat, maxlon, maxlat = self.trackpoints.get_bounds()
        self.center_lon = (maxlon + minlon) / 2
        self.center_lat = (maxlat + minlat) / 2
        self.cur_lon = self.center_lon
        self.cur_lat = self.center_lat

    def cancel_download(self, widget, data=None):
        """Cancel any pending downloads."""
        self.cancelled = True

    def download_area(self, widget):
        """Download tiles covering an area. Not well supported
           and can get your client blacklisted.
        """
        if not self.collection.zoomlevel:
            print("Can't download an area for this collection")
            return

        # Get default values for area and zoom levels:
        minlon, maxlon, minlat, maxlat = self.map_bounds()
        minzoom = self.collection.zoomlevel
        maxzoom = self.collection.zoomlevel + 4

        # Prompt the user for any adjustments to area and zoom:
        dialog = Gtk.Dialog("Download an area", None, 0,
                            (Gtk.STOCK_REFRESH, Gtk.ResponseType.APPLY,
                             Gtk.STOCK_CANCEL, Gtk.ResponseType.CANCEL,
                             Gtk.STOCK_OK, Gtk.ResponseType.OK))
        # dialog.set_size_request(200, 150)
        # dialog.vbox.set_spacing(10)
        frame = Gtk.Frame()
        frame.label = "Current zoom = %d" % self.collection.zoomlevel
        dialog.vbox.pack_start(frame, True, True, 0)

        table = Gtk.Table(4, 3, False)
        table.set_border_width(5)
        table.set_row_spacings(5)
        table.set_col_spacings(10)
        frame.add(table)

        label = Gtk.Label("Min longitude:")
        label.set_justify(Gtk.Justification.RIGHT)
        table.attach(label, 0, 1, 0, 1,
                     Gtk.AttachOptions.SHRINK, 0, 0, 0)
        minlon_entry = Gtk.Entry()
        table.attach(minlon_entry, 1, 2, 0, 1,
                     Gtk.AttachOptions.EXPAND | Gtk.AttachOptions.FILL, 0, 0, 0)

        label = Gtk.Label("Max longitude:")
        label.set_justify(Gtk.Justification.RIGHT)
        table.attach(label, 2, 3, 0, 1,
                     Gtk.AttachOptions.SHRINK, 0, 0, 0)
        maxlon_entry = Gtk.Entry()
        table.attach(maxlon_entry, 3, 4, 0, 1,
                     Gtk.AttachOptions.EXPAND | Gtk.AttachOptions.FILL, 0, 0, 0)

        label = Gtk.Label("Min latitude:")
        label.set_justify(Gtk.Justification.RIGHT)
        table.attach(label, 0, 1, 1, 2,
                     Gtk.AttachOptions.SHRINK, 0, 0, 0)
        minlat_entry = Gtk.Entry()
        table.attach(minlat_entry, 1, 2, 1, 2,
                     Gtk.AttachOptions.EXPAND | Gtk.AttachOptions.FILL, 0, 0, 0)

        label = Gtk.Label("Max latitude:")
        label.set_justify(Gtk.Justification.RIGHT)
        table.attach(label, 2, 3, 1, 2,
                     Gtk.AttachOptions.SHRINK, 0, 0, 0)
        maxlat_entry = Gtk.Entry()
        table.attach(maxlat_entry, 3, 4, 1, 2,
                     Gtk.AttachOptions.EXPAND | Gtk.AttachOptions.FILL, 0, 0, 0)

        label = Gtk.Label("Min zoom:")
        label.set_justify(Gtk.Justification.RIGHT)
        table.attach(label, 0, 1, 2, 3,
                     Gtk.AttachOptions.SHRINK, 0, 0, 0)
        minzoom_entry = Gtk.Entry()
        table.attach(minzoom_entry, 1, 2, 2, 3,
                     Gtk.AttachOptions.EXPAND | Gtk.AttachOptions.FILL, 0, 0, 0)

        label = Gtk.Label("Max zoom:")
        label.set_justify(Gtk.Justification.RIGHT)
        table.attach(label, 2, 3, 2, 3,
                     Gtk.AttachOptions.SHRINK, 0, 0, 0)
        maxzoom_entry = Gtk.Entry()
        table.attach(maxzoom_entry, 3, 4, 2, 3,
                     Gtk.AttachOptions.EXPAND | Gtk.AttachOptions.FILL, 0, 0, 0)

        err_label = Gtk.Label("")
        dialog.vbox.pack_start(err_label, True, True, 0)

        progress_label = Gtk.Label("")
        dialog.vbox.pack_start(progress_label, True, True, 0)

        def flush_events():
            while Gtk.events_pending():
                Gtk.main_iteration()

        def reset_download_dialog():
            minlon_entry.set_text(str(minlon))
            maxlon_entry.set_text(str(maxlon))
            minlat_entry.set_text(str(minlat))
            maxlat_entry.set_text(str(maxlat))
            minzoom_entry.set_text(str(minzoom))
            maxzoom_entry.set_text(str(maxzoom))

        reset_download_dialog()

        dialog.show_all()

        self.cancelled = False

        while True:
            response = dialog.run()
            if response == Gtk.ResponseType.CANCEL:
                dialog.destroy()
                return True
            if response == Gtk.ResponseType.APPLY:
                reset_download_dialog()
                continue
            # Else the response must have been OK.
            # So connect the cancel button to cancel_download(),
            # which means first we have to find the cancel button:
            # Starting with PyGTK 2.22 we can use this easier method:
            # cancelBtn = dialog.get_widget_for_response(Gtk.ResponseType.OK)
            # but for now:
            buttons = dialog.get_action_area().get_children()
            for b in buttons:
                if b.get_label() == 'Gtk-cancel':
                    b.connect("clicked", self.cancel_download, str)
                    break

            try:
                minlon = float(minlon_entry.get_text().strip())
                maxlon = float(maxlon_entry.get_text().strip())
                minlat = float(minlat_entry.get_text().strip())
                maxlat = float(maxlat_entry.get_text().strip())
                minzoom = int(minzoom_entry.get_text().strip())
                maxzoom = int(maxzoom_entry.get_text().strip())
                break

            except ValueError:
                err_label.set_text("Sorry, can't parse one of the values")
                continue

        if self.controller.Debug:
            print("Downloading from %f - %f, %f - %f, zoom %d - %d" \
                % (minlon, maxlon, minlat, maxlat, minzoom, maxzoom))
        for zoom in range(minzoom, maxzoom + 1):
            err_label.set_text("Downloading zoom level %d" % zoom)

            # Show a busy cursor on the dialog:
            busy_cursor = Gdk.Cursor(Gdk.CursorType.WATCH)
            dialog.get_window().set_cursor(busy_cursor)
            flush_events()
            Gdk.flush()

            if self.controller.Debug:
                print("==== Zoom level", zoom)

            # Find the start and end tiles
            (minxtile, minytile, x_off, y_off) = \
                self.collection.deg2num(maxlat, minlon, zoom)
            (maxxtile, maxytile, x_off, y_off) = \
                self.collection.deg2num(minlat, maxlon, zoom)
            if self.controller.Debug:
                print("X tiles from", minxtile, "to", maxxtile)
                print("Y tiles from", minytile, "to", maxytile)

            pathlist = []
            for ytile in range(minytile, maxytile + 1):
                for xtile in range(minxtile, maxxtile + 1):
                    if self.controller.Debug:
                        print("Tile", xtile, ytile, end=' ')
                    filename = os.path.join(self.collection.location,
                                            str(zoom),
                                            str(xtile),
                                            str(ytile)) \
                        + self.collection.ext
                    if os.access(filename, os.R_OK):
                        if self.controller.Debug:
                            print(filename, "is already there")
                        continue
                    pathlist.append(filename)
                    if self.controller.Debug:
                        print("appended as", filename)

            numtiles = len(pathlist)
            err_label.set_text("Zoom level %d: %d tiles" % (zoom, numtiles))
            flush_events()
            num_downloaded = 0

            for filename in pathlist:
                if self.cancelled:
                    dialog.destroy()
                    return True

                url = self.collection.url_from_path(filename, zoom)

                # XXX Parallelize this!
                if self.controller.Debug:
                    print("Downloading", url, "to", filename)
                thedir = os.path.dirname(filename)
                if not os.access(thedir, os.W_OK):
                    os.makedirs(thedir)
                # err_label.set_text("%d %%: %d of %d" % \
                #                   (int(num_downloaded*100 / numtiles),
                #                    num_downloaded, numtiles))
                if self.controller.Debug:
                    print("%d %%: %d of %d" % \
                        (int(num_downloaded * 100 / numtiles),
                         num_downloaded, numtiles))
                progress_label.set_text("%d: %s" % (num_downloaded, url))
                flush_events()
                urlretrieve(url, filename)
                num_downloaded += 1

                # XXX should show progress more graphically.

        dialog.destroy()
        return True

    #
    # Drawing-related routines:
    #

    def get_size(self):
        """Return the width and height of the canvas."""
        return self.drawing_area.get_window().get_geometry()[2:4]

    def set_bg_color(self):
        """Change to the normal background color (usually black)."""
        # self.xgc.set_rgb_fg_color(self.bg_color)
        # self.xgc.foreground = self.xgc.background
        self.set_color(self.black_color)

    def set_color(self, color):
        """Change the foreground color, e.g. for drawing text."""
        # self.xgc.set_rgb_fg_color(color)
        self.cr.set_source_rgb(*color)

    def draw_pixbuf(self, pixbuf, x_off, y_off, x, y, w=0, h=0, opacity=1.):
        """Draw the pixbuf at the given position and size,
           starting at the specified offset.
           If width and height are provided, assume the offset
           has already been subtracted.
        """
        # When this is called from draw_map, self.cr should already be set.
        # In most other cases, it isn't and needs to be created.
        if not self.cr:
            self.cr = self.drawing_area.get_window().cairo_create()
            # XXX Theoretically would be good to limit the region to
            # just the rect being drawn. But apparently self.cr.clip()
            # expects that a region has already been set somehow,
            # like by calling self.cr.rectangle(); and calling clip()
            # after that makes painting fail when updating single tiles
            # if they need to be downloaded at startup.

        if w <= 0:
            w = pixbuf.get_width() - x_off
        if h <= 0:
            h = pixbuf.get_height() - y_off

        xo = x - x_off
        yo = y - y_off

        # GTK3 way: seems to be almost completely undocumented.
        # The last two args of cairo_set_source_pixbuf are the point
        # on the canvas matching the (0, 0) point of the pixmap.
        # The coordinates have to be in pixels.
        Gdk.cairo_set_source_pixbuf(self.cr, pixbuf, xo, yo)

        # But then things get weird. Apparently, for fill(), the
        # rectangle's coordinates should be in pixels, as you might expect:
        # if opacity == 1:
        #     self.cr.rectangle(x, y, w, h)
        #     self.cr.fill()
        #
        # But for paint() and paint_with_alpha(), they need to be
        # normalized to a width and height of 1.
        # This may be what the cairo documentation refers to as
        # "user-space coordinates", but I can't find any place
        # they actually explain that term.
        # If you use w, h without dividing by the window size,
        # the maplet is still painted but you'll see black borders
        # around each tile when panning the map.

        # paint*() doesn't need rectangle() first,
        # they transfer the whole source region.
        self.cr.paint_with_alpha(opacity)

    def draw_marker(self, x_off, y_off, x, y, opacity=1., color=None):
        if not self.marker_svg_bytes:
            with open(self.markerpath, 'rb') as ifp:
                self.marker_svg_bytes = ifp.read()
        if color:
            if type(color) is bytes:
                iconbytes = self.marker_svg_bytes.replace(b'blue', color)
            elif type(color) is str:
                iconbytes = self.marker_svg_bytes.replace(b'blue',
                                                          color.encode())
            # is it an RGB triple, like a list or tuple?
            elif hasattr(color, "__getitem__"):
                iconbytes = self.marker_svg_bytes.replace(
                    # *255 rather than 256 in the next line
                    # to restrict it to 00-ff.
                    b'blue', b'#%02x%02x%02x' % tuple([ int(c*255)
                                                        for c in color ]))
            else:
                print("Internal error: ignoring unknown color type",
                      type(color), file=sys.stderr)

        else:
            iconbytes = self.marker_svg_bytes

        # pixbuf = GdkPixbuf.Pixbuf.new_from_bytes(
        #     GLib.Bytes.new(iconbytes),
        #     GdkPixbuf.Colorspace.RGB, True, 8, 20, 20, 0)

        # Pixbuf.new_from_bytes returns NULL, whereas converting
        # the bytes into a stream works. Sigh.
        pixbuf = GdkPixbuf.Pixbuf.new_from_stream(
            Gio.MemoryInputStream.new_from_bytes(
                GLib.Bytes.new(iconbytes)))

        self.draw_pixbuf(pixbuf, x_off, y_off, x, y, 16, 16, opacity)

    def draw_rect_between(self, fill, x1, y1, x2, y2, color=None):
        """Draw a rectangle. between two sets of ordinates,
           which are not necessarily in UL, LR order.
        """
        minx = min(x1, x2)
        miny = min(y1, y2)
        maxx = max(x1, x2)
        maxy = max(y1, y2)
        self.draw_rectangle(fill, x, y, w, h, color)

    def draw_rectangle(self, fill, x, y, w, h, color=None):
        """Draw a rectangle."""
        if color:
            if len(color) > 3:
                self.cr.set_source_rgba(*color)
            else:
                self.cr.set_source_rgb(*color)

        # cr.rectangle tends to die with "TypeError: a float is required"
        self.cr.rectangle(float(x), float(y), float(w), float(h))

        if fill:
            self.cr.fill()
        else:
            self.cr.stroke()

    def draw_line(self, x, y, x2, y2, color=None, linewidth=None):
        """Draw a line."""
        # print("draw_line", x, y, x2, y2)

        if color:
            self.cr.set_source_rgb(*color)

        if linewidth:
            self.cr.set_line_width(linewidth)

        self.cr.move_to(x, y)
        self.cr.line_to(x2, y2)
        self.cr.stroke()

    def draw_circle(self, fill, xc, yc, r, color=None):
        """Draw a circle, filled or not, centered at xc, yc with radius r."""
        if color:
            self.cr.set_source_rgb(*color)
        self.cr.arc(xc, yc, r, 0, 2*math.pi)
        self.cr.stroke_preserve()
        if fill:
            self.cr.fill()

    def draw_label(self, labelstring, x, y, color=None, dropshadow=None,
                   font=None, offsets=None):
        """Draw a string at the specified point.
           offsets is an optional tuple specifying where the string will
           be drawn relative to the coordinates passed in;
           for instance, if offsets are (-1, -1) the string will be
           drawn with the bottom right edge at the given x, y.
        """
        x, y = int(x), int(y)
        if not color:
            color = self.black_color
        if not font:
            font = self.select_font_desc

        if dropshadow is None:
            if color == self.black_color:
                dropshadow = False
            else:
                dropshadow = True

        if not self.cr:
            self.cr = self.drawing_area.get_window().cairo_create()

        layout = self.drawing_area.create_pango_layout(str(labelstring))
        layout.set_font_description(font)
        label_width, label_height = layout.get_pixel_size()

        if offsets:
            if offsets[0] == 0:
                x -= int(label_width/2)
            elif offsets[0] != 1:
                x += int(label_width * offsets[0])
            if offsets[1] != 1:
                y += int(label_height * offsets[1] - label_height/2)

        if x < 0:
            x = self.win_width - label_width + x
        if y < 0:
            y = self.win_height - label_height + y

        if dropshadow:
            self.cr.set_source_rgb(*self.black_color)
            if label_height < 15:
                self.draw_rectangle(True, x, y, label_width, label_height)
            else:
                self.cr.move_to(x, y+2)
                PangoCairo.show_layout(self.cr, layout)
                self.cr.stroke()
                self.cr.move_to(x, y-2)
                PangoCairo.show_layout(self.cr, layout)
                self.cr.stroke()
                self.cr.move_to(x-2, y+2)
                PangoCairo.show_layout(self.cr, layout)
                self.cr.stroke()
                self.cr.move_to(x+2, y+2)
                PangoCairo.show_layout(self.cr, layout)
                self.cr.stroke()

        self.cr.set_source_rgb(*color)
        self.cr.move_to(x, y)
        PangoCairo.show_layout(self.cr, layout)
        self.cr.stroke()

        # This isn't needed from draw_map(), but it is if it's
        # called incidentally, like from a mouse click.
        # That doesn't seem to have anything to do with what the
        # documentation says restore() is for (to return to a saved
        # state after an earlier save(), which we never do).
        # Maybe PangoCairo does a save() internally?
        # self.cr.restore()

    @staticmethod
    def load_image_from_file(filename):
        pixbuf = GdkPixbuf.Pixbuf.new_from_file(filename)
        return pixbuf

    def draw_string_scale(self, x, y, s, whichfont=None):
        """Draw a string at the specified location.
           If x or y is negative, we'll draw from the right or bottom edge.
           If whichfont is "waypoint" it'll be a little bigger and italic;
           if "attribution" even bigger and also italic;
           if it's "select" it'll be a lot bigger.
        """
        # layout = self.drawing_area.create_pango_layout(s)
        layout = PangoCairo.create_layout(self.cr)
        layout.set_text(s, -1)
        if whichfont == "waypoint":
            layout.set_font_description(self.wpt_font_desc)
        elif whichfont == "attribution":
            layout.set_font_description(self.attr_font_desc)
        elif whichfont == "select":
            layout.set_font_description(self.select_font_desc)
        else:
            layout.set_font_description(self.font_desc)
        if x < 0 or y < 0:
            win_width, win_height = self.get_size()
            lw, lh = layout.get_pixel_size()
            if x < 0:
                x = win_width - lw + x
            if y < 0:
                y = win_height - lh + y

        # GTK2 way:
        # self.drawing_area.get_window().draw_layout(self.xgc, x, y, layout)

        # GTK3 way:
        # Pango_cr = PangoCairo.CairoContext(self.cr)
        # Pango_cr.set_source_rgb(0, 0, 0)
        self.cr.move_to(x, y)
        PangoCairo.show_layout(self.cr, layout)
        self.cr.stroke()

    # Save the current map as something which could be gimped or printed.
    # XXX THIS IS BROKEN, code assumes start_lon/start_lat but has center_.
    def save_as(self):
        """Save a static map. Somewhat BROKEN, needs rewriting."""

        file_list = ""

        # Calculate dAngle in decimal degrees
        dAngle = self.collection.img_width / self.collection.xscale

        # Calculate number of charts based on window size, and round up
        # so the saved map shows at least as much as the window does.
        num_lon = int(.8 + float(self.win_width) / self.collection.img_width)
        num_lat = int(.8 + float(self.win_height) / self.collection.img_height)

        ny = 0
        curlat = self.center_lat + dAngle * num_lat * .25
        while ny < num_lat:
            curlon = self.center_lon - dAngle * num_lon * .25
            nx = 0
            while nx < num_lon:
                file_list += " " + \
                    self.collection.coords_to_filename(curlon, curlat)
                curlon += dAngle
                nx += 1
            curlat -= dAngle
            ny += 1

        outfile = self.map_save_dir + "topo" + "_" + \
            str(self.center_lon) + "_" + str(self.center_lat) + ".gif"
        cmdstr = "montage -geometry 262x328 -tile " + \
                 str(nx) + "x" + str(ny) + " " + \
                 file_list + " " + outfile
        # print("Running:", cmdstr)
        os.system(cmdstr)

        if (os.access(outfile, os.R_OK)):
            print("Saved:", outfile)

    def on_size_allocate(self, _unused, allocation):
        """Notice a new window width and height"""
        self.width = allocation.width
        self.height = allocation.height

    def draw_handler(self, widget, cr):
        self.draw_map()

    def key_press_event(self, widget, event):
        """Handle key presses."""
        if event.string == "q":
            self.graceful_exit()
            # Must return here: Gtk.main_quit() (called from graceful_exit())
            # won't actually return immediately, so without a return
            # we'll fall through and end up drawing the map again
            # before exiting.
            return True
        elif event.string == "+" or event.string == "=":
            self.zoom(amount=1)
            if self.controller.Debug and hasattr(self.collection, 'zoomlevel'):
                print("zoomed in to", self.collection.zoomlevel)
        elif event.string == "-":
            self.zoom(amount=-1)
            if self.controller.Debug and hasattr(self.collection, 'zoomlevel'):
                print("zoomed out to", self.collection.zoomlevel)
        elif event.keyval == Gdk.KEY_Left:
            self.center_lon -= \
                float(self.collection.img_width) / self.collection.xscale
            self.gps_centered = False
        elif event.keyval == Gdk.KEY_Right:
            self.center_lon += \
                float(self.collection.img_width) / self.collection.xscale
            self.gps_centered = False
        elif event.keyval == Gdk.KEY_Up:
            self.center_lat += \
                float(self.collection.img_height) / self.collection.yscale
            self.gps_centered = False
        elif event.keyval == Gdk.KEY_Down:
            self.center_lat -= \
                float(self.collection.img_height) / self.collection.yscale
            self.gps_centered = False
        elif event.keyval == Gdk.KEY_space:
            self.set_center_to_pin(None)
            self.gps_centered = False
        elif event.keyval == Gdk.KEY_l and \
                event.state == Gdk.ModifierType.CONTROL_MASK:
            pass    # Just fall through to draw_map()
        elif event.keyval == Gdk.KEY_q and \
                event.state == Gdk.ModifierType.CONTROL_MASK:
            self.graceful_exit()
        elif event.keyval == Gdk.KEY_z and \
                event.state == Gdk.ModifierType.CONTROL_MASK:
            self.undo()
        # m pops up a window to choose a point
        elif event.string == "m":
            if self.selection_window():
                self.set_center_to_pin(None)

        # Save As is broken, commented out.
        # elif event.string == "s":
        #     self.save_as()
        #     return True

        else:
            # print("Unknown key,", event.keyval)
            return False

        self.force_redraw()
        return True

    def map_bounds(self):
        """Return the extents of the current map in geographic coordinates:
           minlon, maxlon, minlat, maxlat
        """
        halfwidth = self.win_width / self.collection.xscale / 2
        halfheight = self.win_height / self.collection.yscale / 2
        return (self.center_lon - halfwidth,
                self.center_lon + halfwidth,
                self.center_lat - halfheight,
                self.center_lat + halfheight)

    def xy2coords(self, x, y, xscale=None, yscale=None):
        """Convert pixels to longitude/latitude."""
        # collection.x_scale is in pixels per degree.
        if not xscale:
            xscale = self.collection.xscale
        if not yscale:
            yscale = self.collection.yscale
        return (self.center_lon -
                float(self.win_width / 2 - x) / xscale,
                self.center_lat +
                float(self.win_height / 2 - y) / yscale)

    def coords2xy(self, lon, lat, win_width=None, win_height=None,
                  xscale=None, yscale=None):
        """Convert lon/lat to pixels."""
        if not win_width:
            win_width = self.win_width
        if not win_height:
            win_height = self.win_height
        if not xscale:
            xscale = self.collection.xscale
        if not yscale:
            yscale = self.collection.yscale
        return (int((lon - self.center_lon) * xscale
                    + win_width / 2),
                int((self.center_lat - lat) * yscale
                    + win_height / 2))

    def drag_event(self, widget, event):
        """Move the map as the user drags."""

        # event.state is <flags GDK_BUTTON1_MASK of type Gdk.ModifierType>

        # The GTK documentation @ 24.2.1
        # http://www.pyGtk.org/pyGtk2tutorial/sec-EventHandling.html
        # says the first event is a real motion event and subsequent
        # ones are hints; but in practice, nothing but hints are
        # ever sent.
        if event.is_hint:
            bogo, x, y, state = event.window.get_pointer()
        else:
            x = event.x
            y = event.y
            state = event.state

        if self.press_timeout:
            GLib.source_remove(self.press_timeout)
            self.press_timeout = None

        # On a tablet (at least the ExoPC), almost every click registers
        # as a drag. So if a drag starts in the zoom control area,
        # it was probably really meant to be a single click.
        if self.was_click_in_zoom(event.x, event.y):
            return False

        if not self.is_dragging:
            self.x_start_drag = x
            self.y_start_drag = y
            self.is_dragging = True

        # Rubberbanding doesn't currently work, and there is not Gdk.XOR
        # if self.is_rubberbanding:
        #     # Draw the new box:
        #     self.xgc.function = Gdk.XOR
        #     self.set_color(self.white_color)
        #     if self.x_last_drag and self.y_last_drag:
        #         self.draw_rect_between(False,
        #                                self.x_start_drag, self.y_start_drag,
        #                                self.x_last_drag, self.y_last_drag)
        #     self.draw_rect_between(False,
        #                            self.x_start_drag, self.y_start_drag,
        #                            x, y)
        #     self.x_last_drag = x
        #     self.y_last_drag = y
        #     return True

        self.gps_centered = False
        self.move_to(x, y, widget)
        return True

    def move_to(self, x, y, widget):
        """Move the map, e.g. during a mouse drag."""
        # traceback.print_stack()
        # print("=======")

        # Has the position changed enough to redraw?
        if not widget.drag_check_threshold(self.x_start_drag, self.y_start_drag,
                                           x, y):
            return

        dx = x - self.x_start_drag
        dy = y - self.y_start_drag
        self.center_lon -= dx / self.collection.xscale
        self.center_lat += dy / self.collection.yscale
        self.force_redraw()

        # Reset the drag coordinates now that we're there
        self.x_start_drag = x
        self.y_start_drag = y

    def click_draw(self, widget, event):
        """Handle mouse button presses when in drawing mode"""
        if event.button != 1:
            print("We only handle button 1 so far when drawing tracks.")
            return False

        lon, lat = self.xy2coords(event.x, event.y)

        self.trackpoints.handle_track_point(lat, lon, timestamp=0,
                                            waypoint_name=None)

        # XXX Preferably, just draw the line ourselves,
        # and figure it'll get drawn nicely later when the map needs to redraw.
        # This way there's some annoying flicker.
        self.force_redraw()

        return True

    def mousepress(self, widget, event):
        """Handle mouse button presses"""

        # We're either about to add a new timeout, or not time out
        # because we had a doubleclick. Either way, remove any
        # existing timeout:
        if self.press_timeout:
            GLib.source_remove(self.press_timeout)
            self.press_timeout = None

        # Was it a right click?
        if event.button == 3:
            bogo, x, y, state = self.drawing_area.get_window().get_pointer()
            self.context_x = x
            self.context_y = y
            self.cur_lon, self.cur_lat = self.xy2coords(x, y)
            self.context_menu(event)
            return True

        if event.button != 1:
            return False

        # If it wasn't a double click, set a timeout for LongPress
        if event.type != Gdk.EventType.DOUBLE_BUTTON_PRESS:
            self.press_timeout = GLib.timeout_add(1000, self.longpress)
            return False

        # Zoom in if we get a double-click.
        self.center_lon, self.center_lat = self.xy2coords(event.x, event.y)

        self.zoom(amount=1)
        if self.controller.Debug and hasattr(self.collection, 'zoomlevel'):
            print("doubleclick: zoomed in to", self.collection.zoomlevel)
        self.force_redraw()
        return True

    def longpress(self):
        """Handle longpress, for running on tablets.
           Hasn't been tested in a long time.
        """
        if self.press_timeout:
            GLib.source_remove(self.press_timeout)
            self.press_timeout = None
        bogo, x, y, state = self.drawing_area.get_window().get_pointer()
        self.cur_lon, self.cur_lat = self.xy2coords(x, y)
        self.context_menu(None)
        return True

    def mouserelease(self, widget, event):
        """Handle button releases."""

        # print("Setting context coords to", self.context_x, self.context_y)
        if self.press_timeout:
            GLib.source_remove(self.press_timeout)
            self.press_timeout = None
            # return False

        if self.is_rubberbanding:
            # is_rubberbanding is a list or tuple,
            # where the first item is the callback function to call.
            # and everything else is the arguments to pass.
            # The function will be called with args:
            # (start_x, start_y, end_x, end_y, other_args...)

            self.xgc.function = Gdk.COPY

            lon1, lat1 = self.xy2coords(self.x_start_drag, self.y_start_drag)
            lon2, lat2 = self.xy2coords(event.x, event.y)

            self.is_rubberbanding[0](lon1, lat1, lon2, lat2,
                                     *self.is_rubberbanding[1:])
            self.is_rubberbanding = False
            self.is_dragging = False
            self.x_last_drag = None
            self.y_last_drag = None

            self.force_redraw()

            return True

        if self.is_dragging:
            self.is_dragging = False
            bogo, x, y, state = event.window.get_pointer()
            self.move_to(x, y, widget)
            self.draw_overlays()
            return True

        if event.button == 1:
            # If we're drawing a track, everything is different.
            if self.drawing_track:
                return self.click_draw(widget, event)

            zoom = self.was_click_in_zoom(event.x, event.y)
            if zoom:
                self.zoom(amount=zoom)
                if self.controller.Debug and hasattr(self.collection,
                                                     'zoomlevel'):
                    print("zoomed to", self.collection.zoomlevel)
                self.force_redraw()
                return True

            # Clicking on the blue GPS circle toggles following GPS,
            # and recenters on the GPS position if there is one.
            if  self.was_click_in_gps(event.x, event.y):
                self.gps_centered = not self.gps_centered
                if self.gps_centered and self.last_gpsd and self.last_gpsd.fix:
                    self.center_lon = self.last_gpsd.fix.longitude
                    self.center_lat = self.last_gpsd.fix.latitude
                    self.cur_lon = self.center_lon
                    self.cur_lat = self.center_lat
                    self.force_redraw()
                return True

            # Is this needed for anything?
            # It breaks passing location to context menus.
            cur_long, cur_lat = self.xy2coords(event.x, event.y)

            if self.controller.Debug:
                print("Click:", \
                    MapUtils.dec_deg2dms_str(cur_long), \
                    MapUtils.dec_deg2dms_str(cur_lat))

            # Find angle and distance since last click.
            if self.controller.Debug or \
               event.state & Gdk.ModifierType.SHIFT_MASK:
                print("Shift click")
                if self.click_last_long != 0 and self.click_last_lat != 0:
                    dist = MapUtils.haversine_distance(self.click_last_lat,
                                                       self.click_last_long,
                                                       cur_lat, cur_long,
                                                       metric=self.use_metric)
                    self.path_distance += dist
                    if self.use_metric:
                        print("Distance: %.2f km" % dist)
                        print("Total distance: %.2f km" % self.path_distance)
                    else:
                        print("Distance: %.2f mi" % dist)
                        print("Total distance: %.2f mi" % self.path_distance)

                    # Now calculate bearing.
                    angle = MapUtils.bearing(self.click_last_lat,
                                             self.click_last_long,
                                             cur_lat, cur_long)
                    print("Bearing:", angle, "=", \
                        MapUtils.angle_to_quadrant(angle))

            self.click_last_long = cur_long
            self.click_last_lat = cur_lat

            # Is the click near a track or waypoint we're displaying?
            near_track, near_point, near_waypoint, polygons = \
                self.find_nearest_trackpoint(event.x, event.y)
            if near_track is not None:
                self.select_track(near_track)
            else:
                self.select_track(None)
            if near_waypoint is not None:
                self.selected_waypoint = near_waypoint
            else:
                self.selected_waypoint = None

            self.force_redraw()

        return True

    @staticmethod
    def nop(*args):
        """Do nothing."""
        return True

    def graceful_exit(self, extra=None):
        """Clean up the window and exit.
           The "extra" argument is so it can be calld from GTK callbacks.
        """
        # Try to stop any GPS thread
        if self.gps_poller:
            print("Stopping GPS poller")
            self.gps_poller.stopGPS()

        self.controller.save_sites()    # save any new sites/tracks

        Gtk.main_quit()
        # The python profilers don't work if you call sys.exit here.

        # Too bad, because Gtk.main_quit() doesn't actually exit
        # until later. So any function that calls this must be sure
        # to guard against anything like extra map redraws.
#
# End of MapWindow class
#
