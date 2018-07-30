# coding: utf-8
from sys import platform

LINUX = platform == "linux"
MAC = platform == "darwin"
WINDOWS = platform == "win32"

BUNDLE_IDENTIFIER = "org.nuxeo.drive"
APP_NAME = "Nuxeo Drive"

TIMEOUT = 20
STARTUP_PAGE_CONNECTION_TIMEOUT = 30
TX_TIMEOUT = 300
FILE_BUFFER_SIZE = 1024 ** 2
MAX_LOG_DISPLAYED = 50000

DOWNLOAD_TMP_FILE_PREFIX = "."
DOWNLOAD_TMP_FILE_SUFFIX = ".nxpart"

UNACCESSIBLE_HASH = "TO_COMPUTE"

TOKEN_PERMISSION = "ReadWrite"
