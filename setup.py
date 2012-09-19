#! /usr/bin/env python
#
# Copyright (C) 2012 Nuxeo
#

import sys
from datetime import datetime

from distutils.core import setup
executables = []
scripts = ["nuxeo-drive-client/bin/ndrive"]

if '--freeze' in sys.argv:
    print "Building standalone executable..."
    sys.argv.remove('--freeze')
    from cx_Freeze import setup, Executable

    # build_exe does not seem to take the package_dir info into account
    sys.path.append('nuxeo-drive-client')

    base = None
    if sys.platform == "win32":
        #base = "Win32GUI"
        base = None
    executables = [Executable(s, base=base) for s in scripts]
    scripts = []
    # TODO: investigate with esky to get an auto-updateable version but
    # then make sure that we can still have .msi and .dmg packages
    # instead of simple zip files.

name = 'nuxeo-drive'

version = '0.1.0'
if '--dev' in sys.argv:
    # timestamp the dev artifacts for continuous integration
    # distutils only accepts "b" + digit
    sys.argv.remove('--dev')
    timestamp = datetime.utcnow().isoformat()
    timestamp = timestamp.replace(":", "")
    timestamp = timestamp.replace(".", "")
    timestamp = timestamp.replace("T", "")
    timestamp = timestamp.replace("-", "")
    version += "b" + timestamp

setup(
    name=name,
    version=version,
    description="Desktop synchronization client for Nuxeo.",
    author="Olivier Grisel",
    author_email="ogrisel@nuxeo.com",
    url='http://github.com/nuxeo/nuxeo-drive',
    packages=[
        'nxdrive',
        'nxdrive.tests',
    ],
    package_dir={'nxdrive': 'nuxeo-drive-client/nxdrive'},
    scripts=scripts,
    executables=executables,
    options = {
        "build_exe": {
            "packages": [
                "nxdrive",
                "nxdrive.tests",
                "sqlalchemy.dialects.sqlite",
                "nose",
            ],
            "excludes": [
                "ipdb",
                "clf",
                "IronPython",
                "pydoc",
                "tkinter",
            ],
        },
        "bdist_msi": {
            #    "add-to-path": True,
            #    "upgrade-code": name + '--' + version,
        },
    },
    long_description=open('README.rst').read(),
)
