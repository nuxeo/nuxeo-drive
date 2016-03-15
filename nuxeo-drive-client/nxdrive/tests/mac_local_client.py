'''
Intent of this file is ...

https://msdn.microsoft.com/en-us/library/windows/desktop/bb775771(v=vs.85).aspx
Using SHFileOperation as the MSDN advise to use it for multithread

IFileOperation can only be applied in a single-threaded apartment (STA) situation. It cannot be used for a multithreaded apartment (MTA) situation. For MTA, you still must use SHFileOperation.
'''
from nxdrive.client.local_client import LocalClient
from common import log

import os
import sys
if sys.platform == 'darwin':
    import Cocoa


class MacLocalClient(LocalClient):
    def __init__(self, base_folder, digest_func='md5', ignored_prefixes=None,
                    ignored_suffixes=None, check_suspended=None, case_sensitive=None, disable_duplication=False):
        super(MacLocalClient, self).__init__(base_folder, digest_func, ignored_prefixes, ignored_suffixes,
                                             check_suspended, case_sensitive, disable_duplication)
        self.fm = Cocoa.NSFileManager.defaultManager()

    '''
    Copy either a file, or an entire directory at relative (to the local client's base_folder) path 'srcref'
    to the relative path 'dstref'.
    If the 'srcref' is a file and 'dstref' is a file, it means it rename the source file or the new name (in the 'dstref').
    If the 'srcref' is a directory and 'dstref' is a directory, it copies the directory and its content with the same name,
    under the 'dstref'.
    If the 'srcref' is a file and 'dstref' is a directory, it copies the file with the same name under the 'dstref'.
    '''
    def copy(self, srcref, dstref):
        if os.path.exists(srcref):
            src = srcref
        else:
            src = self._abspath(srcref)
        if os.path.exists(dstref):
            dst = dstref
        else:
            dst = self._abspath(dstref)
        path, name = os.path.split(src)
        if not os.path.exists(dst) and not os.path.exists(os.path.dirname(dst)):
            raise ValueError('parent destination directory %s does not exist', os.path.dirname(dst))
        if os.path.isdir(src) and os.path.exists(dst) and os.path.isfile(dst):
            raise ValueError('cannnot copy directory %s to a file %s', src, dst)
        if os.path.exists(dst) and os.path.isdir(dst):
            dst = os.path.join(dst, name)

        error = None
        result = self.fm.copyItemAtPath_toPath_error_(src, dst, error)
        self._process_result(result)

    def move(self, srcref, parentref, name=None):
        if os.path.exists(srcref):
            src = srcref
        else:
            src = self._abspath(srcref)
        if os.path.exists(parentref):
            parent = parentref
        else:
            parent = self._abspath(parentref)
        path, srcname = os.path.split(src)
        if not os.path.exists(parent):
            raise ValueError('parent destination directory %s does not exist', parent)

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
        name = os.path.basename(srcref)
        dstref = os.path.join(parent, name)
        self.move(srcref, dstref)

    def delete(self, ref):
        path = self._abspath(ref)
        error = None
        result = self.fm.removeItemAtPath_error_(path, error)
        self._process_result(result)

    def _process_result(self, result):
        log.debug('result: %s%s', 'ok' if result[0] else 'error (', '' if result[0] else result[1] + ')')
        if not result[0]:
            raise IOError(result[1])


class MacFileManagerUtils(object):
    fm = Cocoa.NSFileManager.defaultManager()

    @staticmethod
    def copy(cls, src, dst):
        path, name = os.path.split(src)
        if not os.path.exists(dst) and not os.path.exists(os.path.dirname(dst)):
            raise ValueError('parent destination directory %s does not exist', os.path.dirname(dst))
        if os.path.isdir(src) and os.path.exists(dst) and os.path.isfile(dst):
            raise ValueError('cannnot copy directory %s to a file %s', src, dst)
        if os.path.exists(dst) and os.path.isdir(dst):
            dst = os.path.join(dst, name)

        error = None
        result = cls.fm.copyItemAtPath_toPath_error_(src, dst, error)
        cls._process_result(cls, result)

    @staticmethod
    def move(cls, src, parent, name=None):
        path, srcname = os.path.split(src)
        if not os.path.exists(parent):
            raise ValueError('parent destination directory %s does not exist', parent)

        if name:
            srcname = name
        dst = os.path.join(parent, srcname)

        error = None
        result = cls.fm.moveItemAtPath_toPath_error_(src, dst, error)
        cls._process_result(cls, result)

    @staticmethod
    def rename(cls, src, to_name):
        parent = os.path.dirname(src)
        dst = os.path.join(parent, to_name)
        cls.move(cls, src, dst)

    @staticmethod
    def delete(cls, path):
        error = None
        result = cls.fm.removeItemAtPath_error_(path, error)
        cls._process_result(cls, result)

    @staticmethod
    def _process_result(cls, result):
        log.debug('result: %s%s', 'ok' if result[0] else 'error (', '' if result[0] else str(result[1]) + ')')
        if not result[0]:
            raise IOError(result[1])