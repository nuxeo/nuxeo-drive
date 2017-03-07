"""
Intent of this file is to use OSX File Manager to make FS operations to simulate
user actions.
"""
import sys

import os

from nxdrive.client.local_client import LocalClient

if sys.platform == 'darwin':
    import Cocoa


class MacLocalClient(LocalClient):
    def __init__(self, base_folder, digest_func='md5', ignored_prefixes=None,
                 ignored_suffixes=None, check_suspended=None,
                 case_sensitive=None, disable_duplication=False):
        super(MacLocalClient, self).__init__(base_folder, digest_func,
                                             ignored_prefixes, ignored_suffixes,
                                             check_suspended, case_sensitive,
                                             disable_duplication)
        self.fm = Cocoa.NSFileManager.defaultManager()

    def copy(self, srcref, dstref):
        src = self._abspath(srcref)
        dst = self._abspath(dstref)
        path, name = os.path.split(src)
        if not os.path.exists(dst) and not os.path.exists(os.path.dirname(dst)):
            raise ValueError('parent destination directory %s does not exist',
                             os.path.dirname(dst))
        if os.path.isdir(src) and os.path.exists(dst) and os.path.isfile(dst):
            raise ValueError('cannnot copy directory %s to a file %s', src, dst)
        if os.path.exists(dst) and os.path.isdir(dst):
            dst = os.path.join(dst, name)

        error = None
        result = self.fm.copyItemAtPath_toPath_error_(src, dst, error)
        self._process_result(result)

    def move(self, srcref, parentref, name=None):
        src = self._abspath(srcref)
        parent = self._abspath(parentref)
        path, srcname = os.path.split(src)

        if name:
            srcname = name
        dst = os.path.join(parent, srcname)

        error = None
        result = self.fm.moveItemAtPath_toPath_error_(src, dst, error)
        self._process_result(result)

    def duplicate_file(self, srcref):
        parent = os.path.dirname(srcref)
        name = os.path.basename(srcref)
        os_path, name = self._abspath_deduped(parent, name)
        dstref = os.path.join(parent, name)
        self.copy(srcref, dstref)
        return dstref

    def rename(self, srcref, to_name):
        parent = os.path.dirname(srcref)
        dstref = os.path.join(parent)
        self.move(srcref, dstref, name=to_name)

    def delete(self, ref):
        path = self._abspath(ref)
        error = None
        result = self.fm.removeItemAtPath_error_(path, error)
        self._process_result(result)

    @staticmethod
    def _process_result(result):
        if not result[0]:
            raise IOError(result[1])
