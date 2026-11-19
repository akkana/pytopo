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

from math import pi, log10, ceil

from datetime import datetime, timedelta, UTC

import sys


INIT_WIDTH = 800
INIT_HEIGHT = 600

GPSTIMEFMT = "%Y-%m-%dT%H:%M:%SZ"

LEFTMARGIN = 50
TOPMARGIN = 35
BOTTOMMARGIN = 60    # Room for date labels

# Text alignment
ALIGN_LEFT = -1
ALIGN_RIGHT = 1
ALIGN_TOP = 1
ALIGN_BOTTOM = -1
ALIGN_CENTER = 0


class ChartHandlerGTK:

    def __init__(self, map2chartqueue, chart2mapqueue):
        self.charts = {}
        self.map2chartqueue = map2chartqueue
        self.chart2mapqueue = chart2mapqueue

        GLib.timeout_add(1200, self.read_from_chart_queue)

        Gtk.main()

    def make_chart(self, indata):
        """Draw a chart with the given data.
           Expects a dictionary that looks something like:
           {
             'chartlabel': 'Speed profile',
             'ylabel': 'Speed',
             'times': [ datetime, datetime, ... ],
             'keys': [ 'GPX speed', 'Calculated speed' ],
             'vals: { 'GPX speed': [ 1.1, 3.4, ...],
                      'Calculated speed': [ 1.1, 3.4, ...] },
             'type': 'line',
           }
        """

        # Use the Y label as the key
        chartkey = indata['ylabel']

        self.charts[chartkey] = indata

        self.vline = None

        self.charts[chartkey]['surface'] = None

        win = Gtk.Window()
        self.charts[chartkey]['win'] = win

        win.set_name(self.charts[chartkey]['chartlabel'])
        win.set_title(self.charts[chartkey]['chartlabel'])
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
        timestamp = first_timestamp \
            + timedelta(seconds=(event.x - LEFTMARGIN) * secrange / chartwidth)
        self.chart2mapqueue.put(("click", timestamp, UTC))

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
            cr.set_source_rgb(1., .7, 0.)
            cr.set_line_width(2)
            x = self.timestamp_to_x(self.vline, chartkey)
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
        """Return first timestamp and end - start in seconds"""
        return (self.charts[key]['times'][0],
                (self.charts[key]['times'][-1]
                 - self.charts[key]['times'][0]).seconds)

    def timestamp_to_x(self, timestamp, chartkey):
        """Translate a timestamp to an X coordinate in the window"""
        first_timestamp, ts_range = self.get_timestamprange(chartkey)
        da_width, da_height, chart_width, chart_height = \
            self.get_da_and_chart_size(self.charts[chartkey]['drawingarea'])
        return (LEFTMARGIN
                + (self.vline - first_timestamp).seconds * chart_width / ts_range)

    def draw_chart(self, widget, surface):
        """Draw a chart of the given type.
        """
        # Get the containing GTK window:
        win = widget.get_toplevel()
        # In GTK4, get_toplevel is gone, replaced with:
        # win = widget.get_root()
        if not isinstance(win, Gtk.Window):
            print("Eek, win isn't a Gtk.Window")

        cr = cairo.Context(surface)
        winwidth, winheight, chartwidth, chartheight = \
            self.get_da_and_chart_size(widget)
        barwidth = 3

        chartkey = win.ylabel
        chart = self.charts[chartkey]
        times = chart['times']

        # Wow, named or HTML-style colors in cairo are a huge PITA!
        rgba = Gdk.RGBA()
        COLORS = []
        # matplotlib’s color-blind-friendly tab10 hex values:
        # for color in [ '#1f77b4', '#ff7f0e', '#2ca02c', '#d62728', '#9467bd',
        #                '#8c564b', '#e377c2', '#7f7f7f', '#bcbd22', '#17becf' ]:
        # They're not very contrasty, though. Revisit this issue.
        for color in [ 'blue', 'red', 'green', 'purple', 'cyan' ]:
            if rgba.parse(color):
                COLORS.append((rgba.red, rgba.green, rgba.blue))

        # Fill the background
        cr.set_source_rgb(1., 1., 1.)
        cr.rectangle(0.0, 0.0, float(winwidth), float(winheight))
        cr.fill()

        # Find the min/max of everything being plotted in this chart
        datamin = 1.e10;
        datamax = 0.
        for key in chart['vals'].keys():
            # Heart rate data is sparse, and 0 obviously isn't a real value.
            # Throw out any zeros.
            # But draw the chart from zero.
            chartmin = min(datamin, min(chart['vals'][key]))
            if key == 'hr':
                datamin = min([v for v in chart['vals'][key] if v])
            else:
                datamin = chartmin
            datamax = max(datamax, max(chart['vals'][key]))

        def chartx(x):
            return x + LEFTMARGIN

        def charttime(t):
            """Convert datetime t to x in the window"""
            return (LEFTMARGIN + (t - first_timestamp).seconds
                    * chartwidth / secrange)

        def charty(y):
            """0 at bottom, not top"""
            return chartheight + TOPMARGIN - y

        def chartdata(d):
            """0 at bottom, not top, scaled to data"""
            return (chartheight + TOPMARGIN
                    - ((d - chartmin) * chartheight/(datamax-chartmin)))

        for valnum, key in enumerate(chart['vals'].keys()):
            vals = chart['vals'][key]
            color = COLORS[valnum]

            # How many seconds does the chart span?
            first_timestamp, secrange = self.get_timestamprange(chartkey)

            cr.set_source_rgb(*color)

            if self.charts[chartkey]['charttype'] == 'bar':
                if len(vals) * barwidth > chartwidth:
                    if len(vals) < chartwidth:
                        barwidth = int(chartwidth/vals)
                    else:
                        print("Eek, chart isn't wide enough for the full bar graph")

                # Fill the bars
                cr.set_source_rgb(0., 0., 1.)
                for i, d in enumerate(vals):
                    barheight = int(d * (float(chartheight/datamax)))
                    cr.rectangle(charttime(times[i]),
                                 charty(barheight),
                                 # XXX charty works out to
                                 # height - BOTTOMMARGIN - barheight
                                 # as it should, but somehow, there are sometimes
                                 # a few pixels visible below the bottom of the bar.
                                 # Also chartdata(d) for barheight is too high.
                                 # Need to figure out why.
                                 barwidth, barheight)
                    cr.fill()

            elif self.charts[chartkey]['charttype'] == 'line':
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

        # Title at the top, centered
        self.show_text(self.charts[chartkey]['chartlabel']
                       + ' (max=%.2f, min=%.2f)' % (datamax, datamin),
                       chartwidth/2, TOPMARGIN/2, cr, ALIGN_CENTER, ALIGN_CENTER)

        # Date on the bottom
        self.show_text(times[0].strftime("%Y-%m-%d"),
                       chartwidth/2, winheight, cr, ALIGN_CENTER, ALIGN_BOTTOM)

        # Data Y label on the left. self.show_text doesn't handle rotation yet.
        cr.move_to(11, charty(chartheight/2))
        cr.rotate(-pi/2)
        cr.show_text(chartkey)
        cr.rotate(pi/2)

        # Y Labels
        cr.set_font_size(14)

        def roundstep(therange):
            # Calculate a reasonable spacing, nearest multiple of 10
            thestep = int(therange / 10)
            if thestep <= 0:
                thestep = 1
            pow10 = int(10 ** round(log10(thestep)))
            pow10_2 = pow10/2
            if abs(thestep - pow10_2) < abs(thestep - pow10):
                return pow10_2
            else:
                return pow10

        ystep = roundstep(datamax - chartmin)
        # XXX it's slightly wasteful to loop up from zero rather than calculating
        for i in range(0, round(datamax), round(ystep)):
            if i < chartmin:
                continue
            self.show_text(str(i), LEFTMARGIN-3, chartdata(i) + 7, cr,
                           ALIGN_RIGHT, ALIGN_CENTER)

        # Draw horizontal grid lines with vertical spacing of ystep or ystep/2
        if ystep % 2:
            gridspacing = int(ystep)
        else:
            gridspacing = int(ystep / 2)
        cr.set_source_rgba(0., 0., 0., .5)
        cr.set_line_width(1)
        for i in range(0, ceil(datamax), gridspacing):
            if i < chartmin:
                continue
            cr.move_to(LEFTMARGIN, chartdata(i) + 3)
            cr.line_to(chartx(chartwidth), chartdata(i))
            cr.stroke()

        # How many minutes does it span?
        totmins = (times[-1] - times[0]).seconds // 60
        timestep = roundstep(totmins)

        # For the first tic, round up to the next multiple of the timestep.
        t = times[0]
        modmin = times[0].minute % timestep
        if modmin:
           t  += timedelta(minutes=timestep-modmin)

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

            t += timedelta(minutes=timestep)

        if len(chart['vals'].keys()) > 1:
            LINEHEIGHT = 1.2   # multiplier
            BOXMARGIN = 8      # pixels

            cr.set_font_size(13)
            keys = list(chart['vals'].keys())
            # font_extents gives one consistent height for every line,
            # unlike text_extents, which varies with the letters (p, d, etc.)
            ascent, descent, fheight, _, _ = cr.font_extents()
            lineheight = fheight * LINEHEIGHT
            maxtwidth = max(cr.text_extents(k).x_advance for k in keys)

            rightedge = winwidth - ascent/2
            leftedge = rightedge - maxtwidth - BOXMARGIN*2
            topedge = ascent/2
            bottomedge = topedge + len(keys) * lineheight + BOXMARGIN
            bottomedge = topedge + BOXMARGIN*2 \
                + (len(keys) - 1) * lineheight + ascent

            # Fill
            cr.set_source_rgb(1, 1, .9)
            cr.rectangle(leftedge, topedge,
                         rightedge - leftedge, bottomedge - topedge)
            cr.fill()

            # Outline (rectangle() makes a closed path, so all 4 sides draw)
            cr.set_source_rgb(0, 0, 0)
            cr.set_line_width(3)
            cr.rectangle(leftedge, topedge,
                         rightedge - leftedge, bottomedge - topedge)
            cr.stroke()

            # Labels: y is the baseline, so start at top + padding + ascent
            for valnum, key in enumerate(keys):
                cr.set_source_rgb(*COLORS[valnum])
                self.show_text(key, rightedge - BOXMARGIN,
                               topedge + BOXMARGIN + valnum * lineheight,
                               cr, ALIGN_RIGHT, ALIGN_TOP)

    def show_text(self, text, x, y, cr,
                  halign=ALIGN_LEFT, valign=ALIGN_BOTTOM):
        # FOR DEBUGGING: draw an X at x, y
        # CROSSSIZE = 6
        # cr.set_line_width(1)
        # cr.move_to(x-CROSSSIZE, y-CROSSSIZE)
        # cr.line_to(x+CROSSSIZE, y+CROSSSIZE)
        # cr.move_to(x-CROSSSIZE, y+CROSSSIZE)
        # cr.line_to(x+CROSSSIZE, y-CROSSSIZE)
        # cr.stroke()

        xbearing, ybearing, width, height, xadv, yadv = cr.text_extents(text)

        if halign == ALIGN_CENTER:
            x -= xadv / 2
        elif halign == ALIGN_RIGHT:
            x -= xadv

        if valign == ALIGN_TOP:
            y -= ybearing
        elif valign == ALIGN_CENTER:
            y -= ybearing + height / 2
        # VAlign.BOTTOM: y is already the baseline

        cr.move_to(x, y)
        cr.show_text(text)

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

