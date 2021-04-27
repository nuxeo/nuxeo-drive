import errno
from enum import Enum
from pathlib import Path
from sys import platform

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
# time, the server will finish way before that timeout.
TX_TIMEOUT = 60 * 60 * 6  # 6 hours

# Number of transfers displayed in the Direct Transfer window, onto the monitoring tab
DT_MONITORING_MAX_ITEMS = 20

# Number of sessions displayed in the Direct Transfer window, onto the active sessions tab
DT_ACTIVE_SESSIONS_MAX_ITEMS = 15

# List of chars that cannot be used in filenames (either OS or Nuxeo restrictions)
INVALID_CHARS = r'/:\\|*><?"'

# Default update channel
DEFAULT_CHANNEL = "centralized"

ROOT = Path()

UNACCESSIBLE_HASH = "TO_COMPUTE"

TOKEN_PERMISSION = "ReadWrite"

DEFAULT_SERVER_TYPE = "NXDRIVE"

SYNC_ROOT = "/org.nuxeo.drive.service.impl.DefaultTopLevelFolderItemFactory#"

# Document's UID and token regexp
DOC_UID_REG = "[0-f]{8}-[0-f]{4}-[0-f]{4}-[0-f]{4}-[0-f]{12}"

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
    """Used to figure out which login endpoint is used for a given server."""

    DEL_SERVER = "delete_server"
    UNSYNC = "unsync"
    ROLLBACK = "rollback"


class DigestStatus(Enum):
    """Used to figure out the document's digest state."""

    # Digest and digest algorithm are fine
    OK = 0

    # No digest?!
    REMOTE_HASH_EMPTY = 1

    # The document is using a non-standard digest on purpose: it will be computed async (see NXDRIVE-2140).
    # This is only for files uploaded with S3 direct upload and bigger than a (usually small) limit
    # (any file uploaded in multipart will need an async digest, and multipart is often enabled by
    # client libraries after 16MB or a similar size). So it'll apply to a lot of media files.
    # Also it always applies for S3 direct upload when server-side encryption with SSE-KMS is enabled.
    # Also it always applies if the server blob provider is configured to use another digest algorithm than MD5.
    REMOTE_HASH_ASYNC = 2

    # The document is using a non-standard digest and thus we cannot compute it locally
    # (this is likely a Live Connect document, see NXDRIVE-1973 comment)
    REMOTE_HASH_EXOTIC = 3


class TransferStatus(Enum):
    """Used to represent an upload/download status."""

    ONGOING = 1
    PAUSED = 2
    SUSPENDED = 3
    DONE = 4
    # Note: there used to be a CANCELLED status, set to 4. At the time, DONE was set to 5.
    # But a "small" mess was done with NXDRIVE-1784 and fixed later with NXDRIVE-1901.
    # So we cannot use 5 as a value. Never again.
    CANCELLED = 6
