#!/usr/bin/env python3


"""The base MapWindow class is intended to be overridden by a
   UI-specific class, like MapWindowGTK.
   This base class contains functions that non-GTK classes might reference,
   which a GUI class must define.
"""

import sys

# For mypy
from typing import Any


class MapWindow(object):
    def __init__(self, _controller):
        self.controller = _controller

        # Variables to keep MyPy happy. Inheritors should define these usefully.
        self.center_lon:float = 0.
        self.center_lat:float = 0.
        self.win_width:int = 800
        self.win_height:int = 600
        self.controller:Any = None

    if TYPE_CHECKING:
        def __getattr__(self, name: str) -> Any:
            print(name, "doesn't exist in the base MapWindow")

    def load_image_from_file(self, path):
        print("Sorry, load_image_from_file isn't defined in base MapWindow",
              file=sys.stderr)

    def idle_add(self, fcn, *args):
        """Call a function at the next convenient opportunity.
           GUI subclasses will need to implement this using an
           appropriate idle function; see MapWindowGTK.
        """
        fcn(*args)
