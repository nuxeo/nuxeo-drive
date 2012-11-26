#!/usr/bin/env python
"""Commandline interface for the Nuxeo Drive filesystem synchronizer"""

import sys
import os

if sys.platform == "darwin":
    # Workaround a bug of the py2app code freezer that can only be
    # reproduced on the Continuous Integration machine building the
    # .dmg package of Nuxeo Drive
    import nxdrive
    dynload_folder = os.path.normpath(os.path.join(
        os.path.dirname(nxdrive.__file__),
        '../../lib-dynload'
    ))
    if os.path.exists(dynload_folder) and dynload_folder not in sys.path:
        sys.path.append(dynload_folder)

from nxdrive.commandline import main
sys.exit(main())
