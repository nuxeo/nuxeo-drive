#! /usr/bin/env python
#
# Copyright (C) 2012 Nuxeo
#

import os
import sys
from datetime import datetime

from distutils.core import setup

scripts = ["nuxeo-drive-client/scripts/ndrive"]
freeze_options = {}

name = 'nuxeo-drive'
packages = [
    'nxdrive',
    'nxdrive.client',
    'nxdrive.tests',
    'nxdrive.gui',
    'nxdrive.protocol_handler',
    'nxdrive.data',
    'nxdrive.data.icons',
]
package_data = {
    'nxdrive.data.icons': ['*.png', '*.svg', '*.ico', '*.icns'],
}
script = 'nuxeo-drive-client/scripts/ndrive'
icons_home = 'nuxeo-drive-client/nxdrive/data/icons'
win_icon = os.path.join(icons_home, 'nuxeo_drive_icon_64.ico')
png_icon = os.path.join(icons_home, 'nuxeo_drive_icon_64.png')
osx_icon = os.path.join(icons_home, 'nuxeo_drive_app_icon_128.icns')

if sys.platform == 'win32':
    icon = win_icon
elif sys.platform == 'darwin':
    icon = osx_icon
else:
    icon = png_icon

icons_files = []
for filename in os.listdir(icons_home):
    filepath = os.path.join(icons_home, filename)
    if os.path.isfile(filepath):
        icons_files.append(filepath)

old_version = None
init_file = os.path.abspath(os.path.join(
        'nuxeo-drive-client', 'nxdrive', '__init__.py'))
with open(init_file, 'rb') as f:
    version = f.readline().split("=")[1].strip().replace('\'', '')

if '--dev' in sys.argv:
    # timestamp the dev artifacts for continuous integration
    # distutils only accepts "b" + digit
    sys.argv.remove('--dev')
    timestamp = datetime.utcnow().isoformat()
    timestamp = timestamp.replace(":", "")
    timestamp = timestamp.replace(".", "")
    timestamp = timestamp.replace("T", "")
    timestamp = timestamp.replace("-", "")
    old_version = version
    version = version.replace('-dev', "b" + timestamp)
    with open(init_file, 'wb') as f:
        f.write("__version__ = '%s'" % version)
    print "Updated version to " + version

includes = [
    "PySide",
    "PySide.QtCore",
    "PySide.QtNetwork",
    "PySide.QtGui",
    "atexit",  # implicitly required by PySide
    "sqlalchemy.dialects.sqlite",
]
excludes = [
    "ipdb",
    "clf",
    "IronPython",
    "pydoc",
    "tkinter",
]

if '--freeze' in sys.argv:
    print "Building standalone executable..."
    sys.argv.remove('--freeze')
    from cx_Freeze import setup, Executable

    # build_exe does not seem to take the package_dir info into account
    sys.path.append('nuxeo-drive-client')

    executables = [Executable(script, base=None)]

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
    icons_home = 'nuxeo-drive-client/nxdrive/data/icons'
    include_files = [(os.path.join(icons_home, f), "icons/%s" % f)
                     for f in os.listdir(icons_home)]
    freeze_options = dict(
        executables=executables,
        options={
            "build_exe": {
                "includes": includes,
                "packages": packages + [
                    "nose",
                ],
                "excludes": excludes,
                "include_files": include_files,
            },
            "bdist_msi": {
                "add_to_path": True,
                "upgrade_code": '{800B7778-1B71-11E2-9D65-A0FD6088709B}',
            },
        },
    )
    # TODO: investigate with esky to get an auto-updateable version but
    # then make sure that we can still have .msi and .dmg packages
    # instead of simple zip files.

elif sys.platform == 'darwin':
    # Under OSX we use py2app instead of cx_Freeze because we need:
    # - argv_emulation=True for nxdrive:// URL scheme handling
    # - easy Info.plit customization
    import py2app  # install the py2app command

    freeze_options = dict(
        app=["nuxeo-drive-client/scripts/ndrive.py"],
        data_files=[('icons', icons_files)],
        options=dict(
            py2app=dict(
                iconfile=osx_icon,
                argv_emulation=False,  # We use QT for URL scheme handling
                plist=dict(
                    CFBundleDisplayName="Nuxeo Drive",
                    CFBundleName="Nuxeo Drive",
                    CFBundleIdentifier="org.nuxeo.drive",
                    LSUIElement=True,  # Do not launch as a Dock application
                    CFBundleURLTypes=[
                        dict(
                            CFBundleURLName='Nuxeo Drive URL',
                            CFBundleURLSchemes=['nxdrive'],
                        )
                    ]
                ),
                includes=includes,
                excludes=excludes,
            )
        )
    )

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

if old_version is not None:
    with open(init_file, 'wb') as f:
        f.write("__version__ = '%s'" % old_version)
    print "Restored version to " + old_version
