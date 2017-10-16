# coding: utf-8
"""
cx_Freeze extension

Extends:

- the 'build' command with the 'exe-command' option to allow using a
different command from 'build_exe' to build executables from Python scripts.

- the 'install' command with the 'skip-sub-commands' option to allow not
running a set of sub commands, e.g.:

    install --skip-sub-commands=install_lib,install_scripts,install_data

- the 'bdist_msi' command to handle LaunchAfterInstall and a clean uninstall.
"""

from __future__ import unicode_literals

import distutils.command.build
import os
import sys

from cx_Freeze.dist import _AddCommandClass, build as cx_build, \
    install as cx_install, setup as cx_setup


class build(cx_build):

    cx_build.user_options.append(
        ('exe-command=', None, 'Python script executables command'))

    def initialize_options(self):
        cx_build.initialize_options(self)
        self.exe_command = 'build_exe'

    def get_sub_commands(self):
        subCommands = distutils.command.build.build.get_sub_commands(self)
        if self.distribution.executables:
            subCommands.append(self.exe_command)
        return subCommands


class install(cx_install):

    cx_install.user_options.append(
        ('skip-sub-commands=', None,
         'sub commands to ignore when running command'))

    def initialize_options(self):
        cx_install.initialize_options(self)
        self.skip_sub_commands = None

    def get_sub_commands(self):
        sub_commands = cx_install.get_sub_commands(self)
        if self.skip_sub_commands:
            skip_sub_commands = self.skip_sub_commands.split(',')
            for cmd in skip_sub_commands:
                if cmd in sub_commands:
                    sub_commands.remove(cmd)
        return sub_commands


if sys.platform == 'win32':
    import msilib
    from cx_Freeze.windist import bdist_msi as cx_bdist_msi

    class bdist_msi(cx_bdist_msi):
        attribs = None
        initial_target_dir = None
        __licence = None

        def finalize_options(self):
            self.distribution.get_name()
            if self.initial_target_dir is None:
                if distutils.util.get_platform() == 'win-amd64':
                    program_files_folder = 'ProgramFiles64Folder'
                else:
                    program_files_folder = 'ProgramFilesFolder'
                self.initial_target_dir = r'[%s]\%s' % (
                    program_files_folder, self.attribs.get_install_dir())
            # Using old style class so can't use super
            import cx_Freeze
            cx_Freeze.windist.bdist_msi.finalize_options(self)

        def get_executable(self):
            return self.attribs.get_win_target_name()

        def get_licence(self):
            if self.__licence is None:
                self.__licence = self.attribs.get_gpl_licence()
            return self.__licence

        def add_licence_dialog(self):
            msilib.add_data(self.db, 'InstallUISequence',  [(
                'LicenceDialog', None, 380)])
            dialog = distutils.command.bdist_msi.PyDialog(
                self.db, 'LicenceDialog',
                self.x, self.y, self.width, self.height, self.modal,
                self.title, 'Next', 'Next', 'Cancel')
            dialog.text('LicenseTitle', 15, 10, 320, 20, 0x3, 'License')
            dialog.control(
                'License', 'ScrollableText', 15, 30, 340, 200,  0x7,
                None, self.get_licence(), None, None)
            dialog.control(
                'LicenseAccepted', 'CheckBox', 15, 240, 320, 20, 0x3,
                'LicenseAccepted', 'I have accepted this agreement', None, None)
            button = dialog.cancel('Cancel', 'Next')
            button.event('EndDialog', 'Exit')
            button = dialog.next('Next', 'Cancel', active=False)
            button.condition('Enable', 'LicenseAccepted')
            button.condition('Disable', 'not LicenseAccepted')
            button.event('EndDialog', 'Return')

        def add_exit_dialog(self):
            # Add the license screen
            if self.get_licence() is not None:
                self.add_licence_dialog()

            # Allow to customize the MSI
            if hasattr(self.attribs, 'customize_msi'):
                self.attribs.customize_msi(self.db)

            # Add the product icon in control panel Install/Remove softwares
            icon_file = os.path.join(self.attribs.get_icons_home(),
                                     self.attribs.get_win_icon())
            if os.path.exists(icon_file):
                msilib.add_data(self.db, 'Property', [
                    ('ARPPRODUCTICON', 'InstallIcon'),
                ])
                msilib.add_data(self.db, 'Icon', [(
                    'InstallIcon', msilib.Binary(icon_file))])

            # Copy/paste from parent's method
            dialog = distutils.command.bdist_msi.PyDialog(
                self.db, 'ExitDialog',
                self.x, self.y, self.width, self.height, self.modal,
                self.title, 'Finish', 'Finish', 'Finish')
            dialog.title('Completing the [ProductName]')
            dialog.back('< Back', 'Finish', active=False)
            dialog.cancel('Cancel', 'Back', active=False)
            dialog.text(
                'Description', 15, 235, 320, 20, 0x30003,
                'Click the Finish button to exit the installer.')
            button = dialog.next('Finish', 'Cancel', name='Finish')
            button.event('EndDialog', 'Return')

            """
            Does not work as expected, no more time for that as an icon
            is created on the desktop and in the menu.
            # Launch product checkbox
            msilib.add_data(self.db, 'Property', [(
                'StartClient', '1')])
            c = dialog.control(
                'LaunchAfterInstall', 'CheckBox',  15, 200, 320, 20, 0x3,
                'StartClient', 'Launch [ProductName]', None, None)
            c.condition('Hide', 'Progress1<>"Install"')
            msilib.add_data(self.db, 'CustomAction', [(
                'LaunchNuxeoDrive', 768, 'TARGETDIR', 'start /B %s' % self.get_executable())])
            msilib.add_data(self.db, 'InstallExecuteSequence', [(
                'LaunchNuxeoDrive', 'StartClient=1 and Progress1="Install"', 6600 - 2)])
            """


# Override cx_Freeze setup to override build and install commands.
def setup(**attrs):
    command_classes = attrs.setdefault('cmdclass', {})
    _AddCommandClass(command_classes, 'build', build)
    _AddCommandClass(command_classes, 'install', install)
    if sys.platform == 'win32':
        bdist_msi.attribs = attrs.get('attribs')
        _AddCommandClass(command_classes, 'bdist_msi', bdist_msi)
    cx_setup(**attrs)
