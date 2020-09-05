# PyTopo

PyTopo is a tiled map viewer and a track log viewer/editor.

![PyTopo screenshot, Bandelier National Monument](http://shallowsky.com/software/topo/screenshots/bandelier-ssT.jpg "PyTopo Screenshot")

Downloaded map tiles are cached locally, so you can use PyTopo offline
if you've already cached the tiles for an area.

See the project home page at http://shallowsky.com/software/topo
for more information, examples, screenshots, hints on creating
custom maps, and more.

Or read the official documentation here:
https://pytopo.readthedocs.io/en/latest/

By default, PyTopo uses tiles from OpenStreetMap, but you can specify
a variety of tile sources (which may or may not require API keys);
or you can create your own tiles.
It can also use tiles from a few commercial programs like the old
National Geographic Topo!

The package also includes ellie, a simple script for reporting and
plotting distance and elevation change statistics from a GPX track log.
More information: http://shallowsky.com/software/ellie/

## Track Logs and Waypoints

PyTopo can read track logs in GPX, KML, KMZ or geojson format.
It can make simple edits, like splitting a track or deleting to
the begin or end point and can save as GPX.

It can also measure distances and bearing angles between points,
or report the coordinates of a point.

## Installing and Dependencies

You can install PyTopo with ```pip install pytopo```

Dependencies include GTK (and its various dependencies),
requests-futures (for downloading map tiles in the background),
simplejson (for reading GPX and KML files)
and numpy (for analyzing track statistics like distance),
and optionally matplotlib (for Ellie's track log visualizations).
If you want to read from a GPS, you'll need gpsd and python-gps.

The first time you run pytopo, it will create a ~/.config/pytopo
directory for its configuration files, and a ~/Maps directory for
map data.

## Other Info

pytopo -h gives usage examples.

If you need custom maps., edit ~/.config/pytopo/pytopo.sites to add new
map Collections (see examples in that file or on the project home page).

Code contributions appreciated!

## Tests and Documentation

There are some unit tests in the test/ directory;
run them with
    python -m unittest discover
from the top-level directory.

The docs directory contains documentation on the two apps and the API.
To build the documentation:

```
python setup.py build_sphinx
```

or

```
cd sphinxdoc
make html
```

Happy mapping!
