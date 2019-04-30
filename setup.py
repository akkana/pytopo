#!/usr/bin/env python

# from distutils.core import setup
from setuptools import setup, Command
import os

# Utility function to read the README file.
# Used for the long_description.
def read(fname):
    return open(os.path.join(os.path.dirname(__file__), fname)).read()

def get_version():
    '''Read the pytopo module versions from pytopo/__init__.py'''
    return "1.6"
    with open("pytopo/__init__.py") as fp:
        for line in fp:
            line = line.strip()
            if line.startswith("__version__"):
                versionpart = line.split("=").strip()
                if versionpart.startswith('"') or versionpart.startswith("'"):
                    versionpart = versionpart[1:]
                if versionpart.endswith('"') or versionpart.endswith("'"):
                    versionpart = versionpart[:-1]
                return versionpart

class CleanCommand(Command):
    """Custom clean command to tidy up the project root."""
    user_options = []
    def initialize_options(self):
        pass
    def finalize_options(self):
        pass
    def run(self):
        os.system('rm -vrf ./build ./dist ./*.pyc ./*.tgz ./*.egg-info ./docs/sphinxdoc/_build')

setup(name='pytopo',
      packages=['pytopo'],
      version=get_version(),
      description='Map viewer, using cached offline map tiles and track files',
      long_description=read('README'),
      author='Akkana Peck',
      author_email='akkana@shallowsky.com',
      license="GPLv2+",
      url='http://shallowsky.com/software/topo/',
      zip_safe=False,

      # This only works if the data files are inside the package directory,
      # i.e. from here they have to be in pytopo/resources, not just resources.
      include_package_data=True,

      entry_points={
          # This probably should be gui_scripts according to some
          # pages I've found, but the official documentation
          # mostly talks about console_scripts and not gui_scripts.
          # On Linux they're the same, but on Windows, console_scripts
          # bring up a terminal, gui_scripts don't.
          'gui_scripts': [
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

