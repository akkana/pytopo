#!/usr/bin/env python3

import unittest
import sys, os

sys.path.insert(0, '..')

import pytopo.configfile as configfile


class ConfigFileTests(unittest.TestCase):

    # executed prior to each test
    def setUp(self):
        pass

    # executed after each test
    def tearDown(self):
        pass

    def test_parse_saved_sites(self):
        test_lines = [
            '[ \'paria-ranger\', -111.912, 37.106, "opencyclemap" ]',
            ' \t [ "coldspring",    -109.3734,  37.2150,  \'USGS\' ]  ',
            '[ "PEEC", -106.183758, 35.530912, opencyclemap, 18] \n',
        ]
        parsed_lines = [
            [ 'paria-ranger', -111.912,      37.106, 'opencyclemap' ],
            [ 'coldspring',   -109.3734, 37.2150, 'USGS' ],
            [ 'PEEC',         -106.183758,    35.530912, "opencyclemap", 18 ],
        ]

        known_sites = []
        for i, line in enumerate(test_lines):
            site = configfile.parse_saved_site_line(line)
            # print(i, ":", site)
            self.assertEqual(site, parsed_lines[i])
            known_sites.append(site)

        configfile.CONFIG_DIR = "test/files"
        configfile.save_sites(known_sites)
        self.assertEqual(configfile.saved_sites_filename(),
                         "test/files/saved.sites")
        self.assertTrue(os.path.exists(configfile.saved_sites_filename()))

        read_sites = configfile.read_saved_sites()
        self.assertEqual(read_sites, known_sites)

        os.unlink(configfile.saved_sites_filename())


