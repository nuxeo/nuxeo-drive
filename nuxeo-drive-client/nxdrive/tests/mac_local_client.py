from nxdrive.client.local_client import LocalClient

import os
import sys
from common import log

if sys.platform == 'darwin':
    import Cocoa

if sys.platform == 'darwin':
    class MacLocalClient(LocalClient):
        def __init__(self, base_folder, digest_func='md5', ignored_prefixes=None,
                    ignored_suffixes=None, check_suspended=None, case_sensitive=None,
                    disable_duplication=False, fm=None):
            super(MacLocalClient, self).__init__(base_folder, digest_func, ignored_prefixes, ignored_suffixes,
                                                 check_suspended, case_sensitive, disable_duplication)
            if fm:
                self.fm = fm
            else:
                self.fm = Cocoa.NSFileManager.defaultManager()

        '''
        Copy either a file, or an entire directory at path 'src' to the path 'dst'.

        '''
        def copy(self, src, dst_parent):
            path, name = os.path.split(src)
            if os.path.isdir(dst_parent):
                dst = os.path.join(dst_parent, name)

            error = None
            result = self.fm.copyItemAtPath_toPath_error_(src, dst, error)
            self._process_result(result)

        def move(self, src, parent, name=None):
            path, srcname = os.path.split(src)
            if name:
                srcname = name
            dst = os.path.join(parent, srcname)

            error = None
            result = self.fm.moveItemAtPath_toPath_error_(src, dst, error)
            self._process_result(result)

        def duplicate_file(self, src):
            parent = os.path.dirname(src)
            name = os.path.basename(src)
            os_path, name = self._abspath_deduped(parent, name)
            dst = os.path.join(parent, name)
            self.copy(src, dst)
            return dst

        def rename(self, src, to_name):
            parent = os.path.dirname(src)
            self.move(src, parent, name=to_name)

        def delete(self, path):
            error = None
            result = self.fm.removeItemAtPath_error_(path, error)
            self._process_result(result)

        def _process_result(self, result):
            log.debug('result: %s%s', 'ok' if result[0] else 'error (',
                      '' if result[0] else result[1].description().encode('utf8') + ')')
            if not result[0]:
                raise IOError(result[1].description().encode('utf8'))


    class MacFileManagerUtils(object):
        fm = Cocoa.NSFileManager.defaultManager()

        @staticmethod
        def copy(src, dst_parent):
            path, name = os.path.split(src)
            if os.path.isdir(dst_parent):
                dst = os.path.join(dst_parent, name)

            error = None
            result = MacFileManagerUtils.fm.copyItemAtPath_toPath_error_(src, dst, error)
            MacFileManagerUtils._process_result(result)

        @staticmethod
        def move(src, parent, name=None):
            path, srcname = os.path.split(src)
            if name:
                srcname = name
            dst = os.path.join(parent, srcname)

            error = None
            result = MacFileManagerUtils.fm.moveItemAtPath_toPath_error_(src, dst, error)
            MacFileManagerUtils._process_result(result)

        @staticmethod
        def rename(src, to_name):
            parent = os.path.dirname(src)
            MacFileManagerUtils.move(src, parent, name=to_name)

        @staticmethod
        def delete(path):
            error = None
            result = MacFileManagerUtils.fm.removeItemAtPath_error_(path, error)
            MacFileManagerUtils._process_result(result)

        @staticmethod
        def _process_result(result):
            log.debug('result: %s%s', 'ok' if result[0] else 'error (',
                      '' if result[0] else result[1].description().encode('utf8') + ')')
            if not result[0]:
                raise IOError(result[1].description().encode('utf8'))
