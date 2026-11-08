#!/usr/bin/env python3

from unittest import mock
import requests
import time
import sys

sys.path.insert(0, '..')

from pytopo.OSMMapCollection import OSMMapCollection
from pytopo.ui_gtk.MapWindowGTK import MapWindowGTK


def slow_timeout_send(self, request, **kwargs):
    """Stand-in for Session.send: block for the requested timeout, then fail."""
    timeout = kwargs.get("timeout")
    print(f"[{time.monotonic():.1f}] send called, timeout={timeout}",
          flush=True)
    if timeout is None:
        raise AssertionError("code under test made a request with no timeout")
    if isinstance(timeout, tuple):          # (connect, read)
        timeout = timeout[0]
    time.sleep(timeout)
    print(f"[{time.monotonic():.1f}] send raising", flush=True)
    raise requests.exceptions.ConnectTimeout(
        f"simulated timeout after {timeout}s", request=request)


class DummyController:
    def __init__(self):
        self.Debug = False

    def main(self):
        with mock.patch.object(requests.Session, "send", slow_timeout_send):
            self.collection = OSMMapCollection("test", "test/files/Maps/test",
                                               ".png", 256, 256, 10,
                                       "https://example.com/{z}/{x}/{y}.png",
                                               maxzoom=22,
                                               attribution="Test maps")
            self.mapwin = MapWindowGTK(self)

            self.mapwin.collection = self.collection
            self.collection.mapwin = self.mapwin

            self.mapwin.center_lon = -106.1794532
            self.mapwin.center_lat = 35.8267128

            self.mapwin.show_window(600, 400)

    def save_sites(self):
        print("Not saving any sites")


if __name__ == '__main__':
    controller = DummyController()
    controller.main()

