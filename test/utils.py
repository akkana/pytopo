#!/usr/bin/env python3

import math
import os

# unittest almostEqual requires more closeness than there is between
# gpx and kml.
def assertCloseEnough(a, b, tolerance=1e-5):
    """Assert if two values aren't close enough within a tolerance.
       Can accept two scalars or two iterables.
    """
    if hasattr(a, "__getitem__") and hasattr(b, "__getitem__"):
        if len(a) != len(b):
            raise AssertionError('Different lengths, %d vs %d'
                                 % (len(a), len(b)))
        for i, (aval, bval) in enumerate(zip(a, b)):
            if not math.isclose(aval, bval, rel_tol=tolerance):
                raise AssertionError("%dth elements differ: %f != %f"
                                     % (i, aval, bval))
        return

    if not math.isclose(a, b, rel_tol=tolerance):
        raise AssertionError('%f not close enough to %f' % (a, b))

def create_kmz(filebase):
    """Compress a kml file to create a kmz.
       filebase is the basename of the kml and kmz files.
       Returns the kmz filename.
    """
    kmlfile = filebase + ".kml"
    zipfile = filebase + ".zip"
    kmzfile = filebase + ".kmz"
    # XXX Could do this the hard way with the zipfile library
    os.system("/usr/bin/zip -9 %s %s" % (zipfile, kmlfile))
    # zip has no option to specify the output file name!
    os.rename(zipfile, kmzfile)

    return kmzfile
