"""Common utilities for local and remote clients."""

import re
import os
import stat
from functools import partial
from collections import Iterable


registry = set()


def register(*args, **kwargs):
    def decorator(func):
        try:
            apply_to_parent = kwargs['apply_to_parent']
        except KeyError:
            apply_to_parent = False
        func2 = partial(func, *args, **kwargs)
        func2.apply_to_parent = apply_to_parent
        registry.add(func2)
        return func2
    return decorator


def remove_ignore_filter(func_name):
    partial_func = None
    for f in registry:
        if f.func.func_name == func_name:
            partial_func = f
            break
    if partial_func:
        registry.remove(partial_func)
    return partial_func


def add_ignore_filter(func, **kwargs):
    # func could be the actual function of a partial function (from the registry)
    if func is not None and hasattr(func, "func"):
        func = getattr(func, "func", None)
    if func:
        register(**kwargs)(func)
    return func


@register(prefixes=(
        '.',  # hidden Unix files
        '~$',  # Windows lock files
        'Thumbs.db',  # Thumbnails files
        'Icon\r',  # Mac Icon
        'desktop.ini',  # Icon for windows
), apply_to_parent=True
)
def ignore_prefixes(client, parent, name, **kwargs):
    # only needs the (file) name, client and parent are not used
    prefixes = kwargs['prefixes']
    if prefixes is None:
        return False
    if isinstance(prefixes, Iterable):
        for prefix in prefixes:
            if name.startswith(prefix):
                return True
    elif isinstance(prefixes, str):
        if name.startswith(prefixes):
            return True
    else:
        return False


@register(suffixes=(
        '~',  # editor buffers
        '.swp',  # vim swap files
        '.lock',  # some process use file locks
        '.LOCK',  # other locks
        '.part', '.crdownload', '.partial',  # partially downloaded files by browsers
))
def ignore_suffixes(client, parent, name, **kwargs):
    # only needs the (file) name, client and parent are not used
    suffixes = kwargs['suffixes']
    if suffixes is None:
        return False
    if isinstance(suffixes, Iterable):
        for suffix in suffixes:
            if name.endswith(suffix):
                return True
    elif isinstance(suffixes, str):
        if name.endswith(suffixes):
            return True
    else:
        return False


@register(prefixes=('~', '#',), suffixes=('.tmp', '#',))
def ignore_prefix_and_suffix(client, parent, name, **kwargs):
    # only needs the (file) name, client and parent are not used
    prefixes = kwargs['prefixes']
    suffixes = kwargs['suffixes']
    if prefixes is None or suffixes is None:
        return False
    if len(name) < 2:
        return False
    if isinstance(prefixes, str) and isinstance(suffixes, str):
        return name.startswith(prefixes) and name.endswith(suffixes)

    if isinstance(prefixes, Iterable) and isinstance(suffixes, Iterable):
        for prefix, suffix in zip(prefixes, suffixes):
            if name.startswith(prefix) and name.endswith(suffix):
                return True
    return False


def base_is_ignored(client, parent_ref, file_name):
    ignore_parent = False
    if parent_ref:
        grandparent_ref, dir_name = os.path.split(parent_ref)
        if dir_name:
            ignore_parent = any(f(client, grandparent_ref, dir_name) for f in registry if f.apply_to_parent)
    return ignore_parent or any(f(client, parent_ref, file_name) for f in registry)


class BaseClient(object):
    @staticmethod
    def set_path_readonly(path):
        current = os.stat(path).st_mode
        if os.path.isdir(path):
            # Need to add
            right = (stat.S_IXUSR | stat.S_IRGRP | stat.S_IXGRP | stat.S_IRUSR)
            if current & ~right == 0:
                return
            os.chmod(path, right)
        else:
            # Already in read only
            right = (stat.S_IRGRP | stat.S_IRUSR)
            if current & ~right == 0:
                return
            os.chmod(path, right)

    @staticmethod
    def unset_path_readonly(path):
        current = os.stat(path).st_mode
        if os.path.isdir(path):
            right = (stat.S_IXUSR | stat.S_IRGRP | stat.S_IXGRP |
                                stat.S_IRUSR | stat.S_IWGRP | stat.S_IWUSR)
            if current & right == right:
                return
            os.chmod(path, right)
        else:
            right = (stat.S_IRGRP | stat.S_IRUSR |
                             stat.S_IWGRP | stat.S_IWUSR)
            if current & right == right:
                return
            os.chmod(path, right)

    def unlock_path(self, path, unlock_parent=True):
        result = 0
        if unlock_parent:
            parent_path = os.path.dirname(path)
            if (os.path.exists(parent_path) and
                not os.access(parent_path, os.W_OK)):
                self.unset_path_readonly(parent_path)
                result |= 2
        if os.path.exists(path) and not os.access(path, os.W_OK):
            self.unset_path_readonly(path)
            result |= 1
        return result

    def lock_path(self, path, locker):
        if locker == 0:
            return
        if locker & 1 == 1:
            self.set_path_readonly(path)
        if locker & 2 == 2:
            parent = os.path.dirname(path)
            self.set_path_readonly(parent)


class NotFound(Exception):
    pass

DEFAULT_REPOSITORY_NAME = 'default'


# Default buffer size for file upload / download and digest computation
FILE_BUFFER_SIZE = 1024 ** 2

# Name of the folder holding the files locally edited from Nuxeo
LOCALLY_EDITED_FOLDER_NAME = 'Locally Edited'

COLLECTION_SYNC_ROOT_FACTORY_NAME = 'collectionSyncRootFolderItemFactory'

UNACCESSIBLE_HASH = "TO_COMPUTE"


def safe_filename(name, replacement=u'-'):
    """Replace invalid character in candidate filename"""
    return re.sub(ur'(/|\\|\*|:|\||"|<|>|\?)', replacement, name)
