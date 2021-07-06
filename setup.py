#!/usr/bin/env python

# from distutils.core import setup
from setuptools import setup, Command
import os

# Utility function to read the README file.
# Used for the long_description.
# Github and readthedocs can both handle relative image links,
# but the images don't get copied up to pypi, so instead,
# replace them with images from the latest readthedocs run.
def file_contents(fname):
    with open(os.path.join(os.path.dirname(__file__), fname)) as fp:
        return fp.read().replace(" images/",
                           " https://pytopo.readthedocs.io/en/latest/_images/")

def get_version():
    '''Read the pytopo module versions from pytopo/__init__.py'''
    with open("pytopo/__init__.py") as fp:
        for line in fp:
            line = line.strip()
            if line.startswith("__version__"):
                versionpart = line.split("=")[-1] \
                                  .strip().replace('"', '').replace("'", '')
                if versionpart.startswith('"') or versionpart.startswith("'"):
                    versionpart = versionpart[1:]
                if versionpart.endswith('"') or versionpart.endswith("'"):
                    versionpart = versionpart[:-1]
                return versionpart

long_description = file_contents("README.rst")

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
      description='Tiled map viewer and track editor',
      long_description=long_description,
      long_description_content_type="text/x-rst",
      author='Akkana Peck',
      author_email='akkana@shallowsky.com',
      license="GPLv2+",
      url='http://shallowsky.com/software/topo/',
      zip_safe=False,

      # Data files.
      # This only works if the data files are inside the package directory,
      # i.e. from here they have to be in pytopo/resources, not just resources.
      include_package_data=True,

      entry_points={
          # This probably should be gui_scripts according to some
          # pages I've found, but the official documentation
          # discusses console_scripts and doesn't mention gui_scripts.
          # On Linux they're the same, but on Windows, console_scripts
          # bring up a terminal, gui_scripts don't.
          'gui_scripts': [
              'pytopo=pytopo.MapViewer:main',
          ],
          'console_scripts': [
              'ellie=pytopo.trackstats:main'
          ],
      },
      project_urls={
          'Source Code': 'https://github.com/akkana/pytopo/',
          'Documentation': 'https://pytopo.readthedocs.io/',
          'Bug Tracker': 'https://github.com/akkana/pytopo/issues',
      },

      install_requires=["PyGObject", "pycairo",
                        "requests-futures",
                        "simplejson"],

      # numpy and matplotlib are optional dependencies for ellie,
      # but there doesn't seem to be any way for a user to see this.
      extras_require={
          'elliplots':  ["numpy", "matplotlib"],
      },

      keywords=['maps', 'map viewer', 'track files', 'track logs',
                'GPX', 'KML', "GeoJSON"],

      classifiers = [
          'Programming Language :: Python :: 3',
          'License :: OSI Approved :: GNU General Public License v2 or later (GPLv2+)',
          'Intended Audience :: End Users/Desktop',
          'Intended Audience :: Science/Research',
          'Topic :: Scientific/Engineering :: GIS',
        ],

      cmdclass={
          'clean': CleanCommand,
      }
     )

