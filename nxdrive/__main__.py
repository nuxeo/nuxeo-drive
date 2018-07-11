# coding: utf-8
import sys

# We cannot use a relative import here, else Drive will not start
# when packaged. See https://github.com/pyinstaller/pyinstaller/issues/2560
from nxdrive.commandline import CliHandler

if sys.version_info < (3, 6):
    raise RuntimeError("Nuxeo Drive requires Python 3.6+")

sys.exit(CliHandler().handle(sys.argv))
