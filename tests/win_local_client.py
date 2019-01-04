# coding: utf-8
"""
Intent of this file is to use Explorer operations to make FS to simulate user
actions.

https://msdn.microsoft.com/en-us/library/windows/desktop/bb775771(v=vs.85).aspx
Using SHFileOperation as the MSDN advise to use it for multithread

IFileOperation can only be applied in a single-threaded apartment (STA)
situation. It cannot be used for a multithreaded apartment (MTA) situation.
For MTA, you still must use SHFileOperation.
"""

import time
from pathlib import Path
from typing import Union

from win32com.shell import shell, shellcon

from . import LocalTest, log

RawPath = Union[Path, str]


class WindowsLocalClient(LocalTest):
    def __init__(self, base_folder, **kwargs):
        super().__init__(base_folder, **kwargs)

    def delete_final(self, ref: RawPath) -> None:
        path = str(self.abspath(ref))
        res = shell.SHFileOperation(
            (0, shellcon.FO_DELETE, path, None, shellcon.FOF_NOCONFIRMATION, None, None)
        )
        if res[0] != 0:
            raise OSError(res, locals())

    def move(self, ref: RawPath, new_parent_ref: RawPath, name: str = None) -> None:
        path = self.abspath(ref)
        name = name or path.name
        new_path = self.abspath(new_parent_ref) / name
        res = shell.SHFileOperation(
            (
                0,
                shellcon.FO_MOVE,
                str(path),
                str(new_path),
                shellcon.FOF_NOCONFIRMATION,
                None,
                None,
            )
        )
        if res[0] != 0:
            raise OSError(res, locals())

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

    def rename(self, srcref: RawPath, to_name: str) -> Path:
        path = self.abspath(srcref)
        new_path = path.with_name(to_name)
        res = shell.SHFileOperation(
            (
                0,
                shellcon.FO_RENAME,
                str(path),
                str(new_path),
                shellcon.FOF_NOCONFIRMATION,
                None,
                None,
            )
        )
        time.sleep(0.5)
        if res[0] != 0:
            raise OSError(res, locals())
        return new_path

    def delete(self, ref: RawPath) -> None:
        path = self.abspath(ref)
        # FOF_ALLOWUNDO send to Trash
        res = shell.SHFileOperation(
            (
                0,
                shellcon.FO_DELETE,
                str(path),
                None,
                shellcon.FOF_NOCONFIRMATION | shellcon.FOF_ALLOWUNDO,
                None,
                None,
            )
        )
        if res[0] != 0:
            raise OSError(res, locals())
