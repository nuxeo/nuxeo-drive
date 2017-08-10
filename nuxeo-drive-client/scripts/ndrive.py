#!/usr/bin/env python
# coding: utf-8
"""
Commandline interface for the Nuxeo Drive filesystem synchronizer.
TODO: With NXDRIVE-739 this file should be the same as others in this directory.
"""

import sys

try:
    from nxdrive.commandline import main
except ImportError:
    from os.path import dirname
    from sys import path
    from utils import module_path

    path.append(dirname(module_path()))
    from nxdrive.commandline import main


sys.exit(main())
