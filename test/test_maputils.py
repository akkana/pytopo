#!/usr/bin/env python3

from __future__ import print_function

import unittest
import sys

sys.path.insert(0, '..')

from pytopo.MapUtils import MapUtils

class MapUtilsTests(unittest.TestCase):

    # executed prior to each test
    def setUp(self):
        pass

    # executed after each test
    def tearDown(self):
        pass

    def test_map_utils(self):
        san_francisco = [ 37.471, -122.245 ]
        los_alamos = [ 35.531, -106.184 ]
        sydney = [ -33.517, 151.125 ]

        def test_between_two_points(p1, p2, havdist,
                                    bearing1, bearing2):
            dist1 = MapUtils.haversine_distance(*p1, *p2)
            dist2 = MapUtils.haversine_distance(*p2, *p1)
            self.assertEqual(dist1, dist2)
            self.assertEqual(round(dist1, 1), havdist)

            self.assertEqual(round(MapUtils.bearing(*p1, *p2), 1), bearing1)
            self.assertEqual(round(MapUtils.bearing(*p2, *p1), 1), bearing2)


        test_between_two_points(san_francisco, los_alamos,
                                901.0, 93.7, 283.3)
        test_between_two_points(san_francisco, sydney,
                                7412.7, 240.6, 56.1)

