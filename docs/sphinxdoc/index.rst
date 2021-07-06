.. PyTopo documentation master file, created by
   sphinx-quickstart on Sun Dec 11 16:05:29 2016.
   You can adapt this file completely to your liking, but it should at least
   contain the root `toctree` directive.

.. toctree::
   :maxdepth: 2

.. include:: ../../README.rst


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

.. include:: modules.rst

* :ref:`genindex`
* :ref:`modindex`
* :ref:`search`


