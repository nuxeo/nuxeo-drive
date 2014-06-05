"""cx_Freeze extension

Extends the 'build' command with the 'exe-command' option to allow using a
different command from 'build_exe' to build executables from Python scripts.
"""

import sys
import distutils.command.build
from cx_Freeze.dist import build as cx_build
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


# Override cx_Freeze setup to override build command.
def setup(**attrs):
    commandClasses = attrs.setdefault("cmdclass", {})
    _AddCommandClass(commandClasses, "build", build)
    cx_setup(**attrs)
