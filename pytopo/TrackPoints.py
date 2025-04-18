# Copyright (C) 2009-2025 by Akkana Peck.
# You are free to use, share or modify this program under
# the terms of the GPLv2 or, at your option, any later GPL.

"""Parsing and handling of GPS track files in pytopo.
"""

from __future__ import print_function

import os
import xml.dom.minidom
import re
import zipfile
import json
import time

from pytopo import __version__


# Waypoints must have a name, to distinguish them from trackpoints.
# This is a way to flag waypoints that should have no displayed name.
NULL_WP_NAME = "__WP__"


# Regular expression matching extensions like osmand:speed in GPX files.
SPEEDRE = re.compile(".*:speed")


# for debugging: print an xml.dom.minidom node.
# def serializeXML(elem):
#     if not elem:
#         print("None")
#         return
#     out = "<" + elem.nodeName + ">"
#     for c in elem.childNodes:
#         if c.nodeType == xml.dom.minidom.Node.TEXT_NODE:
#             out += c.nodeValue
#         else:
#             if c.nodeType == xml.dom.minidom.Node.ELEMENT_NODE:
#                 if c.childNodes.length == 0:
#                     out += "<" + c.nodeName + "/>"
#                 else:
#                     cs = serializeXML(c)
#                     out += cs
#                     out += "</" + c.nodeName + ">"
#     return out


class GeoPoint(object):
    """A single track point or waypoint."""
    # Note: GPX files imported from KML may have no timestamps.
    # lat and lon are floats; the rest are strings.
    # At least from GPX format,
    # ele is a string representing elevation in meters;
    # timestamp is a string like 2014-08-07T01:19:24Z.
    # If you need to add timestamps, see add_bogus_timestamps.
    # attrs is an optional list of other attributes like hdop and speed.
    def __init__(self, lat, lon, ele=None, speed=None,
                 name=False, timestamp=None, attrs=None):
        self.lat = lat
        self.lon = lon
        self.ele = ele
        self.speed = speed
        self.name = name
        self.timestamp = timestamp
        self.attrs = attrs

    def __repr__(self):
        if self.ele:
            s ="(%f, %f, %s)" % (self.lat, self.lon, self.ele)
        else:
            s ="(%f, %f)" % (self.lat, self.lon)
        if self.name:
            s += " '%s'" % self.name
        if self.timestamp:
            s += " [%s]" % self.timestamp
        if self.attrs:
            s += "{ "
            for k in list(self.attrs.keys()):
                s += "%s: %s, " % (k, self.attrs[k])
            # Remove the final comma
            s = s[:-2]
            s += " }"

        return s

    def format_timestamp(self):
        if self.timestamp:
            return self.timestamp

        # timestamp should be in a format like 2015-12-02T16:50:34Z
        self.timestamp = time.strftime('%Y-%m-%dT%H:%M:%SZ',
                                       time.gmtime(time.time()))
        return self.timestamp


# Impossible values:
TOOBIGLON = 361
TOOSMALLLON = -361
TOOBIGLAT = 91
TOOSMALLLAT = -91

class BoundingBox(object):

    def __init__(self):
        self.minlon = TOOBIGLON
        self.maxlon = TOOSMALLLON
        self.minlat = TOOBIGLAT
        self.maxlat = TOOSMALLLAT

    def __repr__(self):
        return "<BoundingBox lat %.3f to %.3f, lon %.3f to %.3f>" \
            % (self.minlat, self.maxlat, self.minlon, self.maxlon)

    def __bool__(self):
        return not self.uninitialized()

    def as_tuple(self):
        """Return a tuple of minlon, minlat, maxlon, maxlat
        """
        return (self.minlon, self.minlat, self.maxlon, self.maxlat)

    def uninitialized(self):
        if self.minlon == TOOBIGLON:
            return True
        if self.maxlon == TOOSMALLLON:
            return True
        if self.minlat == TOOBIGLAT:
            return True
        if self.maxlat == TOOSMALLLAT:
            return True
        return False

    def add_point(self, lat, lon):
        """Extend the bounds if the given coords are outside.
        """
        if lon < self.minlon:
            self.minlon = lon
        if lon > self.maxlon:
            self.maxlon = lon
        if lat < self.minlat:
            self.minlat = lat
        if lat > self.maxlat:
            self.maxlat = lat

    def union(self, bbox):
        """Set the current bbox to be the union of itself and
           the bbox passed in.
        """
        self.minlon = min(self.minlon, bbox.minlon)
        self.maxlon = max(self.maxlon, bbox.maxlon)
        self.minlat = min(self.minlat, bbox.minlat)
        self.maxlat = max(self.maxlat, bbox.maxlat)

    def center(self):
        """Return the center of the given bounding box as lat, lon
        """
        # This doesn't compensate for crossing the date line.
        return ((self.maxlat + self.minlat) / 2.,
                (self.maxlon + self.minlon) / 2.)


class TrackPoints(object):

    """Parsing and handling of GPS track files.
       Supports GPX, KML, KMZ and GeoJSON.
       A TrackPoints object can include a track (points[]),
       a list of waypoints, and a list of polygons.
       A MapWindow will have one TrackPoints object.

       Each point in a track can be either a trackpoint or the beginning
       of a new track segment.

       Beginnings of segments are represented by the name of the
       segment as a string or unicode, but use is_start() to test for
       that in case of future changes.

       Waypoint origin (filename) can be specified in a similar way:
       a string in the list of waypoints applies to all successive waypoints.

       A trackpoint is an array where the first two elements are
       longitude and latitude, as floatings.
       Following longitude there may be an optional elevation, a float,
       or waypoint name, a string or unicode.
       Finally, a dictionary may be present, containing additional
       elements like time (timestamp).

       polygons is a list of OrderedDicts, which have keys
       "class" (for purposes of coloring), "coordinates" and optionally "name".
       Polygons currently can only be read in from GeoJSON format.
    """

    def __init__(self):
        self.points = []
        self.waypoints = []
        self.polygons = []

        # Bounding boxes.
        # self.bbox contains all trackpoints and waypoints,
        # but not polygons, because they might be an overlay
        # covering a wide area.
        self.bbox = BoundingBox()

        # self.outer_bbox contains the polygons too,
        # in case there are no track- or waypoints
        self.outer_bbox = BoundingBox()

        self.max_speed = 0
        self.min_ele = 0
        self.max_ele = 0

        # Remember which files each set of points came from
        self.srcfiles = {}

        self.saved_points = False

        # fieldnames is a list of keys that can be used to indicate
        # class (for colorizing purposes) of polygons in a geojson file.
        self.fieldnames = None

        self.Debug = False

    def __repr__(self):
        return "<TrackPoints: %d points, %s waypoints, %d polygons>" \
            % (len(self.points), len(self.waypoints), len(self.polygons))

    def __bool__(self):
        return bool(self.points) or bool(self.waypoints or bool(self.polygons))

    @staticmethod
    def get_version():
        # There doesn't seem to be any good way of getting the current
        # module's version. from . import __version__ works from external
        # scripts that are importing the module, but if you try to run
        # this file's main(), it dies with
        #   ValueError: Attempted relative import in non-package
        # The only solution I've found is to import the whole module,
        # then get the version from it.
        return __version__

    def is_start(self, point):
        """Is this the start of a new track segment?
           If so, it's a string (or unicode), the name of the track section.
        """
        # Apparently there's no good way in Python
        return not isinstance(point, GeoPoint)

    def get_bounds(self):
        """Return a bounding box:
           - for all track- and waypoints, if any
           - for all polygons, if any
           - if no points or polygons, return None.
        """
        if not self.bbox.uninitialized():
            return self.bbox
        if not self.outer_bbox.uninitialized():
            return self.outer_bbox
        return None

    def is_attributes(self, point):
        """Is this point actually a set of attributes?"""
        return isinstance(point, dict)

    def attributes(self, trackindex):
        """Does the indicated track have attributes? Then return them.
        """
        # Currently attributes are represented by a dictionary
        # as the next item after the name in the trackpoints list.
        try:
            if self.is_attributes(self.points[trackindex + 1]):
                return self.points[trackindex + 1]
        except:
            pass
        return None

    def handle_track_point(self, lat, lon, ele=None, speed=None,
                           timestamp=None, waypoint_name=False, attrs=None):
        """Add a new trackpoint or waypoint after some basic sanity checks.
           lat and lon are in degrees.
           If waypoint_name, we assume this is a waypoint,
           otherwise assume it's a track point.
           attrs is an optional dict of other attributes, like hdop or speed.
           If timestamp==0, add a bogus timestamp; if None, add no timestamp.
           Return the newly created trackpoint.
        """
        self.bbox.add_point(lat, lon)

        if timestamp == 0:
            timestamp = self.make_bogus_timestamp()
        point = GeoPoint(lat, lon, ele=ele, speed=speed, timestamp=timestamp,
                         name=waypoint_name, attrs=attrs)

        try:
            if point.ele:
                if not self.min_ele or point.ele < self.min_ele:
                    self.min_ele = point.ele
                if point.ele > self.max_ele:
                    self.max_ele = point.ele
        except:
            pass

        try:
            self.max_speed = max(self.max_speed, float(speed))
        except:
            pass

        if waypoint_name:
            self.add_waypoint(point)
        else:
            self.points.append(point)

        return point

    def add_waypoint(self, point):
        """Add the given point as a waypoint, if there isn't already
           a waypoint at the given location.
           If there is, append the name to the existing point.
           Currently this requires an exact match, but eventually
           it should use some sort of "close enough" metric.
        """
        for wp in self.waypoints:
            if type(wp) is str:
                continue
            if wp.lat == point.lat and wp.lon == point.lon:
                if point.name != wp.name:
                    wp.name += "\n" + point.name
                return
        self.waypoints.append(point)

    def inside_box(self, pt, bb):
        """Is the point inside the given bounding box?
           Bounding box is (min_lon, min_lat, max_lon, max_lat).
        """
        return (pt.lon >= bb[0] and pt.lon <= bb[2] and
                pt.lat >= bb[1] and pt.lat <= bb[3])

    def get_segment_name(self, seg):
        """See if this trkseg or trk has a <name> child.
           If so, return the text out of it, else None.
        """
        trkname = seg.getElementsByTagName("name")
        if trkname and \
           trkname[0].parentNode == seg and \
           trkname[0].hasChildNodes() and \
           trkname[0].firstChild.nodeName == '#text' and \
           trkname[0].firstChild.wholeText:
            return trkname[0].firstChild.wholeText
        return None

    def read_track_file_GPX(self, filename):
        """Read a GPX track file into the current TrackPoints object.
           Return the BoundingBox.
           Raise FileNotFoundError if the file doesn't exist,
           RuntimeError if it's not a track file,
           IOError or other exceptions as needed.
        """

        if self.Debug:
            print("Reading track file", filename)
        try:
            dom = xml.dom.minidom.parse(filename)
        except xml.parsers.expat.ExpatError as e:
            print("Expat error parsing", filename, ":", e)
            import sys
            sys.exit(1)

        bbox = BoundingBox()

        # Handle track(s) and routes:
        def handle_track(segname, ptname):
            first_segment_name = None
            segs = dom.getElementsByTagName(segname)
            for seg in segs:
                trkpts = seg.getElementsByTagName(ptname)

                # need to keep different track files and segments
                # separate: don't draw lines from the end of a track
                # to the beginning of the next.
                if trkpts:
                    # See if the segment itself has a name
                    segname = self.get_segment_name(seg)
                    # See if the parent track has a name.
                    trk = seg
                    while trk.nodeName != "trk" and trk.nodeName != "rte":
                        trk = trk.parentNode
                    trkname = self.get_segment_name(trk)
                    if trkname and segname:
                        self.points.append(trkname + ':' + segname)
                    elif segname:
                        self.points.append(segname)
                    elif trkname:
                        self.points.append(trkname)
                    else:
                        self.points.append(os.path.basename(filename))
                    if not first_segment_name:
                        first_segment_name = self.points[-1]

                    for pt in trkpts:
                        lat, lon, ele, speed, ts, attrs = \
                            self.GPX_point_coords(pt)
                        self.handle_track_point(lat, lon,
                                                ele=ele, speed=speed,
                                                timestamp=ts,
                                                attrs=attrs)
                        bbox.add_point(lat, lon)

        handle_track("trkseg", "trkpt")

        # Treat routepoints the same as trackpoints.
        handle_track("rte", "rtept")

        # Handle waypoints
        first_segment_name = None
        waypts = dom.getElementsByTagName("wpt")
        if waypts:
            self.waypoints.append(os.path.basename(filename))
            for pt in waypts:
                lat, lon, ele, speed, time, attrs = self.GPX_point_coords(pt)
                name = self.get_DOM_text(pt, "name")
                if not name:
                    name = NULL_WP_NAME
                self.handle_track_point(lat, lon, ele=ele, timestamp=time,
                                        waypoint_name=name, attrs=attrs)
                bbox.add_point(lat, lon)

        return bbox

    def filename_for_index(self, index):
        filename = ''
        for i in self.srcfiles:
            if i > index:
                return filename
            filename = self.srcfiles[i]

    def find_matching_child(self, node, childname):
        """Find a child node with a name matching childname,
           which may be a regexp.
        """
        nodes = node.getElementsByTagName(childname)
        if nodes:
            return nodes[0]

        if type(childname) is not re.Pattern:
            return None

        matchnode = None
        for child in node.childNodes:
            if childname.match(child.nodeName):
                return child

            if child.nodeName == "extensions":
                matchnode = self.find_matching_child(child,
                                                     childname=childname)
                if matchnode:
                    return matchnode

        return None

    def get_DOM_text(self, node, childname=None):
        """Return the text out of a DOM node.
           Or, if childname is specified,
           find a matching child (see previous function)
           and return the text inside.
        """
        if childname:
            node = self.find_matching_child(node, childname)
        if not node:
            return None

        n = node.childNodes
        if len(n) < 1:
            return None

        if n[0].nodeType == n[0].TEXT_NODE or \
           n[0].nodeType == n[0].CDATA_SECTION_NODE:
            return n[0].data

        return None

    def GPX_point_coords(self, pointnode):
        """Parse a new trackpoint or waypoint from a GPX node.
           Returns lat (float), lon (float), ele (string or None),
           speed (string or None),
           time (string or None), attrs (dict or None).
        """
        lat = float(pointnode.getAttribute("lat"))
        lon = float(pointnode.getAttribute("lon"))
        time = self.get_DOM_text(pointnode, "time")

        ele = self.get_DOM_text(pointnode, "ele")
        try:
            ele = float(ele)
        except:
            ele = 0.

        # Python dom and minidom have no easy way to combine sub-nodes
        # into a dictionary, or to serialize them.
        # Also nodes are mostly undocumented.
        # You can loop over point.childNodes and look at .nodeName, .nodeValue
        # but for now, let's only look at a few types of points.
        attrs = {}
        hdop = self.get_DOM_text(pointnode, "hdop")
        if hdop:
            attrs['hdop'] = hdop

        # print("pointnode:", serializeXML(pointnode))

        # Old versions of osmand used a <speed> node, but now it's inside
        # <extensions><osmand:speed>.
        speed = self.get_DOM_text(pointnode, SPEEDRE)
        try:
            speed = float(speed)
        except:
            speed = None

        # If there were no extra attributes, pass None, not an empty dict.
        if not attrs:
            attrs = None

        # For now, keep elevation and time as unchanged strings.
        return lat, lon, ele, speed, time, attrs

    @staticmethod
    def make_bogus_timestamp(t=None):
        if not t:
            t = time.time()
        return time.strftime('%Y-%m-%dT%H:%M:%S', time.gmtime(t))

    def add_bogus_timestamps(self):
        """Add made-up timestamps to every track point."""
        # 2007-10-02T09:22:06Z
        t = time.time()
        # How many seconds will we advance each time?
        interval = 15
        for pt in self.points:
            if not self.is_start(pt) and not pt.timestamp:
                pt.timestamp = self.make_bogus_timestamp(t)
                t += interval

    def undo(self):
        """Undo a change to a track, like removing early or late points."""
        if self.saved_points:
            self.points = self.saved_points

    def save_for_undo(self):
        """Save points that have been deleted, so they're available for undo."""
        self.saved_points = self.points[:]

    def print_tracks(self):
        """For debugging: a concise way of representing all current tracks."""
        count = 0
        curtrack = None
        for pt in self.points:
            if self.is_start(pt):
                if curtrack:
                    print("%s: %d points" % (curtrack, count))
                count = 0
                curtrack = pt
            else:
                count += 1
        if curtrack:
            print("%s: %d points" % (curtrack, count))

    def remove_after(self, pointidx):
        """Remove all points after index pointidx."""
        self.save_for_undo()
        nextstart = None
        for i in range(pointidx+1, len(self.points)):
            if self.is_start(self.points[i]):
                nextstart = i
                break
        if nextstart:
            self.points = self.points[:pointidx] + self.points[nextstart:]
        else:
            self.points = self.points[:pointidx]

    def remove_before(self, pointidx):
        """Remove all points before index pointidx."""
        self.save_for_undo()
        laststart = None

        for i in range(pointidx+1, 0, -1):
            if self.is_start(self.points[i]):
                laststart = i
                break

        if laststart:
            self.points = self.points[:laststart+1] + self.points[pointidx:]
        else:
            # This shouldn't happen: there should always be a track start.
            print("Internal error, no track start")
            self.points = [ "Track start" ] + self.points[pointidx+1:]

    #
    # Format handling, file reading and saving functions:
    #

    def read_track_file(self, filename):
        """Read a track file.
           Return the BoundingBox.
           Raise FileNotFoundError if the file doesn't exist,
           RuntimeError if it's not a track file,
           IOError or other exceptions as needed.
        """
        # XXX Should read magic number rather than depending on extension

        ext = self.lowerext(filename)

        # mappers has to be defined at the end of the class
        # or it won't see the function names like read_track_file_GPX.
        for mapper in self.mappers:
            if ext in mapper[0]:
                self.srcfiles[len(self.points)] = filename
                return mapper[1](self, filename)

        raise(RuntimeError("Track file %s doesn't end in one of " % filename
                           + ', '.join([ ', '.join(m[0])
                                         for m in self.mappers])))

    @classmethod
    def lowerext(classname, filename):
        base, ext = os.path.splitext(filename)
        if ext.startswith('.'):
            ext = ext[1:]
        ext = ext.lower()
        return ext

    @classmethod
    def is_track_file(classname, filename):
        """Is the file a type PyTopo recognizes as a track file?
           But it's more efficient to call read_track_file() wrapped in a try
           to avoid checking the extension twice.
        """
        ext = classname.lowerext(filename)
        for mapper in classname.mappers:
            if ext in mapper[0]:
                return True
        return False

    def save_GPX_in_region(self, start_lon, start_lat, end_lon, end_lat,
                           filename):
        # print("Save GPX in", filename, start_lon, start_lat, end_lon, end_lat)
        self.save_GPX(filename, (start_lon, start_lat, end_lon, end_lat))

    def save_GPX(self, filename, boundingbox=None):
        """Save all known tracks and waypoints as a GPX file.
           XXX We don't have valid <time> saved for these points.
        """
        if boundingbox:
            # Make sure it's ordered right
            boundingbox = (min(boundingbox[0], boundingbox[2]),
                           min(boundingbox[1], boundingbox[3]),
                           max(boundingbox[0], boundingbox[2]),
                           max(boundingbox[1], boundingbox[3]))

        with open(filename, "w") as outfp:
            outfp.write('''<?xml version='1.0' encoding='UTF-8' standalone='yes' ?>
<gpx version="1.1" creator="PyTopo %s~" xmlns="http://www.topografix.com/GPX/1/1" xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance" xsi:schemaLocation="http://www.topografix.com/GPX/1/1 http://www.topografix.com/GPX/1/1/gpx.xsd">
''' % __version__)

            for pt in self.waypoints:
                # If it doesn't have lat, lon then it's not a GeoPoint
                # and can't be added to the track.
                if not hasattr(pt, 'lat') or not hasattr(pt, 'lon'):
                    continue
                if not boundingbox or self.inside_box(pt, boundingbox):
                    outfp.write('''  <wpt lat="%f" lon="%f">
    <time>%s</time>
    <name>%s</name>
  </wpt>\n''' % (pt.lat, pt.lon, pt.format_timestamp(), pt.name))

            if self.points:
                outfp.write("  <trk>\n")
                segstr = ''
                skipping = False
                if not self.is_start(self.points[0]):
                    outfp.write("    <trkseg>\n")
                for pt in self.points:
                    if self.is_start(pt):
                        if segstr:
                            segstr += "    </trkseg>\n"
                            outfp.write(segstr)
                        segstr = "    <trkseg>\n"
                        if pt:
                            segstr += "      <name>%s</name>\n" % pt
                        skipping = False
                        continue

                    # If it doesn't have lat, lon then it's not a GeoPoint
                    # and can't be added to the track.
                    # It might be a dict of attributes from a GeoJSON.
                    if not hasattr(pt, 'lat') or not hasattr(pt, 'lon'):
                        continue

                    # Skipping this trkseg?
                    if skipping:
                        continue

                    if boundingbox:
                        if not self.inside_box(pt, boundingbox):
                            segstr = ''
                            skipping = True
                            continue

                    segstr += '      <trkpt lat="%f" lon="%f">\n' % (pt.lat,
                                                                     pt.lon)
                    if pt.ele:
                        segstr += '        <ele>%s</ele>\n' % pt.ele
                    if pt.timestamp:
                        segstr += '        <time>%s</time>\n' % pt.timestamp

                    # Extra attributes
                    if pt.attrs:
                        if 'hdop' in pt.attrs:
                            segstr += '        <hdop>%s</hdop>\n' \
                                      % pt.attrs['hdop']
                        if 'speed' in pt.attrs:
                            # Speed is an extension.
                            segstr += '''        <extensions>
          <speed>%s</speed>
        </extensions>\n''' % pt.attrs['speed']

                    # Done with this trackpoint.
                    segstr += '      </trkpt>\n'
                if segstr:
                    segstr += "    </trkseg>\n"
                segstr += "  </trk>\n"
                outfp.write(segstr)

            outfp.write("</gpx>")


    def read_track_file_GeoJSON(self, filename):
        """Read a GeoJSON track or polygon file.
           Return the BoundingBox.
           Raises FileNotFoundError if the file doesn't exist,
           RuntimeError if it's not a track file,
           IOError or other exceptions as needed.
        """
        with open(filename) as fp:
            gj = json.loads(fp.read())

        if gj["type"] != "FeatureCollection":
            print(filename, "isn't a FeatureCollection")
            return None
        if "features" not in gj:
            print("No features in geojson file", filename)
            return None

        bbox = BoundingBox()

        for feature in gj["features"]:
            featuretype = feature["geometry"]["type"]

            if featuretype == 'Point':
                lon = feature["geometry"]["coordinates"][0]
                lat = feature["geometry"]["coordinates"][1]
                if "name" in feature["properties"]:
                    name = feature["properties"]["name"]
                elif "description" in feature["properties"]:
                    name = feature["properties"]["description"]
                if not name:
                    # It has to have some non-null name, since that's
                    # the signal handle_track_point uses to tell it's
                    # a waypoint and not a track point.
                    # So make a name that will be invisible.
                    name = " "
                self.handle_track_point(lat, lon, waypoint_name=name)
                bbox.add_point(lat, lon)
                continue

            def add_polygon(polycoords, polyname, properties):
                polyclasses = []
                for field in self.fieldnames:
                    if field in properties:
                        polyclasses.append(properties[field])
                        break
                newpoly = {}
                if name:
                    newpoly["name"] = polyname
                newpoly["class"] = ", ".join(polyclasses)
                newpoly["coordinates"] = featurepoly

                # Bounding box: min lon,  max lon, min lat, max lat
                poly_bbox = BoundingBox()
                for (lon, lat) in newpoly["coordinates"]:
                    poly_bbox.add_point(lat, lon)
                newpoly["bounds"] = poly_bbox.as_tuple()

                self.polygons.append(newpoly)
                bbox.union(poly_bbox)

            def look_for_name(feature):
                if "name" in feature["properties"]:
                    return feature["properties"]["name"]
                elif "description" in feature["properties"]:
                    return feature["properties"]["description"]
                elif "name" in feature:
                    return feature["name"]
                elif "id" in feature:
                    return "id=%s" % str(feature["id"])
                else:
                    return None

            if featuretype == "Polygon" or featuretype == "MultiPolygon":
                name = look_for_name(feature)
                # A feature may have more than one polygon
                # in its coordinate list. First store the values
                # that apply to all of them:

                if not self.fieldnames:
                    self.fieldnames = ["class"]

                # Loop over the polygons in this feature.
                if featuretype == "Polygon":
                    for featurepoly in feature["geometry"]["coordinates"]:
                        add_polygon(featurepoly, name, feature["properties"])
                    continue

                elif featuretype == "MultiPolygon":
                    for container in feature["geometry"]["coordinates"]:
                        for featurepoly in container:
                            add_polygon(featurepoly, name,
                                        feature["properties"])
                    continue

            if featuretype != "LineString" and featuretype != "MultiLineString":
                print("Don't know how to handle GeoJSON feature of type",
                      featuretype)
                continue

            # It's a track. Add it.
            name = None
            if "properties" in feature:
                props = feature["properties"]
                for key in props:
                    kl = key.lower()
                    if kl == "name" or kl == "trailname":
                        name = props[key]
                        break
            if not name:
                name = look_for_name(feature)

            # Properties may specify a null name, but we need something.
            if not name:
                name = "unnamed"

            if featuretype == "LineString":
                self.points.append(name)
                # What is in feature["properties"] in a GeoJSON?
                # How should it be represented?
                # if "properties" in feature and feature["properties"]:
                #     self.points.append(feature["properties"])
                for coords in feature["geometry"]["coordinates"]:
                    try:
                        lon, lat, ele = coords
                    except ValueError:
                        lon, lat = coords
                        ele = None
                    self.handle_track_point(lat, lon, ele=ele)
                    bbox.add_point(lat, lon)

            elif featuretype == "MultiLineString":
                for linestring in feature["geometry"]["coordinates"]:
                    self.points.append(name)
                    # if "properties" in feature:
                    #     self.points.append(feature["properties"])
                    for coords in linestring:
                        try:
                            lon, lat, ele = coords
                        except ValueError:
                            lon, lat = coords
                            ele = None
                        self.handle_track_point(lat, lon, ele=ele)
                        bbox.add_point(lat, lon)

        return bbox


    def save_geojson(self, filename, boundingbox=None):
        """Save known tracks and waypoints as a GeoJSON file,
           with each track segment a different feature
           (rather than using MultiLineStrings).
        """
        if boundingbox:
            # Make sure it's ordered right
            boundingbox = (min(boundingbox[0], boundingbox[2]),
                           min(boundingbox[1], boundingbox[3]),
                           max(boundingbox[0], boundingbox[2]),
                           max(boundingbox[1], boundingbox[3]))

        with open(filename, "w") as outfp:
            jsonout = {
                "type": "FeatureCollection",
                "features": []
            }

            # Convert waypoints
            for pt in self.waypoints:
                # If it doesn't have lat, lon then it's not a GeoPoint
                # and can't be added to the track.
                if not hasattr(pt, 'lat') or not hasattr(pt, 'lon'):
                    continue
                if not boundingbox or self.inside_box(pt, boundingbox):
                    jsonout["features"].append({
                        "type": "Feature",
                        "properties": {
                            "name": pt.name,
                        },
                        "geometry": {
                            "type": "Point",
                            "coordinates": [ pt.lon, pt.lat ]
                        }
                    })
                    if pt.ele:
                        jsonout["features"][-1]["geometry"]["coordinates"] \
                            .append(pt.ele)

            # Convert tracks:
            if self.points:
                for pt in self.points:
                    if self.is_start(pt):
                        jsonout["features"].append({
                            "properties": {
                                "name": pt
                            },
                            "type": "Feature",
                            "geometry": {
                                "type": "LineString",
                                "coordinates": []
                            }
                        })
                        continue

                    # If it doesn't have lat, lon then it's not a GeoPoint
                    # and can't be added to the track.
                    # It might be a dict of attributes from a GeoJSON.
                    if not hasattr(pt, 'lat') or not hasattr(pt, 'lon'):
                        continue

                    # Else it's presumably a coordinate pair or triple
                    if boundingbox:
                        if not self.inside_box(pt, boundingbox):
                            continue

                    if pt.ele:
                        jsonout["features"][-1]["geometry"]["coordinates"] \
                            .append((pt.lon, pt.lat, pt.ele))
                    else:
                        jsonout["features"][-1]["geometry"]["coordinates"] \
                            .append((pt.lon, pt.lat))

            print(json.dumps(jsonout, indent=2), file=outfp)


    def read_track_file_KML(self, filename):
        """Read a KML or KMZ track file.
           Return the BoundingBox.
           Just read Placemarks (which cover both paths and points);
           ignore all styles.
           Raise FileNotFoundError if the file doesn't exist,
           RuntimeError if it's not a track file,
           IOError or other exceptions as needed.
        """

        if self.Debug:
            print("Reading track file", filename)

        # Handle kmz compressed files, which are much more common in practice
        # than actual KML files.
        # XXX Supposedly kmz can include supporting files as well as
        # the main .kml file, but I haven't seen an example in practice yet.
        if filename.lower().endswith(".kmz") and zipfile.is_zipfile(filename):
            zipf = zipfile.ZipFile(filename)
            namelist = zipf.namelist()
            kmlfile = 'doc.kml'
            if kmlfile not in namelist:
                kmlfile = None
                for n in namelist:
                    if n.lower().endswith('.kml'):
                        kmlfile = n
                        break
            if not kmlfile:
                raise ValueError("No *.kml in %s" % filename)
            if len(namelist) > 1:
                print("Warning: ignoring files besides %s in %s:"
                      % (kmlfile, filename))
                print(" ", " ".join(namelist))
            kmlfp = zipf.open(kmlfile)
            doc_kml = kmlfp.read()
            kmlfp.close()
            dom = xml.dom.minidom.parseString(doc_kml)
            doc_kml = None
        else:
            dom = xml.dom.minidom.parse(filename)

        bbox = BoundingBox()

        # Features we care about are <Placemark> containing either
        # <LineString> (tracks) or <Point> (waypoints).
        # A Placemark also contains <name>The name</name>,
        # Placemarks are apparently grouped inside a <Document>
        # but let's not worry about that now.

        placemarks = dom.getElementsByTagName("Placemark")
        for placemark in placemarks:
            # Try to get a trail name.
            name = None
            try:
                name = placemark.getElementsByTagName("name")[0] \
                                .childNodes[0].data.strip()
            except:
                # no <name> tag, try for more esoteric schemes.
                # Lynn's USFS trail data has a scheme like
                # <ExtendedData><SchemaData ...><<SimpleData name="TrailName">
                # where the name might be TrailName or TrailNam_1
                try:
                    sdata = placemark.getElementsByTagName("ExtendedData")[0] \
                                     .getElementsByTagName("SimpleData")
                    for tag in sdata:
                        if tag.getAttribute("name").startswith("TrailNam"):
                            name = tag.childNodes[0].data.strip()
                            break
                except:
                    pass

            # Handle tracks:
            if not name:
                name = "unnamed"
            linestrings = placemark.getElementsByTagName("LineString")
            for linestring in linestrings:
                coord_triples = self.get_KML_coordinates(linestring)
                if not coord_triples:
                    continue
                self.points.append(name)
                for triple in coord_triples:
                    self.handle_track_point(triple[1], triple[0],
                                            ele=triple[2])
                    bbox.add_point(triple[1], triple[0])

            # Handle waypoints:
            if not name:
                name = NULL_WP_NAME
            points = placemark.getElementsByTagName("Point")
            for point in points:
                coord_triples = self.get_KML_coordinates(point)
                for triple in coord_triples:
                    if len(triple) == 3:
                        self.handle_track_point(triple[1], triple[0],
                                                ele=triple[2],
                                                waypoint_name=name)
                    elif len(triple) == 2:
                        self.handle_track_point(triple[1], triple[0],
                                                waypoint_name=name)
                    bbox.add_point(triple[1], triple[0])

        return bbox

    def get_KML_coordinates(self, el):
        """Get the contents of the first <coordinates> tuple
           inside the given element (which is inside a KML file).
           Inside a LineString, coordinate pairs or triples are separated
           by whitespace, which may include newlines.
           Return a list of tuple floats [[lat, lon, ele], [lat, lon, ele]]
           Not all KMLs have elevation, so use None in that case.
           coords may look like
              <coordinates> -70.35432000,  18.93176000</coordinates>
           or like
              <coordinates>
                -106.222544642583,35.81443097698173,0 -1 06.2213118192909,35.81387726967753,0 ...
              </coordinates>
        """
        coords = el.getElementsByTagName("coordinates")
        if not coords or len(coords) < 1:
            return None
        # coord_tuples = coords[0].childNodes[0].data.strip().split()
        coord_tuples = re.findall(
            r'\s*([0-9.-]+)\s*,\s*([0-9.-]+)(\s*,\s*[0-9.-]+)?',
            coords[0].childNodes[0].data)
        # This gives a list of things like
        # ('-106.222544642583', '35.81443097698173', ',0')
        ret = []
        for ctuple in coord_tuples:
            if len(ctuple) > 2 and ctuple[2]:
                ele = ctuple[2]
                if ele.startswith(','):
                    ele = ele[1:]
                ele = float(ele)
            else:
                ele = None
            ctuple = [float(ctuple[0]), float(ctuple[1])]
            ctuple.append(ele)
            ret.append(ctuple)

        return ret

    # mappers has to be defined at the end of the class
    # or it won't see the function names like read_track_file_GPX.
    mappers = (
        ( ('gpx',),            read_track_file_GPX ),
        ( ('kml', 'kmz'),      read_track_file_KML ),
        ( ('json', 'geojson'), read_track_file_GeoJSON )
    )
    """A list of file extensions recognized, and the functions that read them"""
