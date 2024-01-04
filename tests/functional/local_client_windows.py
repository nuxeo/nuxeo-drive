"""
Intent of this file is to use Explorer operations to make FS to simulate user
actions.

https://msdn.microsoft.com/en-us/library/windows/desktop/bb775771(v=vs.85).aspx
Using SHFileOperation as the MSDN advise to use it for multithread

IFileOperation can only be applied in a single-threaded apartment (STA)
situation. It cannot be used for a multithreaded apartment (MTA) situation.
For MTA, you still must use SHFileOperation.

Note that any string passed to SHFileOperation needs to be double-null terminated.
This is automatically handled by pywin32:
https://github.com/mhammond/pywin32/blob/059b7be/com/win32comext/shell/src/shell.cpp#L940
"""

import errno
import logging
import os
import time
from pathlib import Path
from typing import Union

from win32com.shell import shell, shellcon

from . import LocalTest

RawPath = Union[Path, str]
log = logging.getLogger(__name__)


class WindowsLocalClient(LocalTest):
    def abspath(self, ref: RawPath) -> Path:
        # Remove \\?\
        abs_path = super().abspath(ref).resolve()
        if len(str(abs_path)) >= 255:
            log.warning(
                "The path is longer than 255 characters and the "
                "WindowsLocalClient is about the remove the long path "
                "prefix. So the test is likely to fail."
            )
        return abs_path

    def do_op(
        self, op: int, path_from: Path, path_to: Union[Path, None], flags: int
    ) -> None:
        """Actually do the requested SHFileOperation operation.
        Errors are automatically handled.
        """
        # *path_to* can be set to None for deletion of *path_from*
        if path_to:
            path_to = str(path_to)

        rc, aborted = shell.SHFileOperation((0, op, str(path_from), path_to, flags))

        if aborted:
            rc = errno.ECONNABORTED
        if rc != 0:
            raise OSError(rc, os.strerror(rc), path_from)

    def copy(self, srcref: RawPath, dstref: RawPath) -> None:
        """Make a copy of the file (with xattr included)."""
        self.do_op(
            shellcon.FO_COPY,
            self.abspath(srcref),
            self.abspath(dstref),
            shellcon.FOF_NOCONFIRMATION,
        )

    def delete(self, ref: RawPath) -> None:
        # FOF_ALLOWUNDO send to trash
        self.do_op(
            shellcon.FO_DELETE,
            self.abspath(ref),
            None,
            shellcon.FOF_NOCONFIRMATION | shellcon.FOF_ALLOWUNDO,
        )

    def delete_final(self, ref: RawPath) -> None:
        self.do_op(
            shellcon.FO_DELETE,
            self.abspath(ref),
            None,
            flags=shellcon.FOF_NOCONFIRMATION,
        )

    def move(self, ref: RawPath, new_parent_ref: RawPath, name: str = None) -> None:
        path = self.abspath(ref)
        new_path = self.abspath(new_parent_ref) / (name or path.name)
        self.do_op(shellcon.FO_MOVE, path, new_path, shellcon.FOF_NOCONFIRMATION)

    def rename(self, srcref: RawPath, to_name: str) -> Path:
        path = self.abspath(srcref)
        new_path = path.with_name(to_name)
        self.do_op(shellcon.FO_RENAME, path, new_path, shellcon.FOF_NOCONFIRMATION)
        time.sleep(0.5)
        return new_path
