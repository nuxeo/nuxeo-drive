import os
import time
from threading import Thread

from nxdrive.tests.common import IntegrationTestCase
from nxdrive.client import LocalClient


class TestIntegrationConcurrentSynchronization(IntegrationTestCase):

    def create_docs(self, remote_client, parent, number,
        name_pattern=None, delay=1):
        return remote_client.execute("NuxeoDrive.CreateTestDocuments",
           op_input="doc:" + parent, namePattern=name_pattern,
           number=number, delay=int(delay * 1000))

    def test_find_changes_with_many_doc_creations(self):
        # Setup a controller and bind a root for user_1
        ctl = self.controller_1
        remote_client = self.remote_document_client_1
        ctl.bind_server(self.local_nxdrive_folder_1, self.nuxeo_url,
                        self.user_1, self.password_1)
        ctl.bind_root(self.local_nxdrive_folder_1, self.workspace)
        syn = ctl.synchronizer

        # Synchronize the workspace folder
        self.wait()
        syn.loop(delay=0.010, max_loops=1)

        # Open a local client on the local workspace root
        expected_folder = os.path.join(self.local_nxdrive_folder_1,
                                       self.workspace_title)
        local_client = LocalClient(expected_folder)
        self.assertEquals(local_client.get_children_info(u'/'), [])

        # List of children names to create
        n_children = 5
        child_name_pattern = "child_%03d.txt"
        children_names = [child_name_pattern % i
                          for i in range(n_children)]

        # Launch a synchronizer thread concurrently that will stop
        # automatically as soon as all the children are synchronized
        def synchronization_loop():
            for i in range(3):
                syn.loop(delay=1, max_loops=2)

                local_children_names = [
                    c.name for c in local_client.get_children_info(u'/')]
                local_children_names.sort()
                if local_children_names == children_names:
                    # All remote children have been successfully synchronized
                    # in the local folder
                    return

        sync_thread = Thread(target=synchronization_loop)
        sync_thread.start()

        # Create the children to synchronize on the remote server concurrently
        # in a long running transaction
        remote_client.timeout = 10  # extend the timeout
        self.create_docs(remote_client, self.workspace, n_children,
            name_pattern=child_name_pattern, delay=0.5)

        # Wait for the synchronizer thread to complete
        sync_thread.join()

        # Check that all the children creations where detected despite the
        # creation transaction spanning longer than the individual audit
        # query time ranges.
        local_children_names = [
            c.name for c in local_client.get_children_info(u'/')]
        local_children_names.sort()
        self.assertEquals(local_children_names, children_names)

    def test_delete_local_folder_2_clients(self):

        # Define 2 controllers, one for each device
        ctl1 = self.controller_1
        ctl2 = self.controller_2

        # Get local clients for each device and remote client
        local1 = LocalClient(self.local_nxdrive_folder_1)
        local2 = LocalClient(self.local_nxdrive_folder_2)
        remote = self.remote_document_client_1

        # Bind each device to the server with the same account:
        # nuxeoDriveTestUser_user_1 and bind test workspace
        ctl1.bind_server(self.local_nxdrive_folder_1, self.nuxeo_url,
                        self.user_1, self.password_1)
        ctl2.bind_server(self.local_nxdrive_folder_2, self.nuxeo_url,
                        self.user_1, self.password_1)
        ctl1.bind_root(self.local_nxdrive_folder_1, self.workspace)

        # Check synchronization roots for nuxeoDriveTestUser_user_1,
        # there should be 1, the test workspace
        sync_roots = remote.get_roots()
        self.assertEquals(len(sync_roots), 1)
        self.assertEquals(sync_roots[0].name, self.workspace_title)

        # Launch first synchronization on both devices
        time.sleep(self.AUDIT_CHANGE_FINDER_TIME_RESOLUTION)
        self.wait()
        sync1 = ctl1.synchronizer
        sync2 = ctl2.synchronizer
        sync1.loop(delay=0.1, max_loops=1)
        sync2.loop(delay=0.1, max_loops=1)

        # Test workspace should be created locally on both devices
        self.assertTrue(local1.exists('/Nuxeo Drive Test Workspace'))
        self.assertTrue(local2.exists('/Nuxeo Drive Test Workspace'))

        # Make nuxeoDriveTestUser_user_1 create a remote folder in the
        # test workspace and a file inside this folder,
        # then synchronize both devices
        test_folder = remote.make_folder(self.workspace, 'Test folder')
        remote.make_file(test_folder, 'test.odt', 'Some content.')

        time.sleep(self.AUDIT_CHANGE_FINDER_TIME_RESOLUTION)
        self.wait()
        sync1.loop(delay=0.1, max_loops=1)
        sync2.loop(delay=0.1, max_loops=1)

        # Test folder should be created locally on both devices
        self.assertTrue(local1.exists(
                        '/Nuxeo Drive Test Workspace/Test folder'))
        self.assertTrue(local1.exists(
                        '/Nuxeo Drive Test Workspace/Test folder/test.odt'))
        self.assertTrue(local2.exists(
                        '/Nuxeo Drive Test Workspace/Test folder'))
        self.assertTrue(local2.exists(
                        '/Nuxeo Drive Test Workspace/Test folder/test.odt'))

        # Delete Test folder locally on one of the devices
        local1.delete('/Nuxeo Drive Test Workspace/Test folder')
        self.assertFalse(local1.exists(
                                    '/Nuxeo Drive Test Workspace/Test folder'))

        # Launch synchronization on both devices in separate threads
        def sync1_loop():
            sync1.loop(delay=1.0, max_loops=3)

        def sync2_loop():
            sync2.loop(delay=1.0, max_loops=3)

        sync1_thread = Thread(target=sync1_loop)
        sync2_thread = Thread(target=sync2_loop)
        sync1_thread.start()
        sync2_thread.start()

        # Wait for synchronization threads to complete
        sync1_thread.join()
        sync2_thread.join()

        # Test folder should be deleted on the server and on both devices
        self.assertFalse(remote.exists(test_folder))
        self.assertFalse(local1.exists(
                                    '/Nuxeo Drive Test Workspace/Test folder'))
        self.assertFalse(local2.exists(
                                    '/Nuxeo Drive Test Workspace/Test folder'))

    def test_delete_local_folder_delay_remote_changes_fetch(self):

        # Get local and remote clients
        local = LocalClient(self.local_nxdrive_folder_1)
        remote = self.remote_document_client_1

        # Bind server and test workspace for nuxeoDriveTestUser_user_1
        ctl = self.controller_1
        ctl.bind_server(self.local_nxdrive_folder_1, self.nuxeo_url,
                        self.user_1, self.password_1)
        ctl.bind_root(self.local_nxdrive_folder_1, self.workspace)

        # Launch first synchronization
        time.sleep(self.AUDIT_CHANGE_FINDER_TIME_RESOLUTION)
        self.wait()
        sync = ctl.synchronizer
        sync.loop(delay=0.1, max_loops=1)

        # Test workspace should be created locally
        self.assertTrue(local.exists('/Nuxeo Drive Test Workspace'))

        # Create a local folder in the test workspace and a file inside
        # this folder, then synchronize
        local.make_folder('/Nuxeo Drive Test Workspace', 'Test folder')
        local.make_file('/Nuxeo Drive Test Workspace/Test folder',
                        'test.odt', 'Some content.')

        sync.loop(delay=0.1, max_loops=1)

        # Test folder should be created remotely in the test workspace
        self.assertTrue(remote.exists('/Test folder'))
        self.assertTrue(remote.exists('/Test folder/test.odt'))

        # Delete Test folder locally before fetching remote changes,
        # then synchronize
        local.delete('/Nuxeo Drive Test Workspace/Test folder')
        self.assertFalse(local.exists(
                                    '/Nuxeo Drive Test Workspace/Test folder'))

        time.sleep(self.AUDIT_CHANGE_FINDER_TIME_RESOLUTION)
        self.wait()
        sync.loop(delay=0.1, max_loops=1)

        # Test folder should be deleted remotely in the test workspace.
        # Even though fetching the remote changes will send
        # 'documentCreated' events for Test folder and its child file
        # as a result of the previous synchronization loop, since the folder
        # will not have been renamed nor moved since last synchronization,
        # its remote pair state will not be marked as 'modified',
        # see Model.update_remote().
        # Thus the pair state will be ('deleted', 'synchronized'), resolved as
        # 'locally_deleted'.
        self.assertFalse(remote.exists('Test folder'))

        # Check Test folder has not been re-created locally
        self.assertFalse(local.exists(
                                    '/Nuxeo Drive Test Workspace/Test folder'))

    def test_delete_local_folder_update_remote_folder_property(self):

        # Get local and remote clients
        local = LocalClient(self.local_nxdrive_folder_1)
        remote = self.remote_document_client_1

        # Bind server and test workspace for nuxeoDriveTestUser_user_1
        ctl = self.controller_1
        ctl.bind_server(self.local_nxdrive_folder_1, self.nuxeo_url,
                        self.user_1, self.password_1)
        ctl.bind_root(self.local_nxdrive_folder_1, self.workspace)

        # Launch first synchronization
        time.sleep(self.AUDIT_CHANGE_FINDER_TIME_RESOLUTION)
        self.wait()
        sync = ctl.synchronizer
        sync.loop(delay=0.1, max_loops=1)

        # Test workspace should be created locally
        self.assertTrue(local.exists('/Nuxeo Drive Test Workspace'))

        # Create a local folder in the test workspace and a file inside
        # this folder, then synchronize
        local.make_folder('/Nuxeo Drive Test Workspace', 'Test folder')
        local.make_file('/Nuxeo Drive Test Workspace/Test folder',
                        'test.odt', 'Some content.')

        sync.loop(delay=0.1, max_loops=1)

        # Test folder should be created remotely in the test workspace
        self.assertTrue(remote.exists('/Test folder'))
        self.assertTrue(remote.exists('/Test folder/test.odt'))

        # Delete Test folder locally and remotely update one of its properties
        # concurrently, then synchronize
        local.delete('/Nuxeo Drive Test Workspace/Test folder')
        self.assertFalse(local.exists(
                                    '/Nuxeo Drive Test Workspace/Test folder'))
        test_folder_ref = remote._check_ref('/Test folder')
        # Wait for 1 second to make sure the folder's last modification time
        # will be different from the pair state's last remote update time
        time.sleep(1.0)
        remote.update(test_folder_ref,
                      properties={'dc:description': 'Some description.'})
        test_folder = remote.fetch(test_folder_ref)
        self.assertEqual(test_folder['properties']['dc:description'],
                         'Some description.')

        time.sleep(self.AUDIT_CHANGE_FINDER_TIME_RESOLUTION)
        self.wait()
        sync.loop(delay=0.1, max_loops=1)

        # Test folder should be deleted remotely in the test workspace.
        # Even though fetching the remote changes will send a
        # 'documentModified' event for Test folder as a result of its
        # dc:description property update, since the folder will not have been
        # renamed nor moved since last synchronization, its remote pair state
        # will not be marked as 'modified', see Model.update_remote().
        # Thus the pair state will be ('deleted', 'synchronized'), resolved as
        # 'locally_deleted'.
        self.assertFalse(remote.exists('/Test folder'))

        # Check Test folder has not been re-created locally
        self.assertFalse(local.exists(
                                    '/Nuxeo Drive Test Workspace/Test folder'))

    def test_update_local_file_content_update_remote_file_property(self):

        # Get local and remote clients
        local = LocalClient(self.local_nxdrive_folder_1)
        remote = self.remote_document_client_1

        # Bind server and test workspace for nuxeoDriveTestUser_user_1
        ctl = self.controller_1
        ctl.bind_server(self.local_nxdrive_folder_1, self.nuxeo_url,
                        self.user_1, self.password_1)
        ctl.bind_root(self.local_nxdrive_folder_1, self.workspace)

        # Launch first synchronization
        time.sleep(self.AUDIT_CHANGE_FINDER_TIME_RESOLUTION)
        self.wait()
        sync = ctl.synchronizer
        sync.loop(delay=0.1, max_loops=1)

        # Test workspace should be created locally
        self.assertTrue(local.exists('/Nuxeo Drive Test Workspace'))

        # Create a local file in the test workspace then synchronize
        local.make_file('/Nuxeo Drive Test Workspace',
                        'test.odt', 'Some content.')

        sync.loop(delay=0.1, max_loops=1)

        # Test file should be created remotely in the test workspace
        self.assertTrue(remote.exists('/test.odt'))

        # Locally update the file content and remotely update one of its
        # properties concurrently, then synchronize
        time.sleep(self.OS_STAT_MTIME_RESOLUTION)
        local.update_content('/Nuxeo Drive Test Workspace/test.odt',
                             'Updated content.')
        self.assertEquals(local.get_content(
                                    '/Nuxeo Drive Test Workspace/test.odt'),
                          'Updated content.')
        test_file_ref = remote._check_ref('/test.odt')
        # Wait for 1 second to make sure the file's last modification time
        # will be different from the pair state's last remote update time
        time.sleep(1.0)
        remote.update(test_file_ref,
                      properties={'dc:description': 'Some description.'})
        test_file = remote.fetch(test_file_ref)
        self.assertEqual(test_file['properties']['dc:description'],
                         'Some description.')

        time.sleep(self.AUDIT_CHANGE_FINDER_TIME_RESOLUTION)
        self.wait()
        sync.loop(delay=0.1, max_loops=2)

        # Test file should be updated remotely in the test workspace,
        # and no conflict should be detected.
        # Even though fetching the remote changes will send a
        # 'documentModified' event for the test file as a result of its
        # dc:description property update, since the file will not have been
        # renamed nor moved and its content not modified since last
        # synchronization, its remote pair state will not be marked as
        # 'modified', see Model.update_remote().
        # Thus the pair state will be ('modified', 'synchronized'), resolved as
        # 'locally_modified'.
        self.assertTrue(remote.exists('/test.odt'))
        self.assertEquals(remote.get_content('/test.odt'), 'Updated content.')
        test_file = remote.fetch(test_file_ref)
        self.assertEqual(test_file['properties']['dc:description'],
                         'Some description.')
        self.assertEqual(len(remote.get_children_info(self.workspace)), 1)

        # Check that the content of the test file has not changed
        self.assertTrue(local.exists('/Nuxeo Drive Test Workspace/test.odt'))
        self.assertEquals(local.get_content(
                                    '/Nuxeo Drive Test Workspace/test.odt'),
                          'Updated content.')
        self.assertEqual(len(local.get_children_info(
                                            '/Nuxeo Drive Test Workspace')), 1)
