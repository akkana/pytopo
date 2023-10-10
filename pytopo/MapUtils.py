# Copyright (C) 2009-2016 by Akkana Peck.
# You are free to use, share or modify this program under
# the terms of the GPLv2 or, at your option, any later GPL.

"""MapUtils: some useful utility functions useful for mapping classes.
"""

import math
import re

EARTH_RADIUS_MI = 3959.
EARTH_RADIUS_KM = 6371.

def coord2str_dd(lon, lat):
    """Convert a longitude, latitude pair into a pretty string,
       in decimal degrees"""
    s = "%.7f E  " % lon
    if lat >= 0:
        s += "%.7f N" % lat
    else:
        s += "%.5f S" % -lat
    return s


def dec_deg2dms(dd):
    """Convert decimal degrees to (degrees, minutes, seconds)"""
    is_positive = dd >= 0
    dd = abs(dd)
    minutes, seconds = divmod(dd*3600, 60)
    degrees, minutes = divmod(minutes, 60)
    degrees = degrees if is_positive else -degrees
    return (int(degrees), int(minutes), seconds)


def dec_deg2dms_str(coord):
    """Convert decimal degrees to a human-readable degrees/minutes string"""
    deg, mins, secs = dec_deg2dms(coord)
    return "%d° %d' %.4f\"" % (deg, mins, secs)


def dec_deg2deg_min(coord):
    """Convert decimal degrees to degrees . decimal minutes"""
    if coord < 0:
            sgn = -1
            coord = -coord
    else:
        sgn = 1
    deg = int_trunc(coord)
    minutes = abs(coord - deg) * .6
    return sgn * (deg + minutes)


def deg_min2dec_deg(coord):
    """Convert degrees.decimal_minutes to decimal degrees"""
    deg = int_trunc(coord)
    dec = (coord - deg) / .6
    return deg + dec


def deg_min_sec2dec_deg(coord):
    """Convert degrees.minutes_seconds to decimal degrees"""
    if coord >= 0:
        sign = 1
    else:
        sign = -1
    coord = abs(coord)
    deg = int_trunc(coord)
    val = (coord - deg) * 100
    mins = int_trunc(val)
    secs = (val - mins) * 100

    return (deg + mins/60. + secs/3600.) * sign


def parse_full_coords(coordstr, degformat="DD"):
    """Parse a full coordinate string, e.g.
       35 deg 53' 30.81" N 106 deg 24' 4.17" W"
       Return a tuple of floats.
       # XXX Needs smarts about which is lat and which is lon.
       Can also parse a single coordinate, in which case returns a 1-tuple.
    """
    firstcoord, charsmatched = to_decimal_degrees(coordstr, degformat,
                                                  report_chars_matched=True)
    if not charsmatched:
        # This can happen in a case like "37.123 -102.456")
        try:
            coordstrings = coordstr.split()
            if len(coordstrings) > 0:
                return (firstcoord, to_decimal_degrees(coordstrings[1],
                                                       degformat))
        except:
            return (firstcoord)

    coordstr = coordstr[charsmatched:]
    if not coordstr:
        return (firstcoord)
    return ( firstcoord, to_decimal_degrees(coordstr, degformat) )


def to_decimal_degrees(coord, degformat="DD", report_chars_matched=False):
    """Try to parse various different forms of deg-min-sec strings
       as well as floats for a single coordinate (lat or lon, not both).
       Returns float decimal degrees.

       degformat can be "DM", "DMS" or "DD" and controls whether
       float inputs are just passed through, or converted
       from degrees + decimal minutes or degrees minutes seconds.

       If report_chars_matched is true, returns a tuple:
       the coordinate parsed, plus the number of characters matched,
       to make it easier to parse the second coordinate.
    """
    # Is it already a number?
    try:
        coord = float(coord)

        if type(coord) is float or type(coord) is int:
            if degformat == "DD":
                pass
            elif degformat == "DMS":
                coord = deg_min_sec2dec_deg(coord)
            elif degformat == "DM":
                coord = deg_min2dec_deg(coord)
            else:
                print("Error: unknown coordinate format %s" % degformat)
                coord = None

            if report_chars_matched:
                return (coord, 0)
            return coord
    except:
        pass

    # Match the following formats and variants:
    # jhead, for EXIF from photos:    N 35d 51m 21.08s
    # exiftool for EXIF from photos:  35 deg 51' 21.08" N
    # More general format:            35° 54' 35.67" N, 106 deg 16' 10.78" W
    # For degrees, accept deg d ° ^
    # For minutes, accept ' min m
    # For seconds, accept " sec s
    # NSEW can either begin or end the string, or may be missing entirely,
    # in which case positive means north/east.
    # Degrees may start with a + or -
    coord_pat = r"\s*([NSEW])?\s*([+-]?[0-9]{1,3})\s*(?:deg|d|°|\^)" \
        r"\s*([0-9]{1,3})(?:'|m|min)\s*" \
        r"([0-9]{1,3})(.[0-9]+)?\s*(?:\"|s|sec)\s*([NSEW])?"
    m = re.match(coord_pat, coord)
    if not m:
        raise ValueError("Can't parse '%s' as a coordinate" % coord)

    direc1, deg, mins, secs, subsecs, direc2 = m.groups()
    if direc1 and direc2 and direc1 != direc2:
        print("%s: Conflicting directions, %s vs %s" % (coord,
                                                        direc1, direc2),
              file=sys.stderr)
        raise ValueError("Can't parse '%s' as a coordinate" % coord)

    # Sign fiddling: end up with positive value but save the sign
    if direc2 and not direc1:
        direc1 = direc2
    if direc1 == 'S' or direc1 == 'W':
        sign = -1
    else:
        sign = 1
    val = int(deg) * sign
    if val < 0:
        sign = -1
        val = -val
    else:
        sign = 1

    secs = float(secs)
    if subsecs:
        if subsecs.endswith('"'):
            subsecs = subsecs[:-1]
        secs += float(subsecs)
    mins = int(mins) + secs/60.
    if val >= 0:
        val += mins/60.
    else:
        val -= mins/60.

    # Restore the sign
    val *= sign

    if report_chars_matched:
        return (val, len(m.group(0)))
    return val


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
def angle_to_quadrant(angle):
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


def int_trunc(num):
    """Truncate to an integer, but no .999999 stuff"""
    return int(num + .00001)


def truncate2frac(num, frac):
    """Truncate to a multiple of the given fraction"""
    t = float(int_trunc(num / frac)) * frac
    if num < 0:
        t = t - frac
    return t


def ohstring(num, numdigits):
    """Return a zero-prefixed string of the given number of digits."""
    fmt = '%%0%dd' % numdigits
    return fmt % num


def haversine_angle(latitude_1, longitude_1, latitude_2, longitude_2):
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


def haversine_distance(latitude_1, longitude_1,
                       latitude_2, longitude_2, metric=False):
    """
    Haversine distance between two points.
    Returns distance in miles or meters.
    """
    c = haversine_angle(latitude_1, longitude_1,
                                 latitude_2, longitude_2)
    if metric:
        return EARTH_RADIUS_KM * c
    else:
        return EARTH_RADIUS_MI * c


def main():
    """You can use this file for degree conversions.
       It's installed as a commandline script called "degreeconv".
    """
    import sys

    def Usage():
        import os
        print("Usage: %s [--dm] deg deg deg" % os.path.basename(sys.argv[0]))
        print("""      --dm enables decimal minutes mode, so floating point 
      numbers will be interpreted as dd.mmmm.""")
        sys.exit(1)

    degfmt = "DD"
    for coordstr in sys.argv[1:]:
        if coordstr == "-h" or coordstr == "--help":
            Usage()
        if coordstr == "--dm":
            degfmt = "DM"
            continue
        try:
            coords = parse_full_coords(coordstr, degfmt)
        except RuntimeError as e:
            print("Can't parse", coordstr, ":", e)
            Usage()

        print('\n"%s":' % coordstr)
        print("Decimal degrees:         ", coords)
        for c in coords:
            d, m, s = dec_deg2dms(c)
            print("Degrees Minutes Seconds:  %d° %d' %.3f\"" % (d, m, s))
            print("Degrees.Minutes          ", dec_deg2deg_min(c))


if __name__ == '__main__':
    main()
