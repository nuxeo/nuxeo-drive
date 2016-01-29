from nxdrive.tests.common_unit_test import UnitTestCase
from nxdrive.logging_config import get_logger
log = get_logger(__name__)

class TestLocalFilter(UnitTestCase):

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
        self.engine_1.start()
        # Get local and remote clients
        local = self.local_client_1
        remote = self.remote_document_client_1

        # Create documents in the remote root workspace
        # then synchronize
        remote.make_folder('/', 'Test folder')
        remote.make_file('/Test folder', 'joe.txt', 'Some content')
        self.wait_sync(wait_for_async=True)
        # Fake server binding with the unit test class
        self.assertTrue(local.exists('/Test folder'))
        self.assertTrue(local.exists('/Test folder/joe.txt'))

        # Add remote folder as filter then synchronize
        doc = remote.get_info('/Test folder')
        root_path = "/org.nuxeo.drive.service.impl.DefaultTopLevelFolderItemFactory#/defaultSyncRootFolderItemFactory#default#"
        root_path = root_path + doc.root
        doc_path = (root_path + "/defaultFileSystemItemFactory#default#"
                    + doc.uid)

        self.engine_1.add_filter(doc_path)
        self.wait_sync()
        self.assertFalse(local.exists('/Test folder'))

        self.engine_1.remove_filter(doc_path)
        self.wait_sync()
        self.assertTrue(local.exists('/Test folder'))
        self.assertTrue(local.exists('/Test folder/joe.txt'))

        self.engine_1.add_filter(doc_path)
        self.wait_sync()
        self.assertFalse(local.exists('/Test folder'))

        # Delete sync root then synchronize
        self.engine_1.add_filter(root_path)
        self.wait_sync()
        self.assertFalse(local.exists('/'))

        # Restore sync root from trash then synchronize
        self.engine_1.remove_filter(root_path)
        self.wait_sync()
        self.assertTrue(local.exists('/'))
        self.assertTrue(local.exists('/Test folder'))
        self.assertTrue(local.exists('/Test folder/joe.txt'))

    def test_synchronize_local_office_temp(self):
        # Should synchronize directly local folder with hex name
        # Bind the server and root workspace
        hexaname = "1234ABCD"
        hexafile = "2345BCDF"
        self.engine_1.start()
        self.wait_sync()
        self.local_client_1.make_folder('/', hexaname)
        self.local_client_1.make_file('/', hexafile, 'test')
        # Make sure that a folder is synchronized directly no matter what and the file is postponed
        self.wait_sync(enforce_errors=False,fail_if_timeout=False)
        children = self.remote_document_client_1.get_children_info(self.workspace)
        self.assertEquals(len(children), 1)
        # Note are renamed to .txt when come back from the server
        # TODO Not sure it is a good behavior
        self.assertFalse(self.local_client_1.exists("/" + hexafile + ".txt"))
        # Force the postponed to ensure it's synchronized now
        self.engine_1.get_queue_manager().requeue_errors()
        self.wait_sync(wait_for_async=True)
        self.assertTrue(self.local_client_1.exists("/" + hexafile + ".txt"))
        children = self.remote_document_client_1.get_children_info(self.workspace)
        log.debug("Children retrieved: %r", children)
        self.assertEquals(len(children), 2)

    def test_synchronize_local_filter_with_move(self):
        # Bind the server and root workspace
        self.engine_1.start()
        # Get local and remote clients
        local = self.local_client_1
        remote = self.remote_document_client_1

        # Create documents in the remote root workspace
        # then synchronize
        remote.make_folder('/', 'Test')
        remote.make_file('/Test', 'joe.txt', 'Some content')
        remote.make_folder('/Test', 'Subfolder')
        remote.make_folder('/Test', 'Filtered')
        remote.make_file('/Test/Subfolder', 'joe2.txt', 'Some content')
        remote.make_file('/Test/Subfolder', 'joe3.txt', 'Somecossntent')
        remote.make_folder('/Test/Subfolder/', 'SubSubfolder')
        remote.make_file('/Test/Subfolder/SubSubfolder', 'joe4.txt',
                                                    'Some qwqwqontent')

        # Fake server binding with the unit test class
        self.wait_sync(wait_for_async=True)
        self.assertTrue(local.exists('/Test'))
        self.assertTrue(local.exists('/Test/joe.txt'))
        self.assertTrue(local.exists('/Test/Filtered'))
        self.assertTrue(local.exists('/Test/Subfolder'))
        self.assertTrue(local.exists('/Test/Subfolder/joe2.txt'))
        self.assertTrue(local.exists('/Test/Subfolder/joe3.txt'))
        self.assertTrue(local.exists('/Test/Subfolder/SubSubfolder'))
        self.assertTrue(local.exists('/Test/Subfolder/SubSubfolder/joe4.txt'))

        # Add remote folder as filter then synchronize
        doc_file = remote.get_info('/Test/joe.txt')
        doc = remote.get_info('/Test')
        filtered_doc = remote.get_info('/Test/Filtered')
        root_path = "/org.nuxeo.drive.service.impl.DefaultTopLevelFolderItemFactory#/defaultSyncRootFolderItemFactory#default#"
        root_path = root_path + doc.root
        doc_path_filtered = (root_path +
                "/defaultFileSystemItemFactory#default#" + doc.uid +
                "/defaultFileSystemItemFactory#default#" + filtered_doc.uid)

        self.engine_1.add_filter(doc_path_filtered)
        self.wait_sync()
        self.assertFalse(local.exists('/Test/Filtered'))

        # Move joe.txt to filtered folder on the server
        remote.move(doc_file.uid, filtered_doc.uid)
        self.wait_sync(wait_for_async=True)

        # It now delete on the client
        self.assertFalse(local.exists('/Test/joe.txt'))
        self.assertTrue(local.exists('/Test/Subfolder'))
        self.assertTrue(local.exists('/Test/Subfolder/joe2.txt'))
        self.assertTrue(local.exists('/Test/Subfolder/joe3.txt'))
        self.assertTrue(local.exists('/Test/Subfolder/SubSubfolder'))
        self.assertTrue(local.exists('/Test/Subfolder/SubSubfolder/joe4.txt'))

        # Now move the subfolder
        doc_file = remote.get_info('/Test/Subfolder')
        remote.move(doc_file.uid, filtered_doc.uid)
        self.wait_sync(wait_for_async=True)

        # Check that all has been deleted
        self.assertFalse(local.exists('/Test/joe.txt'))
        self.assertFalse(local.exists('/Test/Subfolder'))
        self.assertFalse(local.exists('/Test/Subfolder/joe2.txt'))
        self.assertFalse(local.exists('/Test/Subfolder/joe3.txt'))
        self.assertFalse(local.exists('/Test/Subfolder/SubSubfolder'))
        self.assertFalse(local.exists('/Test/Subfolder/SubSubfolder/joe4.txt'))

    def test_synchronize_local_filter_with_remote_trash(self):
        self.engine_1.start()

        # Get local and remote clients
        local = self.local_client_1
        remote = self.remote_document_client_1

        # Create documents in the remote root workspace
        # then synchronize
        remote.make_folder('/', 'Test')
        remote.make_file('/Test', 'joe.txt', 'Some content')

        self.wait_sync(wait_for_async=True)
        self.assertTrue(local.exists('/Test'))
        self.assertTrue(local.exists('/Test/joe.txt'))

        # Add remote folder as filter then synchronize
        doc = remote.get_info('/Test')
        root_path = "/org.nuxeo.drive.service.impl.DefaultTopLevelFolderItemFactory#/defaultSyncRootFolderItemFactory#default#"
        root_path = root_path + doc.root
        doc_path = (root_path + "/defaultFileSystemItemFactory#default#"
                    + doc.uid)

        self.engine_1.add_filter(doc_path)
        self.wait_sync()
        self.assertFalse(local.exists('/Test'))

        # Delete remote folder then synchronize
        remote.delete('/Test')
        self.wait_sync(wait_for_async=True)
        self.assertFalse(local.exists('/Test'))

        # Restore folder from trash then synchronize
        # Undeleting each item as following 'undelete' transition
        # doesn't act recursively, should use TrashService instead
        # through a dedicated operation
        remote.undelete('/Test')
        remote.undelete('/Test/joe.txt')
        # NXDRIVE-xx check that the folder is not created as it is filtered
        self.wait_sync(wait_for_async=True)
        self.assertFalse(local.exists('/Test'))
