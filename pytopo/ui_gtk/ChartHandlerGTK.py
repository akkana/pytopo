#!/usr/bin/env python3

"""Draw charts related to Pytopo.
   This is intended to be run in a separate thread,
   It will communicate with the calling window.
   It can handle multiple charts, each in a separate window.
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

import queue

from math import pi

from datetime import datetime, timezone, timedelta

import sys


INIT_WIDTH = 800
INIT_HEIGHT = 600

GPSTIMEFMT = "%Y-%m-%dT%H:%M:%SZ"

LEFTMARGIN = 50
TOPMARGIN = 35
BOTTOMMARGIN = 60    # Room for date labels


class ChartHandlerGTK:

    def __init__(self, map2chartqueue, chart2mapqueue):
        self.charts = {}
        self.map2chartqueue = map2chartqueue
        self.chart2mapqueue = chart2mapqueue

        GLib.timeout_add(1200, self.read_from_chart_queue)

        Gtk.main()

    def make_chart(self, indata):
        # print("Making a new chart of", indata['ylabel'])

        # Use the Y label as the key
        chartkey = indata['ylabel']

        self.charts[chartkey] = {}

        self.charts[chartkey]['title'] = indata['chartlabel']
        self.charts[chartkey]['charttype'] = indata['type']

        # data['data'] is a dict of time: value, both as strings
        self.charts[chartkey]['times'] = []
        self.charts[chartkey]['vals'] = []
        for t in indata['data']:
            # UTC datetime
            self.charts[chartkey]['times'].append(
                datetime.strptime(t, GPSTIMEFMT).replace(
                tzinfo=timezone.utc
            ))
            self.charts[chartkey]['vals'].append(float(indata['data'][t]))

        self.vline = None

        self.charts[chartkey]['surface'] = None

        win = Gtk.Window()
        self.charts[chartkey]['win'] = win

        win.set_name(self.charts[chartkey]['title'])
        win.set_title(self.charts[chartkey]['title'])
        win.connect("destroy", self.close_window)
        win.set_border_width(5)

        win.ylabel = chartkey

        vbox = Gtk.VBox(spacing=3)
        self.charts[chartkey]['win'].add(vbox)

        drawing_area = Gtk.DrawingArea()
        self.charts[chartkey]['drawingarea'] = drawing_area
        vbox.pack_start(drawing_area, True, True, 0)

        drawing_area.set_events(Gdk.EventMask.EXPOSURE_MASK |
                                Gdk.EventMask.BUTTON_PRESS_MASK)

        drawing_area.connect('draw', self.draw)

        drawing_area.connect("button-press-event", self.mousepress)
        # The default focus in/out handlers on drawing area cause
        # spurious expose events.  Trap the focus events, to block that:
        drawing_area.connect("focus-in-event", self.nop)
        drawing_area.connect("focus-out-event", self.nop)

        # Handle key presses on the drawing area.
        drawing_area.set_property('can-focus', True)
        drawing_area.connect("key-press-event", self.key_press_event)

        # This has to happen before setting configure_event
        win.show_all()

        # Size changes
        drawing_area.connect("configure-event", self.on_configure)

        # Resize after connecting the configure handler,
        # and after show_all(), otherwise size spuriously enlarges a lot.
        win.resize(INIT_WIDTH, INIT_HEIGHT)

    def read_from_chart_queue(self):
        """Listen for messages from a chart window. Upon seeing one,
           show the nearest trackpoint in the map window.
        """
        if not self.map2chartqueue:
            return False
        try:
            # print("ChartHandler checking chartqueue...")
            msg = self.map2chartqueue.get(block=False)
            if msg == "EXIT":
                Gtk.main_quit()
                return
            if 'chartlabel' in msg and 'ylabel' in msg:
                self.make_chart(msg)
            else:
                print("ChartHandler: Didn't understand message", msg,
                      "type", type(msg),
                      file=sys.stderr)
            return True
        except queue.Empty:
            # Nothing to read
            return True

    def key_press_event(self, widget, event):
        """Handle key presses"""
        if event.string == "q":
            self.close_window(widget)

    def mousepress(self, drawingarea, event):
        """Handle mouse button presses"""
        if event.button != 1:
            return

        chartkey = drawingarea.get_toplevel().ylabel
        width, height, chartwidth, chartheight = \
            self.get_da_and_chart_size(drawingarea)
        first_timestamp, secrange = self.get_timestamprange(chartkey)

        # Figure out the time corresponding to where the mouse was pressed
        timestamp = (event.x - LEFTMARGIN) \
            * secrange / chartwidth + first_timestamp
        self.chart2mapqueue.put(("click", datetime.utcfromtimestamp(timestamp)))

        self.vline = timestamp

        for key in self.charts:
            self.charts[key]['drawingarea'].queue_draw()

    def draw(self, widget, cr):
        chartkey = widget.get_toplevel().ylabel
        if self.charts[chartkey]['surface']:
            cr.set_source_surface(self.charts[chartkey]['surface'], 0, 0)
            cr.paint()
        else:
            print("No cached surface")

        if self.vline:
            first_timestamp, ts_range = self.get_timestamprange(chartkey)
            da_width, da_height, chart_width, chart_height = \
                self.get_da_and_chart_size(widget)
            cr.set_source_rgb(1., 0., 0.)
            cr.set_line_width(2)
            x = LEFTMARGIN \
                + (self.vline - first_timestamp) * chart_width / ts_range
            cr.move_to(x, TOPMARGIN)
            cr.line_to(x, widget.get_allocated_height() - BOTTOMMARGIN)
            cr.stroke()

        return False

    # Window resize
    def on_configure(self, widget, cr):
        chartkey = widget.get_toplevel().ylabel
        width = widget.get_allocated_width()
        height = widget.get_allocated_height()
        # print("on_configure: allocated size", width, height)
        self.charts[chartkey]['surface'] = cairo.ImageSurface(
            cairo.FORMAT_ARGB32, width, height)
        self.draw_chart(widget, self.charts[chartkey]['surface'])

        self.vline = None

        return False

    def get_da_and_chart_size(self, widget):
        """Return da_width, da_height, chart_width, chart_height"""
        width, height = widget.get_window().get_geometry()[2:4]
        return (width, height,
                width - LEFTMARGIN, height - TOPMARGIN - BOTTOMMARGIN)

    def get_timestamprange(self, key):
        """Return first timestamp and range of timestamps (end - start)"""
        return (self.charts[key]['times'][0].timestamp(),
                (self.charts[key]['times'][-1]
                 - self.charts[key]['times'][0]).seconds)

    def draw_chart(self, widget, surface):
        """Draw a chart of the given type
        """
        # Get the containing GTK window:
        win = widget.get_toplevel()
        # In GTK4, get_toplevel is gone, replaced with:
        # win = widget.get_root()
        if not isinstance(win, Gtk.Window):
            print("Eek, win isn't a Gtk.Window")

        chartkey = win.ylabel
        chart = self.charts[chartkey]
        times = chart['times']
        vals = chart['vals']

        cr = cairo.Context(surface)
        width, height, chartwidth, chartheight = \
            self.get_da_and_chart_size(widget)
        barwidth = 3
        if len(vals) * barwidth > width:
            width = len(vals) * barwidth
            win.resize(width, width)

        # How many seconds does the chart span?
        first_timestamp, secrange = self.get_timestamprange(chartkey)

        # Get the Y range
        datamin = min(vals)
        datamax = max(vals)

        def chartx(x):
            return x + LEFTMARGIN

        def charttime(t):
            """Convert datetime t to x in the window"""
            return (LEFTMARGIN + (t.timestamp() - first_timestamp)
                    * chartwidth / secrange)

        def charty(y):
            """0 at bottom, not top"""
            return chartheight + TOPMARGIN - y

        def chartdata(d):
            """0 at bottom, not top, scaled to data"""
            return (chartheight + TOPMARGIN
                    - ((d - datamin) * chartheight/(datamax-datamin)))

        # Fill the background
        cr.set_source_rgb(1., 1., 1.)
        cr.rectangle(0.0, 0.0, float(width), float(height))
        cr.fill()

        if self.charts[chartkey]['charttype'] == 'bar':
            # Fill the bars
            cr.set_source_rgb(0., 0., 1.)
            for i, d in enumerate(vals):
                barheight = d * (chartheight/datamax)
                cr.rectangle(charttime(times[i]),
                             charty(barheight),
                             # XXX charty works out to
                             # height - BOTTOMMARGIN - barheight
                             # as it should, but somehow, there are sometimes
                             # a few pixesl visible below the bottom of the bar.
                             # Need to figure out why.
                             barwidth, barheight)
                cr.fill()
        elif self.charts[chartkey]['charttype'] == 'line':
            cr.set_source_rgba(0., 0., 1., 1.)
            cr.set_line_width(2)
            lastx = 0
            lasty = 0
            for i, d in enumerate(vals):
                x = charttime(times[i])
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
        cr.move_to(chartwidth/2, TOPMARGIN/2)
        cr.show_text(self.charts[chartkey]['title'])

        # Date on the bottom
        cr.move_to(chartx(chartwidth/2) - 50, height - 5)
        cr.show_text(times[0].strftime("%Y-%m-%d"))

        # Data Y label on the left
        cr.move_to(11, charty(chartheight/2))
        cr.rotate(-pi/2)
        cr.show_text(chartkey)
        cr.rotate(pi/2)

        # Y Labels
        cr.set_font_size(14)
        for i in range(0, int(datamax), 10):
            if i < datamin:
                continue
            cr.move_to(LEFTMARGIN - 25, chartdata(i) + 7)
            cr.show_text(str(i))

        # Draw horizontal grid lines with vertical spacing of 5
        # XXX adjust spacing to data
        GRIDSPACING = 5
        cr.set_source_rgba(0., 0., 0., .5)
        cr.set_line_width(1)
        for i in range(0, int(datamax), 5):
            if i < datamin:
                continue
            cr.move_to(LEFTMARGIN, chartdata(i) + 3)
            cr.line_to(chartx(chartwidth), chartdata(i))
            cr.stroke()

        # Vertical grid with spacing of 5 min.
        # For the first tic, round up to the next multiple of 5 minutes.
        t = times[0]
        modmin = times[0].minute % 5
        if modmin:
           t  += timedelta(minutes=5-modmin)

        # X axis grid lines and labels
        ROTATION = pi * 1.65
        while True:
            if t > times[-1]:
                break
            cr.set_source_rgba(0., 0., 0., .5)
            x = charttime(t)
            cr.move_to(x, charty(0))
            cr.line_to(x, charty(chartheight))
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

    def close_window(self, widget):
        # Somehow, this gets called twice. I'm not sure why,
        # but it currently doesn't seem to cause any harm.

        win = widget.get_toplevel()

        if win.ylabel in self.charts:
            del self.charts[win.ylabel]

        win.destroy()

        if not self.charts:
            # print(win.ylabel, "was the last chart: quitting GTK session")
            self.chart2mapqueue.put("exiting")
            Gtk.main_quit()


# For callers to use in a thread
def start_chart_handler(map2chartqueue, chart2mapqueue):
    chartthread = ChartHandlerGTK(map2chartqueue, chart2mapqueue)


if __name__ == '__main__':
    # This doesn't currently do anything useful, don't bother running it
    dummydata = {
        "chartlabel": "Heart Rate",
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

    chartthread = ChartThreadGTK(None)
    # win = chartthread.make_chart(dummydata)

