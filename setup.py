#!/usr/bin/env python

from setuptools import setup

setup(name='pytopo',
      version='1.4',
      description='Map and track file viewer, using cached offline map tiles',
      long_description=read('README'),
      author='Akkana Peck',
      author_email='akkana@shallowsky.com',
      license="GPLv2+",
      url='http://shallowsky.com/software/topo/',
      scripts=['ellie'],
      data_files=[ ('/usr/share/applications', ["resources/pytopo.desktop"]),
                   ('/usr/share/pixmaps', ["resources/pytopo.png"]),
                   ('/usr/share/pytopo', ["resources/pytopo-pin.png"])
                 ]
      entry_points={
          # This probably should be gui_scripts according to some
          # pages I've found, but none of the official documentation
          # mentions gui_scripts at all.
          'console_scripts': [
              'pytopo=pytopo.MapViewer:main'
          ]
      },
      download_url='https://github.com/akkana/pytopo/tarball/1.4',
      # pip can't handle pygtk, so alas, we can't specify our dependency.
      # install_requires=["pygtk"],
      keywords=['maps', 'map viewer', 'track files', 'track logs',
                'GPX', 'KML'],
      # There aren't any appropriate classifiers for mapping apps.
      classifiers = [
          'Programming Language :: Python :: 2',
          'Programming Language :: Python :: 2.7',
          'License :: OSI Approved :: GNU General Public License v2 or later (GPLv2+)',
          'Intended Audience :: End Users/Desktop',
          'Topic :: Multimedia :: Graphics',
          'Topic :: Multimedia :: Graphics :: Viewers',
          'Topic :: Utilities'
        ]
     )

