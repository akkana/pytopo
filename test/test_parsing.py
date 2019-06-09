#!/usr/bin/env python3

from __future__ import print_function

import unittest
import sys

sys.path.insert(0, '..')

from pytopo.MapViewer import parse_saved_site_line

class ParseTests(unittest.TestCase):

    # executed prior to each test
    def setUp(self):
        pass

    # executed after each test
    def tearDown(self):
        pass

    def test_parsing(self):
        lines = [
            '"San Francisco", -122.245, 37.471',
            'sydney, 151.125, -33.517, "", 11',
            '[ "Treasure Island, zoomed", -122.221287, 37.493330, humanitarian, 13]',
        ]
        expected = [
            ['San Francisco', '-122.245', '37.471'],
            ['sydney', '151.125', '-33.517', '', '11'],
            ['Treasure Island, zoomed', '-122.221287', '37.493330',
             'humanitarian', '13'],
        ]
        for i, line in enumerate(lines):
            parsed = parse_saved_site_line(line)
            self.assertEqual(parsed, expected[i])

