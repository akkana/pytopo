#!/usr/bin/env python3

"""Draw charts related to Pytopo.
   This is intended to be run in a separate thread.
   It will communicate with the calling window.
"""

import gi
gi.require_version('Gtk', '3.0')
gi.require_version('Gdk', '3.0')
gi.require_version('PangoCairo', '1.0')
from gi.repository import Gtk
from gi.repository import Gdk
from gi.repository import GLib
from gi.repository import GObject
from gi.repository import GdkPixbuf
from gi.repository import Pango, PangoCairo
import cairo

from math import pi

from datetime import datetime, timezone, timedelta


INIT_WIDTH = 800
INIT_HEIGHT = 600

GPSTIMEFMT = "%Y-%m-%dT%H:%M:%SZ"

LEFTMARGIN = 35
TOPMARGIN = 35
BOTTOMMARGIN = 80    # Room for date labels


class ChartWindowGTK:

    def __init__(self, data, label, chartqueue=None):
        # data['data'] is a dict of time: value, both as strings
        self.times = []
        self.vals = []
        for t in data['data']:
            # UTC datetime
            self.times.append(datetime.strptime(t, GPSTIMEFMT).replace(
                tzinfo=timezone.utc
            ))
            self.vals.append(float(data['data'][t]))

        self.label = label

        self.chartqueue = chartqueue

        self.vline = None

        self.cached_surface = None

        self.win = Gtk.Window()
        self.win.set_name(label)
        self.win.set_title(label)
        self.win.connect("destroy", self.close_window)
        self.win.set_border_width(5)

        vbox = Gtk.VBox(spacing=3)
        self.win.add(vbox)

        self.drawing_area = Gtk.DrawingArea()
        vbox.pack_start(self.drawing_area, True, True, 0)

        self.drawing_area.set_events(Gdk.EventMask.EXPOSURE_MASK |
                                     Gdk.EventMask.BUTTON_PRESS_MASK)

        self.drawing_area.connect('draw', self.draw)

        self.drawing_area.connect("button-press-event", self.mousepress)
        # The default focus in/out handlers on drawing area cause
        # spurious expose events.  Trap the focus events, to block that:
        self.drawing_area.connect("focus-in-event", self.nop)
        self.drawing_area.connect("focus-out-event", self.nop)

        # Handle key presses on the drawing area.
        self.drawing_area.set_property('can-focus', True)
        self.drawing_area.connect("key-press-event", self.key_press_event)

        # Size changes
        self.drawing_area.connect("configure-event", self.on_configure)

        self.win.resize(INIT_WIDTH, INIT_HEIGHT)

        self.win.show_all()

        Gtk.main()

    def get_size(self):
        """Return the width and height of the canvas."""
        return self.drawing_area.get_window().get_geometry()[2:4]

    def key_press_event(self, widget, event):
        """Handle key presses"""
        if event.string == "q":
            self.close_window()

    def mousepress(self, widget, event):
        """Handle mouse button presses"""
        if event.button != 1:
            return

        self.vline = event.x
        self.drawing_area.queue_draw()

        # Figure out the time corresponding to where the mouse was pressed
        timestamp = (event.x - LEFTMARGIN) \
            * self.secrange / self.chartwidth + self.first_timestamp
        print("timestamp clicked:", timestamp)
        self.chartqueue.put(("click", datetime.utcfromtimestamp(timestamp)))

    def draw(self, widget, cr):
        print("draw()")
        if self.cached_surface:
            print("Draw from cached surface")
            cr.set_source_surface(self.cached_surface, 0, 0)
            cr.paint()
        else:
            print("No cached surface")

        if self.vline:
            print("Drawing the vline")
            cr.set_source_rgb(1., 0., 0.)
            cr.set_line_width(2)
            cr.move_to(self.vline, TOPMARGIN)
            cr.line_to(self.vline, widget.get_allocated_height() - BOTTOMMARGIN)
            cr.stroke()
        else:
            print("No vline")

        return False

    # Window resize
    def on_configure(self, widget, cr):
        print("on_configure")
        width = widget.get_allocated_width()
        height = widget.get_allocated_height()
        self.cached_surface = cairo.ImageSurface(cairo.FORMAT_ARGB32,
                                                 width, height)
        self.bar_chart(widget, self.cached_surface)

        self.vline = None

        return False

    def bar_chart(self, widget, surface):
        print("Redrawing the bar chart")
        cr = cairo.Context(surface)
        width, height = self.get_size()
        barwidth = 3
        print(f"Window size is {width} x {height}")
        if len(self.vals) * barwidth > width:
            width = len(self.vals) * barwidth
            self.win.resize(width, width)

        self.chartwidth = width - LEFTMARGIN
        self.chartheight = height - TOPMARGIN - BOTTOMMARGIN
        print(f"Chart size is {self.chartwidth} x {self.chartheight}")

        # How many seconds does the chart span?
        self.secrange = (self.times[-1] - self.times[0]).seconds
        self.first_timestamp = self.times[0].timestamp()

        # Get the Y range
        self.datamax = max(self.vals)

        def chartx(x):
            return x + LEFTMARGIN

        def charttime(t):
            """Convert datetime t to x in the window"""
            return LEFTMARGIN + (t.timestamp()
                         - self.first_timestamp) * self.chartwidth / self.secrange

        def charty(y):
            """0 at bottom, not top"""
            return self.chartheight + TOPMARGIN - y

        def chartdata(d):
            """0 at bottom, not top, scaled to data"""
            return self.chartheight + TOPMARGIN - (d * self.chartheight/self.datamax)

        # Fill the background
        cr.set_source_rgb(1., 1., 1.)
        cr.rectangle(0.0, 0.0, float(width), float(height))
        cr.fill()

        # Fill the bars
        cr.set_source_rgb(0., 0., 1.)
        for i, d in enumerate(self.vals):
            barheight = d * (self.chartheight/self.datamax)
            cr.rectangle(charttime(self.times[i]),
                         charty(barheight),
                         barwidth, barheight)
            cr.fill()

        # Draw a horizontal grid with vertical spacing of 5
        GRIDSPACING = 5
        cr.set_source_rgba(0., 0., 0., .5)
        cr.set_line_width(1)
        for i in range(0, int(self.datamax), 5):
            cr.move_to(LEFTMARGIN/2, chartdata(i) + 3)
            cr.line_to(chartx(self.chartwidth), chartdata(i))
            cr.stroke()

        # Labels
        cr.set_source_rgb(0., 0., 0.)
        cr.set_font_size(13)
        for i in range(0, int(self.datamax), 10):
            cr.move_to(3, chartdata(i) + 7)
            cr.show_text(str(i))

        # Vertical grid with spacing of 5 min
        # Round up to the next multiple of 5 minutes
        t = self.times[0] \
                .replace(second=0, microsecond=0,
                         minute=self.times[0].minute
                         - (self.times[0].minute % 5) + 5)

        ROTATION = pi * 1.65
        while True:
            if t > self.times[-1]:
                break
            cr.set_source_rgba(0., 0., 0., .5)
            x = charttime(t)
            cr.move_to(x, charty(0))
            cr.line_to(x, charty(self.chartheight))
            cr.stroke()

            # Label it
            cr.set_source_rgb(0., 0., 0.)
            label = t.astimezone().strftime("%H:%M")
            cr.move_to(x-10, charty(-38))
            cr.rotate(ROTATION)
            cr.show_text(label)
            cr.rotate(-ROTATION)

            t += timedelta(minutes=5)

    @staticmethod
    def nop(*args):
        """Do nothing."""
        return True

    def close_window(self, extra=None):
        self.win.destroy()


# For callers to use in a thread
def open_chart_window(data, label, chartqueue):
    print("Opening a chart for", label)
    win = ChartWindowGTK(data, label, chartqueue)


if __name__ == '__main__':
    dummydata = {
        "chartlabel": "hr",
        "ylabel": "hr",
        "data": {
            "2026-08-21T14:17:38Z": "54",
            "2026-08-21T14:17:43Z": "50",
            "2026-08-21T14:19:48Z": "54",
            "2026-08-21T14:19:54Z": "58",
            "2026-08-21T14:20:51Z": "0",
            "2026-08-21T14:20:57Z": "0",
            "2026-08-21T14:21:13Z": "60",
            "2026-08-21T14:21:19Z": "64",
            "2026-08-21T14:22:09Z": "71",
            "2026-08-21T14:22:31Z": "0",
            "2026-08-21T14:22:36Z": "0",
            "2026-08-21T14:23:22Z": "70",
            "2026-08-21T14:23:56Z": "69",
        } }
    win = ChartWindowGTK(dummydata, "Heart Rate")

