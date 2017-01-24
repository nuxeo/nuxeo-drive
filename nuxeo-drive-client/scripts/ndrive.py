#!/usr/bin/env python
"""Commandline interface for the Nuxeo Drive filesystem synchronizer"""
try:
    from nxdrive.commandline import main
except ImportError:
    from os.path import dirname
    from sys import path
    from utils import module_path

    path.append(dirname(module_path()))
    from nxdrive.commandline import main


exit(main())
