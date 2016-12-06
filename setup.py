#!/usr/bin/env python

# http://docs.python.org/distutils/setupscript.html

from distutils.core import setup

setup(name='pytopo',
      version='1.3',
      description='Map and track file viewer, using cached offline map tiles',
      author='Akkana Peck',
      author_email='akkana@shallowsky.com',
      url='http://shallowsky.com/software/topo/',
      scripts=['pytopo'],
      data_files=[ ('/usr/share/applications', ["resources/pytopo.desktop"]),
                   ('/usr/share/pixmaps', ["resources/pytopo.png"]),
                   ('/usr/share/pytopo', ["resources/pytopo-pin.png"])
                 ]
     )

