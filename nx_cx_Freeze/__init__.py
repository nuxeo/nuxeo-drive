"""cx_Freeze extension

Extends:

- the 'build' command with the 'exe-command' option to allow using a
different command from 'build_exe' to build executables from Python scripts.

- the 'install' command with the 'skip-sub-commands' option to allow not
running a set of sub commands, e.g.:

    install --skip-sub-commands=install_lib,install_scripts,install_data
"""

import sys
import distutils.command.build
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


# Override cx_Freeze setup to override build and install commands.
def setup(**attrs):
    commandClasses = attrs.setdefault("cmdclass", {})
    _AddCommandClass(commandClasses, "build", build)
    _AddCommandClass(commandClasses, "install", install)
    cx_setup(**attrs)
