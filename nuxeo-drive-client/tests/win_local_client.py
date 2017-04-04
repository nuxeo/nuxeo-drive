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
from win32com.shell import shell, shellcon

from nxdrive.client.local_client import LocalClient
from tests.common import log


class WindowsLocalClient(LocalClient):
    def __init__(self, base_folder, digest_func='md5', ignored_prefixes=None,
                 ignored_suffixes=None, check_suspended=None,
                 case_sensitive=None, disable_duplication=False):
        super(WindowsLocalClient, self).__init__(base_folder, digest_func,
                                                 ignored_prefixes,
                                                 ignored_suffixes,
                                                 check_suspended,
                                                 case_sensitive,
                                                 disable_duplication)

    def delete_final(self, ref):
        path = self.abspath(ref)
        res = shell.SHFileOperation((0, shellcon.FO_DELETE, path, None,
                                     shellcon.FOF_NOCONFIRMATION, None, None))
        if res[0] != 0:
            raise IOError(res)

    def move(self, ref, new_parent_ref, name=None):
        path = self.abspath(ref)
        if name is None:
            name = os.path.basename(path)
        new_path = os.path.join(self.abspath(new_parent_ref), name)
        res = shell.SHFileOperation((0, shellcon.FO_MOVE, path, new_path,
                                     shellcon.FOF_NOCONFIRMATION, None, None))
        if res[0] != 0:
            raise IOError(res)

    def duplicate_file(self, ref):
        # return super(WindowsLocalClient, self).duplicate_file(ref)
        parent = os.path.dirname(ref)
        name = os.path.basename(ref)
        locker = self.unlock_ref(parent, False)
        os_path, name = self._abspath_deduped(parent, name)
        try:
            res = shell.SHFileOperation((0, shellcon.FO_COPY, os_path,
                                         self.abspath(ref),
                                         shellcon.FOF_NOCONFIRMATION, None,
                                         None))
            if res[0] != 0:
                raise IOError(res)
            if parent == u"/":
                return u"/" + name
            return parent + u"/" + name
        finally:
            self.lock_ref(parent, locker)

    def abspath(self, ref):
        # Remove \\?\
        abs_path = super(WindowsLocalClient, self).abspath(ref)
        if len(abs_path) >= 260:
            log.warning(('The path is longer than 260 characters and '
                         'WindowsLocalClient is about the remove the long path '
                         'prefix. So the test is likely to fail.'))
        return abs_path[4:]

    def rename(self, ref, to_name):
        path = self.abspath(ref)
        new_path = os.path.join(os.path.dirname(path), to_name)
        res = shell.SHFileOperation((0, shellcon.FO_RENAME, path, new_path,
                                     shellcon.FOF_NOCONFIRMATION, None, None))
        if res[0] != 0:
            raise IOError(res)

    def delete(self, ref):
        path = self.abspath(ref)
        # FOF_ALLOWUNDO send to Trash
        res = shell.SHFileOperation((0, shellcon.FO_DELETE, path, None,
                                     shellcon.FOF_NOCONFIRMATION | shellcon.FOF_ALLOWUNDO,
                                     None, None))
        if res[0] != 0:
            raise IOError(res)
