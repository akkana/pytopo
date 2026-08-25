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

LEFTMARGIN = 50
TOPMARGIN = 35
BOTTOMMARGIN = 60    # Room for date labels


class ChartWindowGTK:

    def __init__(self, data, chartqueue=None):
        # data['data'] is a dict of time: value, both as strings
        self.times = []
        self.vals = []
        for t in data['data']:
            # UTC datetime
            self.times.append(datetime.strptime(t, GPSTIMEFMT).replace(
                tzinfo=timezone.utc
            ))
            self.vals.append(float(data['data'][t]))

        self.title = data['chartlabel']
        self.ylabel = data['ylabel']

        self.charttype = data['type']

        self.chartqueue = chartqueue

        self.vline = None

        self.cached_surface = None

        self.win = Gtk.Window()
        self.win.set_name(self.title)
        self.win.set_title(self.title)
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
        self.chartqueue.put(("click", datetime.utcfromtimestamp(timestamp)))

    def draw(self, widget, cr):
        if self.cached_surface:
            cr.set_source_surface(self.cached_surface, 0, 0)
            cr.paint()
        else:
            print("No cached surface")

        if self.vline:
            cr.set_source_rgb(1., 0., 0.)
            cr.set_line_width(2)
            cr.move_to(self.vline, TOPMARGIN)
            cr.line_to(self.vline, widget.get_allocated_height() - BOTTOMMARGIN)
            cr.stroke()

        return False

    # Window resize
    def on_configure(self, widget, cr):
        width = widget.get_allocated_width()
        height = widget.get_allocated_height()
        self.cached_surface = cairo.ImageSurface(cairo.FORMAT_ARGB32,
                                                 width, height)
        self.draw_chart(widget, self.cached_surface)

        self.vline = None

        return False

    def draw_chart(self, widget, surface):
        """Draw a chart of the given type
        """
        cr = cairo.Context(surface)
        width, height = self.get_size()
        barwidth = 3
        if len(self.vals) * barwidth > width:
            width = len(self.vals) * barwidth
            self.win.resize(width, width)

        self.chartwidth = width - LEFTMARGIN
        self.chartheight = height - TOPMARGIN - BOTTOMMARGIN

        # How many seconds does the chart span?
        self.secrange = (self.times[-1] - self.times[0]).seconds
        self.first_timestamp = self.times[0].timestamp()

        # Get the Y range
        self.datamin = min(self.vals)
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
            return (self.chartheight + TOPMARGIN
                    - ((d - self.datamin)
                       * self.chartheight/(self.datamax-self.datamin)))

        # Fill the background
        cr.set_source_rgb(1., 1., 1.)
        cr.rectangle(0.0, 0.0, float(width), float(height))
        cr.fill()

        if self.charttype == 'bar':
            # Fill the bars
            cr.set_source_rgb(0., 0., 1.)
            for i, d in enumerate(self.vals):
                barheight = d * (self.chartheight/self.datamax)
                cr.rectangle(charttime(self.times[i]),
                             charty(barheight),
                             # XXX charty works out to
                             # height - BOTTOMMARGIN - barheight
                             # as it should, but somehow, there are sometimes
                             # a few pixesl visible below the bottom of the bar.
                             # Need to figure out why.
                             barwidth, barheight)
                cr.fill()
        elif self.charttype == 'line':
            cr.set_source_rgba(0., 0., 1., 1.)
            cr.set_line_width(2)
            lastx = 0
            lasty = 0
            for i, d in enumerate(self.vals):
                x = charttime(self.times[i])
                y = chartdata(d)
                if lastx and lasty:
                    cr.move_to(lastx, lasty)
                    cr.line_to(x, y)
                    cr.stroke()
                lastx = x
                lasty = y

        # Graph title and axis labels
        cr.set_source_rgb(0., 0., 0.)
        cr.set_font_size(15)

        # Title at the top
        cr.move_to(self.chartwidth/2, TOPMARGIN/2)
        cr.show_text(self.title)

        # Date on the bottom
        cr.move_to(chartx(self.chartwidth/2) - 50, height - 5)
        cr.show_text(self.times[0].strftime("%Y-%m-%d"))

        # Data Y label on the left
        cr.move_to(8, charty(self.chartheight/2))
        cr.rotate(-pi/2)
        cr.show_text(self.ylabel)
        cr.rotate(pi/2)

        # Y Labels
        cr.set_font_size(14)
        for i in range(0, int(self.datamax), 10):
            if i < self.datamin:
                continue
            cr.move_to(LEFTMARGIN - 25, chartdata(i) + 7)
            cr.show_text(str(i))

        # Draw horizontal grid lines with vertical spacing of 5
        # XXX adjust spacing to data
        GRIDSPACING = 5
        cr.set_source_rgba(0., 0., 0., .5)
        cr.set_line_width(1)
        for i in range(0, int(self.datamax), 5):
            if i < self.datamin:
                continue
            cr.move_to(LEFTMARGIN, chartdata(i) + 3)
            cr.line_to(chartx(self.chartwidth), chartdata(i))
            cr.stroke()

        # Vertical grid with spacing of 5 min
        # Round up to the next multiple of 5 minutes
        t = self.times[0] \
                .replace(second=0, microsecond=0,
                         minute=self.times[0].minute
                         - (self.times[0].minute % 5) + 5)

        # X axis grid lines and labels
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
            cr.move_to(x-10, charty(-40))
            cr.rotate(ROTATION)
            cr.show_text(label)
            cr.rotate(-ROTATION)

            t += timedelta(minutes=5)

    @staticmethod
    def nop(*args):
        """Do nothing."""
        return True

    def close_window(self, extra=None):
        # Somehow, this is getting called multiple times, and self.chartqueue
        # is getting set to null which causes this, and the whole exiting
        # process, to fail. Guard against that:
        try:
            self.chartqueue.put("exiting")
        except Exception as e:
            # print("chartqueue is gone:", e)
            pass
        self.win.destroy()
        Gtk.main_quit()


# For callers to use in a thread
def open_chart_window(data, chartqueue):
    win = ChartWindowGTK(data, chartqueue)


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

