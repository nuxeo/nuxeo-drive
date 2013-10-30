import time

from nxdrive.tests.common import IntegrationTestCase
from nxdrive.client import LocalClient
from nxdrive.client import RemoteDocumentClient


class TestIntegrationPermissionHierarchy(IntegrationTestCase):

    def test_sync_delete_root(self):

        # Bind server
        ctl = self.controller_1
        ctl.bind_server(self.local_nxdrive_folder_1, self.nuxeo_url,
                        self.user_1, self.password_1)
        syn = ctl.synchronizer

        # Get remote and local clients
        admin_remote_client = self.root_remote_client
        user_remote_client = RemoteDocumentClient(
            self.nuxeo_url, self.user_1, u'nxdrive-test-device-1',
            self.version, password=self.password_1,
            upload_tmp_dir=self.upload_tmp_dir)
        local_client = LocalClient(self.local_nxdrive_folder_1)

        # Activate permission hierarchy profile as Administrator
        admin_remote_client.activate_profile('permission')

        # Create test user workspace as Administrator
        user_workspaces_path = '/default-domain/UserWorkspaces/'
        user_workspace_title = 'nuxeoDriveTestUser_user_1'
        admin_remote_client.make_folder(user_workspaces_path,
                                       user_workspace_title,
                                       doc_type='Workspace')
        user_workspace_path = user_workspaces_path + user_workspace_title
        # Grant ReadWrite permission to test user on its workspace
        op_input = "doc:" + user_workspace_path
        admin_remote_client.execute("Document.SetACE",
            op_input=op_input,
            user="nuxeoDriveTestUser_user_1",
            permission="ReadWrite",
            grant="true")

        # Create test folder in user workspace as test user
        user_remote_client.make_folder(user_workspace_path, 'test_folder')
        test_folder_path = user_workspace_path + '/test_folder'
        # Create a document in the test folder
        user_remote_client.make_file(test_folder_path, 'test_file.txt',
                                    "Some content.")

        # Register test folder as a sync root
        user_remote_client.register_as_root(test_folder_path)

        # Synchronize
        self._synchronize(syn)

        # Check locally synchronized content
        self.assertTrue(local_client.exists('/My Docs/test_folder'))
        self.assertTrue(local_client.exists(
                                        '/My Docs/test_folder/test_file.txt'))

        # Delete test folder
        user_remote_client.delete(test_folder_path)

        # Synchronize
        self._synchronize(syn)

        # Check locally synchronized content
        self.assertFalse(local_client.exists('/My Docs/test_folder'))
        self.assertEquals(len(local_client.get_children_info('/My Docs')), 0)

        # Cleanup
        admin_remote_client.delete(user_workspace_path, use_trash=False)

    def _synchronize(self, synchronizer):
        time.sleep(self.AUDIT_CHANGE_FINDER_TIME_RESOLUTION)
        self.wait()
        synchronizer.loop(delay=0.1, max_loops=1)
