# coding: utf-8
"""
Test behaviors when the server allows duplicates and not the client.
"""
from .common_unit_test import UnitTestCase


class TestSynchronizationDedup(UnitTestCase):

    def test_children_of_folder_in_dedup_error(self):
        """
        NXDRIVE-1037: Children of a folder that is in DEDUP error should be
        ignored.
        """

        local = self.local_client_1
        engine = self.engine_1
        remote = self.remote_document_client_1
        engine.start()

        # Step 1: create Unisys folder (1st)
        remote.make_folder('/', 'Unisys')
        self.wait_sync(wait_for_async=True)
        assert local.exists('/Unisys')

        # Step 2: create Unisys folder (2nd)
        unisys2 = remote.make_folder('/', 'Unisys')
        self.wait_sync(wait_for_async=True)

        # Check DEDUP error
        doc_pair = engine.get_dao().get_normal_state_from_remote(
            'defaultFileSystemItemFactory#default#' + unisys2)
        assert doc_pair.last_error == 'DEDUP'

        # Step 3: create a child in the 2nd Unisys folder
        foo = remote.make_file(unisys2, 'foo.txt', content=b'42')
        self.wait_sync(wait_for_async=True, fatal=True)

        # Check the file is not created and not present in the database
        assert not local.exists('/Unisys/foo.txt')
        assert not engine.get_dao().get_normal_state_from_remote(
            'defaultFileSystemItemFactory#default#' + unisys2 + '/' + foo)


class TestSynchronizationDedupCaseSensitive(UnitTestCase):

    def _setup(self):
        self.engine_1.start()
        self.wait_sync(wait_for_async=True, enforce_errors=False)

    def test_file_sync_under_dedup_shared_folders_rename_dupe_remotely(self):
        """ NXDRIVE-842: do not sync duplicate conflicted folder content. """

        local = self.local_root_client_1
        remote = self.remote_document_client_1

        # Make documents in the 1st future root folder
        remote.make_folder('/', 'citrus')
        folder1 = remote.make_folder('/citrus', 'fruits')
        remote.make_file(folder1, 'lemon.txt', content='lemon')
        remote.make_file(folder1, 'orange.txt', content='orange')

        # Make documents in the 2nd future root folder
        folder2 = remote.make_folder('/', 'fruits')
        remote.make_file(folder2, 'cherries.txt', content='cherries')
        remote.make_file(folder2, 'mango.txt', content='mango')
        remote.make_file(folder2, 'papaya.txt', content='papaya')

        # Register new roots
        remote.unregister_as_root(self.workspace)
        remote.register_as_root(folder1)
        remote.register_as_root(folder2)

        # Start and wait
        self.engine_1.start()
        self.wait_sync(wait_for_async=True, enforce_errors=False)

        # Checks
        self.assertEqual(len(local.get_children_info('/')), 1)
        self.assertEqual(len(local.get_children_info('/fruits')), 3)

        # Fix the duplicate error
        new_folder = 'fruits-renamed-remotely'
        remote.update(folder1, properties={'dc:title': new_folder})
        self.wait_sync(wait_for_async=True, enforce_errors=False)
        self.assertEqual(len(local.get_children_info('/')), 2)
        self.assertEqual(len(local.get_children_info('/' + new_folder)), 2)
        self.assertEqual(len(local.get_children_info('/fruits')), 3)

    def test_file_sync_under_dedup_shared_folders_rename_remotely(self):
        """ NXDRIVE-842: do not sync duplicate conflicted folder content. """

        local = self.local_root_client_1
        remote = self.remote_document_client_1

        # Make documents in the 1st future root folder
        remote.make_folder('/', 'citrus')
        folder1 = remote.make_folder('/citrus', 'fruits')
        remote.make_file(folder1, 'lemon.txt', content='lemon')
        remote.make_file(folder1, 'orange.txt', content='orange')

        # Make documents in the 2nd future root folder
        folder2 = remote.make_folder('/', 'fruits')
        remote.make_file(folder2, 'cherries.txt', content='cherries')
        remote.make_file(folder2, 'mango.txt', content='mango')
        remote.make_file(folder2, 'papaya.txt', content='papaya')

        # Register new roots
        remote.unregister_as_root(self.workspace)
        remote.register_as_root(folder1)
        remote.register_as_root(folder2)

        # Start and wait
        self.engine_1.start()
        self.wait_sync(wait_for_async=True)

        # Checks
        self.assertEqual(len(local.get_children_info('/')), 1)
        self.assertEqual(len(local.get_children_info('/fruits')), 3)

        # Fix the duplicate error
        new_folder = 'fruits-renamed-remotely'
        remote.update(folder2, properties={'dc:title': new_folder})
        self.wait_sync(wait_for_async=True)
        self.assertEqual(len(local.get_children_info('/')), 2)
        self.assertEqual(len(local.get_children_info('/' + new_folder)), 3)
        self.assertEqual(len(local.get_children_info('/fruits')), 2)

    def test_file_sync_under_dedup_shared_folders_delete_remotely(self):
        """ NXDRIVE-842: do not sync duplicate conflicted folder content. """

        local = self.local_root_client_1
        remote = self.remote_document_client_1

        # Make documents in the 1st future root folder
        remote.make_folder('/', 'citrus')
        folder1 = remote.make_folder('/citrus', 'fruits')
        remote.make_file(folder1, 'lemon.txt', content='lemon')
        remote.make_file(folder1, 'orange.txt', content='orange')

        # Make documents in the 2nd future root folder
        folder2 = remote.make_folder('/', 'fruits')
        remote.make_file(folder2, 'cherries.txt', content='cherries')
        remote.make_file(folder2, 'mango.txt', content='mango')
        remote.make_file(folder2, 'papaya.txt', content='papaya')

        # Register new roots
        remote.unregister_as_root(self.workspace)
        remote.register_as_root(folder1)
        remote.register_as_root(folder2)

        # Start and wait
        self.engine_1.start()
        self.wait_sync(wait_for_async=True)

        # Checks
        self.assertEqual(len(local.get_children_info('/')), 1)
        self.assertEqual(len(local.get_children_info('/fruits')), 3)

        # Fix the duplicate error
        remote.delete(folder2)
        self.wait_sync(wait_for_async=True)
        self.assertEqual(len(local.get_children_info('/')), 1)
        self.assertEqual(len(local.get_children_info('/fruits')), 2)

    def test_file_sync_under_dedup_shared_folders_delete_dupe_remotely(self):
        """ NXDRIVE-842: do not sync duplicate conflicted folder content. """

        local = self.local_root_client_1
        remote = self.remote_document_client_1

        # Make documents in the 1st future root folder
        remote.make_folder('/', 'citrus')
        folder1 = remote.make_folder('/citrus', 'fruits')
        remote.make_file(folder1, 'lemon.txt', content='lemon')
        remote.make_file(folder1, 'orange.txt', content='orange')

        # Make documents in the 2nd future root folder
        folder2 = remote.make_folder('/', 'fruits')
        remote.make_file(folder2, 'cherries.txt', content='cherries')
        remote.make_file(folder2, 'mango.txt', content='mango')
        remote.make_file(folder2, 'papaya.txt', content='papaya')

        # Register new roots
        remote.unregister_as_root(self.workspace)
        remote.register_as_root(folder1)
        remote.register_as_root(folder2)

        # Start and wait
        self.engine_1.start()
        self.wait_sync(wait_for_async=True)

        # Checks
        self.assertEqual(len(local.get_children_info('/')), 1)
        self.assertEqual(len(local.get_children_info('/fruits')), 3)

        # Fix the duplicate error
        remote.delete(folder1)
        self.wait_sync(wait_for_async=True)
        self.assertEqual(len(local.get_children_info('/')), 1)
        self.assertEqual(len(local.get_children_info('/fruits')), 3)
        # TODO Check error count

    def test_file_sync_under_dedup_shared_folders_delete_locally(self):
        """ NXDRIVE-842: do not sync duplicate conflicted folder content. """

        local = self.local_root_client_1
        remote = self.remote_document_client_1

        # Make documents in the 1st future root folder
        remote.make_folder('/', 'citrus')
        folder1 = remote.make_folder('/citrus', 'fruits')
        remote.make_file(folder1, 'lemon.txt', content='lemon')
        remote.make_file(folder1, 'orange.txt', content='orange')

        # Make documents in the 2nd future root folder
        folder2 = remote.make_folder('/', 'fruits')
        remote.make_file(folder2, 'cherries.txt', content='cherries')
        remote.make_file(folder2, 'mango.txt', content='mango')
        remote.make_file(folder2, 'papaya.txt', content='papaya')

        # Register new roots
        remote.unregister_as_root(self.workspace)
        remote.register_as_root(folder1)
        remote.register_as_root(folder2)

        # Start and wait
        self.engine_1.start()
        self.wait_sync(wait_for_async=True)

        # Checks
        self.assertEqual(len(local.get_children_info('/')), 1)
        self.assertEqual(len(local.get_children_info('/fruits')), 3)

        # Fix the duplicate error
        local.delete('/fruits')
        self.wait_sync(wait_for_async=True)
        self.assertEqual(len(local.get_children_info('/')), 1)
        self.assertTrue(folder1 in local.get_remote_id('/fruits'))
        self.assertEqual(len(local.get_children_info('/fruits')), 2)

    def test_file_sync_under_dedup_shared_folders_rename_locally(self):
        """ NXDRIVE-842: do not sync duplicate conflicted folder content. """

        local = self.local_root_client_1
        remote = self.remote_document_client_1

        # Make documents in the 1st future root folder
        remote.make_folder('/', 'citrus')
        folder1 = remote.make_folder('/citrus', 'fruits')
        remote.make_file(folder1, 'lemon.txt', content='lemon')
        remote.make_file(folder1, 'orange.txt', content='orange')

        # Make documents in the 2nd future root folder
        folder2 = remote.make_folder('/', 'fruits')
        remote.make_file(folder2, 'cherries.txt', content='cherries')
        remote.make_file(folder2, 'mango.txt', content='mango')
        remote.make_file(folder2, 'papaya.txt', content='papaya')

        # Register new roots
        remote.unregister_as_root(self.workspace)
        remote.register_as_root(folder1)
        remote.register_as_root(folder2)

        # Start and wait
        self.engine_1.start()
        self.wait_sync(wait_for_async=True)

        # Checks
        self.assertEqual(len(local.get_children_info('/')), 1)
        self.assertEqual(len(local.get_children_info('/fruits')), 3)

        # Fix the duplicate error
        local.rename('/fruits', 'fruits-renamed')
        self.wait_sync(wait_for_async=True)
        self.assertEqual(len(local.get_children_info('/')), 2)
        self.assertEqual(len(local.get_children_info('/fruits')), 2)
        self.assertEqual(len(local.get_children_info('/fruits-renamed')), 3)
