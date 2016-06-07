#! /usr/bin/env python
#
# Copyright (C) 2012 Nuxeo
#

import os
import sys
from datetime import datetime

try:
    import nx_esky
except Exception as e:
    print e
from esky.bdist_esky import Executable as es_Executable

OUTPUT_DIR = 'dist'
SERVER_MIN_VERSION = '5.6'


def read_version(init_file):
    if 'DRIVE_VERSION' in os.environ:
        return os.environ['DRIVE_VERSION']
    with open(init_file, 'rb') as f:
        return f.readline().split("=")[1].strip().replace('\'', '')


def update_version(init_file, version):
    with open(init_file, 'wb') as f:
        f.write("__version__ = '%s'\n" % version)


def create_json_metadata(client_version, server_version):

    output_dir = os.path.abspath(OUTPUT_DIR)
    if not os.path.exists(output_dir):
        os.makedirs(output_dir)

    file_path = os.path.abspath(os.path.join(OUTPUT_DIR,
                                             client_version + '.json'))
    with open(file_path, 'wb') as f:
        f.write('{"nuxeoPlatformMinVersion": "%s"}\n' % server_version)
    return file_path


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
        # get all the directories with non trivial python files (derived from
        # http://stackoverflow.com/questions/9994414/python-get-folder-containing-specific-files-extension)
        package_dirs = set(folder for folder, _, files in os.walk(root)
                           for file_ in files
                           if self._isNonTrivialPythonFile(file_))
        for package_dir in package_dirs:
            dir_ = package_dir.replace("\\", "/")
            aa = self._make_package_name_from_path(root, dir_)
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
        self.recursive_result = None

    def load(self):
        result = []
        if not (os.path.exists(os.path.normpath(self.home_dir))):
            return result
        for filename in os.listdir(os.path.normpath(self.home_dir)):
            filepath = os.path.join(self.home_dir, filename)
            if os.path.isfile(filepath):
                self.include_files.append(
                        (filepath, os.path.join(self.subfolderName, filename)))
                result.append(filepath)
        return result

    def load_recursive(self, path=None, shortpath=None):
        if path is None:
            self.recursive_result = []
            shortpath = self.subfolderName
            path = self.home_dir
        result = []
        if not (os.path.exists(os.path.normpath(path))):
            return []
        for filename in os.listdir(os.path.normpath(path)):
            filepath = os.path.join(path, filename)
            childshortpath = os.path.join(shortpath, filename)
            if os.path.isfile(filepath):
                self.include_files.append(
                        (filepath, childshortpath))
                result.append(filepath)
            elif os.path.isdir(filepath):
                self.load_recursive(filepath, childshortpath)
        self.recursive_result.append((shortpath, result))
        return self.recursive_result


class NuxeoDriveAttributes(object):

    def get_uid(self):
        return '{800B7778-1B71-11E2-9D65-A0FD6088709B}'

    def rubric_company(self):
        return 'nuxeo'

    def rubric_top_dir(self):
        return 'nuxeo-drive'

    def rubric_2nd_dir(self):
        return 'nuxeo-drive-client'

    def rubric_3rd_dir(self):
        return 'nxdrive'

    def rubric_super_dir(self):
        return ''

    def rubric_product_name(self):
        return 'Nuxeo Drive'

    def get_name(self):
        return self.rubric_top_dir()

    def get_package_data(self):
        package_data = {
                self.rubric_3rd_dir() + '.data': self._get_recursive_data('data'),
        }
        return package_data

    def _get_recursive_data(self, data_dir):
        data_files = []
        data_dir_path = os.path.join(self.rubric_2nd_dir(), self.rubric_3rd_dir(), data_dir)
        for dirpath, _, filenames in os.walk(data_dir_path):
            rel_path = dirpath.rsplit(data_dir, 1)[1]
            if rel_path.startswith(os.path.sep):
                rel_path = rel_path[1:]
            data_files.extend([os.path.join(rel_path, filename)
                               for filename in filenames
                               if not (filename.endswith('.py') or filename.endswith('.pyc'))])
        return data_files

    def get_package_dirs(self):
        package_dirs = [os.path.join(self.rubric_2nd_dir(),
                                     self.rubric_3rd_dir())]

        return package_dirs

    def get_script(self):
        return os.path.join(self.rubric_2nd_dir(), 'scripts', 'ndrive')

    def get_scripts(self):
        return [es_Executable(self.get_script()), 'launcher.pyw']

    def get_win_script(self):
        return os.path.join(self.rubric_2nd_dir(), 'scripts', 'ndrivew.pyw')

    def get_app(self):
        return self.get_scripts()

    def get_ui5_home(self):
        return os.path.join(self.rubric_2nd_dir(), self.rubric_3rd_dir(),
                            'data', 'ui5')

    def get_icons_home(self):
        return os.path.join(self.rubric_2nd_dir(), self.rubric_3rd_dir(),
                            'data', 'icons')

    def get_win_icon(self):
        return 'nuxeo_drive_icon_64.ico'

    def get_png_icon(self):
        return 'nuxeo_drive_icon_64.png'

    def get_osx_icon(self):
        return 'nuxeo_drive_app_icon_128.icns'

    def get_init_file(self):
        return os.path.abspath(os.path.join(self.rubric_2nd_dir(),
                                            self.rubric_3rd_dir(),
                                            '__init__.py'))

    def append_includes(self, includes):
        pass

    def get_win_targetName(self):
        return "ndrivew.exe"

    def shortcutName(self):
        return "Nuxeo Drive"

    def get_CFBundleURLSchemes(self):
        return ['nxdrive']

    def get_package_dir(self):
        return {'nxdrive': os.path.join(self.rubric_2nd_dir(),
                                        self.rubric_3rd_dir())}

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

    def get_install_dir(self):
        return os.path.join(self.get_author(), 'Drive')

    def get_author_email(self):
        return "contact@nuxeo.com"

    def get_url(self):
        return 'http://github.com/nuxeo/nuxeo-drive'

    def get_long_description(self):
        return open('README.md').read()

    def get_data_files(self):
        return []

    def get_includes(self):
        return []

    def get_licence(self):
        return None

    def get_gpl_licence(self):
        license_ = open('LICENSE.txt').read().replace('\n', '\\line')
        return '{\\rtf1\\ansi\\ansicpg1252\\deff0\\deftab720{'\
                '\\fonttbl{\\f0\\froman\\fprq2 Times New Roman;}}'\
                '{\\colortbl\\red0\\green0\\blue0;}' + license_ + '}'

    def customize_msi(self, db):
        import msilib
        # Make the appdata folder writable to enable Windows Auto update
        msilib.add_data(db, "CustomAction", [("AllowAutoUpdate", 3234,
                        "TARGETDIR", "Icacls . /grant Users:(OI)(CI)(M,DC) /t /c /q")])
        msilib.add_data(db, "InstallExecuteSequence",
                        [("AllowAutoUpdate", 'NOT Installed', 6401)])
        # Add the possibility to bind an engine with MSI
        msilib.add_data(db, "CustomAction", [("NuxeoDriveBinder", 82,
                        self.get_win_targetName(),
                        "bind-server --password \"[TARGETPASSWORD]\" --local-folder \"[TARGETDRIVEFOLDER]\" [TARGETUSERNAME] [TARGETURL]")])
        msilib.add_data(db, "InstallExecuteSequence", [("NuxeoDriveBinder",
                              'NOT (TARGETUSERNAME="" OR TARGETURL="")', -1)])


class NuxeoDrivePackageAttributes(NuxeoDriveAttributes):
    def rubric_product_name(self):
        return self.get_name()
    def get_long_description(self):
        return ""

class NuxeoDriveSetup(object):

    def __init__(self, driveAttributes):

        from distutils.core import setup

        attribs = driveAttributes
        freeze_options = {}
        ext_modules = []

        script = attribs.get_script()
        scripts = attribs.get_scripts()
        name = attribs.get_name()
        packages = Packages(attribs.get_package_dirs()).load()

        # special handling for data files, except for Linux
        if ((sys.platform == "win32" or sys.platform == 'darwin')
                and 'nxdrive.data' in packages):
            packages.remove('nxdrive.data')
        package_data = attribs.get_package_data()
        icons_home = attribs.get_icons_home()
        ui5_home = attribs.get_ui5_home()

        win_icon = os.path.join(icons_home, attribs.get_win_icon())
        png_icon = os.path.join(icons_home, attribs.get_png_icon())
        osx_icon = os.path.join(icons_home, attribs.get_osx_icon())

        if sys.platform == 'win32':
            icon = win_icon
        elif sys.platform == 'darwin':
            icon = osx_icon
        else:
            icon = png_icon

        # Files to include in frozen app
        # build_exe freeze with cx_Freeze (Windows)
        include_files = attribs.get_includes()
        # bdist_esky freeze with cx_Freeze (Windows) and py2app (OS X)
        # In fact this is a global setup option
        # TODO NXP-13810: check removed data_files from py2app and added to
        # global setup
        icon_files = data_file_dir(icons_home, 'icons', include_files).load()
        ui5_files = data_file_dir(ui5_home, 'ui5', include_files).load_recursive()
        data_files = [('icons', icon_files)]
        data_files.extend(ui5_files)
        data_files.extend(attribs.get_data_files())
        old_version = None
        init_file = attribs.get_init_file()
        version = read_version(init_file)

        if '-dev' in version:
            # timestamp the dev artifacts as distutils only accepts "b" + digit
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
            # TODO: align on latest distutils versioning
            month_day = timestamp[4:8]
            if month_day.startswith('0'):
                month_day = month_day[1:]
            version = version.replace('-dev', ".%s" % (
                month_day))
            update_version(init_file, version)
            print "Updated version to " + version

        # Create JSON metadata file for the frozen application
        json_file = create_json_metadata(version, SERVER_MIN_VERSION)
        print "Created JSON metadata file for frozen app: " + json_file

        includes = [
            "PyQt4",
            "PyQt4.QtCore",
            "PyQt4.QtNetwork",
            "PyQt4.QtGui",
            "atexit",  # implicitly required by PyQt4
            "cffi",
            "xattr"
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
            freeze_options = dict()
            if sys.platform == "win32":
                # Windows GUI program that can be launched without a cmd
                # console
                script_w = attribs.get_win_script()
                if script_w is not None:
                    scripts.append(
                        es_Executable(script_w, icon=icon,
                                      shortcutDir="ProgramMenuFolder",
                                      shortcutName=attribs.shortcutName()))

                    executables.append(
                        cx_Executable(script_w,
                                      targetName=attribs.get_win_targetName(),
                                      base="Win32GUI", icon=icon,
                                      shortcutDir="ProgramMenuFolder",
                                      shortcutName=attribs.shortcutName()))
                freeze_options.update({'attribs': attribs})

            package_data = {}
            esky_app_name = (attribs.get_name()
                             + '-' + version + '.' + get_platform())
            esky_dist_dir = os.path.join(OUTPUT_DIR, esky_app_name)
            freeze_options.update({
                'executables': executables,
                'options': {
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
                        "freezer_options": {
                            "packages": packages + [
                                "nose",
                            ],
                        },
                        "rm_freeze_dir_after_zipping": False,
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
                        "upgrade_code":
                            attribs.get_uid(),
                    },
                },
            })

            # Include cffi compiled C extension under Linux
            if sys.platform.startswith('linux'):
                import xattr
                includeFiles = [(os.path.join(os.path.dirname(xattr.__file__), '_cffi__x7c9e2f59xb862c7dd.so'),
                                 '_cffi__x7c9e2f59xb862c7dd.so')]
                freeze_options['options']['bdist_esky']['freezer_options'].update({
                    "includeFiles": includeFiles
                })

        if sys.platform == 'darwin':
            # Under OSX we use py2app instead of cx_Freeze because we need:
            # - argv_emulation=True for nxdrive:// URL scheme handling
            # - easy Info.plist customization
            import py2app  # install the py2app command
            import xattr
            ext_modules = [xattr.lib.ffi.verifier.get_extension()]
            includes.append("_cffi__x7c9e2f59xb862c7dd")
            name = attribs.get_CFBundleName()
            py2app_options = dict(
                iconfile=icon,
                qt_plugins='imageformats',
                argv_emulation=False,  # We use QT for URL scheme handling
                plist=dict(
                    CFBundleDisplayName=attribs.get_CFBundleDisplayName(),
                    CFBundleName=attribs.get_CFBundleName(),
                    CFBundleIdentifier=attribs.get_CFBundleIdentifier(),
                    LSUIElement=True,  # Do not launch as a Dock application
                    CFBundleURLTypes=[
                        dict(
                            CFBundleURLName=attribs.get_CFBundleURLName(),
                            CFBundleURLSchemes=(attribs
                                                .get_CFBundleURLSchemes()),
                        )
                    ],
                    NSServices=[
                        dict(
                            NSMenuItem=dict(
                                default=attribs.get_CFBundleDisplayName()
                            ),
                            NSMessage=u"macRightClick",
                            NSPortName=attribs.get_CFBundleDisplayName(),
                            NSRequiredContext=dict(),
                            NSSendTypes=[
                                u'NSStringPboardType',
                            ],
                            NSSendFileTypes=[
                                u"public.item"
                            ]
                        )
                    ]
                ),
                includes=includes,
                excludes=excludes,
            )
            freeze_options = dict(
                app=attribs.get_app(),
                options=dict(
                    py2app=py2app_options,
                    bdist_esky=dict(
                        enable_appdata_dir=True,
                        create_zipfile=False,
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
            ext_modules=ext_modules,
            **freeze_options
        )

        if old_version is not None:
            update_version(init_file, old_version)
            print "Restored version to " + old_version


def main(argv=None):
    attribs = None
    if ("bdist_esky" in sys.argv or "bdist_msi" in sys.argv):
        attribs = NuxeoDriveAttributes()
    else:
        attribs = NuxeoDrivePackageAttributes()
    NuxeoDriveSetup(attribs)

if __name__ == '__main__':
    sys.exit(main())
