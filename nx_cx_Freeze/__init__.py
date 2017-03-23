"""cx_Freeze extension

Extends:

- the 'build' command with the 'exe-command' option to allow using a
different command from 'build_exe' to build executables from Python scripts.

- the 'install' command with the 'skip-sub-commands' option to allow not
running a set of sub commands, e.g.:

    install --skip-sub-commands=install_lib,install_scripts,install_data

- the 'bdist_msi' command to handle LaunchAfterInstall and a clean uninstall.
"""

import distutils.command.build
import sys
import os
from cx_Freeze.dist import build as cx_build
from cx_Freeze.dist import install as cx_install
from cx_Freeze.dist import setup as cx_setup
from cx_Freeze.dist import _AddCommandClass


class build(cx_build):

    cx_build.user_options.append(
        ('exe-command=', None, "Python script executables command"))

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
         "sub commands to ignore when running command"))

    def initialize_options(self):
        cx_install.initialize_options(self)
        self.skip_sub_commands = None

    def get_sub_commands(self):
        subCommands = cx_install.get_sub_commands(self)
        if self.skip_sub_commands:
            skip_sub_commands = self.skip_sub_commands.split(',')
            for cmd in skip_sub_commands:
                if cmd in subCommands:
                    subCommands.remove(cmd)
        return subCommands


if sys.platform == 'win32':
    from cx_Freeze.windist import bdist_msi as cx_bdist_msi

    class bdist_msi(cx_bdist_msi):
        attribs = None
        initial_target_dir = None

        def finalize_options(self):
            self.distribution.get_name()
            if self.initial_target_dir is None:
                if distutils.util.get_platform() == "win-amd64":
                    programFilesFolder = "ProgramFiles64Folder"
                else:
                    programFilesFolder = "ProgramFilesFolder"
                self.initial_target_dir = r"[%s]\%s" % (programFilesFolder,
                                            self.attribs.get_install_dir())
            # Using old style class so can't use super
            import cx_Freeze
            cx_Freeze.windist.bdist_msi.finalize_options(self)

        def get_executable(self):
            return self.attribs.get_win_targetName()

        def get_license(self):
            return self.attribs.get_licence()

        def add_licence_dialog(self):
            import msilib
            msilib.add_data(self.db, 'InstallUISequence',
                [("LicenceDialog", None, 380)])
            dialog = distutils.command.bdist_msi.PyDialog(self.db,
                                                          "LicenceDialog",
                    self.x, self.y, self.width, self.height, self.modal,
                    self.title, "Next", "Next", "Cancel")
            dialog.text("LicenseTitle", 15, 10, 320, 20, 0x3, "License")
            dialog.control("License", "ScrollableText",
                                  15, 30, 340, 200, 0x7, None,
                                    self.get_license(), None, None)
            dialog.control("LicenseAccepted", "CheckBox",
                               15, 240, 320, 20, 0x3,
                               "LicenseAccepted",
                               "I've accepted this agreement", None, None)
            button = dialog.cancel("Cancel", "Next")
            button.event("EndDialog", "Exit")
            button = dialog.next("Next", "Cancel", active=False)
            button.condition("Enable", "LicenseAccepted")
            button.condition("Disable", "not LicenseAccepted")
            button.event("EndDialog", "Return")

        def add_exit_dialog(self):
            import msilib
            if self.get_license() is not None:
                self.add_licence_dialog()
            dialog = distutils.command.bdist_msi.PyDialog(self.db,
                                                          "ExitDialog",
                    self.x, self.y, self.width, self.height, self.modal,
                    self.title, "Finish", "Finish", "Finish")
            dialog.title("Completing the [ProductName]")
            dialog.back("< Back", "Finish", active=False)
            dialog.cancel("Cancel", "Back", active=False)
            dialog.text("Description", 15, 235, 320, 20, 0x30003,
                    "Click the Finish button to exit the installer.")
            button = dialog.next("Finish", "Cancel", name="Finish")
            button.event("EndDialog", "Return")
            msilib.add_data(self.db, "Property",
                     [("StartClient", "1")])
            # Launch product checkbox
            c = dialog.control("LaunchAfterInstall", "CheckBox",
                               15, 200, 320, 20, 0x3,
                               "StartClient", "Launch [ProductName]",
                               None, None)
            c.condition("Hide", 'Progress1<>"Install"')
            # 18 is for execute a .exe from install
            msilib.add_data(self.db, "CustomAction", [("LaunchNuxeoDrive", 82,
                                                       "launcher.exe",
                                                       self.get_executable())])
            button.event("DoAction", "LaunchNuxeoDrive",
                         'StartClient=1 and Progress1="Install"')
            msilib.add_data(self.db, "CustomAction", [("NuxeoDriveCleanUp", 82,
                                                       self.get_executable(),
                                                       "uninstall")])
            # Deffered action with noImpersonate to have the correct privileges
            msilib.add_data(self.db, "CustomAction", [("NuxeoDriveFolderCleanUp", 3234,
                                                       "TARGETDIR",
                                                       "cmd.exe /C \"rmdir /S /Q appdata\"")])
            msilib.add_data(self.db, "InstallExecuteSequence",
                            [("NuxeoDriveCleanUp",
                              'REMOVE="ALL" AND NOT UPGRADINGPRODUCTCODE',
                              1260)])
            # After InstallInitialize
            msilib.add_data(self.db, "InstallExecuteSequence",
                            [("NuxeoDriveFolderCleanUp",
                              'REMOVE="ALL" AND NOT UPGRADINGPRODUCTCODE',
                              1560)])
            # Add product icon
            icon_file = os.path.join(self.attribs.get_icons_home(), self.attribs.get_win_icon())
            if os.path.exists(icon_file):
                msilib.add_data(self.db, "Property", [("ARPPRODUCTICON", "InstallIcon")])
                msilib.add_data(self.db, "Icon", [("InstallIcon", msilib.Binary(icon_file))])
            # Allow to customize the MSI
            if getattr(self.attribs, 'customize_msi', None) is not None:
                self.attribs.customize_msi(self.db)


# Override cx_Freeze setup to override build and install commands.
def setup(**attrs):
    commandClasses = attrs.setdefault("cmdclass", {})
    _AddCommandClass(commandClasses, "build", build)
    _AddCommandClass(commandClasses, "install", install)
    if sys.platform == 'win32':
        bdist_msi.attribs = attrs.get("attribs")
        _AddCommandClass(commandClasses, "bdist_msi", bdist_msi)
    cx_setup(**attrs)
