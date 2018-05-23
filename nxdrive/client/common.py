# coding: utf-8
"""Common utilities for local and remote clients."""

import re


class NotFound(Exception):
    pass


class DuplicationDisabledError(ValueError):
    """
    Exception raised when de-duplication is disabled and there is a
    file collision.
    """
    pass


# Default buffer size for file upload / download and digest computation

COLLECTION_SYNC_ROOT_FACTORY_NAME = 'collectionSyncRootFolderItemFactory'

UNACCESSIBLE_HASH = 'TO_COMPUTE'


def safe_filename(name, replacement=u'-'):
    """Replace invalid character in candidate filename"""
    return re.sub(ur'(/|\\|\*|:|\||"|<|>|\?)', replacement, name)
