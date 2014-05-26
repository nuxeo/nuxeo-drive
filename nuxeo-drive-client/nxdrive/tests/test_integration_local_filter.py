import os
from nxdrive.tests.common import IntegrationTestCase
from nxdrive.client import LocalClient
from nxdrive.model import Filter


class TestIntegrationLocalFilter(IntegrationTestCase):

    def test_synchronize_local_filter(self):
        """Test that filtering remote documents is impacted client side

        Just do a single test as it is the same as
        test_integration_remote_deletion

        Use cases:
          - Filter delete a regular folder
              => Folder should be locally deleted
          - Unfilter restore folder from the trash
              => Folder should be locally re-created
          - Filter a synchronization root
              => Synchronization root should be locally deleted
          - Unfilter synchronization root from the trash
              => Synchronization root should be locally re-created

        See TestIntegrationSecurityUpdates.test_synchronize_denying_read_access
        as the same uses cases are tested
        """
        # Bind the server and root workspace
        ctl = self.controller_1
        ctl.bind_server(self.local_nxdrive_folder_1, self.nuxeo_url,
                        self.user_1, self.password_1)
        ctl.bind_root(self.local_nxdrive_folder_1, self.workspace)

        # Get local and remote clients
        local = LocalClient(os.path.join(self.local_nxdrive_folder_1,
                                         self.workspace_title))
        remote = self.remote_document_client_1

        # Create documents in the remote root workspace
        # then synchronize
        remote.make_folder('/', 'Test folder')
        remote.make_file('/Test folder', 'joe.txt', 'Some content')

        session = ctl.get_session()

        # Fake server binding with the unit test class
        syn = ctl.synchronizer
        syn.loop(1)
        self.assertTrue(local.exists('/Test folder'))
        self.assertTrue(local.exists('/Test folder/joe.txt'))

        # Delete remote folder then synchronize
        doc = remote.get_info('/Test folder')
        root_path = "/org.nuxeo.drive.service.impl.DefaultTopLevelFolderItemFactory#/defaultSyncRootFolderItemFactory#default#"
        root_path = root_path + doc.root
        doc_path = (root_path + "/defaultFileSystemItemFactory#default#"
                    + doc.uid)

        server_binding = ctl.get_server_binding(self.local_nxdrive_folder_1,
                                                session=session)
        Filter.add(session, server_binding, doc_path)
        syn.loop(1)
        self.assertFalse(local.exists('/Test folder'))

        # Restore folder from trash then synchronize
        # Undeleting each item as following 'undelete' transition
        # doesn't act recursively, should use TrashService instead
        # through a dedicated operation
        Filter.remove(session, server_binding, doc_path)
        syn.loop(1)
        self.assertTrue(local.exists('/Test folder'))
        self.assertTrue(local.exists('/Test folder/joe.txt'))

        # Delete sync root then synchronize
        server_binding = ctl.get_server_binding(self.local_nxdrive_folder_1,
                                                session=session)
        Filter.add(session, server_binding, root_path)
        syn.loop(1)
        self.assertFalse(local.exists('/'))

        # Restore sync root from trash then synchronize
        Filter.remove(session, server_binding, root_path)
        syn.loop(1)
        self.assertTrue(local.exists('/'))
        self.assertTrue(local.exists('/Test folder'))
        self.assertTrue(local.exists('/Test folder/joe.txt'))
