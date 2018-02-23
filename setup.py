# coding: utf-8
from __future__ import print_function

import io
import os
import re
import sys
import warnings

try:
    import nx_esky
except ImportError as e:
    print(e)
try:
    from esky.bdist_esky import Executable as es_Executable
except ImportError:
    pass

OUTPUT_DIR = 'dist'
DEFAULT_SERVER_MIN_VERSION = '7.10'


def create_json_metadata(client_version, server_version):
    string = unicode if sys.version[0] == '2' else str

    output_dir = os.path.abspath(OUTPUT_DIR)
    if not os.path.exists(output_dir):
        os.makedirs(output_dir)

    file_path = os.path.abspath(
        os.path.join(OUTPUT_DIR, client_version + '.json'))
    with io.open(file_path, mode='w', encoding='utf-8') as f:
        txt = string('{"nuxeoPlatformMinVersion": "%s"}\n' % server_version)
        f.write(txt)
    return file_path


def get_version(init_file):
    """ Find the current version. """

    with io.open(init_file, encoding='utf-8') as handler:
        for line in handler.readlines():
            if line.startswith('__version__'):
                return re.findall(r"'(.+)'", line)[0]


class Packages(object):
    def __init__(self, directory_list):
        self.directory_list = directory_list
        self.packages = []

    def _make_package_name_from_path(self, root, filepath):
        basename = '/' + os.path.basename(root)
        dir_name = filepath[filepath.find(basename):]
        package_name = dir_name.replace('/', '.')[1:]
        return package_name

    def _isNonTrivialPythonFile(self, afile):
        if afile.endswith('/__init__.py'):
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
        for directory in self.directory_list:
            self._load_packages_in_tree(directory)
        return self.packages


class DataFileDir(object):
    def __init__(self, home_dir, subfolder_name, include_files):
        self.home_dir = home_dir
        self.subfolder_name = subfolder_name
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
                        (filepath, os.path.join(self.subfolder_name, filename)))
                result.append(filepath)
        return result

    def load_recursive(self, path=None, shortpath=None):
        if path is None:
            self.recursive_result = []
            shortpath = self.subfolder_name
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

    def include_xattr_binaries(self):
        return sys.platform != 'win32'

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
                               if not filename.endswith(('.py', '.pyc'))])
        return data_files

    def get_package_dirs(self):
        return [os.path.join(self.rubric_2nd_dir(), self.rubric_3rd_dir())]

    def get_script(self):
        file_ = 'ndrivew.pyw' if sys.platform == 'win32' else 'ndrive'
        return os.path.join(self.rubric_2nd_dir(), 'scripts', file_)

    def get_ui5_home(self):
        return os.path.join(
            self.rubric_2nd_dir(), self.rubric_3rd_dir(), 'data', 'ui5')

    def get_i18n_home(self):
        return os.path.join(
            self.rubric_2nd_dir(), self.rubric_3rd_dir(), 'data', 'i18n')

    def get_icons_home(self):
        return os.path.join(
            self.rubric_2nd_dir(), self.rubric_3rd_dir(), 'data', 'icons')

    def get_win_icon(self):
        return 'nuxeo_drive_icon_64.ico'

    def get_png_icon(self):
        return 'nuxeo_drive_icon_64.png'

    def get_osx_icon(self):
        return 'nuxeo_drive_app_icon_128.icns'

    def get_init_file(self):
        return os.path.abspath(os.path.join(
            self.rubric_2nd_dir(), self.rubric_3rd_dir(), '__init__.py'))

    def append_includes(self, includes):
        pass

    def get_win_target_name(self):
        return 'ndrivew.exe'

    def shortcutName(self):
        return 'Nuxeo Drive'

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
        return 'org.nuxeo.drive'

    def get_CFBundleURLName(self):
        return 'org.nuxeo.nxdrive.direct-edit'

    def get_CFBundleTypeRole(self):
        return 'Editor'

    def get_description(self):
        return 'Desktop synchronization client for Nuxeo.'

    def get_author(self):
        return 'Nuxeo'

    def get_install_dir(self):
        return os.path.join(self.get_author(), 'Drive')

    def get_author_email(self):
        return 'maintainers-python+drive@nuxeo.com'

    def get_url(self):
        return 'https://github.com/nuxeo/nuxeo-drive'

    def get_long_description(self):
        with open('README.md') as handler:
            return handler.read()

    def get_data_files(self):
        return []

    def get_includes(self):
        return []

    def get_licence(self):
        return 'LGPLv2+'

    def get_gpl_licence(self):
        with open('LICENSE.txt') as handler:
            content = handler.read().replace('\n', '\\line')
            return ('{\\rtf1\\ansi\\ansicpg1252\\deff0\\deftab720{'
                    '\\fonttbl{\\f0\\froman\\fprq2 Times New Roman;}}'
                    '{\\colortbl\\red0\\green0\\blue0;}' + content + '}')

    def customize_msi(self, db):
        """ Add custom actions to the MSI. """

        import msilib

        # Make the appdata folder writable to enable Windows Auto update
        msilib.add_data(db, 'CustomAction', [(
            'AllowAutoUpdate', 3234, 'TARGETDIR', 'Icacls . /grant Users:(OI)(CI)(M,DC) /t /c /q')])
        msilib.add_data(db, 'InstallExecuteSequence', [(
            'AllowAutoUpdate', 'NOT Installed', 6401)])

        # Call OSI.uninstall() on uninstallation
        # Deffered action with noImpersonate to have the correct privileges
        msilib.add_data(db, 'CustomAction', [(
            'NuxeoDriveCleanUp', 82, self.get_win_target_name(), 'uninstall')])
        msilib.add_data(db, 'InstallExecuteSequence', [(
            'NuxeoDriveCleanUp', 'REMOVE="ALL" AND NOT UPGRADINGPRODUCTCODE', 1260)])
        msilib.add_data(db, 'CustomAction', [(
            'NuxeoDriveFolderCleanUp', 3170, 'TARGETDIR', 'cmd.exe /C "rmdir /S /Q appdata"')])
        msilib.add_data(db, 'InstallExecuteSequence', [(
            'NuxeoDriveFolderCleanUp', 'REMOVE="ALL" AND NOT UPGRADINGPRODUCTCODE', 1560)])

        # Add the possibility to bind an engine with MSI
        args = (
            'bind-server'
            ' --password \"[TARGETPASSWORD]\"'
            ' --local-folder \"[TARGETDRIVEFOLDER]\"'
            ' \"[TARGETUSERNAME]\" \"[TARGETURL]\"')
        msilib.add_data(db, 'CustomAction', [(
            'NuxeoDriveBinder', 82, self.get_win_target_name(), args)])
        # Arguments TARGETUSERNAME and TARGETURL are mandatory
        msilib.add_data(db, 'InstallExecuteSequence', [(
            'NuxeoDriveBinder', 'NOT (TARGETUSERNAME="" OR TARGETURL="")', -1)])


class NuxeoDrivePackageAttributes(NuxeoDriveAttributes):
    def rubric_product_name(self):
        return self.get_name()

    def get_long_description(self):
        return ''

    def include_xattr_binaries(self):
        return False


class NuxeoDriveSetup(object):

    def __init__(self, attribs):

        from distutils.core import setup

        freeze_options = {}
        ext_modules = []

        script = attribs.get_script()
        scripts = [script]
        name = attribs.get_name()
        packages = Packages(attribs.get_package_dirs()).load()

        package_data = attribs.get_package_data()
        i18n_home = attribs.get_i18n_home()
        icons_home = attribs.get_icons_home()
        ui5_home = attribs.get_ui5_home()

        if sys.platform == 'win32':
            icon = os.path.join(icons_home, attribs.get_win_icon())
        elif sys.platform == 'darwin':
            icon = os.path.join(icons_home, attribs.get_osx_icon())
        else:
            icon = os.path.join(icons_home, attribs.get_png_icon())

        # Files to include in frozen app
        # build_exe freeze with cx_Freeze (Windows)
        include_files = attribs.get_includes()

        # bdist_esky freeze with cx_Freeze (Windows) and py2app (OS X)
        # In fact this is a global setup option
        # TODO NXP-13810: check removed data_files from py2app and added to
        # global setup
        i18n_files = DataFileDir(i18n_home, 'i18n', include_files).load()
        icon_files = DataFileDir(icons_home, 'icons', include_files).load()
        ui5_files = DataFileDir(ui5_home, 'ui5', include_files).load_recursive()
        data_files = [('icons', icon_files), ('i18n', i18n_files)]
        data_files.extend(ui5_files)
        data_files.extend(attribs.get_data_files())
        drive_version = get_version(attribs.get_init_file())

        # Create JSON metadata file for the frozen application
        json_file = create_json_metadata(drive_version, DEFAULT_SERVER_MIN_VERSION)
        print('Created JSON metadata file for frozen app: ' + json_file)

        includes = [
            'atexit',  # Implicitly required by PyQt4
            'js2py.pyjs',  # Implicitly required by pypac
        ]
        excludes = [
            'ipdb',
            'pydoc',
            'yappi',
        ]
        if attribs.include_xattr_binaries():
            includes.append('cffi')
            includes.append('xattr')
        else:
            excludes.append('cffi')
            excludes.append('xattr')
        attribs.append_includes(includes)

        if '--freeze' in sys.argv:
            print('Building standalone executable...')
            sys.argv.remove('--freeze')
            from nx_cx_Freeze import setup
            from cx_Freeze import Executable as cx_Executable
            from esky.util import get_platform

            # build_exe does not seem to take the package_dir info into account
            sys.path.insert(0, attribs.get_path_append())

            try:
                packages.remove('nxdrive.data')
            except ValueError:
                pass

            executables = [cx_Executable(script)]
            freeze_options = dict()
            if sys.platform == 'win32':
                # Copy OpenSSL DLL
                data_files.append('libeay32.dll')
                data_files.append('ssleay32.dll')

                # Windows GUI program that can be launched without a cmd
                # console
                scripts.append(es_Executable(
                    attribs.get_script(),
                    icon=icon,
                    shortcutDir='ProgramMenuFolder',
                    shortcutName=attribs.shortcutName(),
                ))
                executables.append(cx_Executable(
                    attribs.get_win_target_name(),
                    targetName=attribs.get_win_target_name(),
                    base='Win32GUI',
                    icon=icon,
                    shortcutDir='ProgramMenuFolder',
                    shortcutName=attribs.shortcutName(),
                ))

                # Add a shortcut on the desktop
                executables.append(cx_Executable(
                    attribs.get_win_target_name(),
                    targetName=attribs.get_win_target_name(),
                    base='Win32GUI',
                    icon=icon,
                    shortcutDir='DesktopFolder',
                    shortcutName=attribs.shortcutName(),
                ))

                freeze_options.update({'attribs': attribs})

            package_data = {}
            esky_app_name = (attribs.get_name()
                             + '-' + drive_version + '.' + get_platform())
            esky_dist_dir = os.path.join(OUTPUT_DIR, esky_app_name)
            freeze_options.update({
                'executables': executables,
                'options': {
                    'build': {
                        'exe_command': 'bdist_esky',
                    },
                    'build_exe': {
                        'includes': includes,
                        'packages': packages,
                        'excludes': excludes,
                        'include_files': include_files,
                    },
                    'bdist_esky': {
                        'includes': includes,
                        'excludes': excludes,
                        'enable_appdata_dir': True,
                        'freezer_options': {
                            'packages': packages,
                        },
                        'rm_freeze_dir_after_zipping': False,
                    },
                    'install': {
                        'skip_sub_commands':
                            'install_lib,install_scripts,install_data',
                    },
                    'install_exe': {
                        'skip_build': True,
                        'build_dir': esky_dist_dir,
                    },
                    'bdist_msi': {
                        'add_to_path': True,
                        'upgrade_code': attribs.get_uid(),
                    },
                },
            })

        if sys.platform == 'darwin':
            # Under OSX we use py2app instead of cx_Freeze because we need:
            # - argv_emulation=True for nxdrive:// URL scheme handling
            # - easy Info.plist customization
            name = attribs.get_CFBundleName()
            py2app_options = {
                'iconfile': icon,
                'qt_plugins': 'imageformats',
                'argv_emulation': False,  # We use Qt for URL scheme handling
                'plist': {
                    'CFBundleDisplayName': attribs.get_CFBundleDisplayName(),
                    'CFBundleName': attribs.get_CFBundleName(),
                    'CFBundleIdentifier': attribs.get_CFBundleIdentifier(),
                    'LSUIElement': True,  # Do not launch as a Dock application
                    'CFBundleURLTypes': [{
                        'CFBundleURLName': attribs.get_CFBundleURLName(),
                        'CFBundleTypeRole': attribs.get_CFBundleTypeRole(),
                        'CFBundleURLSchemes': attribs.get_CFBundleURLSchemes(),
                    }],
                    'NSServices': [{
                        'NSMenuItem': {
                            'default': 'Access online',
                        },
                        'NSMessage': 'openInBrowser',
                        'NSPortName': attribs.get_CFBundleDisplayName(),
                        'NSRequiredContext': {},
                        'NSSendTypes': [
                            'NSStringPboardType',
                        ],
                        'NSSendFileTypes': [
                            'public.item',
                        ],
                    }, {
                        'NSMenuItem': {
                            'default': 'Copy share-link',
                        },
                        'NSMessage': 'copyShareLink',
                        'NSPortName': attribs.get_CFBundleDisplayName(),
                        'NSRequiredContext': {},
                        'NSSendTypes': [
                            'NSStringPboardType',
                        ],
                        'NSSendFileTypes': [
                            'public.item',
                        ],
                    }],
                },
                'includes': includes,
                'excludes': excludes,
            }
            freeze_options = {
                'app': scripts,
                'options': {
                    'py2app': py2app_options,
                    'bdist_esky': {
                        'enable_appdata_dir': True,
                        'create_zipfile': False,
                        'freezer_options': py2app_options,
                    }
                }
            }

        entry_points = {}
        if sys.platform == 'win32':
            entry_points = {
                'console_scripts': ['ndrive=nxdrive.commandline:main'],
                'gui_scripts': ['ndrivew=nxdrive.commandline:main'],
            }

        with warnings.catch_warnings():
            # Hide Windows "Unknown distribution option: 'attribs'"
            warnings.simplefilter('ignore', category=UserWarning)
            setup(
                name=name,
                version=drive_version,
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
                entry_points=entry_points,
                platforms=['Darwin', 'Linux', 'Windows'],
                license=attribs.get_licence(),
                **freeze_options
            )


def main():
    if 'bdist_esky' in sys.argv or 'bdist_msi' in sys.argv:
        attribs = NuxeoDriveAttributes()
    else:
        attribs = NuxeoDrivePackageAttributes()
    NuxeoDriveSetup(attribs)


if __name__ == '__main__':
    sys.exit(main())
