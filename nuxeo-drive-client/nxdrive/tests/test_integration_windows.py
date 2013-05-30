import os
import time

from nxdrive.tests.common import IntegrationTestCase
from nxdrive.client import LocalClient
from shutil import copyfile


class TestIntegrationWindows(IntegrationTestCase):

    def test_local_replace(self):
        # Bind the server and root workspace
        ctl = self.controller_1
        ctl.bind_server(self.local_nxdrive_folder_1, self.nuxeo_url,
                        self.user_1, self.password_1)
        ctl.bind_root(self.local_nxdrive_folder_1, self.workspace)

        # Launch first synchronization
        time.sleep(self.AUDIT_CHANGE_FINDER_TIME_RESOLUTION)
        self.wait()
        syn = ctl.synchronizer
        syn.loop(delay=0.1, max_loops=1)

        # Get local and remote clients
        local = LocalClient(self.local_test_folder_1)
        remote = self.remote_document_client_1

        # Create 2 files with the same name but different content
        # in separate folders
        local.make_file('/', 'test.odt', 'Some content.')
        local.make_folder('/', 'folder')
        copyfile(os.path.join(self.local_test_folder_1, 'test.odt'),
                 os.path.join(self.local_test_folder_1, 'folder', 'test.odt'))
        local.update_content('/folder/test.odt', 'Updated content.')

        # Copy the newest file to the root workspace and synchronize it
        sync_root = os.path.join(self.local_nxdrive_folder_1,
                                 self.workspace_title)
        copyfile(os.path.join(self.local_test_folder_1, 'folder', 'test.odt'),
                 os.path.join(sync_root, 'test.odt'))
        syn.loop(delay=0.1, max_loops=1)
        self.assertTrue(remote.exists('/test.odt'))
        self.assertEquals(remote.get_content('/test.odt'), 'Updated content.')

        # Copy the oldest file to the root workspace and synchronize it
        copyfile(os.path.join(self.local_test_folder_1, 'test.odt'),
                 os.path.join(sync_root, 'test.odt'))
        syn.loop(delay=0.1, max_loops=1)
        self.assertTrue(remote.exists('/test.odt'))
        self.assertEquals(remote.get_content('/test.odt'), 'Some content.')
