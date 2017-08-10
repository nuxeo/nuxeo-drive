# coding: utf-8
""" Commandline interface for the Nuxeo Drive installation."""

import subprocess
import sys

if len(sys.argv) < 2:
    sys.exit(1)


def launch(exe):
    executable = sys.executable
    if sys.platform == 'darwin':
        executable = executable.replace('python', exe)
    elif sys.platform == 'win32':
        executable = executable.replace('launcher.exe', exe)
    else:
        executable = executable.replace('launcher', exe)
    args = [executable]
    print 'Launch Drive'
    subprocess.Popen(args)

if '..' not in sys.argv[1]:
    # install stuff
    launch(sys.argv[1])

sys.exit(0)
