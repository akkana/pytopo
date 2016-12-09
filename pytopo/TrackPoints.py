# Copyright (C) 2009-2016 by Akkana Peck.
# You are free to use, share or modify this program under
# the terms of the GPLv2 or, at your option, any later GPL.

'''Parsing and handling of GPS track files in pytopo.
'''

import os
import xml.dom.minidom
import zipfile
import simplejson

from pytopo import __version__


class TrackPoints(object):

    """Parsing and handling of GPS track files.
       Supports GPX, KML, KMZ and GeoJSON.
       A TrackPoints object can include a track (points[])
       and a list of waypoints (waypoints[]).

       Each point in a track can be either a trackpoint or the beginning
       of a new track segment.

       Beginnings of segments are represented by the name of the
       segment as a string or unicode, but use is_start() to test for
       that in case of future changes.

       A trackpoint is an array where the first two elements are
       longitude and latitude, as floatings.
       Following longitude there may be an optional elevation, a float,
       or waypoint name, a string or unicode.
       Finally, a dictionary may be present, containing additional
       elements like time (timestamp).

    """

    def __init__(self):
        self.points = []
        self.waypoints = []
        self.minlon = 361
        self.maxlon = -361
        self.minlat = 91
        self.maxlat = -91

        self.Debug = False

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
        '''Is this the start of a new track segment?
           If so, it's a string (or unicode), the name of the track section.
        '''
        return isinstance(point, str) or isinstance(point, unicode)

    def get_bounds(self):
        '''Get bounds encompassing all contained tracks and waypoints.'''
        return self.minlon, self.minlat, self.maxlon, self.maxlat

    def is_attributes(self, point):
        '''Is this point actually a set of attributes?'''
        return isinstance(point, dict)

    def attributes(self, trackindex):
        '''Does the indicated track have attributes? Then return them.
        '''
        # Currently attributes are represented by a dictionary
        # as the next item after the name in the trackpoints list.
        if self.is_attributes(self.points[trackindex + 1]):
            return self.points[trackindex + 1]
        return None

    def handle_track_point(self, lat, lon,
                           ele=None, waypoint_name=False, timestamp=None):
        '''Add a new trackpoint or waypoint after some basic sanity checks.
           If waypoint_name, we assume this is a waypoint,
           otherwise assume it's a track point.
        '''
        if lon < self.minlon:
            self.minlon = lon
        if lon > self.maxlon:
            self.maxlon = lon
        if lat < self.minlat:
            self.minlat = lat
        if lat > self.maxlat:
            self.maxlat = lat

        point = [lon, lat]

        if waypoint_name:
            point.append(waypoint_name)

        if ele:
            point.append(ele)

        if timestamp:
            point.append({"time": timestamp})
        # Note: GPX files imported from KML may have no timestamps.

        if waypoint_name:
            self.waypoints.append(point)
        else:
            self.points.append(point)

    def get_ele(self, point):
        """Get the saved elevation of a point, if any.
        """
        if len(point) < 3:
            return None
        ele = point[2]
        if isinstance(ele, str) or isinstance(ele, unicode):
            return ele
        return None

    def get_timestamp(self, point):
        """Does the point have a dict with a time element? If so, return it.
        """
        dic = point[-1]
        if isinstance(dic, dict):
            return None
        if "time" not in dic:
            return None
        return dic["time"]

    def read_track_file(self, filename):
        """Read a track file. Throw IOError if the file doesn't exist."""
        # XXX Should read magic number rather than depending on extension
        if filename.lower().endswith('.kml') or \
           filename.lower().endswith('.kmz'):
            return self.read_track_file_KML(filename)
        elif filename.lower().endswith('json'):
            return self.read_track_file_GeoJSON(filename)
        return self.read_track_file_GPX(filename)

    def read_track_file_GPX(self, filename):
        """Read a GPX track file. Throw IOError if the file doesn't exist."""

        if not os.path.exists(filename):
            raise IOError("Can't open track file %s" % filename)

        if self.Debug:
            print "Reading track file", filename
        dom = xml.dom.minidom.parse(filename)

        # Handle track(s).
        segs = dom.getElementsByTagName("trkseg")
        for seg in segs:
            trkpts = seg.getElementsByTagName("trkpt")

            # need to keep different track files and segments separate: don't
            # draw lines from the end of a track to the beginning of the next.
            if trkpts:
                # See if the parent track has a name.
                trk = seg
                while trk.nodeName != "trk":
                    trk = trk.parentNode
                trkname = trk.getElementsByTagName("name")
                if trkname and \
                   trkname[0].hasChildNodes() and \
                   trkname[0].firstChild.nodeName == '#text' and \
                   trkname[0].firstChild.wholeText:
                    self.points.append(trkname[0].firstChild.wholeText)
                else:
                    self.points.append(os.path.basename(filename))

                for pt in trkpts:
                    # self.handle_track_pointGPX(pt, False)
                    lat, lon, ele, ts = self.GPX_point_coords(pt)
                    self.handle_track_point(lat, lon, ele, None, timestamp=ts)

        # Handle waypoints
        waypts = dom.getElementsByTagName("wpt")
        if waypts:
            self.waypoints.append(os.path.basename(filename))
            for pt in waypts:
                lat, lon, ele, time = self.GPX_point_coords(pt)
                name = "WP"
                name = self.get_DOM_text(pt, "name")
                self.handle_track_point(lat, lon, ele, name, timestamp=time)

        # GPX also allows for routing, rtept, but I don't think we need those.

    def get_DOM_text(self, node, childname=None):
        '''Get the text out of a DOM node.
           Or, if childname is specified, get the text out of a child
           node with node name childname.
        '''
        # print "get_DOM_text", node
        if childname:
            nodes = node.getElementsByTagName(childname)
            # print "node has", len(nodes), childname, "children"
            if not nodes:
                return None
            node = nodes[0]
        if not node:
            return None
        n = node.childNodes
        if len(n) >= 1 and n[0].nodeType == n[0].TEXT_NODE:
            return n[0].data
        return None

    def GPX_point_coords(self, point):
        '''Add a new trackpoint or waypoint from a GPX node'''
        lat = float(point.getAttribute("lat"))
        lon = float(point.getAttribute("lon"))
        ele = self.get_DOM_text(point, "ele")
        time = self.get_DOM_text(point, "time")
        # For now, keep elevation and time as unchanged strings.
        return lat, lon, ele, time

    def save_GPX(self, filename):
        '''Save all known tracks and waypoints as a GPX file.
           XXX We don't have valid <time> saved for these points.
        '''
        with open(filename, "w") as outfp:
            print >>outfp, '''<?xml version='1.0' encoding='UTF-8' standalone='yes' ?>
<gpx version="1.1" creator="PyTopo %s~" xmlns="http://www.topografix.com/GPX/1/1" xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance" xsi:schemaLocation="http://www.topografix.com/GPX/1/1 http://www.topografix.com/GPX/1/1/gpx.xsd">
''' % __version__
            if self.points:
                print >>outfp, "  <trk>"
                started = False
                for pt in self.points:
                    if self.is_start(pt):
                        if started:
                            print >>outfp, "    </trkseg>"
                        else:
                            started = True
                        print >>outfp, "    <trkseg>"
                    else:
                        print >>outfp, \
                            '      <trkpt lat="%f" lon="%f">' % (pt[1], pt[0])
                        ele = self.get_ele(pt)
                        if ele:
                            print >>outfp, '        <ele>%s</ele>' % ele
                        ts = self.get_timestamp(pt)
                        if ts:
                            print >>outfp, '        <time>%s</time>' % ts
                        print >>outfp, '      </trkpt>'
                print >>outfp, "    </trkseg>"
                print >>outfp, "  </trk>"

            for pt in self.waypoints:
                if self.is_start(pt):
                    continue
                print >>outfp, '''  <wpt lat="%f" lon="%f">
    <time>2015-12-02T16:50:34Z</time>
    <name>%s</name>
  </wpt>''' % (pt[1], pt[0], pt[2])

            print >>outfp, "</gpx>"

    def read_track_file_GeoJSON(self, filename):
        """Read a GeoJSON track file.
        """
        with open(filename) as fp:
            gj = simplejson.loads(fp.read())
        if gj["type"] != "FeatureCollection":
            print filename, "isn't a FeatureCollection"
            return
        if "features" not in gj:
            print "No features in geojson file", filename
            return
        for feature in gj["features"]:
            featuretype = feature["geometry"]["type"]
            if featuretype != "LineString" and featuretype != "MultiLineString":
                continue
            # It's a track. Add it.
            name = None
            if "properties" in feature:
                props = feature["properties"]
                for key in props:
                    kl = key.lower()
                    if kl == "name" or kl == "trailname":
                        name = props[key]

            # Properties may specify a null name, but we need something.
            if not name:
                name = "unnamed"

            if featuretype == "LineString":
                self.points.append(name)
                if "properties" in feature:
                    self.points.append(feature["properties"])
                for coords in feature["geometry"]["coordinates"]:
                    lon, lat, ele = coords
                    self.handle_track_point(lat, lon, ele, None)
            elif featuretype == "MultiLineString":
                for linestring in feature["geometry"]["coordinates"]:
                    self.points.append(name)
                    if "properties" in feature:
                        self.points.append(feature["properties"])
                    for coords in linestring:
                        lon, lat, ele = coords
                        self.handle_track_point(lat, lon, ele, None)

    def read_track_file_KML(self, filename):
        """Read a KML or KMZ track file.
           Just read Placemarks (which cover both paths and points);
           ignore all styles.
           Throw IOError if the file doesn't exist.
        """

        if not os.path.exists(filename):
            raise IOError("Can't open track file %s" % filename)

        if self.Debug:
            print "Reading track file", filename

        # Handle kmz compressed files, which are much more common in practice
        # than actual KML files:
        if filename.lower().endswith(".kmz") and zipfile.is_zipfile(filename):
            zipf = zipfile.ZipFile(filename)
            namelist = zipf.namelist()
            if "doc.kml" not in namelist:
                raise ValueError("No doc.kml in %s" % filename)
            if len(namelist) > 1:
                print "Warning: ignoring files other than doc.kml in", filename
            kmlfp = zipf.open("doc.kml")
            doc_kml = kmlfp.read()
            kmlfp.close()
            dom = xml.dom.minidom.parseString(doc_kml)
            doc_kml = None
        else:
            dom = xml.dom.minidom.parse(filename)

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
                name = placemark.getElementsByTagName("name")[0].childNodes[0].data.strip()
            except:
                # no <name> tag, try for more esoteric schemes.
                # Lynn's USFS trail data has a scheme like
                # <ExtendedData><SchemaData ...><<SimpleData name="TrailName">
                # where the name might be TrailName or TrailNam_1
                try:
                    sdata = placemark.getElementsByTagName("ExtendedData")[0].getElementsByTagName("SimpleData")
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
                    self.handle_track_point(triple[1], triple[0], triple[2],
                                            None)

            # Handle waypoints:
            if not name:
                name = "WP"
            points = placemark.getElementsByTagName("Point")
            for point in points:
                coord_triples = self.get_KML_coordinates(point)
                for triple in coord_triples:
                    if len(triple) == 3:
                        self.handle_track_point(triple[1], triple[0],
                                                triple[2], name)
                    elif len(triple) == 2:
                        self.handle_track_point(triple[1], triple[0],
                                                None, name)

    def get_KML_coordinates(self, el):
        '''Get the contents of the first <coordinates> triple
           inside the given element (which is inside a KML file).
           Inside a LineString, coordinate pairs or triples are separated
           by whitespace, which may include newlines.
           Return a list of triples [[lat, lon, ele], [lat, lon, ele] ...]
           Not all KMLs have elevation, so use None in that case.
        '''
        coords = el.getElementsByTagName("coordinates")
        if not coords or len(coords) < 1:
            return None
        coord_triples = coords[0].childNodes[0].data.strip().split()
        ret = []
        for s in coord_triples:
            triple = s.split(',')
            triple = map(float, triple)
            if len(triple) == 2:
                triple.append(None)
            ret.append(triple)

        return ret
