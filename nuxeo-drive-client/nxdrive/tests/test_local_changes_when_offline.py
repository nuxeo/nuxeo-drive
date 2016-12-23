'''
Created on 15-Dec-2016

    Test if changes made to local file system when nuxeo-drive is offline 
    sync's back later when nuxeo-drive becomes online

@author: dgraja
@author: mkeshava

'''
from common_unit_test import UnitTestCase
from nxdrive.tests.common_unit_test import FILE_CONTENT
from nxdrive.osi import AbstractOSIntegration
from nxdrive.logging_config import get_logger
import shutil

log = get_logger(__name__)
if AbstractOSIntegration.is_windows():
    from win32com.shell import shell, shellcon
else:
    import xattr
    import Cocoa


class TestOfflineChangesSync(UnitTestCase):
    '''
        All changes made in local PC while drive is offline should sync later
        when drive comes back online
        offline can be one of: suspended, exited or disconnect
    '''
    def setUp(self):
        self.engine_1.start()
        log.debug("Configure drive and wait for sync")
        self.wait_sync(wait_for_async=True)

        self.localpc = self.local_client_1
        self.server = self.remote_document_client_1
        # Create a folder and a file in server side.
        # Wait for Drive to finish sync (download)
        log.debug("Server: Create folder and upload a file")
        self.folder1_remote = self.server.make_folder("/", "Folder1")
        self.file1_remote = self.server.make_file(self.folder1_remote, "File1.txt", FILE_CONTENT)
        self.wait_sync(wait_for_async=True)

        # Verify that the folder and file are sync'd (download) successfully
        log.debug("Client: Verify sync successful")
        self.assertTrue(self.localpc.exists("/Folder1/File1.txt"),"File synced")

    def copy_with_xattr(self, src, dst):
        """
            custom copy tree method that also copies xattr along with shutil.copytree functionality
        """
        if AbstractOSIntegration.is_windows():
            # Make a copy of file1 using shell (to copy including xattr)
            shell.SHFileOperation((0, shellcon.FO_COPY, 
                                   src, dst, shellcon.FOF_NOCONFIRMATION, None, None))
        elif AbstractOSIntegration.is_mac():
            self.fm = Cocoa.NSFileManager.defaultManager()
            self.fm.copyItemAtPath_toPath_error_(src, dst, None)
        else:
            shutil.copy2(src, dst)
            remote_id = unicode(xattr.getxattr(src, "ndrive"), 'utf-8')
            xattr.setxattr(dst,"ndrive", str(remote_id))

    def test_copy_paste_when_engine_suspended(self):
        """
            Copy paste and a rename operation together on same file while drive is offline
            should be detected and synced to server as soon as drive comes back online
        """
        # Make drive offline (by suspend)
        log.debug("Suspend drive client")
        self.engine_1.suspend()

        # Make a copy of the file (with xattr included)
        log.debug("Client: Make a copy of the file at the same location")
        self.copy_with_xattr(src=self.localpc._abspath("/Folder1/File1.txt"),
                             dst=self.localpc._abspath("/Folder1/File1 - Copy.txt"))

        # Rename the original file
        log.debug("Client: Rename the original file")
        self.localpc.rename("/Folder1/File1.txt", "File1_renamed.txt")

        # Bring drive online (by resume)
        log.debug("Resume drive client")
        self.engine_1.resume()
        # Wait for Drive to sync the changes to server
        self.wait_sync(wait_for_async=True)

        # Verify there is no change in local pc
        log.debug("Client: Verify there is no change in local pc")
        self.assertTrue(self.localpc.exists("/Folder1/File1_renamed.txt"), "Renamed file should exist in local PC")
        self.assertTrue(self.localpc.exists("/Folder1/File1 - Copy.txt"), "Copied file should exist in local PC")
        self.assertFalse(self.localpc.exists("/Folder1/File1.txt"), "Original file should not exist in local PC")

        # Verify that local changes are uploaded to server successfully
        log.debug("Server: Verify sync successful")
        if self.server.exists("/Folder1/File1 - Copy.txt"):
            # '/Folder1/File1 - Copy.txt' is uploaded to server.
            # So original file named should be changed as 'File_renamed.txt'
            remote_info = self.server.get_info(self.file1_remote)
            self.assertEqual(remote_info.name, "File1_renamed.txt", "File should be renamed in Server after resume")
        else:
            # Original file is renamed as 'File1 - Copy.txt'. This is a bug only if Drive is online during copy+rename
            self.assertTrue(self.server.exists("/Folder1/File1_renamed.txt"), "File1_renamed.txt should exists in server as a new file")
            remote_info = self.server.get_info(self.file1_remote)
            self.assertEqual(remote_info.name, "File1 - Copy.txt", 
                             "Original File should be renamed as (File1 - Copy.txt or File1_renamed.txt) in Server after resume")
        return

    def test_copy_paste_normal(self):
        """
            Copy paste and a rename operation together on same file while drive is offline
            should be detected and synced to server as soon as drive comes back online
        """
        # Make a copy of the file (with xattr included)
        log.debug("Client: Make a copy of the file at the same location")
        self.copy_with_xattr(src=self.localpc._abspath("/Folder1/File1.txt"),
                             dst=self.localpc._abspath("/Folder1/File1 - Copy.txt"))

        # Rename the original file
        log.debug("Client: Rename original file")
        self.localpc.rename("/Folder1/File1.txt", "File1_renamed.txt")

        # Wait for Drive to sync the changes to server
        self.wait_sync(wait_for_async=True)

        # Verify there is no change in local pc
        log.debug("Client: Verify there is no change in local pc")
        self.assertTrue(self.localpc.exists("/Folder1/File1_renamed.txt"), "Renamed file should exist in local PC")
        self.assertTrue(self.localpc.exists("/Folder1/File1 - Copy.txt"), "Copied file should exist in local PC")
        self.assertFalse(self.localpc.exists("/Folder1/File1.txt"), "Original file should not exist in local PC")

        # Verify that local changes are uploaded to server successfully
        log.debug("Server: Verify sync successful")
        if self.server.exists("/Folder1/File1 - Copy.txt"):
            # '/Folder1/File1 - Copy.txt' is uploaded to server.
            # So original file named should be changed as 'File_renamed.txt'
            remote_info = self.server.get_info(self.file1_remote)
            self.assertEqual(remote_info.name, "File1_renamed.txt", "File should be renamed in Server after resume")
        else:
            # Original file is renamed as 'File1 - Copy.txt'. This is a bug only if Drive is online during copy+rename"
            self.assertTrue(self.server.exists("/Folder1/File1_renamed.txt"), "File1_renamed.txt should exists in server as a new file")
            remote_info = self.server.get_info(self.file1_remote)
            self.assertEqual(remote_info.name, "File1 - Copy.txt", 
                             "Original File should be renamed as (File1 - Copy.txt or File1_renamed.txt) in Server after resume")
        return
