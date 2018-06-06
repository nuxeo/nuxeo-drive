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

import os
import time

from win32com.shell import shell, shellcon

from nxdrive.client.local_client import LocalClient
from . import log


class MockFile:
    def __init__(self, path):
        self.path = path.replace(os.path.sep, '/')


class WindowsLocalClient(LocalClient):
    def __init__(self, base_folder, **kwargs):
        super().__init__(base_folder, **kwargs)

    def delete_final(self, ref):
        path = self.abspath(ref)
        res = shell.SHFileOperation((0, shellcon.FO_DELETE, path, None,
                                     shellcon.FOF_NOCONFIRMATION, None, None))
        if res[0] != 0:
            raise OSError(res, locals())

    def move(self, ref, new_parent_ref, name=None):
        path = self.abspath(ref)
        if name is None:
            name = os.path.basename(path)
        new_path = os.path.join(self.abspath(new_parent_ref), name)
        res = shell.SHFileOperation((0, shellcon.FO_MOVE, path, new_path,
                                     shellcon.FOF_NOCONFIRMATION, None, None))
        if res[0] != 0:
            raise OSError(res, locals())

    def abspath(self, ref):
        # Remove \\?\
        abs_path = super().abspath(ref)
        if len(abs_path) >= 255:
            log.warning(
                'The path is longer than 255 characters and the '
                'WindowsLocalClient is about the remove the long path '
                'prefix. So the test is likely to fail.')
        return abs_path[4:]

    def rename(self, srcref, to_name):
        parent = os.path.dirname(srcref)
        path = self.abspath(srcref)
        new_path = os.path.join(os.path.dirname(path), to_name)
        res = shell.SHFileOperation((0, shellcon.FO_RENAME, path, new_path,
                                     shellcon.FOF_NOCONFIRMATION, None, None))
        time.sleep(0.5)
        if res[0] != 0:
            raise OSError(res, locals())
        return MockFile(os.path.join(parent, to_name))

    def delete(self, ref):
        path = self.abspath(ref)
        # FOF_ALLOWUNDO send to Trash
        res = shell.SHFileOperation((0, shellcon.FO_DELETE, path, None,
                                     shellcon.FOF_NOCONFIRMATION
                                     | shellcon.FOF_ALLOWUNDO,
                                     None, None))
        if res[0] != 0:
            raise OSError(res, locals())
