#!/usr/bin/env python

# http://docs.python.org/distutils/setupscript.html

from distutils.core import setup

setup(name='pytopo',
      version='1.0',
      description='Online and Offline Maps',
      author='Akkana Peck',
      author_email='akkana@shallowsky.com',
      url='http://shallowsky.com/software/topo/',
      scripts=['pytopo'],
      data_files=[ ('/usr/share/applications', ["pytopo.desktop"]),
                   ('/usr/share/pixmaps', ["pytopo.png"]),
                   ('/usr/share/pytopo', ["pytopo-pin.png"])
                 ]
     )

