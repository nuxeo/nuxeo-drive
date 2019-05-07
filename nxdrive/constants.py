# coding: utf-8
import errno
from enum import Enum
from pathlib import Path
from sys import platform

LINUX = platform == "linux"
MAC = platform == "darwin"
WINDOWS = platform == "win32"

BUNDLE_IDENTIFIER = "org.nuxeo.drive"
APP_NAME = "Nuxeo Drive"
COMPANY = "Nuxeo"

TIMEOUT = 20
STARTUP_PAGE_CONNECTION_TIMEOUT = 30
TX_TIMEOUT = 300
FILE_BUFFER_SIZE = 1024 ** 2
MAX_LOG_DISPLAYED = 50000
BATCH_SIZE = 100  # Scroll descendants batch size

DOWNLOAD_TMP_FILE_PREFIX = "."
DOWNLOAD_TMP_FILE_SUFFIX = ".nxpart"
PARTIALS_PATH = Path(".partials")
ROOT = Path()

UNACCESSIBLE_HASH = "TO_COMPUTE"

TOKEN_PERMISSION = "ReadWrite"

# The registry key from the HKCU hive where to look for local configuration on Windows
CONFIG_REGISTRY_KEY = "Software\\Nuxeo\\Drive"

# OSError indicating a lack of disk space
# >>> import errno, os
# >>> for no, label in sorted(errno.errorcode.items()):
# >>>     print(f"{label} (n°{no}): {os.strerror(no)}")
NO_SPACE_ERRORS = {
    errno.EDQUOT,  # Disk quota exceeded
    errno.EFBIG,  # File too large
    errno.ENOMEM,  # Cannot allocate memory
    errno.ENOSPC,  # No space left on device
    errno.ENOBUFS,  # No buffer space available
    errno.ERANGE,  # Result too large
}


class DelAction(Enum):
    """ Used to figure out which login endpoint is used for a given server. """

    DEL_SERVER = "delete_server"
    UNSYNC = "unsync"
    ROLLBACK = "rollback"
