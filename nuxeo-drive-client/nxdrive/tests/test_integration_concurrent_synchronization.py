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

        # Delete Test folder locally and remotely update one of its property
        # concurrently, then synchronize
        local.delete('/Nuxeo Drive Test Workspace/Test folder')
        self.assertFalse(local.exists(
                                    '/Nuxeo Drive Test Workspace/Test folder'))
        test_folder_ref = remote._check_ref('/Test folder')
        # Wait for 1 second to make sure the folder's last modification time
        # is different from the pair state's last remote update time
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
        # renamed nor moved since last synchronization, its pair state will
        # not be marked as 'modified', see Model.update_remote().
        # Thus the pair state will be ('deleted', 'synchronized'), resolved as
        # 'locally_deleted'.
        self.assertFalse(remote.exists('/Test folder'))

        # Check Test folder has not been re-created locally
        self.assertFalse(local.exists(
                                    '/Nuxeo Drive Test Workspace/Test folder'))
