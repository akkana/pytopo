#!/usr/bin/env python3

from PIL import Image, UnidentifiedImageError
from PIL.ExifTags import TAGS, GPSTAGS
from datetime import datetime
import os


def gps_from_image(img_path):
    """Return a dictionary of latitude, longitude, filename, maybe other values,
       or None if img_path isn't an image file,
       has no exif, or other problems.
    """
    try:
        img = Image.open(img_path)
    except UnidentifiedImageError:
        return None

    exif_data = img._getexif()
    if not exif_data:
        return None

    def DMS2dec(dms):
        """Convert an iterable of degrees, mins, secs to decimal degrees"""
        return dms[0] + dms[1]/60. + dms[2]/3600.

    for tag, value in exif_data.items():
        tagname = TAGS.get(tag, tag)
        longitude_sign = 1.0
        gpsdate = None
        gpstime = None
        if tagname == 'GPSInfo':
            gps_info = {}
            for key in value.keys():
                gpskey = GPSTAGS.get(key,key)
                # gps_info[gpskey] = value[key]
                if gpskey == 'GPSLatitude':
                    gps_info['latitude'] = DMS2dec(value[key])
                elif gpskey == 'GPSLongitude':
                    gps_info['longitude'] = DMS2dec(value[key])
                elif gpskey == 'GPSLongitudeRef':
                    if value[key] == 'W':
                        longitude_sign = -1.0
                elif gpskey == 'GPSImgDirection':
                    gps_info['img_direction'] = value[key]
                elif gpskey == 'GPSDateStamp':
                    gpsdate = value[key]
                elif gpskey == 'GPSTimeStamp':
                    gpstime = value[key]
            if 'latitude' not in gps_info or 'longitude' not in gps_info:
                return None

            gps_info['longitude'] *= longitude_sign

            gps_info['filename'] = os.path.basename(img_path)
            if gpsdate and gpstime:
                # gpsdate is a string like '2024:09:25'
                # gpstime is a float-3-tuple like (17.0, 5.0, 55.0)
                # TrackPoints wants a string like '2014-08-07T01:19:24Z'
                gps_info['timestamp'] = '%sT%02d:%02d:%0dZ' % (
                    gpsdate.replace(':', '-'),
                    *(gpstime))
            else:
                gps_info['timestamp'] = None
            return gps_info

    # Didn't see GPSInfo
    return None


if __name__ == '__main__':
    import sys
    for f in sys.argv[1:]:
        gps_data = get_gps_from_image(f)
        print(gps_data)

