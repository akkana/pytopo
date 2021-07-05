# PyTopo

PyTopo is a tiled map viewer and a track log viewer/editor.

[![PyTopo screenshot](http://shallowsky.com/software/topo/screenshots/bandelier-ssT.jpg)](http://shallowsky.com/software/topo/screenshots/bandelier-ss.jpg)
[![PyTopo screenshot](https://shallowsky.com/software/topo/screenshots/ownership_overlay-ssT.jpg)](https://shallowsky.com/software/topo/screenshots/ownership_overlay-ss.jpg)

Downloaded map tiles are cached locally, so you can use PyTopo offline
if you've already cached the tiles for an area.

See the project home page at http://shallowsky.com/software/topo/
for more information, examples, screenshots, hints on creating
custom maps, and more.

Or read the official documentation here:
https://pytopo.readthedocs.io/en/latest/

By default, PyTopo uses tiles from OpenStreetMap, but you can specify
a variety of tile sources (for some you'll have to set up an API key).
Or you can create your own tiles.
It can also use tiles from a few commercial programs like the old
*National Geographic Topo!*

The package also includes ellie, a simple script for reporting and
plotting distance and elevation change statistics from a GPX track log.
More information: http://shallowsky.com/software/ellie/

## Track Logs, Waypoints and Overlays

PyTopo can read track logs in GPX, KML, KMZ or geojson format,
and polygon overlay files in geojson.

You can make simple edits to tracks, like splitting a track into parts
or deleting to the beginning or end point, and can save the resulting
tracks as GPX.

Select a track by left-clicking on it;
split a track or delete everything before or after the mouse
(right-click context menu again),
and save a track as GPX after you've changed it.

You can also provide polygonal overlays from a GeoJSON file:
for example, to colorize areas according to land ownership
or geology.

PyTopo can also measure distances and bearing angles between points
(shift-click and watch standard output), or report the coordinates at
any point (right-click gives the coordinates at the top of the context
menu; if you want to copy/paste, choose that menu item to print it to
standard output).

## Pinning

You can "Pin" a spot on the map and save it as a pinned location
in your PyTopo configuration.

## Installing and Dependencies

You can install the current stable version of PyTopo with
```pip install pytopo```

Dependencies include

* GTK (and its various dependencies, like pango and cairo)
* requests-futures (for downloading map tiles in the background)
* simplejson (for reading XML-based formats like GPX and KML)

Optional dependencies include

* numpy (optional, for analyzing track statistics like distance)
* matplotlib (optional, for Ellie's track log visualizations)
* shapely (optional, used for polygonal overlays)
* gpsd and python-gps (to read from a GPS device)

The first time you run pytopo, it will create a \~/.config/pytopo
directory for its configuration files, and a \~/Maps directory for
cached map tiles. (To change the location of cached tiles,
edit *\~/.config/pytopo/pytopo.sites*. Sorry, there's no GUI for that.)

## Other Info

pytopo -h gives usage examples.

If you need custom maps., edit *\~/.config/pytopo/pytopo.sites* to add new
map Collections: see examples in that file or on the project home page.

Code contributions appreciated!

## Tests and Documentation

The official documentation is at
https://pytopo.readthedocs.io/en/latest/
(automatically generated from the docs/sphinx directory).

To build the documentation locally:

```
python setup.py build_sphinx
```

or

```
cd sphinxdoc
make html
```

There are some unit tests in the test/ directory;
run them with
    python -m unittest discover
from the top-level directory.

Happy mapping!
