# coding: utf-8
import os
import sys
import time
from shutil import copyfile

from mock import Mock, patch

from nuxeo.utils import SwapAttr
from nxdrive.engine.engine import Engine
from .common import OS_STAT_MTIME_RESOLUTION, UnitTestCase


class TestRemoteDeletion(UnitTestCase):

    def test_synchronize_remote_deletion(self):
        """Test that deleting remote documents is impacted client side

        Use cases:
          - Remotely delete a regular folder
              => Folder should be locally deleted
          - Remotely restore folder from the trash
              => Folder should be locally re-created
          - Remotely delete a synchronization root
              => Synchronization root should be locally deleted
          - Remotely restore synchronization root from the trash
              => Synchronization root should be locally re-created

        See TestIntegrationSecurityUpdates.test_synchronize_denying_read_access
        as the same uses cases are tested
        """
        # Bind the server and root workspace
        self.engine_1.start()
        # Get local and remote clients
        local = self.local_1
        remote = self.remote_document_client_1
        remote_admin = self.root_remote

        # Create documents in the remote root workspace
        # then synchronize
        folder_id = remote.make_folder('/', 'Test folder')
        file_id = remote.make_file('/Test folder', 'joe.txt', 'Some content')

        self.wait_sync(wait_for_async=True)
        assert local.exists('/Test folder')
        assert local.exists('/Test folder/joe.txt')

        # Delete remote folder then synchronize
        remote.delete('/Test folder')
        self.wait_sync(wait_for_async=True)
        assert not local.exists('/Test folder')

        # Restore folder from trash then synchronize
        remote.undelete(folder_id)
        remote.undelete(file_id)
        self.wait_sync(wait_for_async=True)
        assert local.exists('/Test folder')
        assert local.exists('/Test folder/joe.txt')

        # Delete sync root then synchronize
        remote_admin.delete(self.workspace)
        self.wait_sync(wait_for_async=True)
        assert not local.exists('/')

        # Restore sync root from trash then synchronize
        remote_admin.undelete(self.workspace)
        remote_admin.undelete(folder_id)
        remote_admin.undelete(file_id)
        self.wait_sync(wait_for_async=True)
        assert local.exists('/')
        assert local.exists('/Test folder')
        assert local.exists('/Test folder/joe.txt')

    def _remote_deletion_while_upload(self):
        local = self.local_1
        remote = self.remote_document_client_1
        self.engine_1.start()

        def _suspend_check(*_):
            """ Add delay when upload and download. """
            time.sleep(1)
            Engine.suspend_client(self.engine_1)

        self.engine_1.remote.check_suspended = _suspend_check
        self.engine_1.invalidate_client_cache()

        # Create documents in the remote root workspace
        remote.make_folder('/', 'Test folder')
        self.wait_sync(wait_for_async=True)

        # Create a document by streaming a binary file
        file_path = os.path.join(
            local.abspath('/Test folder'), 'testFile.pdf')
        copyfile(self.location + '/resources/testFile.pdf', file_path)
        file_path = os.path.join(
            local.abspath('/Test folder'), 'testFile2.pdf')
        copyfile(self.location + '/resources/testFile.pdf', file_path)

        # Delete remote folder then synchronize
        remote.delete('/Test folder')
        self.wait_sync(wait_for_async=True)
        assert not local.exists('/Test folder')

    def test_synchronize_remote_deletion_while_upload(self):
        if sys.platform == 'win32':
            self._remote_deletion_while_upload()
        else:
            with patch('nxdrive.client.remote_client.os.fstatvfs') as mock_os:
                mock_os.return_value = Mock()
                mock_os.return_value.f_bsize = 4096
                self._remote_deletion_while_upload()

    def _remote_deletion_while_download_file(self):
        local = self.local_1
        remote = self.remote_document_client_1

        def _suspend_check(*_):
            """ Add delay when upload and download. """
            if not self.engine_1.has_delete:
                # Delete remote file while downloading
                try:
                    remote.delete('/Test folder/testFile.pdf')
                except:
                    pass
                else:
                    self.engine_1.has_delete = True
            time.sleep(1)
            self.engine_1.suspend_client()

        self.engine_1.start()
        self.engine_1.has_delete = False

        with SwapAttr(self.engine_1.remote, 'check_suspended', _suspend_check):
            # Create documents in the remote root workspace
            remote.make_folder('/', 'Test folder')
            with open(self.location + '/resources/testFile.pdf', 'rb') as pdf:
                remote.make_file('/Test folder', 'testFile.pdf', pdf.read())

            self.wait_sync(wait_for_async=True)
            assert not local.exists('/Test folder/testFile.pdf')

    def test_synchronize_remote_deletion_while_download_file(self):
        if sys.platform == 'win32':
            self._remote_deletion_while_download_file()
        else:
            with patch('os.path.isdir', return_value=False) as mock_os:
                mock_os.return_value = Mock()
                mock_os.return_value.f_bsize = 4096
                self._remote_deletion_while_download_file()

    def test_synchronize_remote_deletion_with_close_name(self):
        self.engine_1.start()
        local = self.local_1
        remote = self.remote_document_client_1
        remote.make_folder('/', 'Folder 1')
        remote.make_folder('/', 'Folder 1b')
        remote.make_folder('/', 'Folder 1c')
        self.wait_sync()
        assert local.exists('/Folder 1')
        assert local.exists('/Folder 1b')
        assert local.exists('/Folder 1c')
        remote.delete('/Folder 1')
        remote.delete('/Folder 1b')
        remote.delete('/Folder 1c')
        self.wait_sync()
        assert not local.exists('/Folder 1')
        assert not local.exists('/Folder 1b')
        assert not local.exists('/Folder 1c')

    def test_synchronize_local_folder_lost_permission(self):
        """Test local folder rename followed by remote deletion"""
        # Bind the server and root workspace

        # Get local and remote clients
        self.engine_2.start()
        local = self.local_2
        remote = self.remote_document_client_2

        # Create a folder with a child file in the remote root workspace
        # then synchronize
        test_folder_uid = remote.make_folder('/', 'Test folder')
        remote.make_file(test_folder_uid, 'joe.odt', 'Some content')

        self.wait_sync(wait_for_async=True, wait_for_engine_1=False,
                       wait_for_engine_2=True)
        assert local.exists('/Test folder')
        assert local.exists('/Test folder/joe.odt')
        input_obj = 'doc:' + self.workspace
        self.root_remote.operations.execute(
            command='Document.RemoveACL', input_obj=input_obj, acl='local')
        self.wait_sync(wait_for_async=True, wait_for_engine_1=False,
                       wait_for_engine_2=True)
        assert not local.exists('/Test folder')

    def test_synchronize_local_folder_rename_remote_deletion(self):
        """Test local folder rename followed by remote deletion"""
        # Bind the server and root workspace

        # Get local and remote clients
        self.engine_1.start()
        local = self.local_1
        remote = self.remote_document_client_1

        # Create a folder with a child file in the remote root workspace
        # then synchronize
        test_folder_uid = remote.make_folder('/', 'Test folder')
        remote.make_file(test_folder_uid, 'joe.odt', 'Some content')

        self.wait_sync(wait_for_async=True)
        assert local.exists('/Test folder')
        assert local.exists('/Test folder/joe.odt')

        # Locally rename the folder then synchronize
        time.sleep(OS_STAT_MTIME_RESOLUTION)
        local.rename('/Test folder', 'Test folder renamed')

        self.wait_sync()
        assert not local.exists('/Test folder')
        assert local.exists('/Test folder renamed')
        assert remote.get_info(test_folder_uid).name == 'Test folder renamed'

        # Delete remote folder then synchronize
        remote.delete('/Test folder')

        self.wait_sync(wait_for_async=True)
        assert not remote.exists('/Test folder renamed')
        assert not local.exists('/Test folder renamed')

    def _check_pair_state(self, _, local_path, pair_state):
        local_path = '/' + self.workspace_title + local_path
        doc_pair = self.engine_1.get_dao().get_state_from_local(local_path)
        assert doc_pair.pair_state == pair_state
