#!/usr/bin/env python3


"""The base MapWindow class is intended to be overridden by a
   UI-specific class, like MapWindowGTK.
   This base class contains functions that non-GTK classes might reference,
   which a GUI class must define.
"""


class MapWindow(object):
    def __init__(self, _controller):
        self.controller = _controller

    def load_image_from_file(path):
        print("Sorry, load_image_from_file isn't defined in base MapWindow",
              file=sys.stderr)

    def idle_add(fcn, *args):
        """Call a function at the next convenient opportunity.
           GUI subclasses will need to implement this using an
           appropriate idle function; see MapWindowGTK.
        """
        fcn(*args)
