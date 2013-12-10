import os
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
