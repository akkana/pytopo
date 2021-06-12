# Copyright (C) 2009-2016 by Akkana Peck.
# You are free to use, share or modify this program under
# the terms of the GPLv2 or, at your option, any later GPL.

"""MapUtils: some useful utility functions useful for mapping classes.
"""

import math

EARTH_RADIUS_MI = 3959.
EARTH_RADIUS_KM = 6371.

class MapUtils:

    """MapUtils really just exists to contain a bunch of utility
       functions useful for mapping classes.
    """

    @classmethod
    def coord2str_dd(cls, lon, lat):
        """Convert a longitude, latitude pair into a pretty string,
           in decimal degrees"""
        s = "%.7f E  " % lon
        if lat >= 0:
            s += "%.7f N" % lat
        else:
            s += "%.5f S" % -lat
        return s

    @classmethod
    def deg_min2dec_deg(cls, coord):
        """Convert degrees.minutes to decimal degrees"""
        deg = cls.int_trunc(coord)
        dec = (coord - deg) / .6
        return deg + dec

    @classmethod
    def dec_deg2deg_min(cls, coord):
        """Convert decimal degrees to degrees.minutes"""
        if coord < 0:
            sgn = -1
            coord = -coord
        else:
            sgn = 1
        deg = cls.int_trunc(coord)
        minutes = abs(coord - deg) * .6
        return sgn * (deg + minutes)

    @classmethod
    def decdeg2dms(cls, dd):
        """Convert decimal degrees to (degrees, minutes, seconds)"""
        is_positive = dd >= 0
        dd = abs(dd)
        minutes, seconds = divmod(dd*3600,60)
        degrees, minutes = divmod(minutes,60)
        degrees = degrees if is_positive else -degrees
        return (int(degrees), int(minutes), seconds)

    @classmethod
    def dec_deg2deg_min_str(cls, coord):
        """Convert decimal degrees to a human-readable degrees/minutes string"""
        if coord < 0:
            sgnstr = '-'
            coord = -coord
        else:
            sgnstr = ''
        deg = cls.int_trunc(coord)
        minutes = abs(coord - deg) * 60.
        minutes = cls.truncate2frac(minutes, .01)
        return sgnstr + str(deg) + "^" + str(minutes) + "'"

    @staticmethod
    def bearing(lat1, lon1, lat2, lon2):
        """Bearing from wp1 to wp2."""
        # Python's trig functions take radians, not degrees
        lat1 = math.radians(lat1)
        lon1 = math.radians(lon1)
        lat2 = math.radians(lat2)
        lon2 = math.radians(lon2)

        # https://www.movable-type.co.uk/scripts/latlong.html
        # Don't trust any code you find for this: test it extensively;
        # most posted bearing finding code is bogus.
        y = math.sin(lon2 - lon1) * math.cos(lat2)
        x = math.cos(lat1) * math.sin(lat2) - \
            math.sin(lat1) * math.cos(lat2) * math.cos(lon2-lon1)

        # Convert back to degrees and make it positive between 0 and 360
        brng = math.degrees(math.atan2(y, x)) % 360
        return brng

    # Convert an angle (deg) to the appropriate quadrant string, e.g. N 57 E.
    @classmethod
    def angle_to_quadrant(cls, angle):
        if angle > 180:
            angle = angle - 360
        if angle == 0:
            return "N"
        if angle == -90:
            return "W"
        if angle == 90:
            return "E"
        if angle == 180:
            return "S"
        if angle > -90 and angle < 90:
            if angle < 0:
                return "N " + str(-angle) + " W"
            return "N " + str(angle) + " E"
        if angle < 0:
            return "S " + str(180 + angle) + " W"
        return "S " + str(180 - angle) + " E"

    @classmethod
    def int_trunc(cls, num):
        """Truncate to an integer, but no .999999 stuff"""
        return int(num + .00001)

    @classmethod
    def truncate2frac(cls, num, frac):
        """Truncate to a multiple of the given fraction"""
        t = float(MapUtils.int_trunc(num / frac)) * frac
        if num < 0:
            t = t - frac
        return t

    @classmethod
    def ohstring(cls, num, numdigits):
        """Return a zero-prefixed string of the given number of digits."""
        fmt = '%%0%dd' % numdigits
        return fmt % num

    @classmethod
    def haversine_angle(cls, latitude_1, longitude_1, latitude_2, longitude_2):
        """
        Haversine angle between two points.
        From https://github.com/tkrajina/gpxpy/blob/master/gpxpy/geo.py
        Implemented from http://www.movable-type.co.uk/scripts/latlong.html
        """
        d_lat = math.radians(latitude_1 - latitude_2)
        d_lon = math.radians(longitude_1 - longitude_2)
        lat1 = math.radians(latitude_1)
        lat2 = math.radians(latitude_2)

        a = math.sin(d_lat / 2) * math.sin(d_lat / 2) + \
            math.sin(d_lon / 2) * math.sin(d_lon / 2) * \
            math.cos(lat1) * math.cos(lat2)
        return 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))

    @classmethod
    def haversine_distance(cls,
                           latitude_1, longitude_1,
                           latitude_2, longitude_2, metric=False):
        """
        Haversine distance between two points.
        Returns distance in miles or meters.
        """
        c = MapUtils.haversine_angle(latitude_1, longitude_1,
                                     latitude_2, longitude_2)
        if metric:
            return EARTH_RADIUS_KM * c
        else:
            return EARTH_RADIUS_MI * c


# End of "MapUtils" pseudo-class.

