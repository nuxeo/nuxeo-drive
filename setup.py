#! /usr/bin/env python
#
# Copyright (C) 2012 Nuxeo
#

import os
import sys
from datetime import datetime

from distutils.core import setup
import nx_esky
from esky.bdist_esky import Executable as es_Executable


def read_version(init_file):
    with open(init_file, 'rb') as f:
        return f.readline().split("=")[1].strip().replace('\'', '')


def update_version(init_file, version):
    with open(init_file, 'wb') as f:
        f.write("__version__ = '%s'\n" % version)

class Packages(object):
    def __init__(self, directory_list):
        self.directory_list = directory_list

    def _make_package_name_from_path(self, root, filepath):
        basename = '/' + os.path.basename(root)
        dir_name = filepath[filepath.find(basename):]
        package_name = dir_name.replace('/', '.')[1:]
        return package_name

        return root
    def _isNonTrivialPythonFile(self, afile):
        if afile.endswith('/' + '__init__.py'):
            return False
        if afile.endswith('.py'):
            return True
        return False

    def _load_packages_in_tree(self, root):
        # get all the directories with non trivial python files (derived from http://stackoverflow.com/questions/9994414/python-get-folder-containing-specific-files-extension)
        package_dirs = set(folder for folder, subfolders, files in os.walk(root) for file_ in files if self._isNonTrivialPythonFile(file_))
        for package_dir in package_dirs:
            dir = package_dir.replace("\\","/")
            aa = self._make_package_name_from_path(root, dir)
            self.packages.append(aa)

    def load(self):
        self.packages = []
        for directory in self.directory_list:
            self._load_packages_in_tree(directory)
        return self.packages

class data_file_dir(object):
    def __init__(self, home_dir, subfolderName, include_files):
        self.home_dir = home_dir
        self.subfolderName = subfolderName
        self.include_files = include_files

    def load(self):
        result = []
        for filename in os.listdir(os.path.normpath(self.home_dir)):
            filepath = self.home_dir + '/' + filename
            if os.path.isfile(filepath):
                self.include_files.append((filepath, self.subfolderName+ '/' + filename))
                result.append(filepath)
        return result

class NuxeoDriveAttributes(object):

    def rubric_company(self): return 'nuxeo'

    def rubric_top_dir(self): return 'nuxeo-drive'
    def rubric_2nd_dir(self): return 'nuxeo-drive-client'
    def rubric_3rd_dir(self): return 'nxdrive'
    def rubric_super_dir(self): return ''
    def rubric_product_name(self): return 'Nuxeo Drive'

    def get_name(self): return self.rubric_top_dir()

    def get_package_data(self):
        package_data = {
                self.rubric_3rd_dir() + '.data.icons': ['*.png', '*.svg', '*.ico', '*.icns'],
        }
        return package_data

    def get_package_dirs(self):
        package_dirs = ['nuxeo-drive-client/nxdrive']

        return package_dirs

    def get_script(self):
        return 'nuxeo-drive-client/scripts/ndrive'

    def get_icons_home(self):
        return self.rubric_2nd_dir() + '/' + self.rubric_3rd_dir() + '/data/icons'

    def get_alembic_home(self):
        return self.rubric_super_dir() + 'nuxeo-drive-client/alembic'

    def get_alembic_versions_home(self):
        return self.rubric_super_dir() + 'nuxeo-drive-client/alembic/versions'

    def get_win_icon(self):
        return 'nuxeo_drive_icon_64.ico'

    def get_png_icon(self):
        return 'nuxeo_drive_icon_64.png'

    def get_osx_icon(self):
        return 'nuxeo_drive_app_icon_128.icns'

    def get_init_file(self):
        return os.path.abspath(self.rubric_2nd_dir() + '/' + self.rubric_3rd_dir() + '/__init__.py')

    def append_includes(self, includes):
        pass

    def targetName(self):
        return "ndrivew.exe"

    def shortcutName(self):
        return "Nuxeo Drive"

    def get_win_script(self):
        return "nuxeo-drive-client/scripts/ndrivew.pyw"
    
    def get_app(self):
        return ["nuxeo-drive-client/scripts/ndrive.py"]

    def get_CFBundleURLSchemes(self):
        return [self.rubric_3rd_dir()]

    def get_package_dir(self):
        return {'nxdrive': 'nuxeo-drive-client/nxdrive'}

    def get_path_append(self):
        return self.rubric_2nd_dir()

    def get_CFBundleDisplayName(self):
        return self.rubric_product_name()

    def get_CFBundleName(self):
        return self.rubric_product_name()

    def get_CFBundleIdentifier(self):
        return "org.nuxeo.drive"

    def get_CFBundleURLName(self):
        return 'Nuxeo Drive URL'
    
    def get_description(self):
        return "Desktop synchronization client for Nuxeo."
    
    def get_author(self):
        return "Nuxeo"
    
    def get_author_email(self):
        return "contact@nuxeo.com"
    
    def get_url(self):
        return 'http://github.com/nuxeo/nuxeo-drive'
    
    def get_long_description(self):
        return open('README.rst').read()

class NuxeoDriveSetup(object):

    def __init__(self, driveAttributes):
        attribs = driveAttributes
        scripts = [es_Executable(attribs.get_script())]
        freeze_options = {}

        name = attribs.get_name()
        packages = Packages(attribs.get_package_dirs()).load()
        package_data = attribs.get_package_data()
        script = attribs.get_script()
        icons_home = attribs.get_icons_home()
        alembic_home = attribs.get_alembic_home()
        alembic_versions_home = attribs.get_alembic_versions_home()

        win_icon = icons_home + '/' + attribs.get_win_icon()
        png_icon = icons_home + '/' + attribs.get_png_icon()
        osx_icon = icons_home + '/' + attribs.get_osx_icon()

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
        icon_files = data_file_dir(icons_home, 'icons', include_files).load()
        alembic_files = data_file_dir(alembic_home, 'alembic', include_files).load()
        alembic_version_files = data_file_dir(alembic_versions_home, 'alembic/versions', include_files).load()

        data_files = data_files=[('icons', icon_files), ('alembic', alembic_files),
                                 ('alembic/versions', alembic_version_files)]

        old_version = None
        init_file = attribs.get_init_file()
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
        attribs.append_includes(includes)
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
            from nx_cx_Freeze import setup
            from cx_Freeze import Executable as cx_Executable
            from esky.util import get_platform

            # build_exe does not seem to take the package_dir info into account
            sys.path.append(attribs.get_path_append())

            executables = [cx_Executable(script)]

            if sys.platform == "win32":
                script_w = attribs.get_win_script()
                if script_w is not None:
                    scripts.append(
                        es_Executable(script_w, icon=icon, shortcutDir="ProgramMenuFolder",
                                      shortcutName=attribs.shortcutName()))
                # Windows GUI program that can be launched without a cmd console
                executables.append(
                    cx_Executable(script, targetName=attribs.targetName(), base="Win32GUI",
                               icon=icon, shortcutDir="ProgramMenuFolder",
                               shortcutName=attribs.shortcutName()))

            # special handling for data files
            package_data = {}
            esky_app_name = attribs.get_name() + '-' + version + '.' + get_platform()
            esky_dist_dir = os.path.join("dist", esky_app_name)
            freeze_options = dict(
                executables=executables,
                options={
                    "build": {
                        "exe_command": "bdist_esky",
                    },
                    "build_exe": {
                        "includes": includes,
                        "packages": packages + [
                            "nose",
                        ],
                        "excludes": excludes,
                        "include_files": include_files,
                    },
                    "bdist_esky": {
                        "excludes": excludes,
                        "enable_appdata_dir": True,
                    },
                    "install": {
                        "skip_sub_commands":
                            "install_lib,install_scripts,install_data",
                    },
                    "install_exe": {
                        "skip_build": True,
                        "build_dir": esky_dist_dir,
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
            from distutils.core import setup

            py2app_options = dict(
                iconfile=osx_icon,
                argv_emulation=False,  # We use QT for URL scheme handling
                plist=dict(
                    CFBundleDisplayName=attribs.get_CFBundleDisplayName(),
                    CFBundleName=attribs.get_CFBundleName(),
                    CFBundleIdentifier=attribs.get_CFBundleIdentifier(),
                    LSUIElement=True,  # Do not launch as a Dock application
                    CFBundleURLTypes=[
                        dict(
                            CFBundleURLName=attribs.get_CFBundleURLName(),
                            CFBundleURLSchemes=attribs.get_CFBundleURLSchemes(),
                        )
                    ]
                ),
                includes=includes,
                excludes=excludes,
            )
            freeze_options = dict(
                app=scripts,
                options=dict(
                    py2app=py2app_options,
                    bdist_esky=dict(
                        enable_appdata_dir=True,
                        freezer_options=py2app_options,
                    )
                )
            )

        setup(
            name=name,
            version=version,
            description=attribs.get_description(),
            author=attribs.get_author(),
            author_email=attribs.get_author_email(),
            url=attribs.get_url(),
            packages=packages,
            package_dir=attribs.get_package_dir(),
            package_data=package_data,
            scripts=scripts,
            long_description=attribs.get_long_description(),
            data_files=data_files,
            **freeze_options
        )

        if old_version is not None:
            update_version(init_file, old_version)
            print "Restored version to " + old_version

if __name__ == '__main__':
    sys.exit(NuxeoDriveSetup(NuxeoDriveAttributes()))
