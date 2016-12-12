.. PyTopo documentation master file, created by
   sphinx-quickstart on Sun Dec 11 16:05:29 2016.
   You can adapt this file completely to your liking, but it should at least
   contain the root `toctree` directive.

================================================================
PyTopo:
================================================================
A viewer for tiled maps, plus track and waypoint files.
================================================================

.. toctree::
   :maxdepth: 2

*PyTopo* is an open source tiled map viewer,
written in Python and GRK. It can download and cache tiles from
OpenStreetMap or other map tile servers, or you can make your own
local tiled maps or use commercial datasets.

PyTopo can also show tracks and waypoints in several different formats,
can save favorite places, and has some rudimentary track editing ability.

==========
Installing
==========

PyTopo is available on PyPI::

  pip install pytopo

It requires PyGTK.
On Linux, you can get PyGTK through your distro;
On Windows, you can use *pip install pygtk*.
Mac is tricky since it has dependencies: the easiest way to get PyGTK
may be to install `GIMP <http://gimp.org/>`_, which comes with PyGTK.

Once you've installed the package, the command to run is *pytopo*.

`PyTopo's source is hosted on GitHub <https://github.com/akkana/pytopo>`_
if you want the latest and greatest.


============
Using PyTopo
============

The first time you run pytopo, it will create a configuration file:
on Linux that is
*~/.config/pytopo/pytopo.sites*

You might want to take a look at the file: this is where you can add
additional map collections or sites you visit frequently.
By default, pytopo will download OpenStreetMap tiles to ~/Maps.
Of course, you can change that.
See the
`PyTopo File Formats <http://shallowsky.com/software/topo/fileformats.html>`_
page for more details.

**pytopo -p** will print out a list of known sites.
With the initial default configuration you'll just have a few cities like
san-francisco, new-york, london, sydney;
this is mostly to show you how to add your own points of interest.


Key/Mouse bindings
==================
Left, Right,<br>Up, Down
    Scroll the map in the indicated direction.
+/=, -
    Zoom in or out.
s
    Save the current map to a file under <i>$HOME/Topo</i>

Space, m
    Jump back to the pinned location.
q
    Quit

Dragging and mousewheel move and scroll the map, as you'd expect.
Right-clicking in the map pops up a menu of various other options.

Click on a track or waypoint to select it and see what's known about it.

Usage (commandline arguments)
=============================

::

  Usage: pytopo
         pytopo trackfile
         pytopo known_site
         pytopo [-t trackfile] [-c collection] [-r] [site_name]
         pytopo [-t trackfile] start_lat start_long collection
         pytopo -p :     list known sites and tracks
         pytopo -r :     re-download all map tiles
         pytopo -h :     print this message

With no arguments, pytopo will display a list of known sites.

Track files may be in GPX, KML, KMZ or GeoJSON format, and may contain
track points and/or waypoints; multiple track files are allowed.

Use degrees.decimal_minutes format for coordinates.
Set up favorite site names in ~/.config/pytopo.sites,
favorite track logs in ~/Tracks


========================
Some Additional Features
========================

Track and Waypoint Files
========================

Pytopo can read tracks and waypoints from GPX, KML, KMZ, and GeoJSON files,
and you can load multiple track files at once.
It shows each track in a different color.
You can toggle waypoint visibility with the right-click context menu
(for when there are too many waypoints and they get in the way of
reading the map).

You can select a track by clicking on it,
split a track (right-click context menu again),
and save a track as GPX after you've split it.

Pinning
=======

You can "Pin" a spot on the map and save it as a pinned location
in your PyTopo configuration.

Switching Background Maps
=========================

*Change Background Map* in the context menu will list all the
MapCollections you have defined, and you can switch between them
interactively.

When you first run PyTopo, it will create a file called
*config/pytopo/pytopo.sites* giving you one MapCollection,
for the basic OpenStreetMap tile set, and a few major cities as Known Sites.

You'll probably want to add your own Known Sites, so you can start PyTopo
by passing it names of sites near you. There are two ways to do that.
You can right-click on any position on the map and choose "Pin this
location", then "Save pin location" and give it a site name.
Or if you're not afraid of editing files, you can edit <i>pytopo.sites</i>
to add your own sites by their latitude or longitude.

The *pytopo.sites* file is also the place to add new MapCollections,
and for this you do have to edit the file (see below).

Mileage and Elevation
=====================

If you need distance between two points, you can shift-click and PyTopo
will print distance and bearing from there to the previous place you
clicked. I know that's not an optimal user interface, but not many
people seem to need that feature and I find it useful enough when I
need it.

Sorry, PyTopo does not yet do anything useful with elevation or mileage
on track logs. But in the meantime you may want to check out my
standalone <a href="ellie/">Ellie</a> script; that's what I use.

Getting Map Data
================

MapCollections
==============

There are lots of different types of MapCollection you can use.
One useful one is to use map tiles from a different tile server.
Most tile servers other than OpenStreetMap require you to sign up for
an API key (which is usually free for light usage, but charges you
for heavier usage). In that case your key will be encoded into the URL
you set up in the MapCollection.

In the default *pytopo.sites*, there's an example of how to use
the `ThunderForest map server <http://thunderforest.com/>`_
with an API key to retrieve OpenCycleMap tiles. It looks like this,
specifying the name of the collection, the location on your local disk to
cache the tiles, the size and type of the tiles, the default zoom level
(your choice), the URL to use for downloading, the maximum zoom level
(this is a function of the tile server), and an attribution string.

::

  OSMMapCollection( "opencyclemap",         # collection name
                    "~/Maps/opencyclemap",  # where to cache
                    ".png", 256, 256,       # file type and size
                    13,                     # default zoom level
                    "https://tile.thunderforest.com/cycle/{z}/{x}/{y}.png?apikey=YOUR_API_KEY_HERE",
                    maxzoom=22,             # maximum zoom level
                    reload_if_older=90,     # reload if &gt; 90 days
                    attribution="Maps © www.thunderforest.com, Data © www.osm.org/copyright"),


You can use the same syntax for many different tile servers to get a
variety of different background map tile styles.
ThunderForest has several nice styles besides OpenCycleMap: you'll see
their list if you sign up for an API key.
You can set up as many MapCollections as you want, either different
styles from the same server or from different servers.

I don't currently know of a tile server that can serve satellite images,
even with an API key.
MapQuest used to offer this service but no longer does.
Please tell me if you know of an alternate server.
Note that the Google Maps terms of service do not allow using their tiles
with non-Google mapping apps, so Google isn't an option.

Download Area
=============

*Download Area* is intended to make it easy to download a
collection of tiles at different zoom levels for a specified area,
so you can have the tiles ready when you travel and will be offline.
In practice, it doesn't work as well as intended, partly because most
map tile servers will throttle connections that request too many tiles,
so it takes forever to download an area. I stopped using it and
therefore it isn't very well maintained.

Commercial Map Data
===================

Aside from OpenStreetMap tile srvers, pytopo can use local map data
on disk or CD; for instance, from the old
*Topo!* local area and specific park map packages
sold in camping/hiking stores,
sometimes under the aegis of National Geographic.

For *Topo!* CD datasets, use a Topo1MapCollection for regions
or a Topo2MapCollection for the park map sets:

::

  Topo1MapCollection( "deathvalley", "~/Maps/deathvalley", 7.5, 266, 328 ),
  Topo2MapCollection( "kingscanyon", "~/Maps/kingscyn", "topo", 410, 256 ),

**Caution: the *Topo! Back Roads Explorer* and the statewide
explorer collections are *not* in this friendly tiled format.**
They use large data files in a proprietary ".tpq" format.
`Tom Trebisky has analyzed the format and has written an extractor <http://cholla.mmto.org/computers/topomaps/>`_,
and he also has `a C GTK viewer <http://cholla.mmto.org/gtopo/>`_
for this format. I have not tried to integrate support
into PyTopo; there are enough good online sources of maps now that
I haven't seen the need to buy any more Topo! datasets myself.

Making Your Own Map Collections
================================

For some areas, you can download USGS topo maps free.
For instance, for California you can get maps in TIFF format from the
`California Spatial Information Library <http://casil.ucdavis.edu/casil/gis.ca.gov/drg/>`_.
You also may need to use specialized maps, such as geologic or land-use maps.

To use this sort of map, you have to split the large map into tiles.
One way is to use ImageMagick, with a command like::

  convert in-map.jpg -rotate 90 -crop 300x300 -repage +0+0 out-map%02d.jpg

Note: previously I included *-trim* as part of that line, and
a lot of pages you'll find googling for image splitting will tell you
to use -trim. Don't: it will give you maps of inconsistent sizes,
and pytopo will have no way to tell where the origin of the map should be.

Maps downloaded as PDF (such as USGS geologic maps) might work
in imagemagick, but if not, try converting them
to a raster format before splitting, using a program like GIMP
or a command like::

  gs -sDEVICE=jpeg -r300 -sOutputFile=output-map.jpg input-map.pdf


==================
API Documentation
==================

The primary PyTopo class is the
`MapViewer <pytopo.html#module-pytopo.MapViewer>`_,
which runs the pytopo application and manages the
`MapWindow <pytopo.html#module-pytopo.MapWindow>`_,
and all the various MapCollections.

There's a hierarchy of
`MapCollection <pytopo.html#module-pytopo.MapCollection>`_ classes
for reading different kinds of map tiles.
The most important collection class is the
`OSMMapCollection <pytopo.html#module-pytopo.OSMMapCollection>`_,
used for displaying and downloading tiles from
`OpenStreetMap <http://openstreetmap.org/>`_,
and from the many other servers that implement the same tile naming scheme
as OpenStreetMap uses.
`TopoMapCollection <pytopo.html#module-pytopo.TopoMapCollection>`_
classes are for reading two of the *Topo!* commercial maps, while
`GenericMapCollection <pytopo.html#module-pytopo.GenericMapCollection>`_
is a base class for inventing your own map formats, such as map tiles
cut from a larger geologic map.

.. inheritance-diagram:: pytopo.MapCollection pytopo.OSMMapCollection pytopo.Topo1MapCollection pytopo.Topo2MapCollection pytopo.GenericMapCollection
   :parts: 1

**API Documentation:**

* :ref:`genindex`
* :ref:`modindex`
* :ref:`search`


