# coding: utf-8
import errno
from enum import Enum, auto
from pathlib import Path
from sys import platform
from types import MappingProxyType

from requests.exceptions import ChunkedEncodingError, ConnectionError, Timeout

LINUX = platform == "linux"
MAC = platform == "darwin"
WINDOWS = platform == "win32"

# Custom protocol URL (nxdrive://...)
NXDRIVE_SCHEME = "nxdrive"

BUNDLE_IDENTIFIER = "org.nuxeo.drive"
APP_NAME = "Nuxeo Drive"
COMPANY = "Nuxeo"

TIMEOUT = 20  # Seconds
STARTUP_PAGE_CONNECTION_TIMEOUT = 30  # Seconds
FILE_BUFFER_SIZE = 1024 ** 2  # 1 MiB
MAX_LOG_DISPLAYED = 50000  # Lines
BATCH_SIZE = 500  # Scroll descendants batch size (max is 1,000)

# Transaction timeout: it is used by the server when generating the whole file after all chunks
# have been uploaded. Setting a high value to be able to handle very big files. Most of the
# time, the server will finish way before thhat timeout.
TX_TIMEOUT = 60 * 60 * 6  # 6 hours

# Default update channel
DEFAULT_CHANNEL = "centralized"

ROOT = Path()

UNACCESSIBLE_HASH = "TO_COMPUTE"

TOKEN_PERMISSION = "ReadWrite"

DEFAULT_SERVER_TYPE = "NXDRIVE"

# Document's UID and token regexp
DOC_UID_REG = "[0-f]{8}-[0-f]{4}-[0-f]{4}-[0-f]{4}-[0-f]{12}"

# Forbidden charaters on the OS (will be replaced by a dash "-")
# On Windows, they are:
#    / : " | * < > ? \
# On Unix, they are:
#    / :
FORBID_CHARS_ALL = MappingProxyType({ord(c): "-" for c in '/:"|*<>?\\'})
FORBID_CHARS_UNIX = MappingProxyType({ord(c): "-" for c in "/:"})

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

# OSError indicating the incapacity to do anything because of too long file name or deep tree
LONG_FILE_ERRORS = {errno.ENAMETOOLONG}
if WINDOWS:
    # WindowsError: [Error 111] ??? (seems related to deep tree)
    # Cause: short paths are disabled on Windows
    LONG_FILE_ERRORS.add(111)
    # WindowsError: [Error 121] The source or destination path exceeded or would exceed MAX_PATH.
    # Cause: short paths are disabled on Windows
    LONG_FILE_ERRORS.add(121)
    # OSError: [WinError 123] The filename, directory name, or volume label syntax is incorrect.
    LONG_FILE_ERRORS.add(123)
    # WindowsError: [Error 124] The path in the source or destination or both was invalid.
    # Cause: dealing with different drives, ie when the sync folder is not on the same drive as Nuxeo Drive one.
    LONG_FILE_ERRORS.add(124)
    # WindowsError: [Error 206] The filename or extension is too long.
    # Cause: even the full short path is too long
    LONG_FILE_ERRORS.add(206)
    # OSError: Couldn't perform operation. Error code: 1223 (seems related to long paths)
    LONG_FILE_ERRORS.add(1223)

CONNECTION_ERROR = (ChunkedEncodingError, ConnectionError, Timeout)


class DelAction(Enum):
    """ Used to figure out which login endpoint is used for a given server. """

    DEL_SERVER = "delete_server"
    UNSYNC = "unsync"
    ROLLBACK = "rollback"


class TransferStatus(Enum):
    """ Used to represent an upload/download status. """

    ONGOING = auto()
    PAUSED = auto()
    SUSPENDED = auto()
    DONE = auto()
