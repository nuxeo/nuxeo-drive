# coding: utf-8
"""
Intent of this file is to use OSX File Manager to make FS operations to simulate
user actions.
"""

import os

import Cocoa

from nxdrive.client.local_client import LocalClient


class MockFile(object):
    def __init__(self, path):
        self.path = path


class MacLocalClient(LocalClient):
    def __init__(self, base_folder, **kwargs):
        super(MacLocalClient, self).__init__(base_folder, **kwargs)
        self.fm = Cocoa.NSFileManager.defaultManager()

    def copy(self, srcref, dstref):
        src = self.abspath(srcref)
        dst = self.abspath(dstref)
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
        src = self.abspath(srcref)
        parent = self.abspath(parentref)
        path, srcname = os.path.split(src)

        if name:
            srcname = name
        dst = os.path.join(parent, srcname)

        error = None
        result = self.fm.moveItemAtPath_toPath_error_(src, dst, error)
        self._process_result(result)

    def rename(self, srcref, to_name):
        parent = os.path.dirname(srcref)
        dstref = os.path.join(parent)
        self.move(srcref, dstref, name=to_name)
        return MockFile(os.path.join(parent, to_name))

    def delete(self, ref):
        path = self.abspath(ref)
        error = None
        result = self.fm.removeItemAtPath_error_(path, error)
        self._process_result(result)

    @staticmethod
    def _process_result(result):
        ok, err = result
        if not ok:
            raise IOError(err.utf8ValueSafe())
