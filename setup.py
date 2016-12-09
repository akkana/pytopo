#!/usr/bin/env python

# from distutils.core import setup
from setuptools import setup, Command
import os

# Utility function to read the README file.
# Used for the long_description.
def read(fname):
    return open(os.path.join(os.path.dirname(__file__), fname)).read()

class CleanCommand(Command):
    """Custom clean command to tidy up the project root."""
    user_options = []
    def initialize_options(self):
        pass
    def finalize_options(self):
        pass
    def run(self):
        os.system('rm -vrf ./build ./dist ./*.pyc ./*.tgz ./*.egg-info')

setup(name='pytopo',
      packages=['pytopo'],
      version='1.4',
      description='Map viewer, using cached offline map tiles and track files',
      long_description=read('README'),
      author='Akkana Peck',
      author_email='akkana@shallowsky.com',
      license="GPLv2+",
      url='http://shallowsky.com/software/topo/',
      # include_package_data=True,
      data_files=[('/usr/share/pixmaps',      ["resources/pytopo.png"]),
                  # Next line builds bdist fine, but on install, gives:
                  # error: can't copy 'resources/pytopo.desktop': doesn't exist or not a regular file
                  ('/usr/share/applications', ["resources/pytopo.desktop"]),
                  ('/usr/share/pytopo',       ["resources/sample.pytopo"]),
                  ('/usr/share/pytopo',       ["resources/pytopo-pin.png"])
                 ],
      entry_points={
          # This probably should be gui_scripts according to some
          # pages I've found, but none of the official documentation
          # mentions gui_scripts at all.
          'console_scripts': [
              'pytopo=pytopo.MapViewer:main',
              'ellie=pytopo.trackstats:main'
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
        ],

      cmdclass={
          'clean': CleanCommand,
      }
     )

