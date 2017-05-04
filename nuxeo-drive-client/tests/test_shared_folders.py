# coding: utf-8
from nxdrive.client import LocalClient, RemoteDocumentClient
from tests.common_unit_test import UnitTestCase
from tests.common import TEST_WORKSPACE_PATH


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

    def test_local_changes_while_stopped(self):
        self._test_local_changes_while_not_running(False)

    def test_local_changes_while_unbinded(self):
        self._test_local_changes_while_not_running(True)

    def _test_local_changes_while_not_running(self, unbind):
        """ NXDRIVE-646: not uploading renamed file from shared folder. """
        local_1 = self.local_root_client_1
        remote_1 = self.remote_document_client_1
        remote_2 = self.remote_document_client_2

        # Unregister test workspace for user_1
        remote_1.unregister_as_root(self.workspace)

        # Remove ReadWrite permission for user_1 on the test workspace
        test_workspace = 'doc:' + TEST_WORKSPACE_PATH
        self.root_remote_client.execute('Document.SetACE',
                                        op_input=test_workspace,
                                        user=self.user_2,
                                        permission='ReadWrite',
                                        grant=True)

        # Create initial folders and files as user_2
        folder = remote_2.make_folder('/', 'Folder01')
        subfolder_1 = remote_2.make_folder(folder, 'SubFolder01')
        remote_2.make_file(subfolder_1, 'Image01.png',
                           self.generate_random_png())
        file_id = remote_2.make_file(folder, 'File01.txt', 'plaintext')

        # Grant Read permission for user_1 on the test folder and register
        self.root_remote_client.execute('Document.SetACE',
                                        op_input='doc:' + folder,
                                        user=self.user_1,
                                        permission='Read')
        remote_1.register_as_root(folder)

        # Start engine and wait for sync
        self.engine_1.start()
        self.wait_sync(wait_for_async=True)

        # First checks
        file_pair_state = self.engine_1.get_dao().get_state_from_local(
           '/Folder01/File01.txt')
        self.assertIsNotNone(file_pair_state)
        file_remote_ref = file_pair_state.remote_ref
        self.assertTrue(remote_2.exists('/Folder01'))
        self.assertTrue(remote_2.exists('/Folder01/File01.txt'))
        self.assertTrue(remote_2.exists('/Folder01/SubFolder01'))
        self.assertTrue(remote_2.exists('/Folder01/SubFolder01/Image01.png'))
        self.assertTrue(local_1.exists('/Folder01'))
        self.assertTrue(local_1.exists('/Folder01/File01.txt'))
        self.assertTrue(local_1.exists('/Folder01/SubFolder01'))
        self.assertTrue(local_1.exists('/Folder01/SubFolder01/Image01.png'))

        # Unbind or stop engine
        if unbind:
            self.send_unbind_engine(1)
            self.wait_unbind_engine(1)
        else:
            self.engine_1.stop()

        # Restore write permission to user_1 (=> ReadWrite)
        self.root_remote_client.execute('Document.SetACE',
                                        op_input='doc:' + folder,
                                        user=self.user_1,
                                        permission='ReadWrite')
        self.wait()

        # Make changes
        local_1.rename('/Folder01/File01.txt', 'File01_renamed.txt')
        local_1.delete('/Folder01/SubFolder01/Image01.png')

        # Bind or start engine and wait for sync
        if unbind:
            self.send_bind_engine(1)
            self.wait_bind_engine(1)
        else:
            self.engine_1.start()
        self.wait_sync()

        # Check client side
        self.assertTrue(local_1.exists('/Folder01'))
        if unbind:
            # File has been renamed and deleted image has been recreated
            self.assertFalse(local_1.exists('/Folder01/File01.txt'))
            self.assertTrue(local_1.exists('/Folder01/File01_renamed.txt'))
            self.assertTrue(local_1.exists('/Folder01/SubFolder01/Image01.png'))
        else:
            # File has been renamed and image deleted
            self.assertFalse(local_1.exists('/Folder01/File01.txt'))
            self.assertTrue(local_1.exists('/Folder01/File01_renamed.txt'))
            self.assertFalse(local_1.exists('/Folder01/SubFolder01/Image01.png'))

        # Check server side
        children = remote_2.get_children_info(folder)
        self.assertEquals(len(children), 2)
        file_info = remote_2.get_info(file_id)
        if unbind:
            # File has not been renamed and image has not been deleted
            self.assertEqual(file_info.name, 'File01.txt')
            self.assertTrue(remote_2.exists('/Folder01/SubFolder01/Image01.png'))
            # File is in conflict
            file_pair_state = self.engine_1.get_dao().get_normal_state_from_remote(file_remote_ref)
            self.assertEqual(file_pair_state.pair_state, 'conflicted')
        else:
            # File has been renamed and image deleted
            self.assertEqual(file_info.name, 'File01_renamed.txt')
            self.assertFalse(remote_2.exists('/Folder01/SubFolder01/Image01.png'))

    def test_conflict_resolution_with_renaming(self):
        """ NXDRIVE-645: shared Folders conflict resolution with renaming. """

        local_1 = self.local_client_1
        remote_2 = self.remote_document_client_2
        self.engine_1.start()
        self.wait_sync(wait_for_async=True)

        # Create initial folder and file
        folder = remote_2.make_folder('/', 'Final')
        remote_2.make_file('/Final', 'Aerial04.jpg', b'42')

        # First checks, everything should be online for every one
        self.wait_sync(wait_for_async=True)
        self.assertTrue(remote_2.exists('/Final'))
        self.assertTrue(remote_2.exists('/Final/Aerial04.jpg'))
        self.assertTrue(local_1.exists('/Final'))
        self.assertTrue(local_1.exists('/Final/Aerial04.jpg'))
        folder_pair_state = self.engine_1.get_dao().get_state_from_local(
            '/' + self.workspace_title + '/Final')
        self.assertIsNotNone(folder_pair_state)

        # Stop clients
        self.engine_1.stop()

        # Make changes
        folder_conflicted = local_1.make_folder('/', 'Finished')
        local_1.make_file(folder_conflicted, 'Aerial04.jpg', b'42.42')
        remote_2.update(folder, properties={'dc:title': 'Finished'})

        # Restart clients and wait
        self.engine_1.start()
        self.wait_sync(wait_for_async=True)

        # Check remote 2
        self.assertTrue(remote_2.exists('/Finished'))
        self.assertTrue(remote_2.exists('/Finished/Aerial04.jpg'))

        # Check client 1
        self.assertTrue(local_1.exists('/Finished'))
        self.assertTrue(local_1.exists('/Finished/Aerial04.jpg'))

        # Check folder status
        folder_pair_state = self.engine_1.get_dao().get_state_from_id(
            folder_pair_state.id)
        self.assertEqual(folder_pair_state.last_error, 'DEDUP')
