import os
from unittest import SkipTest

from tests.common_unit_test import RandomBug, UnitTestCase


class TestDedupSensitiveCaseSync(UnitTestCase):

    def _setup(self):
        super(TestDedupSensitiveCaseSync, self).setUp()
        self.engine_1.start()
        self.wait_sync(wait_for_async=True)

    @staticmethod
    def _dedup_name(name, idx=1):
        name, suffix = os.path.splitext(name)
        return "%s__%d%s" % (name, idx, suffix)

    def test_dedup_multiple_files(self):
        local = self.local_client_1
        remote = self.remote_document_client_1

        if not local.duplication_enabled():
            raise SkipTest('De-duplication disabled.')

        self._setup()

        # Create documents in the remote root workspace
        # then synchronize
        files = 10
        joe_uid = remote.make_file('/', 'joe.odt', 'Some content')
        joe2_uid = remote.make_file('/', 'joe.odt', 'Some content')
        remote.make_file('/', 'joe.odt', 'Some content')
        remote.make_file('/', 'joe.odt', 'Some content')
        remote.make_file('/', 'joe.odt', 'Some content')
        joe3_uid = remote.make_file('/', 'joe__1.odt', 'Some content')
        joe4_uid = remote.make_file('/', 'joe__2.odt', 'Some content')
        joe5_uid = remote.make_file('/', 'joe__3.odt', 'Some content')
        joe6_uid = remote.make_file('/', 'joe__4.odt', 'Some content')
        joe6_uid = remote.make_file('/', 'joe__5.odt', 'Some content')
        self.wait_sync(wait_for_async=True)
        children = remote.get_children_info(self.workspace)
        self.assertEqual(len(children), files)
        local_children = local.get_children_info('/')
        self.assertEqual(len(local_children), files)
        names = []
        names.append("joe.odt")
        for i in range(1,files):
            names.append(self._dedup_name("joe.odt", i))
        for child in local_children:
            if child.name in names:
                names.remove(child.name)
        self.assertEqual(len(names), 0)

    def test_dedup_files(self):
        local = self.local_client_1
        remote = self.remote_document_client_1

        if not local.duplication_enabled():
            raise SkipTest('De-duplication disabled.')

        self._setup()

        # Create documents in the remote root workspace
        # then synchronize
        joe_uid = remote.make_file('/', 'joe.odt', 'Some content 1')
        joe2_uid = remote.make_file('/', 'joe.odt', 'Some content 2')
        self.wait_sync(wait_for_async=True)
        childs = local.get_children_info('/')
        if joe_uid in local.get_remote_id(childs[0].path):
            joe_path = '/joe.odt'
            joe2_path = '/%s' % (self._dedup_name('joe.odt'))
        else:
            joe_path = '/%s' % (self._dedup_name('joe.odt'))
            joe2_path = '/joe.odt'
        self.assertTrue(local.exists(joe_path))
        self.assertTrue(local.exists(joe2_path))
        self.assertEqual(len(local.get_children_info('/')), 2)
        self.assertEqual(remote.get_info(joe_uid).name, 'joe.odt')
        self.assertEqual(remote.get_info(joe2_uid).name, 'joe.odt')
        local.update_content(joe_path, 'Update content 1')
        local.update_content(joe2_path, 'Update content 2')
        self.wait_sync(wait_for_async=True)
        # Verify the content has changed
        self.assertEqual(remote.get_content(joe_uid), 'Update content 1')
        self.assertEqual(remote.get_content(joe2_uid), 'Update content 2')
        # Verify the name are the same
        self.assertEqual(remote.get_info(joe_uid).name, 'joe.odt')
        self.assertEqual(remote.get_info(joe2_uid).name, 'joe.odt')
        local.delete(joe_path)
        self.wait_sync(wait_for_async=True)
        self.assertTrue(remote.exists(joe2_uid))
        self.assertFalse(remote.exists(joe_uid))
        self.assertTrue(local.exists(joe2_path))

    def test_dedup_folders(self):
        local = self.local_client_1
        remote = self.remote_document_client_1

        if not local.duplication_enabled():
            raise SkipTest('De-duplication disabled.')

        self._setup()

        # Create documents in the remote root workspace
        # then synchronize
        test_uid = remote.make_folder('/', 'test')
        test2_uid = remote.make_folder('/', 'test')
        self.wait_sync(wait_for_async=True)
        childs = local.get_children_info('/')
        if test_uid in local.get_remote_id(childs[0].path):
            test_path = '/test'
            test2_path = '/%s' % (self._dedup_name('test'))
        else:
            test_path = '/%s' % (self._dedup_name('test'))
            test2_path = '/test'
        self.assertTrue(local.exists(test_path))
        self.assertTrue(local.exists(test2_path))
        self.assertEqual(len(local.get_children_info('/')), 2)
        self.assertEqual(remote.get_info(test_uid).name, 'test')
        self.assertEqual(remote.get_info(test2_uid).name, 'test')

    @RandomBug('NXDRIVE-819', target='linux', mode='BYPASS')
    def test_dedup_move_files(self):
        local = self.local_client_1
        remote = self.remote_document_client_1

        if not local.duplication_enabled():
            raise SkipTest('De-duplication disabled.')

        self._setup()

        remote.make_folder('/', 'test')
        joe2_uid = remote.make_file('/', 'joe.odt', 'Some content')
        joe_uid = remote.make_file('/test', 'joe.odt', 'Some content')
        joe2_dedup = self._dedup_name('joe.odt')
        self.wait_sync(wait_for_async=True)
        # Check initial sync
        self.assertTrue(local.exists('/test'))
        self.assertTrue(local.exists('/joe.odt'))
        self.assertTrue(local.exists('/test/joe.odt'))
        # Move to a folder containing same file to verify the dedup
        remote.move(joe2_uid, '/test')
        self.wait_sync(wait_for_async=True)
        self.assertEqual(remote.get_info(joe_uid).name, 'joe.odt')
        self.assertEqual(remote.get_info(joe2_uid).name, 'joe.odt')
        self.assertTrue(local.exists('/test/' + joe2_dedup))
        self.assertTrue(local.exists('/test/joe.odt'))
        # Move it back to a non dedup folder
        remote.move(joe2_uid, '/')
        self.wait_sync(wait_for_async=True)
        self.assertEqual(remote.get_info(joe_uid).name, 'joe.odt')
        self.assertEqual(remote.get_info(joe2_uid).name, 'joe.odt')
        self.assertTrue(local.exists('/joe.odt'))
        self.assertTrue(local.exists('/test/joe.odt'))
        # Move again to a dedup folder
        remote.move(joe2_uid, '/test')
        self.wait_sync(wait_for_async=True)
        self.assertEqual(remote.get_info(joe_uid).name, 'joe.odt')
        self.assertEqual(remote.get_info(joe2_uid).name, 'joe.odt')
        self.assertTrue(local.exists('/test/' + joe2_dedup))
        self.assertTrue(local.exists('/test/joe.odt'))
        # Move locally without renaming
        local.move('/test/' + joe2_dedup, '/')
        self.wait_sync(wait_for_async=True)
        self.assertEqual(remote.get_info(joe_uid).name, 'joe.odt')
        self.assertEqual(remote.get_info(joe2_uid).name, joe2_dedup)
        # Might want go back to the original name
        self.assertTrue(local.exists('/' + joe2_dedup))
        self.assertTrue(local.exists('/test/joe.odt'))

    def test_dedup_move_folders(self):
        local = self.local_client_1
        remote = self.remote_document_client_1

        if not local.duplication_enabled():
            raise SkipTest('De-duplication disabled.')

        self._setup()

        test_uid = remote.make_folder('/', 'test')
        test2_uid = remote.make_folder('/test', 'test')
        test2_dedup = self._dedup_name('test')
        self.wait_sync(wait_for_async=True)
        # Check initial sync
        self.assertTrue(local.exists('/test'))
        self.assertTrue(local.exists('/test/test'))
        # Move to a folder containing same file to verify the dedup
        remote.move(test2_uid, '/')
        self.wait_sync(wait_for_async=True)
        self.assertEqual(remote.get_info(test_uid).name, 'test')
        self.assertEqual(remote.get_info(test2_uid).name, 'test')
        self.assertTrue(local.exists('/test'))
        self.assertTrue(local.exists('/' + test2_dedup))
        # Move it back to a non dedup folder
        remote.move(test2_uid, '/test')
        self.wait_sync(wait_for_async=True)
        self.assertEqual(remote.get_info(test_uid).name, 'test')
        self.assertEqual(remote.get_info(test2_uid).name, 'test')
        self.assertTrue(local.exists('/test'))
        self.assertTrue(local.exists('/test/test'))
        # Move again to a dedup folder
        remote.move(test2_uid, '/')
        self.wait_sync(wait_for_async=True)
        self.assertEqual(remote.get_info(test_uid).name, 'test')
        self.assertEqual(remote.get_info(test2_uid).name, 'test')
        self.assertTrue(local.exists('/' + test2_dedup))
        self.assertTrue(local.exists('/test'))
        # Move locally without renaming
        local.move('/' + test2_dedup, '/test')
        self.wait_sync(wait_for_async=True)
        self.assertEqual(remote.get_info(test_uid).name, 'test')
        self.assertEqual(remote.get_info(test2_uid).name, test2_dedup)
        # Might want go back to the original name
        self.assertTrue(local.exists('/test/' + test2_dedup))
        self.assertFalse(local.exists('/' + test2_dedup))

    def test_file_sync_under_dedup_shared_folders(self):
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

        # Fix the dupicate error
        new_folder = 'fruits-renamed-remotely'
        remote.update(folder1, properties={'dc:title': new_folder})
        self.wait_sync(wait_for_async=True)
        self.assertEqual(len(local.get_children_info('/')), 2)
        self.assertEqual(len(local.get_children_info('/' + new_folder)), 2)
