This is PyTopo, an application for exploring tiled maps cached locally.

See the project home page at http://shallowsky.com/software/topo
for more information, examples, screenshots, hints on creating
custom maps, and more.

It can download data from OpenStreetMap or other map servers,
which may or may not require API keys; or you can use tiles from
commercial programs like the Topo! or tiles you've generated yourself.

It can also display GPX, KML or KMZ track logs, and can measure
distances and angles between points or give you the coordinates of
a point.

It uses GTK for its user interface, so you will need libGTK plus
either PyGTK (Python 2), or python-gi plus pygtkcompat (Python 3).
Linux users can't install these from PyPI, but they
can get these through their distro, or by compiling from source;
on Debian or Raspbian, you'll probably need the following packages
and their dependencies:

```
sudo apt-get install python-gi python-gi-cairo gir1.2-gtk-3.0 \
                     python-simplejson python-numpy python-pkg-resources
```

(or the python3- version of each of those packages, if you prefer).
Windows users should be able to install these packages from pip.
I don't have a good answer for Python and GTK on Mac; one possible
solution is to install GIMP (follow the install links from
https://gimp.org) then munge paths so that other programs can find the
PyGTK that comes with GIMP.

If you want to read from a GPS, you'll need gpsd and python-gps.

You can install PyTopo with ```pip install pytopo```
(that doesn't include the GTK requirement because pip can't install GTK
on Linux or Mac). Or install it from the source directory:
```python setup.py install```

You can test-run it from the project directory
if you have the pytopo directory in your PYTHONPATH:
```pytopo/MapViewer.py```
But if you want to see pin images, create a directory
/usr/share/pytopo and copy pytopo-pin.png into it.
Or just have pytopo-pin.png in the current directory when you run pytopo.

The first time you run pytopo, it will create a ~/.config/pytopo
directory for its configuration files, and a ~/Maps directory for
map data.

pytopo -h gives usage examples.

If you need custom maps., edit ~/.config/pytopo/pytopo.sites to add new
map Collections (see examples in that file or on the project home page).

Code contributions appreciated!

Also in this project: ellie, a little script for reporting and plotting
statistics (distance and elevation change) from a GPX track log.
More information: http://shallowsky.com/software/ellie/

There are also a small number of tests in the test/ directory;
run them with
    python -m unittest discover
from the top-level directory.

Have fun!
