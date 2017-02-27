from tests.common_unit_test import UnitTestCase
from nxdrive.client import RemoteDocumentClient
from nxdrive.client import LocalClient


class TestSharedFolders(UnitTestCase):

    def test_move_sync_root_child_to_user_workspace(self):
        """See https://jira.nuxeo.com/browse/NXP-14870"""
        admin_remote_client = self.root_remote_client
        user1_workspace_uid = None
        try:
            # Get remote  and local clients
            remote_user1 = RemoteDocumentClient(
                self.nuxeo_url, self.user_1, u'nxdrive-test-device-1',
                self.version, password=self.password_1,
                upload_tmp_dir=self.upload_tmp_dir)
            remote_user2 = RemoteDocumentClient(
                self.nuxeo_url, self.user_2, u'nxdrive-test-device-2',
                self.version, password=self.password_2,
                upload_tmp_dir=self.upload_tmp_dir)
            local_user2 = LocalClient(self.local_nxdrive_folder_2)

            # Make sure personal workspace is created for user1 and fetch its uid
            user1_workspace_uid = remote_user1.make_file_in_user_workspace('File in user workspace',
                                                                           filename='UWFile.txt')['parentRef']

            # As user1 register personal workspace as a sync root
            remote_user1.register_as_root(user1_workspace_uid)

            # As user1 create a parent folder in user1's personal workspace
            parent_folder_uid = remote_user1.make_folder(user1_workspace_uid, 'Parent')

            # As user1 grant Everything permission to user2 on parent folder
            op_input = "doc:" + parent_folder_uid
            admin_remote_client.execute("Document.SetACE", op_input=op_input, user=self.user_2,
                                        permission="Everything", grant="true")

            # As user1 create a child folder in parent folder
            child_folder_uid = remote_user1.make_folder(parent_folder_uid, 'Child')

            # As user2 register parent folder as a sync root
            remote_user2.register_as_root(parent_folder_uid)
            remote_user2.unregister_as_root(self.workspace)
            # Start engine for user2
            self.engine_2.start()

            # Wait for synchronization
            self.wait_sync(wait_for_async=True, wait_for_engine_1=False, wait_for_engine_2=True)

            # Check locally synchronized content
            self.assertEqual(len(local_user2.get_children_info('/')), 1)
            self.assertTrue(local_user2.exists('/Parent'))
            self.assertTrue(local_user2.exists('/Parent/Child'))

            # As user1 move child folder to user1's personal workspace
            remote_user1.move(child_folder_uid, user1_workspace_uid)

            # Wait for synchronization
            self.wait_sync(wait_for_async=True, wait_for_engine_1=False, wait_for_engine_2=True)

            # Check locally synchronized content
            self.assertFalse(local_user2.exists('/Parent/Child'))

        finally:
            # Cleanup user1 personal workspace
            if user1_workspace_uid is not None and admin_remote_client.exists(user1_workspace_uid):
                admin_remote_client.delete(user1_workspace_uid,
                                           use_trash=False)
