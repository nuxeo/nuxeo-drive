"""cx_Freeze extension

Extends:

- the 'build' command with the 'exe-command' option to allow using a
different command from 'build_exe' to build executables from Python scripts.

- the 'install' command with the 'skip-sub-commands' option to allow not
running a set of sub commands, e.g.:

    install --skip-sub-commands=install_lib,install_scripts,install_data
"""

import distutils.command.build
from cx_Freeze.dist import build as cx_build
from cx_Freeze.dist import install as cx_install
from cx_Freeze.dist import setup as cx_setup
from cx_Freeze.dist import _AddCommandClass
from cx_Freeze.windist import bdist_msi as cx_bdist_msi

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


class bdist_msi(cx_bdist_msi):
    def get_executable(self):
        return "ndrivew.exe"
        
    def add_exit_dialog(self):
        import msilib
        dialog = distutils.command.bdist_msi.PyDialog(self.db, "ExitDialog",
                self.x, self.y, self.width, self.height, self.modal,
                self.title, "Finish", "Finish", "Finish")
        dialog.title("Completing the [ProductName]")
        dialog.back("< Back", "Finish", active = False)
        dialog.cancel("Cancel", "Back", active = False)
        dialog.text("Description", 15, 235, 320, 20, 0x30003,
                "Click the Finish button to exit the installer.")
        button = dialog.next("Finish", "Cancel", name = "Finish")
        button.event("EndDialog", "Return")
        msilib.add_data(self.db, "Property",
                 # See "DefaultUIFont Property"
                 [("StartClient", "1")])
        c = dialog.control("LaunchAfterInstall", "CheckBox", 15, 200, 320, 20, 0x3,
				"StartClient", "Launch [ProductName]", None, None)
        c.condition("Hide",'Progress1<>"Install"')
        # 18 is for execute a .exe from install
        msilib.add_data(self.db, "CustomAction", [("LaunchNuxeoDrive", 18, "launcher.exe", self.get_executable())])
        button.event("DoAction","LaunchNuxeoDrive",'StartClient=1 and Progress1="Install"')

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


# Override cx_Freeze setup to override build and install commands.
def setup(**attrs):
    commandClasses = attrs.setdefault("cmdclass", {})
    _AddCommandClass(commandClasses, "build", build)
    _AddCommandClass(commandClasses, "install", install)
    _AddCommandClass(commandClasses, "bdist_msi", bdist_msi)
    cx_setup(**attrs)
