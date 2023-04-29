#!/usr/bin/env python3

import os.path
import ast


if 'XDG_CONFIG_HOME' in os.environ:
    CONFIG_DIR = os.path.join(os.environ['XDG_CONFIG_HOME'], "pytopo")
else:
    CONFIG_DIR = os.path.expanduser("~/.config/pytopo",)

def saved_sites_filename():
    return os.path.join(CONFIG_DIR, "saved.sites")

DEBUG = False

NEED_SAVED_SITE_REWRITE = False


# Check for a user config file named .pytopo
# in either $HOME/.config/pytopo or $HOME.
#
# Format of the user config file:
# It is a python script, which can include arbitrary python code,
# but the most useful will be KnownSites definitions,
# with coordinates specified in degrees.decimal_minutes,
# like this:
# KnownSites = [
#     # Death Valley
#     [ "zabriskie", 116.475, 36.245, "dv_data" ],
#     [ "badwater", 116.445, 36.125, "dv_data" ],
#     # East Mojave
#     [ "zzyzyx", 116.05, 35.08, "emj_data" ]
#     ]
def exec_config_file(init_width, init_height):
    """Load the user's .pytopo config file,
       found either in $HOME/.config/pytopo/ or $HOME/pytopo.
       Returns a dictionary with keys that may include:
       KnownSites, init_width, init_height, defaultCollection, user_agent
    """
    userfile = os.path.join(CONFIG_DIR, "pytopo.sites")
    if not os.access(userfile, os.R_OK):
        if DEBUG:
            print("Couldn't open", userfile)
        userfile = os.path.expanduser("~/.pytopo")
        if not os.access(userfile, os.R_OK):
            if DEBUG:
                print("Couldn't open", userfile, "either")
            userfile = os.path.join(CONFIG_DIR, "pytopo", ".pytopo")
            if not os.access(userfile, os.R_OK):
                if DEBUG:
                    print("Couldn't open", userfile, "either")
                userfile = create_initial_config()
                if userfile is None:
                    print("Couldn't create a new pytopo config file")
                    return
            else:
                print("Suggestion: rename", userfile, \
                      "to ~/.config/pytopo/pytopo.sites")
                print(userfile, "may eventually be deprecated")
    if DEBUG:
        print("Found", userfile)

    # Now we'd better have a userfile

    # Initial values for the dictionary that will be returned:
    locs = {'Collections': [3, 4],
            'KnownSitesFormat': None,
            'KnownSites': [],
            'init_width': init_width,
            'init_height': init_height
            }
    globs = {}

    # Import the map collection classes automatically:
    execstring = '''
from pytopo import OSMMapCollection
from pytopo import Topo1MapCollection
from pytopo import Topo2MapCollection
from pytopo import GenericMapCollection
'''

    with open(userfile) as fp:
        # exec is a security problem only if you let other people
        # modify your pytopo.sites. So don't.
        execstring += fp.read()
        exec(execstring, globs, locs)

    return locs


def parse_saved_site_line(line):
    """The saved sites file has lines like
       ['paria-ranger', -111.912, 37.106, 'opencyclemap']
       ['PEEC', -106.183758, 35.530912, opencyclemap, 18]
       name, longitude, latitude, collection, optional zoom
       Note the lack of quotes around the collection name in the
       second example; that was a bug in an earlier version of pytopo
       that the parser needs to account for.
    """
    try:
        ret = ast.literal_eval(line)
    except SyntaxError:
        print("Syntax error parsing saved site line '%s'" % line)
        return None
    except ValueError:
        # An unquoted string will raise a ValueError.
        print("Value error parsing saved site line '%s'" % line)
        global NEED_SAVED_SITE_REWRITE
        ret = parse_unquoted_saved_site_line(line)
        if ret and len(ret) >= 3:
            NEED_SAVED_SITE_REWRITE = True

    if type(ret) is not list and type(ret) is not tuple:
        print("Saved site line isn't a list: '%s'" % line)
        return None
    if len(ret) < 3:
        print("Warning: not enough elements in saved site line '%s'" % line)
    return ret


def parse_unquoted_saved_site_line(line):
    """parse a saved_site line where some strings may be unquoted
    """
    from io import StringIO
    import tokenize
    tokens = tokenize.generate_tokens(StringIO(line).readline)
    modified_tokens = (
        (tokenize.STRING, repr(token.string))
          if token.type == tokenize.NAME
          else token[:2]
        for token in tokens)
    fixed_input = tokenize.untokenize(modified_tokens)
    return ast.literal_eval(fixed_input)


def read_saved_sites():
    """Read previously saved (favorite) sites."""

    # A line typically looks like this:
    # [ "san-francisco", -121.750000, 37.400000, "openstreetmap" ]
    # or, with an extra optional zoom level and included comma,
    # [ "Treasure Island, zoomed", -122.221, 37.493, humanitarian, 13 ]
    try:
        sitesfile = open(saved_sites_filename(), "r")
    except:
        return []

    known_sites = []

    for line in sitesfile:
        site = parse_saved_site_line(line.strip())
        if not site:
            print(f"Couldn't parse line: '{ line }'")
            continue

        site[1] = float(site[1])    # longitude
        site[2] = float(site[2])    # latitude
        if len(site) > 4:
            site[4] = int(site[4])  # zoom level

        known_sites.append(site)

    sitesfile.close()
    if NEED_SAVED_SITE_REWRITE:
        print("Updating old-style saved.sites file")
        save_sites(known_sites)
    return known_sites


def read_tracks():
    """Read in all tracks from ~/Tracks."""
    trackdir = os.path.expanduser('~/Tracks')

    tracks = []
    if os.path.isdir(trackdir):
        for f in glob.glob(os.path.join(trackdir, '*.gpx')):
            head, gpx = os.path.split(f)
            filename = gpx.partition('.')[0]
            tracks.append([filename, f])

    return tracks


def save_sites(known_sites):
    """Write any new KnownSites to file.
       Should only be called from graceful exit.
    """
    try:
        savefile = open(saved_sites_filename(), "w")
    except:
        print("Couldn't open save file", saved_sites_filename())
        return

    for site in known_sites:
        # known_sites is a list of lists:
        # [ [ name, lon, lat, [collection], [zoomlevel]
        print('[ "%s", %f, %f' % (site[0], site[1], site[2]),
              end='', file=savefile)
        if len(site) > 3:
            print(', "%s"' % site[3], end='', file=savefile)
        if len(site) > 4:
            print(', %d' % site[4], end='', file=savefile)
        print(" ]", file=savefile)

    savefile.close()


def create_initial_config():
    """Make an initial configuration file.
       If the user has a ~/.config, make ~/.config/pytopo/pytopo.sites.
    """
    if not os.access(CONFIG_DIR, os.W_OK):
        os.makedirs(CONFIG_DIR)
    userfile = os.path.join(CONFIG_DIR, "pytopo.sites")
    fp = open(userfile, 'w')

    # Try to get a username
    import getpass
    try:
        username = getpass.getuser()
        if not username:
            username = "<unknown>"
    except:
        username = "<unknown>"

    # Now we have fp open. Write a very basic config to it.
    print("""# Pytopo site file


#
# Older versions of PyTopo used dd.mmss (degrees, minutes, seconds)
# for coordinates in the KnownSites list.
# As of 2023, the default for new site files has changed to
# "DecimalDegrees"
#
# If KnownSitesFormat is unset, PyTopo will assume coordinates
# are in DD.MMSS, and will convert them to decimal degrees any
# time the site file is rewritten,
# unless you set KnownSitesFormat to "DD.MMSS".
#
# KnownSitesFormat = "DecimalDegrees"


# Map collections

Collections = [
    # OpenStreetMap's Tile Usage Policy is discussed at
    # https://operations.osmfoundation.org/policies/tiles/
    # and requests that apps not use tile.openstreetmap.org without permission.
    # Consider signing up for an API key for a map tile service,
    # like ThunderForest.
    # If you choose to use OSM, please add a user_agent line elsewhere
    # in this file, such as
    # user_agent = "PyTopo customized by Your Name Here"
    # and use it sparingly, so OSM doesn't get upset and ban all PyTopo users.

    # Humanitarian
    OSMMapCollection( "humanitarian", "~/Maps/humanitarian",
                      ".png", 256, 256, 10,
                      "http://a.tile.openstreetmap.fr/hot/{z}/{x}/{y}.png",
                      maxzoom=15,
                      attribution="Humanitarian OSM Maps, map data © OpenStreetMap contributors"),

    # The USGS National Map provides various kinds of tiles.
    # Here's their basic Topo tile.
    # Their documentation says they support zooms to 19,
    # but in practice they give an error after zoom level 15.
    # They're a bit flaky: sometimes they don't load, or load blank tiles.
    OSMMapCollection( "USGS", "~/Maps/USGS",
                      ".jpg", 256, 256, 10,
                       "https://basemap.nationalmap.gov/arcgis/rest/services/USGSTopo/MapServer/WMTS?SERVICE=WMTS&REQUEST=GetTile&VERSION=1.0.0&LAYER=USGSTopo&STYLE=default&TILEMATRIXSET=GoogleMapsCompatible&TILEMATRIX={z}&TILEROW={y}&TILECOL={x}&FORMAT=image%%2Fjpeg",
                      maxzoom=15,
                      attribution="USGS National Map"),

    # USGS also offers satellite tiles:
    OSMMapCollection( "USGS Imagery", "~/Maps/USGS-imagery",
                      ".jpg", 256, 256, 11,
                       "https://basemap.nationalmap.gov/arcgis/rest/services/USGSImageryOnly/MapServer/WMTS?SERVICE=WMTS&REQUEST=GetTile&VERSION=1.0.0&LAYER=USGSImageryOnly&STYLE=default&TILEMATRIXSET=GoogleMapsCompatible&TILEMATRIX={z}&TILEROW={y}&TILECOL={x}&FORMAT=image%%2Fjpeg",
                      maxzoom=15,
                      attribution="USGS National Map"),

    # ThunderForest offers OpenCycleMap tiles and several other good styles,
    # but you'll need to sign up for an API key from http://thunderforest.com.
    # OSMMapCollection( "opencyclemap", "~/Maps/opencyclemap",
    #                   ".png", 256, 256, 13,
    #                   "https://tile.thunderforest.com/cycle/{z}/{x}/{y}.png?apikey=YOUR_API_KEY_HERE",
    #                   maxzoom=22, reload_if_older=90,  # reload if > 90 days
    #                   attribution="Maps © www.thunderforest.com, Data © www.osm.org/copyright"),
    ]

KnownSites = [
    # Some base values to get new users started.
    # Note that these coordinates are a bit northwest of the city centers;
    # they're the coordinates of the map top left, not center.
    [ "san-francisco", -122.245, 37.471, "", 11 ],
    [ "new-york", -74.001, 40.4351, "", 11 ],
    [ "london", -0.072, 51.3098, "", 11 ],
    [ "sydney", 151.125, -33.517, "", 11 ],
    ]

user_agent = "PyTopo customized by %s"
""" % (username), file=fp)
    fp.close()

    print("""Welcome to Pytopo!
Created an initial site file in %s
You can add new sites and collections there; see the instructions at
   http://shallowsky.com/software/topo/
""" % (userfile))

    return userfile


if __name__ == '__main__':
    pass
    # migrate_sites_dms_dd(os.path.expanduser("~/.confi

