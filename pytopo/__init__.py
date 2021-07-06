#!/usr/bin/env python

'''pytopo module: display tiled maps from a variety of sources,
   along with trackpoints, waypoints and other useful information.

   Copyright 2005-2021 by Akkana Peck.
   Feel free to use, distribute or modify this program under the terms
   of the GPL v2 or, at your option, a later GPL version.
   I'd appreciate hearing about it if you make any changes.
'''

__version__ = "1.7"
__author__ = "Akkana Peck <akkana@shallowsky.com>"
__license__ = "GPL v2+"

# Hack to make relative imports work in Python 3 as well as Python 2:
import os, sys; sys.path.append(os.path.dirname(os.path.realpath(__file__)))

from .MapCollection import MapCollection
from .GenericMapCollection import GenericMapCollection
from .TopoMapCollection import TopoMapCollection
from .TopoMapCollection import Topo1MapCollection
from .TopoMapCollection import Topo2MapCollection
from .TiledMapCollection import TiledMapCollection
from .OSMMapCollection import OSMMapCollection
from .MapWindow import MapWindow
from .TrackPoints import TrackPoints
from .MapViewer import MapViewer, ArgParseException

# import trackstats


user_agent = "PyTopo " + __version__
