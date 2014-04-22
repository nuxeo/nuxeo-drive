#! /usr/bin/env python
#
# Copyright (C) 2012 Nuxeo
#

import os
import sys
from datetime import datetime

from distutils.core import setup
from esky import bdist_esky


def read_version(init_file):
    with open(init_file, 'rb') as f:
        return f.readline().split("=")[1].strip().replace('\'', '')


def update_version(init_file, version):
    with open(init_file, 'wb') as f:
        f.write("__version__ = '%s'\n" % version)

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
alembic_home = 'nuxeo-drive-client/alembic'
alembic_versions_home = 'nuxeo-drive-client/alembic/versions'

win_icon = os.path.join(icons_home, 'nuxeo_drive_icon_64.ico')
png_icon = os.path.join(icons_home, 'nuxeo_drive_icon_64.png')
osx_icon = os.path.join(icons_home, 'nuxeo_drive_app_icon_128.icns')

if sys.platform == 'win32':
    icon = win_icon
elif sys.platform == 'darwin':
    icon = osx_icon
else:
    icon = png_icon

# Files to include in frozen app: icons, alembic, alembic versions
# build_exe freeze with cx_Freeze (Windows + Linux)
include_files = []
# bdist_esky freeze with cx_Freeze (Windows + Linux) and py2app freeze (OS X)
# In fact this is a global setup option
# TODO NXP-13810: check removed data_files from py2app and added to global
# setup
data_files = []
icon_files = []
alembic_files = []
alembic_version_files = []

# Icon files
for filename in os.listdir(icons_home):
    filepath = os.path.join(icons_home, filename)
    if os.path.isfile(filepath):
        include_files.append((filepath, "icons/%s" % filename))
        icon_files.append(filepath)

# Alembic files
for filename in os.listdir(alembic_home):
    filepath = os.path.join(alembic_home, filename)
    if os.path.isfile(filepath):
        include_files.append((filepath, "alembic/%s" % filename))
        alembic_files.append(filepath)

# Alembic version files
for filename in os.listdir(alembic_versions_home):
    filepath = os.path.join(alembic_versions_home, filename)
    if os.path.isfile(filepath):
        include_files.append((filepath, "alembic/versions/%s" % filename))
        alembic_version_files.append(filepath)

data_files = data_files=[('icons', icon_files), ('alembic', alembic_files),
                         ('alembic/versions', alembic_version_files)]

old_version = None
init_file = os.path.abspath(os.path.join(
        'nuxeo-drive-client', 'nxdrive', '__init__.py'))
version = read_version(init_file)

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
    # distutils imposes a max 3 levels integer version
    # (+ prerelease markers which are not allowed in a
    # msi package version). On the other hand,
    # msi imposes the a.b.c.0 or a.b.c.d format where
    # a, b, c and d are all 16 bits integers
    version = version.replace('-dev', ".%s" % (
        timestamp[4:8]))
    update_version(init_file, version)
    print "Updated version to " + version

includes = [
    "PyQt4",
    "PyQt4.QtCore",
    "PyQt4.QtNetwork",
    "PyQt4.QtGui",
    "atexit",  # implicitly required by PyQt4
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

    # special handling for data files
    packages.remove('nxdrive.data')
    packages.remove('nxdrive.data.icons')
    package_data = {}
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
            "bdist_esky": {
                "includes": includes,
                "excludes": excludes,
            },
            "bdist_msi": {
                "add_to_path": True,
                "upgrade_code": '{800B7778-1B71-11E2-9D65-A0FD6088709B}',
            },
        },
    )

elif sys.platform == 'darwin':
    # Under OSX we use py2app instead of cx_Freeze because we need:
    # - argv_emulation=True for nxdrive:// URL scheme handling
    # - easy Info.plist customization
    import py2app  # install the py2app command

    freeze_options = dict(
        app=["nuxeo-drive-client/scripts/ndrive.py"],
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
    data_files=data_files,
    **freeze_options
)

if old_version is not None:
    update_version(init_file, old_version)
    print "Restored version to " + old_version
