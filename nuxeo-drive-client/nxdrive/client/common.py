"""Common utilities for local and remote clients."""

class NotFound(Exception):
    pass

# TODO: add support for the move operations

DEFAULT_IGNORED_PREFIXES = [
    '.',  # hidden Unix files
    '~$',  # Windows lock files
]

DEFAULT_IGNORED_SUFFIXES = [
    '~',  # editor buffers
    '.swp',  # vim swap files
    '.lock',  # some process use file locks
    '.LOCK',  # other locks
    '.part',  # partially downloaded files
]

BUFFER_SIZE = 1024 ** 2
