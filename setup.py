#! /usr/bin/env python
#
# Copyright (C) 2012 Nuxeo
#

import sys
from datetime import datetime

from distutils.core import setup
scripts = ["nuxeo-drive-client/bin/ndrive"]
freeze_options = {}

name = 'nuxeo-drive'
packages = [
    'nxdrive',
    'nxdrive.tests',
    'nxdrive.gui',
    'nxdrive.data',
    'nxdrive.data.icons',
]
package_data = {
    'nxdrive.data.icons': ['*.png', '*.svg', '*.ico'],
}
script = 'nuxeo-drive-client/bin/ndrive'
win_icon = 'nuxeo-drive-client/nxdrive/data/icons/nuxeo_drive_icon_64.ico'
png_icon = 'nuxeo-drive-client/nxdrive/data/icons/nuxeo_drive_icon_64.png'
if sys.platform == 'win32':
    icon = win_icon
else:
    icon = png_icon

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


if '--freeze' in sys.argv:
    print "Building standalone executable..."
    sys.argv.remove('--freeze')
    from cx_Freeze import setup, Executable

    # build_exe does not seem to take the package_dir info into account
    sys.path.append('nuxeo-drive-client')

    executables = [Executable(script, base=None, icon=icon)]

    if sys.platform == "win32":
        # Windows GUI program that can be launched without a cmd console
        executables.append(
            Executable(script, targetName="ndrivew.exe", base="Win32GUI",
                       icon=icon, shortcutDir="ProgramMenuFolder",
                       shortcutName="Nuxeo Drive"))
    scripts = []
    # special handling for data files
    packages.remove('nxdrive.data')
    packages.remove('nxdrive.data.icons')
    package_data = {}
    data_home = 'nuxeo-drive-client/nxdrive/data'
    include_files = [
        (data_home + "/icons/nuxeo_drive_icon_%d.png" % i,
         "icons/nuxeo_drive_icon_%d.png" % i)
        for i in [16, 32, 48, 64]
    ]
    freeze_options = dict(
        executables=executables,
        options={
            "build_exe": {
                "includes": [
                    "PySide",
                    "PySide.QtCore",
                    "PySide.QtNetwork",
                    "PySide.QtGui",
                    "atexit",  # implicitly required by PySide
                    "sqlalchemy.dialects.sqlite",
                ],
                "packages": packages + [
                    "nose",
                ],
                "excludes": [
                    "ipdb",
                    "clf",
                    "IronPython",
                    "pydoc",
                    "tkinter",
                ],
                "include_files": include_files,
            },
            "bdist_msi": {
                "add_to_path": True,
                "upgrade_code": '{800B7778-1B71-11E2-9D65-A0FD6088709B}',
            },
            #"bdist_app": {
            #    "bundle_iconfile": "MacOS/icons/nuxeo_drive_icon_64.png",
            #},
            "bdist_dmg": {
                "volume_label": "Nuxeo Drive",
            },
        },
    )
    # TODO: investigate with esky to get an auto-updateable version but
    # then make sure that we can still have .msi and .dmg packages
    # instead of simple zip files.


setup(
    name=name,
    version=version,
    description="Desktop synchronization client for Nuxeo.",
    author="Nuxeo",
    author_email="contact@nuxeo.com",
    url='http://github.com/nuxeo/nuxeo-drive',
    packages=packages,
    package_dir={'nxdrive': 'nuxeo-drive-client/nxdrive'},
    package_data=package_data,
    scripts=scripts,
    long_description=open('README.rst').read(),
    **freeze_options
)
