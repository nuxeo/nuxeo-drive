import os
import time

from nxdrive.tests.common import IntegrationTestCase
from nxdrive.client import LocalClient
from nxdrive.client import RemoteDocumentClient
from nxdrive.model import LastKnownState
from nxdrive.client.common import NotFound


class TestIntegrationLocalMoveAndRename(IntegrationTestCase):

    def setUp(self):
        super(TestIntegrationLocalMoveAndRename, self).setUp()

        self.sb_1 = self.controller_1.bind_server(
            self.local_nxdrive_folder_1,
            self.nuxeo_url, self.user_1, self.password_1)

        self.controller_1.bind_root(self.local_nxdrive_folder_1,
            self.workspace)

        self.controller_1.synchronizer.update_synchronize_server(self.sb_1)

        self.sync_root_folder_1 = os.path.join(self.local_nxdrive_folder_1,
                                       self.workspace_title)
        self.local_client_1 = LocalClient(self.sync_root_folder_1)

        self.local_client_1.make_file('/', u'Original File 1.txt',
            content=u'Some Content 1'.encode('utf-8'))

        self.local_client_1.make_file('/', u'Original File 2.txt',
            content=u'Some Content 2'.encode('utf-8'))

        self.local_client_1.make_folder(u'/', u'Original Folder 1')
        self.local_client_1.make_folder(
            u'/Original Folder 1', u'Sub-Folder 1.1')
        self.local_client_1.make_folder(
            u'/Original Folder 1', u'Sub-Folder 1.2')
        self.local_client_1.make_file(u'/Original Folder 1',
            u'Original File 1.1.txt',
            content=u'Some Content 1'.encode('utf-8'))  # Same content as OF1

        self.local_client_1.make_folder('/', 'Original Folder 2')
        self.local_client_1.make_file('/Original Folder 2',
            u'Original File 3.txt',
            content=u'Some Content 3'.encode('utf-8'))

        self.controller_1.synchronizer.update_synchronize_server(self.sb_1)

    def test_local_rename_file(self):
        sb, ctl = self.sb_1, self.controller_1
        local_client = self.local_client_1
        remote_client = self.remote_document_client_1

        # Rename /Original File 1.txt to /Renamed File 1.txt
        original_file_1_uid = remote_client.get_info(
            u'/Original File 1.txt').uid
        local_client.rename(u'/Original File 1.txt', u'Renamed File 1.txt')
        self.assertFalse(local_client.exists(u'/Original File 1.txt'))
        self.assertTrue(local_client.exists(u'/Renamed File 1.txt'))

        self.assertEquals(ctl.synchronizer.update_synchronize_server(sb), 1)
        self.assertFalse(local_client.exists(u'/Original File 1.txt'))
        self.assertTrue(local_client.exists(u'/Renamed File 1.txt'))
        original_file_1_remote_info = remote_client.get_info(
            original_file_1_uid)
        self.assertEquals(original_file_1_remote_info.name,
            u'Renamed File 1.txt')

        # Rename 'Renamed File 1.txt' to 'Renamed Again File 1.txt'
        # and 'Original File 1.1.txt' to
        # 'Renamed File 1.1.txt' at the same time as they share
        # the same digest but do not live in the same folder
        original_1_1_uid = remote_client.get_info(
            u'/Original Folder 1/Original File 1.1.txt').uid
        local_client.rename(
            u'/Original Folder 1/Original File 1.1.txt',
            u'Renamed File 1.1 \xe9.txt')
        self.assertFalse(local_client.exists(
             '/Original Folder 1/Original File 1.1.txt'))
        self.assertTrue(local_client.exists(
            u'/Original Folder 1/Renamed File 1.1 \xe9.txt'))
        local_client.rename('/Renamed File 1.txt', 'Renamed Again File 1.txt')
        self.assertFalse(local_client.exists(u'/Renamed File 1.txt'))
        self.assertTrue(local_client.exists(u'/Renamed Again File 1.txt'))

        self.assertEquals(ctl.synchronizer.update_synchronize_server(sb), 2)
        self.assertFalse(local_client.exists(u'/Renamed File 1.txt'))
        self.assertTrue(local_client.exists(u'/Renamed Again File 1.txt'))
        self.assertFalse(local_client.exists(
             u'/Original Folder 1/Original File 1.1.txt'))
        self.assertTrue(local_client.exists(
            u'/Original Folder 1/Renamed File 1.1 \xe9.txt'))

        file_1_remote_info = remote_client.get_info(original_file_1_uid)
        self.assertEquals(file_1_remote_info.name,
            u'Renamed Again File 1.txt')

        # User 1 does not have the rights to see the parent container
        # of the test workspace, hence set fetch_parent_uid=False
        parent_of_file_1_remote_info = remote_client.get_info(
            file_1_remote_info.parent_uid, fetch_parent_uid=False)
        self.assertEquals(parent_of_file_1_remote_info.name,
            self.workspace_title)

        file_1_1_remote_info = remote_client.get_info(original_1_1_uid)
        self.assertEquals(file_1_1_remote_info.name,
            u'Renamed File 1.1 \xe9.txt')

        parent_of_file_1_1_remote_info = remote_client.get_info(
            file_1_1_remote_info.parent_uid)
        self.assertEquals(parent_of_file_1_1_remote_info.name,
            u'Original Folder 1')

    def test_local_move_file(self):
        sb, ctl = self.sb_1, self.controller_1
        local_client = self.local_client_1
        remote_client = self.remote_document_client_1

        # Rename /Original File 1.txt to /Renamed File 1.txt
        original_file_1_uid = remote_client.get_info(
            u'/Original File 1.txt').uid
        local_client.move(u'/Original File 1.txt', u'/Original Folder 1')
        self.assertFalse(local_client.exists(u'/Original File 1.txt'))
        self.assertTrue(local_client.exists(
            u'/Original Folder 1/Original File 1.txt'))

        self.assertEquals(ctl.synchronizer.update_synchronize_server(sb), 1)
        self.assertFalse(local_client.exists(u'/Original File 1.txt'))
        self.assertTrue(local_client.exists(
            u'/Original Folder 1/Original File 1.txt'))

        file_1_remote_info = remote_client.get_info(original_file_1_uid)
        self.assertEquals(file_1_remote_info.name, u'Original File 1.txt')
        parent_of_file_1_remote_info = remote_client.get_info(
            file_1_remote_info.parent_uid)
        self.assertEquals(parent_of_file_1_remote_info.name,
            u'Original Folder 1')

    def test_local_move_and_rename_file(self):
        sb, ctl = self.sb_1, self.controller_1
        local_client = self.local_client_1
        remote_client = self.remote_document_client_1

        # Rename /Original File 1.txt to /Renamed File 1.txt
        original_file_1_uid = remote_client.get_info(
            u'/Original File 1.txt').uid

        local_client.rename(u'/Original File 1.txt',
                            u'Renamed File 1 \xe9.txt')
        local_client.move(u'/Renamed File 1 \xe9.txt', u'/Original Folder 1')
        self.assertFalse(local_client.exists(u'/Original File 1.txt'))
        self.assertTrue(local_client.exists(
            u'/Original Folder 1/Renamed File 1 \xe9.txt'))

        self.assertEquals(ctl.synchronizer.update_synchronize_server(sb), 1)
        self.assertFalse(local_client.exists(u'/Original File 1.txt'))
        self.assertTrue(local_client.exists(
            u'/Original Folder 1/Renamed File 1 \xe9.txt'))

        file_1_remote_info = remote_client.get_info(original_file_1_uid)
        self.assertEquals(file_1_remote_info.name, u'Renamed File 1 \xe9.txt')
        parent_of_file_1_remote_info = remote_client.get_info(
            file_1_remote_info.parent_uid)
        self.assertEquals(parent_of_file_1_remote_info.name,
            u'Original Folder 1')

        # Nothing left to do
        time.sleep(self.AUDIT_CHANGE_FINDER_TIME_RESOLUTION)
        self.wait()
        self.assertEquals(ctl.synchronizer.update_synchronize_server(sb), 0)

    def test_local_rename_folder(self):
        sb, ctl = self.sb_1, self.controller_1
        local_client = self.local_client_1
        remote_client = self.remote_document_client_1

        # Save the uid of some files and folders prior to renaming
        original_folder_1_uid = remote_client.get_info(
            u'/Original Folder 1').uid
        original_file_1_1_uid = remote_client.get_info(
            u'/Original Folder 1/Original File 1.1.txt').uid
        original_sub_folder_1_1_uid = remote_client.get_info(
            u'/Original Folder 1/Sub-Folder 1.1').uid

        # Rename a non empty folder with some content
        local_client.rename(u'/Original Folder 1', u'Renamed Folder 1 \xe9')
        self.assertFalse(local_client.exists(u'/Original Folder 1'))
        self.assertTrue(local_client.exists(u'/Renamed Folder 1 \xe9'))

        # Synchronize: only the folder renaming is detected: all
        # the descendants are automatically realigned
        self.assertEquals(ctl.synchronizer.update_synchronize_server(sb), 1)

        # The server folder has been renamed: the uid stays the same
        new_remote_name = remote_client.get_info(original_folder_1_uid).name
        self.assertEquals(new_remote_name, u"Renamed Folder 1 \xe9")

        # The content of the renamed folder is left unchanged
        file_1_1_info = remote_client.get_info(original_file_1_1_uid)
        self.assertEquals(file_1_1_info.name, u"Original File 1.1.txt")
        self.assertEquals(file_1_1_info.parent_uid, original_folder_1_uid)

        sub_folder_1_1_info = remote_client.get_info(
            original_sub_folder_1_1_uid)
        self.assertEquals(sub_folder_1_1_info.name, u"Sub-Folder 1.1")
        self.assertEquals(sub_folder_1_1_info.parent_uid,
            original_folder_1_uid)

        # The more things change, the more they remain the same.
        time.sleep(self.AUDIT_CHANGE_FINDER_TIME_RESOLUTION)
        self.wait()
        self.assertEquals(ctl.synchronizer.update_synchronize_server(sb), 0)

    def test_local_move_folder(self):
        sb, ctl = self.sb_1, self.controller_1
        local_client = self.local_client_1
        remote_client = self.remote_document_client_1

        # Save the uid of some files and folders prior to move
        original_folder_1_uid = remote_client.get_info(
            u'/Original Folder 1').uid
        original_folder_2_uid = remote_client.get_info(
            u'/Original Folder 2').uid
        original_file_1_1_uid = remote_client.get_info(
            u'/Original Folder 1/Original File 1.1.txt').uid
        original_sub_folder_1_1_uid = remote_client.get_info(
            u'/Original Folder 1/Sub-Folder 1.1').uid

        # Move a non empty folder with some content
        local_client.move(u'/Original Folder 1', u'/Original Folder 2')
        self.assertFalse(local_client.exists(u'/Original Folder 1'))
        self.assertTrue(local_client.exists(
            u'/Original Folder 2/Original Folder 1'))

        # Synchronize: only the folder move is detected: all
        # the descendants are automatically realigned
        self.assertEquals(ctl.synchronizer.update_synchronize_server(sb), 1)

        # The server folder has been moved: the uid stays the same
        remote_folder_info = remote_client.get_info(original_folder_1_uid)

        # The parent folder is not folder 2
        self.assertEquals(remote_folder_info.parent_uid,
            original_folder_2_uid)

        # The content of the renamed folder is left unchanged
        file_1_1_info = remote_client.get_info(original_file_1_1_uid)
        self.assertEquals(file_1_1_info.name, u"Original File 1.1.txt")
        self.assertEquals(file_1_1_info.parent_uid, original_folder_1_uid)

        sub_folder_1_1_info = remote_client.get_info(
            original_sub_folder_1_1_uid)
        self.assertEquals(sub_folder_1_1_info.name, u"Sub-Folder 1.1")
        self.assertEquals(sub_folder_1_1_info.parent_uid,
            original_folder_1_uid)

        # The more things change, the more they remain the same.
        time.sleep(self.AUDIT_CHANGE_FINDER_TIME_RESOLUTION)
        self.wait()
        self.assertEquals(ctl.synchronizer.update_synchronize_server(sb), 0)

    def test_concurrent_local_rename_folder(self):
        sb, ctl = self.sb_1, self.controller_1
        local_client = self.local_client_1
        remote_client = self.remote_document_client_1

        # Save the uid of some files and folders prior to renaming
        folder_1_uid = remote_client.get_info(u'/Original Folder 1').uid
        file_1_1_uid = remote_client.get_info(
            u'/Original Folder 1/Original File 1.1.txt').uid
        folder_2_uid = remote_client.get_info(u'/Original Folder 2').uid
        file_3_uid = remote_client.get_info(
            u'/Original Folder 2/Original File 3.txt').uid

        # Rename a non empty folders concurrently
        local_client.rename(u'/Original Folder 1', u'Renamed Folder 1')
        local_client.rename(u'/Original Folder 2', u'Renamed Folder 2')
        self.assertFalse(local_client.exists(u'/Original Folder 1'))
        self.assertTrue(local_client.exists(u'/Renamed Folder 1'))
        self.assertFalse(local_client.exists(u'/Original Folder 2'))
        self.assertTrue(local_client.exists(u'/Renamed Folder 2'))

        # Synchronize: only the folder renamings are detected: all
        # the descendants are automatically realigned
        self.assertEquals(ctl.synchronizer.update_synchronize_server(sb), 2)

        # The server folders have been renamed: the uid stays the same
        folder_1_info = remote_client.get_info(folder_1_uid)
        self.assertEquals(folder_1_info.name, u"Renamed Folder 1")

        folder_2_info = remote_client.get_info(folder_2_uid)
        self.assertEquals(folder_2_info.name, u"Renamed Folder 2")

        # The content of the folder has been left unchanged
        file_1_1_info = remote_client.get_info(file_1_1_uid)
        self.assertEquals(file_1_1_info.name, u"Original File 1.1.txt")
        self.assertEquals(file_1_1_info.parent_uid, folder_1_uid)

        file_3_info = remote_client.get_info(file_3_uid)
        self.assertEquals(file_3_info.name, u"Original File 3.txt")
        self.assertEquals(file_3_info.parent_uid, folder_2_uid)

        # The more things change, the more they remain the same.
        time.sleep(self.AUDIT_CHANGE_FINDER_TIME_RESOLUTION)
        self.wait()
        self.assertEquals(ctl.synchronizer.update_synchronize_server(sb), 0)

    def test_local_rename_sync_root_folder(self):
        sb, ctl = self.sb_1, self.controller_1
        # Use the Administrator to be able to introspect the container of the
        # test workspace.
        remote_client = RemoteDocumentClient(
            self.nuxeo_url, self.admin_user,
            'nxdrive-test-administrator-device',
            self.password, base_folder=self.workspace)

        folder_1_uid = remote_client.get_info(u'/Original Folder 1').uid

        # Create new clients to be able to introspect the test sync root
        toplevel_local_client = LocalClient(self.local_nxdrive_folder_1)

        toplevel_local_client.rename('/' + self.workspace_title,
            'Renamed Nuxeo Drive Test Workspace')
        self.assertEquals(ctl.synchronizer.update_synchronize_server(sb), 1)

        workspace_info = remote_client.get_info(self.workspace)
        self.assertEquals(workspace_info.name,
            u"Renamed Nuxeo Drive Test Workspace")

        folder_1_info = remote_client.get_info(folder_1_uid)
        self.assertEquals(folder_1_info.name, u"Original Folder 1")
        self.assertEquals(folder_1_info.parent_uid, self.workspace)

    def test_local_rename_top_level_folder(self):
        sb, ctl = self.sb_1, self.controller_1
        local_client = LocalClient(self.local_test_folder_1)
        session = ctl.get_session()

        # Check top level folder
        self.assertTrue(local_client.exists(u'/Nuxeo Drive'))
        top_level_folder_info = local_client.get_info(u'/Nuxeo Drive')
        self.assertEquals(top_level_folder_info.name, u'Nuxeo Drive')
        self.assertEquals(top_level_folder_info.filepath,
            os.path.join(self.local_test_folder_1, u'Nuxeo Drive'))
        # Check top level folder state
        top_level_folder_state = session.query(LastKnownState).filter_by(
            local_name=u'Nuxeo Drive').one()
        self.assertEquals(top_level_folder_state.local_path, '/')
        self.assertEquals(top_level_folder_state.local_name, u'Nuxeo Drive')

        # Rename top level folder
        local_client.rename(u'/Nuxeo Drive', u'Nuxeo Drive renamed')
        top_level_folder_info = local_client.get_info(u'/Nuxeo Drive renamed')
        self.assertEquals(top_level_folder_info.name, u'Nuxeo Drive renamed')
        self.assertEquals(top_level_folder_info.filepath,
            os.path.join(self.local_test_folder_1, u'Nuxeo Drive renamed'))

        self.assertEquals(ctl.synchronizer.update_synchronize_server(sb), 1)

        # Check deleted server binding
        self.assertRaises(RuntimeError,
                          ctl.get_server_binding, self.local_nxdrive_folder_1,
                          raise_if_missing=True)
        # Check deleted pair state
        self.assertEquals(len(session.query(LastKnownState).all()), 0)

    def test_local_delete_top_level_folder(self):
        sb, ctl = self.sb_1, self.controller_1
        local_client = LocalClient(self.local_test_folder_1)
        session = ctl.get_session()

        # Check top level folder
        self.assertTrue(local_client.exists(u'/Nuxeo Drive'))

        # Delete top level folder
        local_client.delete(u'/Nuxeo Drive')
        self.assertRaises(NotFound,
                          local_client.get_info, u'/Nuxeo Drive')

        self.assertEquals(ctl.synchronizer.update_synchronize_server(sb), 1)

        # Check deleted server binding
        self.assertRaises(RuntimeError,
                          ctl.get_server_binding, self.local_nxdrive_folder_1,
                          raise_if_missing=True)
        # Check deleted pair state
        self.assertEquals(len(session.query(LastKnownState).all()), 0)

    def test_local_rename_readonly_folder(self):
        sb, ctl = self.sb_1, self.controller_1
        local_client = self.local_client_1
        remote_client = self.remote_document_client_1
        session = ctl.get_session()

        # Check local folder
        self.assertTrue(local_client.exists(u'/Original Folder 1'))
        folder_1_state = session.query(LastKnownState).filter_by(
            local_name=u'Original Folder 1').one()
        self.assertTrue(folder_1_state.remote_can_rename)

        # Set remote folder as readonly for test user
        folder_1_path = self.TEST_WORKSPACE_PATH + u'/Original Folder 1'
        op_input = "doc:" + folder_1_path
        self.root_remote_client.execute("Document.SetACE",
            op_input=op_input,
            user="nuxeoDriveTestUser_user_1",
            permission="Write",
            grant="false")

        # Check can_rename flag in pair state
        folder_1_state.refresh_remote(
            self.remote_file_system_client_1)
        self.assertFalse(folder_1_state.remote_can_rename)

        # Rename local folder
        local_client.rename(u'/Original Folder 1',
                            u'Renamed Folder 1 \xe9')
        self.assertFalse(local_client.exists(u'/Original Folder 1'))
        self.assertTrue(local_client.exists(u'/Renamed Folder 1 \xe9'))

        self.assertEquals(ctl.synchronizer.update_synchronize_server(sb), 1)

        # Check remote folder has not been renamed
        folder_1_remote_info = remote_client.get_info(
            u'/Original Folder 1')
        self.assertEquals(folder_1_remote_info.name,
            u'Original Folder 1')

        # Check state of local folder and its children
        folder_1_state = session.query(LastKnownState).filter_by(
            local_name=u'Renamed Folder 1 \xe9').one()
        self.assertEquals(folder_1_state.local_name,
                          u'Renamed Folder 1 \xe9')
        self.assertEquals(folder_1_state.remote_name,
                          u'Original Folder 1')

        self.assertTrue(local_client.exists(
            u'/Renamed Folder 1 \xe9/Original File 1.1.txt'))
        file_1_1_state = session.query(LastKnownState).filter_by(
            local_name=u'Original File 1.1.txt').one()
        self.assertEquals(file_1_1_state.local_name,
                          u'Original File 1.1.txt')
        self.assertEquals(file_1_1_state.remote_name,
                          u'Original File 1.1.txt')

        self.assertTrue(local_client.exists(
            u'/Renamed Folder 1 \xe9/Sub-Folder 1.1'))
        folder_1_1_state = session.query(LastKnownState).filter_by(
            local_name=u'Sub-Folder 1.1').one()
        self.assertEquals(folder_1_1_state.local_name,
                          u'Sub-Folder 1.1')
        self.assertEquals(folder_1_1_state.remote_name,
                          u'Sub-Folder 1.1')

        self.assertTrue(local_client.exists(
            u'/Renamed Folder 1 \xe9/Sub-Folder 1.2'))
        folder_1_2_state = session.query(LastKnownState).filter_by(
            local_name=u'Sub-Folder 1.2').one()
        self.assertEquals(folder_1_2_state.local_name,
                          u'Sub-Folder 1.2')
        self.assertEquals(folder_1_2_state.remote_name,
                          u'Sub-Folder 1.2')

    def test_local_delete_readonly_folder(self):
        sb, ctl = self.sb_1, self.controller_1
        local_client = self.local_client_1
        remote_client = self.remote_document_client_1
        session = ctl.get_session()

        # Check local folder
        self.assertTrue(local_client.exists(u'/Original Folder 1'))
        folder_1_state = session.query(LastKnownState).filter_by(
            local_name=u'Original Folder 1').one()
        self.assertTrue(folder_1_state.remote_can_delete)

        # Set remote folder as readonly for test user
        folder_1_path = self.TEST_WORKSPACE_PATH + u'/Original Folder 1'
        op_input = "doc:" + folder_1_path
        self.root_remote_client.execute("Document.SetACE",
            op_input=op_input,
            user="nuxeoDriveTestUser_user_1",
            permission="Write",
            grant="false")

        # Check can_delete flag in pair state
        folder_1_state.refresh_remote(
            self.remote_file_system_client_1)
        self.assertFalse(folder_1_state.remote_can_delete)

        # Delete local folder
        local_client.delete(u'/Original Folder 1')
        self.assertRaises(NotFound,
                          local_client.get_info, u'/Original Folder 1')

        self.assertEquals(ctl.synchronizer.update_synchronize_server(sb), 5)

        # Check remote folder and its children have not been deleted
        folder_1_remote_info = remote_client.get_info(
            u'/Original Folder 1')
        self.assertEquals(folder_1_remote_info.name,
            u'Original Folder 1')

        file_1_1_remote_info = remote_client.get_info(
            u'/Original Folder 1/Original File 1.1.txt')
        self.assertEquals(file_1_1_remote_info.name,
            u'Original File 1.1.txt')

        folder_1_1_remote_info = remote_client.get_info(
            u'/Original Folder 1/Sub-Folder 1.1')
        self.assertEquals(folder_1_1_remote_info.name,
            u'Sub-Folder 1.1')

        folder_1_2_remote_info = remote_client.get_info(
            u'/Original Folder 1/Sub-Folder 1.2')
        self.assertEquals(folder_1_2_remote_info.name,
            u'Sub-Folder 1.2')

        # Check local folder and its children have been re-created
        self.assertTrue(local_client.exists(u'/Original Folder 1'))
        folder_1_state = session.query(LastKnownState).filter_by(
            local_name=u'Original Folder 1').one()
        self.assertEquals(folder_1_state.local_name,
                          u'Original Folder 1')
        self.assertEquals(folder_1_state.remote_name,
                          u'Original Folder 1')

        self.assertTrue(local_client.exists(
            u'/Original Folder 1/Original File 1.1.txt'))
        file_1_1_state = session.query(LastKnownState).filter_by(
            local_name=u'Original File 1.1.txt').one()
        self.assertEquals(file_1_1_state.local_name,
                          u'Original File 1.1.txt')
        self.assertEquals(file_1_1_state.remote_name,
                          u'Original File 1.1.txt')

        self.assertTrue(local_client.exists(
            u'/Original Folder 1/Sub-Folder 1.1'))
        folder_1_1_state = session.query(LastKnownState).filter_by(
            local_name=u'Sub-Folder 1.1').one()
        self.assertEquals(folder_1_1_state.local_name,
                          u'Sub-Folder 1.1')
        self.assertEquals(folder_1_1_state.remote_name,
                          u'Sub-Folder 1.1')

        self.assertTrue(local_client.exists(
            u'/Original Folder 1/Sub-Folder 1.2'))
        folder_1_2_state = session.query(LastKnownState).filter_by(
            local_name=u'Sub-Folder 1.2').one()
        self.assertEquals(folder_1_2_state.local_name,
                          u'Sub-Folder 1.2')
        self.assertEquals(folder_1_2_state.remote_name,
                          u'Sub-Folder 1.2')

    # TODO: implement me once canDelete is checked in the synchronizer
    # def test_local_move_sync_root_folder(self):
    #    pass
