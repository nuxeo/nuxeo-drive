"""
Intent of this file is to use OSX File Manager to make FS operations to simulate
user actions.
"""

import os
import time
from pathlib import Path

import Cocoa

from . import LocalTest


class MacLocalClient(LocalTest):
    def __init__(self, base_folder, **kwargs):
        super().__init__(base_folder, **kwargs)
        self.fm = Cocoa.NSFileManager.defaultManager()

    def copy(self, srcref: str, dstref: str) -> None:
        """Make a copy of the file (with xattr included)."""
        src = self.abspath(srcref)
        dst = self.abspath(dstref)
        if not dst.exists() and not dst.parent.exists():
            raise ValueError(
                f"parent destination directory {dst.parent} does not exist"
            )
        if src.is_dir() and dst.exists() and dst.is_file():
            raise ValueError(f"cannot copy directory {src} to a file {dst}")
        if dst.exists() and dst.is_dir():
            dst = dst / src.name

        error = None
        result = self.fm.copyItemAtPath_toPath_error_(str(src), str(dst), error)
        self._process_result(result)

    def move(self, srcref: str, parentref: str, name: str = None) -> None:
        src = self.abspath(srcref)
        parent = self.abspath(parentref)

        dst = parent / (name or src.name)

        error = None
        result = self.fm.moveItemAtPath_toPath_error_(str(src), str(dst), error)
        time.sleep(0.3)
        self._process_result(result)

    def rename(self, srcref: str, to_name: str):
        parent = os.path.dirname(srcref)
        dstref = os.path.join(parent)
        self.move(srcref, dstref, name=to_name)
        return Path(parent) / to_name

    def delete(self, ref):
        path = self.abspath(ref)
        error = None
        result = self.fm.removeItemAtPath_error_(str(path), error)
        self._process_result(result)

    @staticmethod
    def _process_result(result):
        ok, err = result
        if not ok:
            error = (
                f"{err.localizedDescription()} (cause: {err.localizedFailureReason()})"
            )
            raise OSError(error)
