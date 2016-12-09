# Copyright (C) 2009-2016 by Akkana Peck.
# You are free to use, share or modify this program under
# the terms of the GPLv2 or, at your option, any later GPL.

'''MapWindow: pytopo's GTK-based window for showing tiled maps.
'''

from pytopo.MapUtils import MapUtils

import os
import re
import urllib
import math
import collections

import gtk
import gobject
import glib
import gc
import pango


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
(That list is very incomplete and needs to be updated, sorry.)
"""

    def __init__(self, _controller):
        """Initialize variables, but don't create the window yet."""

        # Save a reference to the PyTopo object that created this window.
        # We'll need it to change locations, collections etc.
        self.controller = _controller

        # The current map collection being used:
        self.collection = None

        self.center_lon = 0
        self.center_lat = 0
        self.cur_lon = 0
        self.cur_lat = 0
        self.trackpoints = None
        self.show_waypoints = True
        self.selected_track = None
        self.selected_waypoint = None

        self.win_width = 0
        self.win_height = 0

        self.traildialog = None

        self.Debug = False

        try:
            self.pin = \
                gtk.gdk.pixbuf_new_from_file("/usr/share/pytopo/pytopo-pin.png")
        except:
            try:
                self.pin = gtk.gdk.pixbuf_new_from_file("pytopo-pin.png")
            except:
                self.pin = None
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

        # X/gtk graphics variables we need:
        self.drawing_area = 0
        self.xgc = 0

        self.click_last_long = 0
        self.click_last_lat = 0

        # Context menus don't seem to have any way of passing the location
        # initially clicked. So save x and y on right mouse down.
        self.context_x = None
        self.context_y = None

        self.is_dragging = False

        # The timeout for long press events
        self.press_timeout = None

        # Colors and fonts should of course be configurable:
        # self.bg_color = gtk.gdk.color_parse("black")
        self.black_color = gtk.gdk.color_parse("black")
        self.red_color = gtk.gdk.color_parse("red")
        self.bg_scale_color = gtk.gdk.color_parse("white")
        self.first_track_color = gtk.gdk.color_parse("magenta")
        self.waypoint_color = gtk.gdk.color_parse("blue2")
        self.grid_color = gtk.gdk.color_parse("grey45")

        self.font_desc = pango.FontDescription("Sans 9")
        self.wpt_font_desc = pango.FontDescription("Sans Italic 10")
        self.attr_font_desc = pango.FontDescription("Sans Bold Italic 12")
        self.select_font_desc = pango.FontDescription("Sans Bold 15")

        # For running on tablets:
        settings = gtk.settings_get_default()
        settings.set_property("gtk-touchscreen-mode", True)

    def show_window(self, init_width, init_height):
        """Create the initial window."""
        win = gtk.Window()
        win.set_name("PyTopo")
        win.connect("destroy", self.graceful_exit)
        win.set_border_width(5)

        vbox = gtk.VBox(spacing=3)
        win.add(vbox)

        self.drawing_area = gtk.DrawingArea()
        # There doesn't seem to be any way to resize a window below
        # the initial size of the drawing area. So make the drawing area
        # initially tiny, then just before showing we'll resize the window.
        # self.drawing_area.size(10, 10)
        vbox.pack_start(self.drawing_area)

        self.drawing_area.set_events(gtk.gdk.EXPOSURE_MASK |
                                     gtk.gdk.POINTER_MOTION_MASK |
                                     gtk.gdk.POINTER_MOTION_HINT_MASK |
                                     gtk.gdk.BUTTON_PRESS_MASK |
                                     gtk.gdk.BUTTON_RELEASE_MASK)

        self.drawing_area.connect("expose-event", self.expose_event)
        self.drawing_area.connect("button-press-event", self.mousepress)
        self.drawing_area.connect("button-release-event", self.mouserelease)
        self.drawing_area.connect("scroll-event", self.scroll_event)
        self.drawing_area.connect("motion_notify_event", self.drag_event)

        # The default focus in/out handlers on drawing area cause
        # spurious expose events.  Trap the focus events, to block that:
        # XXX can we pass "pass" in to .connect?
        self.drawing_area.connect("focus-in-event", self.nop)
        self.drawing_area.connect("focus-out-event", self.nop)

        # Handle key presses on the drawing area.
        # If seeing spurious expose events, try setting them on win instead,
        # and comment out gtk.CAN_FOCUS.
        self.drawing_area.set_flags(gtk.CAN_FOCUS)
        self.drawing_area.connect("key-press-event", self.key_press_event)

        # Resize the window now to the desired initial size:
        win.resize(init_width, init_height)

        win.show_all()

        gtk.main()

    #
    # Draw maplets to fill the window, centered at center_lon, center_lat
    #
    def draw_map(self):
        """Redraw the map, centered at center_lon, center_lat."""

        if self.collection is None:
            print "No collection!"
            return
        if not self.drawing_area:
            # Not initialized yet, not ready to draw a map
            return

        self.win_width, self.win_height = self.drawing_area.window.get_size()

        # XXX Collection.draw_map wants center, but we only have lower right.
        if self.Debug:
            print ">>>>>>>>>>>>>>>>"
            print "window draw_map centered at",
            print MapUtils.dec_deg2deg_min_str(self.center_lon),
            print MapUtils.dec_deg2deg_min_str(self.center_lat)
        self.collection.draw_map(self.center_lon, self.center_lat, self)

        self.draw_trackpoints()

        if not self.is_dragging:
            self.draw_zoom_control()

        # Is there a selected track?
        def draw_selected_label(name, labelstring, x, y):
            tracklabel = labelstring + name

            layout = self.drawing_area.create_pango_layout(tracklabel)
            layout.set_font_description(self.select_font_desc)
            label_width, label_height = layout.get_pixel_size()
            self.xgc.set_rgb_fg_color(self.red_color)
            self.drawing_area.window.draw_layout(self.xgc,
                                                 self.win_width-label_width-x,
                                                 y,
                                                 layout)

        if self.selected_track is not None:
            draw_selected_label(self.trackpoints.points[self.selected_track],
                                "Track: ", 15, 15)
        if self.selected_waypoint is not None:
            draw_selected_label(self.trackpoints.waypoints[self.selected_waypoint][2], "Waypoint: ", 15, 40)

        # Copyright info or other attribution
        self.set_color(self.grid_color)
        self.collection.draw_attribution(self)

        # draw pin
        pin_x, pin_y = self.coords2xy(self.pin_lon, self.pin_lat,
                                      self.win_width, self.win_height)

        if self.pin:
            self.draw_pixbuf(self.pin, 0, 0, pin_x + self.pin_xoff,
                             pin_y + self.pin_yoff, -1, -1)

        self.draw_map_scale()

    def contrasting_color(self, color):
        '''Takes a gtk.gdk.Color (RGB values 0:65535)
           and converts it to a similar saturation and value but different hue
        '''
        if not color:
            return self.first_track_color

        # Hue is a floating point between 0 and 1. How much should we jump?
        jump = .37

        return gtk.gdk.color_from_hsv(color.hue + jump,
                                      color.saturation, color.value)

    def draw_trackpoint_segment(self, start, linecolor, linewidth=3,
                                linestyle=gtk.gdk.LINE_ON_OFF_DASH):
        '''Draw a trackpoint segment, starting at the given index.
           Stop drawing if we reach another start string, and return the index
           of that string. Return None if we reach the end of the list.
        '''
        self.set_color(linecolor)
        self.xgc.line_style = linestyle
        self.xgc.line_width = linewidth
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

            x = int((pt[0] - self.center_lon) * self.collection.xscale
                    + self.win_width / 2)
            y = int((self.center_lat - pt[1]) * self.collection.yscale
                    + self.win_height / 2)

            if ((x >= 0 and x < self.win_width and
                 y >= 0 and y < self.win_height) or
                    (cur_x < self.win_width and cur_y < self.win_height)):
                if cur_x is not None and cur_y is not None:
                    # self.set_color(self.track_color)
                    self.draw_line(cur_x, cur_y, x, y)
                    # self.set_color(self.black_color)
                    # self.draw_circle(True, x, y, 3)

                cur_x = x
                cur_y = y
            else:
                # It's off the screen. Skip it.
                # print "Skipping", pt[0], pt[1], \
                #    ": would be", x, ",", y
                cur_x = None
                cur_y = None

    def select_track(self, trackindex):
        '''Mark a track as active.'''
        if self.Debug:
            # Test against None specifically, else we won't be able
            # to select the first track starting at index 0.
            if trackindex is not None:
                print "Selecting track starting at", trackindex
            else:
                print "De-selecting track"
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
        '''Show a dialog giving information about a selected track.'''
        trailname = self.trackpoints.points[self.selected_track]
        if not self.traildialog:
            self.traildialog = gtk.Dialog(trailname,
                                          None, 0,
                                          (gtk.STOCK_CLOSE,
                                           gtk.RESPONSE_CANCEL))
            self.traildialog.set_size_request(400, 300)

            sw = gtk.ScrolledWindow()
            sw.set_shadow_type(gtk.SHADOW_ETCHED_IN)
            sw.set_policy(gtk.POLICY_AUTOMATIC, gtk.POLICY_AUTOMATIC)

            textview = gtk.TextView()
            self.attributes_textbuffer = textview.get_buffer()
            sw.add(textview)
            sw.show()
            textview.show()
            self.traildialog.vbox.pack_start(sw, expand=True)
            self.traildialog.connect("response", self.hide_traildialog)

        else:
            self.traildialog.set_title(trailname)

        self.attributes_textbuffer.set_text("== %s ==\n%s" % (trailname,
                                                              attrstr))

        self.traildialog.show_all()

    def hide_traildialog(self, d, responseid=None):
        d.hide()

    def draw_trackpoints(self):
        if not self.trackpoints:
            return

        # Now draw any trackpoints that are visible.
        # self.trackpoints may be trackpoints or waypoints
        self.track_color = None

        # win_width, win_height = self.drawing_area.window.get_size()
        if len(self.trackpoints.points) > 0:
            cur_x = None
            cur_y = None

            nextpt = 0
            while True:
                self.track_color = self.contrasting_color(self.track_color)
                nextpt = self.draw_trackpoint_segment(nextpt, self.track_color)
                if not nextpt:
                    break

        if self.selected_track is not None:  # None vs. trackpoint 0
            self.draw_trackpoint_segment(self.selected_track,
                                         self.red_color, linewidth=6)

        if self.show_waypoints and len(self.trackpoints.waypoints) > 0:
            self.set_color(self.waypoint_color)
            self.xgc.line_style = gtk.gdk.LINE_SOLID
            self.xgc.line_width = 2
            for pt in self.trackpoints.waypoints:
                if self.trackpoints.is_start(pt) or \
                   self.trackpoints.is_attributes(pt):
                    continue
                x = int((pt[0] - self.center_lon) * self.collection.xscale
                        + self.win_width / 2)
                y = int((self.center_lat - pt[1]) * self.collection.yscale
                        + self.win_height / 2)

                if x >= 0 and x < self.win_width and \
                   y >= 0 and y < self.win_height:
                    layout = self.drawing_area.create_pango_layout(pt[2])
                    layout.set_font_description(self.wpt_font_desc)
                    # tw = layout.get_size()[0] / pango.SCALE
                    th = layout.get_size()[1] / pango.SCALE
                    self.drawing_area.window.draw_layout(self.xgc,
                                                         x + th / 3,
                                                         y - th / 2,
                                                         layout)
                    self.draw_rectangle(True, x - 3, y - 3, 6, 6)

    def find_nearest_trackpoint(self, x, y):
        """Find the nearet track, the nearest point on that track,
           and the nearest waypoint (if any) to a given x, y point.
           Any of the three can be None if nothing is sufficiently close.
           Coords x, y passed in are screen coordinates;
           if None, we'll assume exact center, as if we've already
           set center_lat and center_lon after a mouse click.

           @return: (nearest_track,    Starting point of the nearest track
                    nearest_point,    Index of nearest point on that track
                    nearest_waypoint) Nearest waypoint
        """
        nearest_track = None
        nearest_point = None
        nearest_waypoint = None

        halfwidth, halfheight = \
            [s / 2 for s in self.drawing_area.window.get_size()]
        if x is None:
            x = halfwidth
        if y is None:
            y = halfheight
        CLOSE = 6    # pixels

        if not self.trackpoints:
            return None, None, None

        def closer_dist(pt, sm_dist):
            """Return distance from pt to x, y --
               but only if it's smaller than sm_dist.
            """
            # tx = int((pt[0] - self.center_lon) * self.collection.xscale
            #          + halfwidth)
            # ty = int((self.center_lat - pt[1]) * self.collection.yscale
            #          + halfheight)

            tx, ty = self.coords2xy(pt[0], pt[1],
                                    self.win_width, self.win_height)

            if abs(x - tx) > CLOSE or abs(y - ty) > CLOSE:
                return None

            dist = math.sqrt((x - tx)**2 + (y - ty)**2)
            if dist < sm_dist:
                return dist
            return None

        # Find closest waypoint
        if self.trackpoints.waypoints:
            smallest_dist = CLOSE * 8
            for i, pt in enumerate(self.trackpoints.waypoints):
                if self.trackpoints.is_start(pt) or \
                   self.trackpoints.is_attributes(pt):
                    continue
                d = closer_dist(pt, smallest_dist)
                if d:
                    smallest_dist = d
                    nearest_waypoint = i

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

                """
                # Okay, the click wasn't on a point. Is it on
                # a line between this point and the last one?
                if lastx and lasty:
                    m = float(y-lasty) / float(x-lastx)
                    y1 = m * x + lasty  # Predicted position
                    if abs(y - y1) < CLOSE:
                        self.select_track(track_start)
                        return
                """
        return nearest_track, nearest_point, nearest_waypoint

    def draw_map_scale(self):
        ########################################################################
        #
        # The draw_map_scale function calculates and draws a map scale at the
        # bottom of the map window created by the PyTopo mapping application.
        # Distances are calculated along the surface of the geoid defined by the
        # earth equitorial radius, Req, and the square of the eccentricity of
        # the earth, esq.
        # The map scale is accurate only for the center latitude of the map.
        # The circumference of the earth at the equator is 24901 miles (an upper
        # limit on map size).
        # USGS quadrangles use NAD-27, but WGS-84 is the most recent datum, and
        # GPS uses WGS-84.
        #
        # References:
        #    http://en.wikipedia.org/wiki/Geodetic_system
        #    http://www.gmat.unsw.edu.au/snap/gps/clynch_pdfs/radiigeo.pdf
        #
        # Copyright (C) 2013 Spencer A. Buckner
        #
        ########################################################################

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
        R_km = R_meters/1000	                                   # earth radius (km)
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
        label_mi = str(10)
        label_km = str(10)
        label_mi = '\0' * len(label_mi)
        label_km = '\0' * len(label_km)
        label_mi = "%g mi" % length
        label_km = "%g km" % length

        ##################################################

        # Calculate coordinates of miles map-scale bar
        x1 = int((self.win_width - length_mi) / 2 + 0.5)
        y1 = int(self.win_height - 30 + 0.5)
        x2 = int(x1 + length_mi + 0.5)
        y2 = y1

        # Get label length in pixels;
        # length of "0" string is 7.
        layout = self.drawing_area.create_pango_layout(label_mi)
        layout.set_font_description(self.font_desc)
        width, height = layout.get_pixel_size()
        str_length_mi = width

        # Draw white background for miles map-scale
        self.xgc.line_style = gtk.gdk.LINE_SOLID
        self.set_color(self.bg_scale_color)
        self.xgc.line_width = 20
        self.draw_line(x1 - 10 - 7 - 10, y1, x2 + 10 + str_length_mi + 10, y2)

        # Draw miles map-scale bar
        self.set_bg_color()
        self.xgc.line_width = 1
        self.draw_line(x1, y1, x2, y2)

        # Draw tick marks on miles map-scale bar
        x0 = x1
        for i in range(nticks):
            x1 = x0 + int(i * length_mi / (nticks - 1) + 0.5)
            x2 = x1
            self.draw_line(x1, y1 - 3, x2, y2 + 3)

        # Draw miles map-scale labels
        x = x0 - 10 - 7
        y = self.win_height - 36
        self.draw_string_scale(x, y, "0")
        x = x2 + 10
        self.draw_string_scale(x, y, label_mi)

        ##################################################

        # Calculate coordinates of kilometers map-scale bar
        x1 = int((self.win_width - length_km) / 2 + 0.5)
        y1 = int(self.win_height - 10 + 0.5)
        x2 = int(x1 + length_km + 0.5)
        y2 = y1

        # Get label length in pixels;
        # length of "0" string is 7.
        layout = self.drawing_area.create_pango_layout(label_km)
        layout.set_font_description(self.font_desc)
        width, height = layout.get_pixel_size()
        str_length_km = width

        # Draw white background for kilometers map-scale
        self.xgc.line_style = gtk.gdk.LINE_SOLID
        self.set_color(self.bg_scale_color)
        self.xgc.line_width = 20
        self.draw_line(x1 - 10 - 7 - 10, y1, x2 + 10 + str_length_km + 10, y2)

        # Draw kilometers map-scale bar
        self.set_bg_color()
        self.xgc.line_width = 1
        self.draw_line(x1, y1, x2, y2)

        # Draw tick marks on kilometers map-scale bar
        x0 = x1
        for i in range(nticks):
            x1 = x0 + int(i * length_km / (nticks - 1) + 0.5)
            x2 = x1
            self.draw_line(x1, y1 - 3, x2, y2 + 3)

        # Draw kilometers map-scale labels
        x = x0 - 10 - 6
        y = self.win_height - 16
        self.draw_string_scale(x, y, "0")
        x = x2 + 10
        self.draw_string_scale(x, y, label_km)

    def draw_zoom_control(self):
        """Draw some zoom controls in case we're running on a tablet
           and have no keyboard to zoom or move around.
           Also draw any other controls we might need.
        """
        self.zoom_btn_size = int(self.win_width / 25)
        self.zoom_X1 = 8
        self.zoom_in_Y1 = 10
        self.zoom_out_Y1 = self.zoom_in_Y1 + self.zoom_btn_size * 2
        textoffset = self.zoom_btn_size / 5

        self.xgc.line_style = gtk.gdk.LINE_SOLID
        self.set_color(self.grid_color)
        self.xgc.line_width = 3

        # Draw the boxes
        self.draw_rectangle(False, self.zoom_X1, self.zoom_in_Y1,
                            self.zoom_btn_size, self.zoom_btn_size)
        self.draw_rectangle(False, self.zoom_X1, self.zoom_out_Y1,
                            self.zoom_btn_size, self.zoom_btn_size)

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
           Returns 0 for none, 1 for zoom in, -1 for zoom out.
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

    def print_location(self, widget=None):
        print MapUtils.coord2str_dd(self.cur_lon, self.cur_lat)
        print "%-15s %-15s" % (MapUtils.dec_deg2deg_min_str(self.cur_lon),
                               MapUtils.dec_deg2deg_min_str(self.cur_lat))

    def zoom(self, widget=None):
        self.center_lon = self.cur_lon
        self.center_lat = self.cur_lat
        self.collection.zoom(1)
        self.draw_map()

    def scroll_event(self, button, event):
        if event.direction != gtk.gdk.SCROLL_UP and \
           event.direction != gtk.gdk.SCROLL_DOWN:
            return False

        if event.direction == gtk.gdk.SCROLL_UP:
            direc = 1
        else:
            direc = -1

        # Save off the coordinates currently under the mouse,
        # so we can arrange for it to be under the mouse again after zoom.
        curmouselon, curmouselat = self.xy2coords(event.x, event.y,
                                                  self.win_width,
                                                  self.win_height)

        self.collection.zoom(direc)

        # What are the coordinates for the current mouse pos after zoom?
        newmouselon, newmouselat = self.xy2coords(event.x, event.y,
                                                  self.win_width,
                                                  self.win_height)
        # Shift the map over so the old point will be under the mouse.
        self.center_lon += (curmouselon - newmouselon)
        self.center_lat += (curmouselat - newmouselat)

        self.draw_map()
        return True

    def context_menu(self, event):
        '''Create a context menu. This is called anew on every right-click.'''

        contextmenu = collections.OrderedDict([
            (MapUtils.coord2str_dd(self.cur_lon, self.cur_lat),
             self.print_location),
            ("Zoom here...", self.zoom),
            ("Go to pin...", self.set_center_to_pin),
            ("Pin this location", self.set_pin_by_mouse),
            ("Save pin location...", self.save_location),
            ("Split track here", self.split_track_by_mouse),
            ("My Locations...", self.mylocations),
            ("My Tracks...", self.mytracks),
            ("Download Area...", self.download_area),
            ("Show waypoints...", self.toggle_show_waypoints),
            ("Save GPX...", self.save_tracks_as),
            ("Change background map", self.change_collection),
            ("Quit", self.graceful_exit)
        ])

        menu = gtk.Menu()
        for itemname in contextmenu.keys():
            item = gtk.MenuItem(itemname)

            # Show/Hide waypoints changes its name since it's a toggle:
            if contextmenu[itemname] == self.toggle_show_waypoints:
                if self.show_waypoints:
                    item.set_label("Hide waypoints...")
                item.connect("activate", contextmenu[itemname])

            # Change background map gives a submenu of available collections.
            elif itemname == "Change background map":
                submenu = gtk.Menu()
                for coll in self.controller.collections:
                    subitem = gtk.MenuItem(coll.name)
                    subitem.connect("activate", self.change_collection,
                                    coll.name)
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
        menu.popup(None, None, None, button, t)

    def change_collection(self, widget, name):
        newcoll = self.controller.find_collection(name)
        if newcoll:
            newcoll.zoom_to(self.collection.zoomlevel, self.cur_lat)
            self.collection = newcoll
            self.draw_map()
        else:
            print "Couldn't find a collection named '%s'" % name

    def toggle_show_waypoints(self, widget):
        self.show_waypoints = not self.show_waypoints
        self.draw_map()

    def mylocations(self, widget):
        self.controller.location_select(self)


    def selection_window(self):
        '''Show a window that lets the user choose a known starting point.
           Returns True if the user chose a valid site, otherwise False.
        '''
        dialog = gtk.Dialog("Choose a point", None, 0,
                            (gtk.STOCK_CLOSE, gtk.RESPONSE_NONE,
                             gtk.STOCK_OK, gtk.RESPONSE_OK))
        # dialog.connect('destroy', lambda win: gtk.main_quit())
        dialog.set_size_request(400, 300)

        sw = gtk.ScrolledWindow()
        sw.set_shadow_type(gtk.SHADOW_ETCHED_IN)
        sw.set_policy(gtk.POLICY_AUTOMATIC, gtk.POLICY_AUTOMATIC)

        # List store will hold name, collection-name and site object
        store = gtk.ListStore(str, str, object)

        # Create the list
        for site in self.controller.KnownSites:
            store.append([site[0], site[3], site])

        # http://pygtk.org/pygtk2tutorial/ch-TreeViewWidget.html
        # Make a treeview from the list:
        treeview = gtk.TreeView(store)

        renderer = gtk.CellRendererText()
        column = gtk.TreeViewColumn("Location", renderer, text=0)
        # column.pack_start(renderer, True)
        # column.set_resizable(True)
        treeview.append_column(column)
        renderer = gtk.CellRendererText()
        column = gtk.TreeViewColumn("Collection", renderer, text=1)
        # column.pack_start(renderer, False)
        treeview.append_column(column)

        # store.set_sort_column_id(0, gtk.SORT_ASCENDING)

        sw.set_policy(gtk.POLICY_AUTOMATIC, gtk.POLICY_AUTOMATIC)
        sw.add(treeview)

        dialog.vbox.pack_start(sw, expand=True)

        dialog.show_all()

        response = dialog.run()
        if response == gtk.RESPONSE_OK:
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

    def save_tracks_as(self, widget):
        '''Prompt for a filename to save all tracks and waypoints.'''
        dialog = gtk.FileChooserDialog(title="Save GPX",
                                       action=gtk.FILE_CHOOSER_ACTION_SAVE,
                                       buttons=(gtk.STOCK_CANCEL,
                                                gtk.RESPONSE_CANCEL,
                                                gtk.STOCK_SAVE,
                                                gtk.RESPONSE_OK))
        dialog.set_current_folder(self.controller.config_dir)
        filt = gtk.FileFilter()
        filt.set_name("GPX Files")
        filt.add_pattern("*.gpx")
        dialog.add_filter(filt)

        while True:
            response = dialog.run()

            if response != gtk.RESPONSE_OK:
                dialog.destroy()
                return

            outfile = dialog.get_filename()
            if os.path.exists(outfile):
                d = gtk.MessageDialog(None, gtk.DIALOG_MODAL,
                                      gtk.MESSAGE_QUESTION,
                                      gtk.BUTTONS_YES_NO)

                d = gtk.MessageDialog(None, 0,
                                      gtk.MESSAGE_QUESTION,
                                      gtk.BUTTONS_YES_NO,
                                      "File exists. Overwrite?")
                d.set_default_response(gtk.RESPONSE_YES)

                response = d.run()
                d.destroy()

                if response != gtk.RESPONSE_YES:
                    continue
                else:
                    break
            else:
                break

        # At this point we have a filename, and either it's unique
        # or we've confirmed overwriting.
        # Now save all our tracks and waypoints as a GPX file in outfile.
        dialog.destroy()
        if self.Debug:
            print "Saving GPX to", outfile
        self.trackpoints.save_GPX(outfile)

    def split_track_by_mouse(self, widget):
        """Split a track at the current mouse location."""

        self.draw_map()
        near_track, near_point, near_waypoint = \
            self.find_nearest_trackpoint(self.context_x, self.context_y)

        if near_point is not None:
            # Make a name for the new track segment
            trackname = self.trackpoints.points[near_track]
            match = re.search('(.*) (\d+)$', trackname)
            if match:
                trackname = "%s %d" % (match.group(1), int(match.group(2)) + 1)
            else:
                trackname += " 2"

            # Split the track there
            self.trackpoints.points.insert(near_point, trackname)

        self.draw_map()

    def set_pin_by_mouse(self, widget):
        """Set the pin at the current mouse location"""
        self.pin_lon, self.pin_lat = self.cur_lon, self.cur_lat
        self.draw_map()

    def set_center_to_pin(self, widget):
        """Set the center at the current pin point"""
        self.center_lon, self.center_lat = self.pin_lon, self.pin_lat
        self.draw_map()

    def save_location(self, widget):
        """Save the pinned location.
        XXX should save zoom level too, if different from collection default.
        """
        dialog = gtk.Dialog("Save location", None, 0,
                            (gtk.STOCK_CANCEL, gtk.RESPONSE_NONE,
                             gtk.STOCK_OK, gtk.RESPONSE_OK))
        dialog.set_size_request(200, 150)
        dialog.vbox.set_spacing(10)

        prompt = gtk.Label("Please specify a name:")
        dialog.vbox.pack_start(prompt, expand=False)
        nametext = gtk.Entry()
        dialog.vbox.pack_start(nametext, expand=True)
        comment = gtk.Label("")
        dialog.vbox.pack_start(comment, expand=False)

        dialog.show_all()

        while True:
            response = dialog.run()
            if response == gtk.RESPONSE_OK:
                name = nametext.get_text().strip()
                if not name:
                    comment.set_text("Name can't be empty")
                    continue

                # Add to KnownSites
                self.controller.append_known_site([name,
                    MapUtils.dec_deg2deg_min(self.pin_lon),
                    MapUtils.dec_deg2deg_min(self.pin_lat),
                    self.collection.name,
                    self.collection.zoomlevel])

                dialog.destroy()
                return True
            else:
                dialog.destroy()
                return True

    def mytracks(self, widget):
        self.controller.track_select(self)
        if self.trackpoints is not None:
            self.trackpoints_center()
        self.draw_map()

    def trackpoints_center(self):
        minlon, minlat, maxlon, maxlat = self.trackpoints.get_bounds()
        self.center_lon = (maxlon + minlon) / 2
        self.center_lat = (maxlat + minlat) / 2

    def cancel_download(self, widget, data=None):
        self.cancelled = True

    def download_area(self, widget):
        if not self.collection.zoomlevel:
            print "Can't download an area for this collection"
            return

        # Get default values for area and zoom levels:
        halfwidth = self.win_width / self.collection.xscale / 2
        halfheight = self.win_height / self.collection.yscale / 2
        minlon = self.center_lon - halfwidth
        maxlon = self.center_lon + halfwidth
        minlat = self.center_lat - halfheight
        maxlat = self.center_lat + halfheight
        minzoom = self.collection.zoomlevel
        maxzoom = self.collection.zoomlevel + 4

        # Prompt the user for any adjustments to area and zoom:
        dialog = gtk.Dialog("Download an area", None, 0,
                            (gtk.STOCK_REFRESH, gtk.RESPONSE_APPLY,
                             gtk.STOCK_CANCEL, gtk.RESPONSE_CANCEL,
                             gtk.STOCK_OK, gtk.RESPONSE_OK))
        # dialog.set_size_request(200, 150)
        # dialog.vbox.set_spacing(10)
        frame = gtk.Frame("Current zoom = %d" % self.collection.zoomlevel)
        dialog.vbox.pack_start(frame, True, True, 0)

        table = gtk.Table(4, 3, False)
        table.set_border_width(5)
        table.set_row_spacings(5)
        table.set_col_spacings(10)
        frame.add(table)

        label = gtk.Label("Min longitude:")
        label.set_justify(gtk.JUSTIFY_RIGHT)
        table.attach(label, 0, 1, 0, 1,
                     gtk.SHRINK, 0, 0, 0)
        minlon_entry = gtk.Entry()
        table.attach(minlon_entry, 1, 2, 0, 1,
                     gtk.EXPAND | gtk.FILL, 0, 0, 0)

        label = gtk.Label("Max longitude:")
        label.set_justify(gtk.JUSTIFY_RIGHT)
        table.attach(label, 2, 3, 0, 1,
                     gtk.SHRINK, 0, 0, 0)
        maxlon_entry = gtk.Entry()
        table.attach(maxlon_entry, 3, 4, 0, 1,
                     gtk.EXPAND | gtk.FILL, 0, 0, 0)

        label = gtk.Label("Min latitude:")
        label.set_justify(gtk.JUSTIFY_RIGHT)
        table.attach(label, 0, 1, 1, 2,
                     gtk.SHRINK, 0, 0, 0)
        minlat_entry = gtk.Entry()
        table.attach(minlat_entry, 1, 2, 1, 2,
                     gtk.EXPAND | gtk.FILL, 0, 0, 0)

        label = gtk.Label("Max latitude:")
        label.set_justify(gtk.JUSTIFY_RIGHT)
        table.attach(label, 2, 3, 1, 2,
                     gtk.SHRINK, 0, 0, 0)
        maxlat_entry = gtk.Entry()
        table.attach(maxlat_entry, 3, 4, 1, 2,
                     gtk.EXPAND | gtk.FILL, 0, 0, 0)

        label = gtk.Label("Min zoom:")
        label.set_justify(gtk.JUSTIFY_RIGHT)
        table.attach(label, 0, 1, 2, 3,
                     gtk.SHRINK, 0, 0, 0)
        minzoom_entry = gtk.Entry()
        table.attach(minzoom_entry, 1, 2, 2, 3,
                     gtk.EXPAND | gtk.FILL, 0, 0, 0)

        label = gtk.Label("Max zoom:")
        label.set_justify(gtk.JUSTIFY_RIGHT)
        table.attach(label, 2, 3, 2, 3,
                     gtk.SHRINK, 0, 0, 0)
        maxzoom_entry = gtk.Entry()
        table.attach(maxzoom_entry, 3, 4, 2, 3,
                     gtk.EXPAND | gtk.FILL, 0, 0, 0)

        err_label = gtk.Label("")
        dialog.vbox.pack_start(err_label, True, True, 0)

        progress_label = gtk.Label("")
        dialog.vbox.pack_start(progress_label, True, True, 0)

        def flush_events():
            while gtk.events_pending():
                gtk.main_iteration(False)

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
            if response == gtk.RESPONSE_CANCEL:
                dialog.destroy()
                return True
            if response == gtk.RESPONSE_APPLY:
                reset_download_dialog()
                continue
            # Else the response must have been OK.
            # So connect the cancel button to cancel_download(),
            # which means first we have to find the cancel button:
            # Starting with PyGTK 2.22 we can use this easier method:
            # cancelBtn = dialog.get_widget_for_response(gtk.RESPONSE_OK)
            # but for now:
            buttons = dialog.get_action_area().get_children()
            for b in buttons:
                if b.get_label() == 'gtk-cancel':
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

        if self.Debug:
            print "Downloading from %f - %f, %f - %f, zoom %d - %d" \
                % (minlon, maxlon, minlat, maxlat, minzoom, maxzoom)
        for zoom in range(minzoom, maxzoom + 1):
            err_label.set_text("Downloading zoom level %d" % zoom)

            # Show a busy cursor on the dialog:
            busy_cursor = gtk.gdk.Cursor(gtk.gdk.WATCH)
            dialog.window.set_cursor(busy_cursor)
            flush_events()
            gtk.gdk.flush()

            if self.Debug:
                print "==== Zoom level", zoom

            # Find the start and end tiles
            (minxtile, minytile, x_off, y_off) = \
                self.collection.deg2num(maxlat, minlon, zoom)
            (maxxtile, maxytile, x_off, y_off) = \
                self.collection.deg2num(minlat, maxlon, zoom)
            if self.Debug:
                print "X tiles from", minxtile, "to", maxxtile
                print "Y tiles from", minytile, "to", maxytile

            pathlist = []
            for ytile in range(minytile, maxytile + 1):
                for xtile in range(minxtile, maxxtile + 1):
                    if self.Debug:
                        print "Tile", xtile, ytile,
                    filename = os.path.join(self.collection.location,
                                            str(zoom),
                                            str(xtile),
                                            str(ytile)) \
                        + self.collection.ext
                    if os.access(filename, os.R_OK):
                        if self.Debug:
                            print filename, "is already there"
                        continue
                    pathlist.append(filename)
                    if self.Debug:
                        print "appended as", filename

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
                if self.Debug:
                    print "Downloading", url, "to", filename
                thedir = os.path.dirname(filename)
                if not os.access(thedir, os.W_OK):
                    os.makedirs(thedir)
                # err_label.set_text("%d %%: %d of %d" % \
                #                   (int(num_downloaded*100 / numtiles),
                #                    num_downloaded, numtiles))
                if self.Debug:
                    print "%d %%: %d of %d" % \
                        (int(num_downloaded * 100 / numtiles),
                         num_downloaded, numtiles)
                progress_label.set_text("%d: %s" % (num_downloaded, url))
                flush_events()
                urllib.urlretrieve(url, filename)
                num_downloaded += 1

                # XXX should show progress more graphically.

        dialog.destroy()
        return True

    #
    # Drawing-related routines:
    #

    def get_size(self):
        """Return the width and height of the canvas."""
        return self.drawing_area.window.get_size()

    def set_bg_color(self):
        """Change to the normal background color (usually black)."""
        # self.xgc.set_rgb_fg_color(self.bg_color)
        self.xgc.foreground = self.xgc.background

    def set_color(self, color):
        self.xgc.set_rgb_fg_color(color)

    def draw_pixbuf(self, pixbuf, x_off, y_off, x, y, w, h):
        """Draw the pixbuf at the given position and size,
        starting at the specified offset."""
        # Sometimes the next line prints:
        # GtkWarning: gdk_drawable_real_draw_pixbuf: assertion 'width >= 0 && height >= 0' failed
        # but checking width and height doesn't seem to guard against that.
        # What does?
        # And the message eventually went away and I can't reproduce now
        # (maybe it finally downloaded a new tile).
        # print "Drawing pixbuf that is %d x %d!" \
        #     % (pixbuf.get_width(), pixbuf.get_height())
        # if (pixbuf.get_width() <= 0 or pixbuf.get_height() <= 0):
        #     print "Bad pixbuf size!"
        #     raise RuntimeError("pixbuf is size %d x %d!" \
        #                        % (pixbuf.get_width(), pixbuf.get_height()))
        self.drawing_area.window.draw_pixbuf(self.xgc, pixbuf, x_off, y_off,
                                             x, y, w, h)

    def draw_rectangle(self, fill, x, y, w, h):
        """Draw a rectangle."""
        self.drawing_area.window.draw_rectangle(self.xgc, fill, x, y, w, h)

    def draw_line(self, x, y, x2, y2):
        """Draw a line."""
        self.drawing_area.window.draw_line(self.xgc, x, y, x2, y2)

    def draw_circle(self, fill, xc, yc, r):
        """Draw a circle, filled or not, centered at xc, yc with radius r."""
        self.drawing_area.window.draw_arc(self.xgc, fill, xc - r, yc - 4,
                                          r * 2, r * 2, 0, 23040)  # 64 * 360

    @staticmethod
    def load_image_from_file(filename):
        return gtk.gdk.pixbuf_new_from_file(filename)

    def draw_string_scale(self, x, y, s, whichfont=None):
        """Draw a string at the specified location.
           If x or y is negative, we'll draw from the right or bottom edge.
           If whichfont is "waypoint" it'll be a little bigger and italic;
           if "attribution" even bigger and also italic;
           if it's "select" it'll be a lot bigger.
        """
        layout = self.drawing_area.create_pango_layout(s)
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
        self.drawing_area.window.draw_layout(self.xgc, x, y, layout)

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
        # print "Running:", cmdstr
        os.system(cmdstr)

        if (os.access(outfile, os.R_OK)):
            print "Saved:", outfile

    def expose_event(self, widget, event):
        """Handle exposes on the canvas."""
        # print "Expose:", event.type, "for object", self
        # print "area:", event.area.x, event.area.y, \
        #    event.area.width, event.area.height

        if self.xgc == 0:
            self.xgc = self.drawing_area.window.new_gc()
            # self.xgc.set_foreground(white)

        # x, y, w, h = event.area

        self.draw_map()

        return True

    def key_press_event(self, widget, event):
        """Handle any key press."""
        if event.string == "q":
            self.graceful_exit()
            # Must return here: gtk.main_quit() (called from graceful_exit())
            # won't actually return immediately, so without a return
            # we'll fall through and end up drawing the map again
            # before exiting.
            return True
        elif event.string == "+" or event.string == "=":
            self.collection.zoom(1)
        elif event.string == "-":
            self.collection.zoom(-1)
        elif event.keyval == gtk.keysyms.Left:
            self.center_lon -= \
                float(self.collection.img_width) / self.collection.xscale
        elif event.keyval == gtk.keysyms.Right:
            self.center_lon += \
                float(self.collection.img_width) / self.collection.xscale
        elif event.keyval == gtk.keysyms.Up:
            self.center_lat += \
                float(self.collection.img_height) / self.collection.yscale
        elif event.keyval == gtk.keysyms.Down:
            self.center_lat -= \
                float(self.collection.img_height) / self.collection.yscale
        elif event.keyval == gtk.keysyms.space:
            self.set_center_to_pin(None)
        elif event.keyval == gtk.keysyms.l and \
                event.state == gtk.gdk.CONTROL_MASK:
            pass    # Just fall through to draw_map()
        elif event.keyval == gtk.keysyms.q and \
                event.state == gtk.gdk.CONTROL_MASK:
            self.graceful_exit()
        # m pops up a window to choose a point
        elif event.string == "m":
            if self.selection_window():
                self.set_center_to_pin(None)
        elif event.string == "s":
            self.save_as()
            return True
        else:
            # print "Unknown key,", event.keyval
            return False

        self.draw_map()
        return True

    def xy2coords(self, x, y, win_width, win_height, xscale=None, yscale=None):
        """Convert pixels to longitude/latitude."""
        # collection.x_scale is in pixels per degree.
        if not xscale:
            xscale = self.collection.xscale
        if not yscale:
            yscale = self.collection.yscale
        return (self.center_lon -
                float(win_width / 2 - x) / xscale,
                self.center_lat +
                float(win_height / 2 - y) / yscale)

    def coords2xy(self, lon, lat, win_width, win_height,
                  xscale=None, yscale=None):
        """Convert lon/lat to pixels."""
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

        if self.press_timeout:
            gobject.source_remove(self.press_timeout)
            self.press_timeout = None

        # On a tablet (at least the ExoPC), almost every click registers
        # as a drag. So if a drag starts in the zoom control area,
        # it was probably really meant to be a single click.
        if self.was_click_in_zoom(event.x, event.y):
            return False

        # The GTK documentation @ 24.2.1
        # http://www.pygtk.org/pygtk2tutorial/sec-EventHandling.html
        # says the first event is a real motion event and subsequent
        # ones are hints; but in practice, nothing but hints are
        # ever sent.
        if event.is_hint:
            x, y, state = event.window.get_pointer()
        else:
            x = event.x
            y = event.y
            state = event.state
        if not state & gtk.gdk.BUTTON1_MASK:
            return False
        if not self.is_dragging:
            self.x_start_drag = x
            self.y_start_drag = y
            self.is_dragging = True
        self.move_to(x, y, widget)
        return True

    def move_to(self, x, y, widget):
        if widget.drag_check_threshold(self.x_start_drag, self.y_start_drag,
                                       x, y):
            dx = x - self.x_start_drag
            dy = y - self.y_start_drag
            self.center_lon -= dx / self.collection.xscale
            self.center_lat += dy / self.collection.yscale
            self.draw_map()
            # Reset the drag coordinates now that we're there
            self.x_start_drag = x
            self.y_start_drag = y

    def mousepress(self, widget, event):
        """Handle mouse button presses"""

        # We're either about to add a new timeout, or not time out
        # because we had a doubleclick. Either way, remove any
        # existing timeout:
        if self.press_timeout:
            gobject.source_remove(self.press_timeout)
            self.press_timeout = None

        # Was it a right click?
        if event.button == 3:
            x, y, state = self.drawing_area.window.get_pointer()
            self.context_x = x
            self.context_y = y
            self.cur_lon, self.cur_lat = self.xy2coords(x, y,
                                                        self.win_width,
                                                        self.win_height)
            self.context_menu(event)
            return

        # If it wasn't a double click, set a timeout for LongPress
        if event.type != gtk.gdk._2BUTTON_PRESS:
            self.press_timeout = gobject.timeout_add(1000, self.longpress)
            return False

        # Zoom in if we get a double-click.
        self.center_lon, self.center_lat = self.xy2coords(event.x, event.y,
                                                          self.win_width,
                                                          self.win_height)

        self.collection.zoom(1)
        self.draw_map()
        return True

    def longpress(self):
        if self.press_timeout:
            gobject.source_remove(self.press_timeout)
            self.press_timeout = None
        x, y, state = self.drawing_area.window.get_pointer()
        self.cur_lon, self.cur_lat = self.xy2coords(x, y,
                                                    self.win_width,
                                                    self.win_height)
        self.context_menu(None)
        return True

    def mouserelease(self, widget, event):
        """Handle button releases."""

        # print "Setting context coords to", self.context_x, self.context_y
        if self.press_timeout:
            gobject.source_remove(self.press_timeout)
            self.press_timeout = None
            # return False

        if self.is_dragging:
            self.is_dragging = False
            x, y, state = event.window.get_pointer()
            self.move_to(x, y, widget)
            self.draw_zoom_control()
            return True

        if event.button == 1:
            zoom = self.was_click_in_zoom(event.x, event.y)
            if zoom:
                self.collection.zoom(zoom)
                self.draw_map()
                return True

            # Is this needed for anything?
            # It breaks passing location to context menus.
            cur_long, cur_lat = self.xy2coords(event.x, event.y,
                                               self.win_width, self.win_height)

            if self.Debug:
                print "Click:", \
                    MapUtils.dec_deg2deg_min_str(cur_long), \
                    MapUtils.dec_deg2deg_min_str(cur_lat)

            # Find angle and distance since last click.
            if self.Debug or event.state & gtk.gdk.SHIFT_MASK:
                if self.click_last_long != 0 and self.click_last_lat != 0:
                    dist = MapUtils.distance_on_unit_sphere(self.click_last_lat,
                                                           self.click_last_long,
                                                            cur_lat, cur_long)
                    dist2 = MapUtils.haversine_distance(self.click_last_lat,
                                                        self.click_last_long,
                                                        cur_lat, cur_long)
                    if self.use_metric:
                        print "Distance: %.2f km" % dist
                    else:
                        print "Distance: %.2f mi" % (dist / 1.609)
                        print "Haversine Distance: %.2f mi" % dist2

                    # Now calculate bearing. I don't know how accurate this is.
                    xdiff = (cur_long - self.click_last_long)
                    ydiff = (cur_lat - self.click_last_lat)
                    angle = int(math.atan2(-ydiff, -xdiff) * 180 / math.pi)
                    angle = MapUtils.angle_to_bearing(angle)
                    print "Bearing:", angle, "=", \
                        MapUtils.angle_to_quadrant(angle)

            self.click_last_long = cur_long
            self.click_last_lat = cur_lat

            # Is the click near a track or waypoint we're displaying?
            near_track, near_point, near_waypoint = \
                self.find_nearest_trackpoint(event.x, event.y)
            if near_track is not None:
                self.select_track(near_track)
            else:
                self.select_track(None)
            if near_waypoint is not None:
                self.selected_waypoint = near_waypoint
            else:
                self.selected_waypoint = None

            self.draw_map()

        return True

    @staticmethod
    def nop(*args):
        "Do nothing."
        return True

    def graceful_exit(self, extra=None):
        """Clean up the window and exit.
           The "extra" argument is so it can be calld from GTK callbacks.
        """
        self.controller.save_sites()    # save any new sites/tracks

        gtk.main_quit()
        # The python profilers don't work if you call sys.exit here.

        # Too bad, because gtk.main_quit() doesn't actually exit
        # until later. So any function that calls this must be sure
        # to guard against anything like extra map redraws.
#
# End of MapWindow class
#
