#!/usr/bin/env python

'''pytopo module: display tiled maps from a variety of sources,
   along with trackpoints, waypoints and other useful information.

   Copyright 2005 - 2016 by Akkana Peck, akkana@shallowsky.com
   Please feel free to use, distribute or modify this program
   under the terms of the GPL v2 or, at your option, a later GPL version.
   I'd appreciate hearing about it if you make any changes.
'''

__version__ = "1.4"
__author__ = "Akkana Peck <akkana@shallowsky.com>"
__license__ = "GPL v2+"
__all__ = ['Mapping', 'Cartography']

from MapCollection import MapCollection
from GenericMapCollection import GenericMapCollection
from TopoMapCollection import TopoMapCollection
from TopoMapCollection import Topo1MapCollection
from TopoMapCollection import Topo2MapCollection
from TiledMapCollection import TiledMapCollection
from OSMMapCollection import OSMMapCollection
from DownloadTileQueue import DownloadTileQueue
from MapWindow import MapWindow
from TrackPoints import TrackPoints
from MapViewer import MapViewer
# import trackstats
