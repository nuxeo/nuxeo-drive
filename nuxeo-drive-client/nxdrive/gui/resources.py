"""Helper to lookup UI resources from package"""

import re
import os
from nxdrive.logging_config import get_logger

log = get_logger(__name__)


def find_icon(icon_filename):
    """Find the FS path of an icon on various OS binary packages"""
    import nxdrive
    nxdrive_path = os.path.dirname(nxdrive.__file__)
    icons_path = os.path.join(nxdrive_path, 'data', 'icons')

    cxfreeze_suffix = os.path.join('library.zip', 'nxdrive')
    app_resources = '/Contents/Resources/'

    if app_resources in nxdrive_path:
        # OSX frozen distribution, bundled as an app
        icons_path = re.sub(app_resources + ".*", app_resources + 'icons',
                             nxdrive_path)

    elif nxdrive_path.endswith(cxfreeze_suffix):
        # Frozen distribution of nxdrive, data is out of the zip
        icons_path = nxdrive_path.replace(cxfreeze_suffix, 'icons')

    if not os.path.exists(icons_path):
        log.warning("Could not find the icons folder at: %s", icons_path)
        return None

    icon_filepath = os.path.join(icons_path, icon_filename)
    if not os.path.exists(icon_filepath):
        log.warning("Could not find icon file: %s", icon_filepath)
        return None

    return icon_filepath
