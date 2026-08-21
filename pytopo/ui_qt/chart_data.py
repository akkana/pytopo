#!/usr/bin/env python3

"""PyQtGraph 'plot' window showing data, coordinating with the MapWindow.

Runs as the CLIENT: it connects to PyTopo's socket server. Click
anywhere on the plot to move the crosshair and send the corresponding
time back to the map process. Incoming cursor updates from the map
process move the crosshair here too.

Run map_demo.py first, then this.

Requires: pyqtgraph, PyQt5 (or PySide2/PySide6 - pyqtgraph works with
either), numpy. e.g. `pip install pyqtgraph PyQt5 numpy`.
"""
import socket
import sys
from datetime import datetime, timezone, timedelta
import json

import numpy as np
import pyqtgraph as pg
from pyqtgraph.Qt import QtCore, QtWidgets
from PyQt6.QtGui import QShortcut, QKeySequence

import chart_protocol


class Bridge(QtCore.QObject):
    """Relays socket-thread messages onto the Qt main thread as a signal.
    pyqtgraph's Qt shim aliases Signal/pyqtSignal, so this works whether
    the installed backend is PyQt5 or PySide.
    """
    message = QtCore.Signal(dict)

''' The JSON looks like:
{ 'chartlabel': key,
  'ylabel': key,
  'data': {}
}
'''

GPSTIMEFMT = "%Y-%m-%dT%H:%M:%SZ"

class ChartWindow(QtWidgets.QMainWindow):
    def __init__(self):
        super().__init__()

        self.read_data()

        self.setWindowTitle(self.chartlabel)
        self.resize(800, 400)

        axis = pg.DateAxisItem(orientation='bottom')
        self.plot_widget = pg.PlotWidget(axisItems={'bottom': axis})
        self.setCentralWidget(self.plot_widget)

        # Quit on Q or Ctrl-Q
        QShortcut(QKeySequence("Q"), self, activated=self.close)
        QShortcut(QKeySequence("Ctrl+Q"), self, activated=self.close)

        # Line graph
        # self.plot_widget.plot(self.xs, self.ys, pen="y")

        xs = self.xs
        # But for sparse HR data, a bar graph makes more sense.
        # Use variable width bars, starting with the gap to the next point
        # but capping the maximum bar width so they don't get too wide.
        diffs = np.diff(xs)
        typical = np.median(diffs)
        widths = np.minimum(diffs, typical * 3)
        widths = np.append(widths, typical)

        bars = pg.BarGraphItem(x=xs, height=self.ys, width=widths, brush="y")
        self.plot_widget.addItem(bars)

        self.vline = pg.InfiniteLine(angle=90, movable=False, pen="r")
        self.vline.setPos(self.xs[0])
        self.plot_widget.addItem(self.vline)

        self.plot_widget.scene().sigMouseClicked.connect(self.on_click)

        # Set up communications to the calling process
        try:
            self.bridge = Bridge()
            self.bridge.message.connect(self.on_message_main)

            self.sock = socket.create_connection(("127.0.0.1",
                                                  chart_protocol.DEFAULT_PORT))
            chart_protocol.start_recv_thread(self.sock, self._on_message_bg)
        except:
            self.bridge = None
            self.sock = None

    def read_data(self, filename='/tmp/data.json'):
        with open(filename) as fp:
            jdata = json.load(fp)

        self.chartlabel = jdata['chartlabel']
        self.ylabel = jdata['ylabel']

        # Convert GPX UTC dates to local dates/times
        self.xs = []
        self.ys = []
        self.start_time = None
        self.end_time = None
        for datekey in jdata['data']:
            utc_dt = datetime.strptime(datekey, GPSTIMEFMT).replace(
                tzinfo=timezone.utc
            )
            # local_dt = utc_dt.astimezone()  # system-local timezone
            self.xs.append(utc_dt.timestamp())
            if not self.start_time:
                self.start_time = utc_dt
            self.ys.append(float(jdata['data'][datekey]))
        self.end_time = utc_dt

        self.xs = np.array(self.xs)
        self.ys = np.array(self.ys)

    def _on_message_bg(self, msg):
        # Called from the socket thread - re-emit as a Qt signal so the
        # slot below runs on the GUI thread instead of the socket thread.
        self.bridge.message.emit(msg)

    def on_message_main(self, msg):
        if msg.get("type") == "cursor":
            frac = msg.get("frac")
            if frac is not None:
                self.vline.setPos(frac * TOTAL_SECONDS)

    def on_click(self, event):
        vb = self.plot_widget.getPlotItem().vb
        point = vb.mapSceneToView(event.scenePos())
        click_seconds = max(self.start_time.timestamp(),
                            min(self.end_time.timestamp(), point.x()))
        self.vline.setPos(click_seconds)

        if not self.sock:
            return

        t = datetime.fromtimestamp(click_seconds,
                                   tz=timezone.utc).strftime(GPSTIMEFMT)
        try:
            chart_protocol.send_message(self.sock, {"type": "cursor",
                                                    "time": t})
        except OSError:
            pass


def main():
    app = QtWidgets.QApplication(sys.argv)
    win = ChartWindow()
    win.show()
    # win.raise_()
    # win.activateWindow()
    # Qt6 bindings (PyQt6/PySide6) only have exec(); Qt5 bindings
    # (PyQt5/PySide2) only have exec_(). Support both.
    run = getattr(app, "exec", None) or app.exec_
    sys.exit(run())


if __name__ == "__main__":
    main()

