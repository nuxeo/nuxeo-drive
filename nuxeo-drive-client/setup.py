#! /usr/bin/env python
#
# Copyright (C) 2012 Nuxeo
#
try:
    from esky import bdist_esky
except ImportError:
    print("WARN: Install esky and cx_Freeze if you want to build the "
          " auto-updatable, standalone distribution of nxdrive.")
from distutils.core import setup

setup(
    name='nuxeo-drive',
    version='0.1.0-git',
    description="Desktop synchronization client for Nuxeo.",
    author="Olivier Grisel",
    author_email="ogrisel@nuxeo.com",
    url='http://github.com/nuxeo/nuxeo-drive',
    packages=[
        'nxdrive',
        'nxdrive.tests',
    ],
    scripts=["bin/ndrive"],
    options={
        "bdist_esky": {
            # forcibly include some modules
            #"includes": ["nxdrive"],
            # forcibly exclude some other modules
            "excludes": ["pydoc", "ipdb"],
        }
    },
    long_description=open('README.rst').read(),
)
