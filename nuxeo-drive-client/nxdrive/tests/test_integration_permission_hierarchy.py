import time
from urllib2 import HTTPError

from nxdrive.tests.common import IntegrationTestCase
from nxdrive.client import LocalClient
from nxdrive.client import RemoteDocumentClient
from nxdrive.client import RestAPIClient
from nxdrive.logging_config import get_logger

log = get_logger(__name__)


class TestIntegrationPermissionHierarchy(IntegrationTestCase):

    def test_sync_delete_root(self):
        try:
            user_workspaces_path = '/default-domain/UserWorkspaces/'
            user_workspace_title = 'nuxeoDriveTestUser_user_1'
            user_workspace_path = user_workspaces_path + user_workspace_title

            # Get remote and local clients
            admin_remote_client = self.root_remote_client
            user_remote_client = RemoteDocumentClient(
                self.nuxeo_url, self.user_1, u'nxdrive-test-device-1',
                self.version, password=self.password_1,
                upload_tmp_dir=self.upload_tmp_dir)
            local_client = LocalClient(self.local_nxdrive_folder_1)

            # Activate permission hierarchy profile as Administrator
            admin_remote_client.activate_profile('permission')

            # Bind server
            ctl = self.controller_1
            ctl.bind_server(self.local_nxdrive_folder_1, self.nuxeo_url,
                            self.user_1, self.password_1)
            syn = ctl.synchronizer

            # Create user workspace parent as Administrator if it doesn't exist
            if not admin_remote_client.exists(user_workspaces_path):
                admin_remote_client.make_folder('/default-domain',
                                                'UserWorkspaces',
                                                doc_type='UserWorkspacesRoot')

            # Create test user workspace as Administrator
            admin_remote_client.make_folder(user_workspaces_path,
                                           user_workspace_title,
                                           doc_type='Workspace')
            # Grant ReadWrite permission to test user on its workspace
            op_input = "doc:" + user_workspace_path
            admin_remote_client.execute("Document.SetACE",
                op_input=op_input,
                user="nuxeoDriveTestUser_user_1",
                permission="ReadWrite",
                grant="true")

            # Create test folder in user workspace as test user
            # NXP-14325: Let's try to understand this random failure
            nb_tries = 10
            cpt = 0
            delay = 1.0
            success = False
            rest_api_client = RestAPIClient(self.nuxeo_url, self.admin_user,
                u'nxdrive-test-administrator-device', self.version,
                password=self.password)
            while (cpt < nb_tries and not success):
                log.debug("Try to make remote folder: #%d", cpt)
                try:
                    user_remote_client.make_folder(user_workspace_path,
                                                   'test_folder')
                    success = True
                except HTTPError as e:
                    log.error(e)
                    acls = rest_api_client.execute(user_workspace_path,
                                                  adapter='acl')
                    log.debug("ACL of %s: %r", user_workspace_path, acls)
                    cpt += 1
                    if cpt < nb_tries:
                        log.debug("Waiting for %.0f seconds and retrying",
                                  delay)
                        time.sleep(delay)
            if cpt == nb_tries:
                log.error("ACL still bad after %d tries..., failing", nb_tries)
                assert False
            else:
                log.debug("ACL finally good after %d tries!", cpt)
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
            self.assertEquals(len(local_client.get_children_info('/My Docs')),
                              0)
        finally:
            # Cleanup user workspace
            if admin_remote_client.exists(user_workspace_path):
                admin_remote_client.delete(user_workspace_path,
                                           use_trash=False)
            # Deactivate permission hierarchy profile
            admin_remote_client.deactivate_profile('permission')

    def test_sync_delete_shared_folder(self):
        user_workspaces_path = '/default-domain/UserWorkspaces/'
        user1_workspace_title = 'nuxeoDriveTestUser-user-1'
        user1_workspace_path = user_workspaces_path + user1_workspace_title
        try:
            # Get remote and local clients
            admin_remote_client = self.root_remote_client
            user1_remote_client = RemoteDocumentClient(
                self.nuxeo_url, self.user_1, u'nxdrive-test-device-1',
                self.version, password=self.password_1,
                upload_tmp_dir=self.upload_tmp_dir)
            user2_remote_client = RemoteDocumentClient(
                self.nuxeo_url, self.user_2, u'nxdrive-test-device-2',
                self.version, password=self.password_2,
                upload_tmp_dir=self.upload_tmp_dir)
            local_client_1 = LocalClient(self.local_nxdrive_folder_1)

            # Activate permission hierarchy profile as Administrator
            admin_remote_client.activate_profile('permission')

            # Make sure user1 workspace is created
            user1_remote_client.make_file_in_user_workspace(
                                                    'File in user workspace',
                                                    filename='USFile.txt')

            # Register user workspace as a sync root for user1
            user1_remote_client.register_as_root(user1_workspace_path)

            # Bind server for user1
            ctl_1 = self.controller_1
            ctl_1.bind_server(self.local_nxdrive_folder_1, self.nuxeo_url,
                            self.user_1, self.password_1)
            syn_1 = ctl_1.synchronizer

            # Synchronize
            self._synchronize(syn_1)
            # Check locally synchronized content
            self.assertTrue(local_client_1.exists('/My Docs'))

            # Create test folder in user workspace as user1
            user1_remote_client.make_folder(user1_workspace_path,
                                            'test_folder')
            # Synchronize
            self._synchronize(syn_1)
            # Check locally synchronized content
            self.assertTrue(local_client_1.exists('/My Docs/test_folder'))

            # Grant ReadWrite permission to user2 on test folder
            test_folder_path = user1_workspace_path + '/test_folder'
            op_input = "doc:" + test_folder_path
            admin_remote_client.execute("Document.SetACE",
                op_input=op_input,
                user="nuxeoDriveTestUser_user_2",
                permission="ReadWrite",
                grant="true")

            # Register test folder as a sync root for user2
            user2_remote_client.register_as_root(test_folder_path)

            # Wait for a while:
            time.sleep(2.0)

            # Delete test folder
            user1_remote_client.delete(test_folder_path)

            # Synchronize
            self._synchronize(syn_1)
            # Check locally synchronized content
            self.assertFalse(local_client_1.exists('/My Docs/test_folder'))
            self.assertEquals(len(local_client_1.get_children_info(
                                                            '/My Docs')), 1)
        finally:
            # Cleanup user workspace
            if admin_remote_client.exists(user1_workspace_path):
                admin_remote_client.delete(user1_workspace_path,
                                           use_trash=False)
            # Deactivate permission hierarchy profile
            admin_remote_client.deactivate_profile('permission')

    def _synchronize(self, synchronizer):
        time.sleep(self.AUDIT_CHANGE_FINDER_TIME_RESOLUTION)
        self.wait()
        synchronizer.loop(delay=0.1, max_loops=1)
