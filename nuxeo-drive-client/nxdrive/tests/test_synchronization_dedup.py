import os
import sys
from unittest import SkipTest

from nxdrive.tests.common_unit_test import UnitTestCase
from nxdrive.logging_config import get_logger

log = get_logger(__name__)


class TestDedupInsensitiveCaseSync(UnitTestCase):

    def setUp(self):
        super(TestDedupInsensitiveCaseSync, self).setUp()
        if sys.platform.startswith('linux'):
            raise SkipTest("Case insensitive test")
        self.engine_1.start()
        self.wait_sync(wait_for_async=True)

    def _dedup_name(self, name, idx=1):
        name, suffix = os.path.splitext(name)
        return "%s__%d%s" % (name, idx, suffix)

    def test_dedup_files(self):
        local = self.local_client_1
        remote = self.remote_document_client_1
        # Create documents in the remote root workspace
        # then synchronize
        joe_uid = remote.make_file('/', 'joe.odt', 'Some content')
        Joe_uid = remote.make_file('/', 'Joe.odt', 'Some content')
        self.wait_sync(wait_for_async=True)
        childs = local.get_children_info('/')
        if childs[0].name == 'joe.odt' or childs[1].name == 'joe.odt':
            joe_path = '/joe.odt'
            Joe_path = '/%s' % (self._dedup_name('Joe.odt'))
        else:
            joe_path = '/%s' % (self._dedup_name('joe.odt'))
            Joe_path = '/Joe.odt'
        self.assertTrue(local.exists(joe_path))
        self.assertTrue(local.exists(Joe_path))
        self.assertEquals(len(local.get_children_info('/')), 2)
        self.assertEquals(remote.get_info(joe_uid).name, 'joe.odt')
        self.assertEquals(remote.get_info(Joe_uid).name, 'Joe.odt')
        local.update_content(joe_path, 'Update content joe')
        local.update_content(Joe_path, 'Update content Joe')
        self.wait_sync(wait_for_async=True)
        # Verify the content has changed
        self.assertEquals(remote.get_content(joe_uid), 'Update content joe')
        self.assertEquals(remote.get_content(Joe_uid), 'Update content Joe')
        # Verify the name are the same
        self.assertEquals(remote.get_info(joe_uid).name, 'joe.odt')
        self.assertEquals(remote.get_info(Joe_uid).name, 'Joe.odt')
        local.delete(joe_path)
        self.wait_sync(wait_for_async=True)
        self.assertTrue(remote.exists(Joe_uid))
        self.assertFalse(remote.exists(joe_uid))
        self.assertTrue(local.exists(Joe_path))

    def test_dedup_files_reinit(self):
        local = self.local_client_1
        remote = self.remote_document_client_1
        # Create documents in the remote root workspace
        # then synchronize
        joe_uid = remote.make_file('/', 'joe.odt', 'Some content')
        Joe_uid = remote.make_file('/', 'Joe.odt', 'Some content')
        self.wait_sync(wait_for_async=True)
        childs = local.get_children_info('/')
        if childs[0].name == 'joe.odt' or childs[1].name == 'joe.odt':
            joe_path = '/joe.odt'
            Joe_path = '/%s' % (self._dedup_name('Joe.odt'))
        else:
            joe_path = '/%s' % (self._dedup_name('joe.odt'))
            Joe_path = '/Joe.odt'
        self.assertTrue(local.exists(joe_path))
        self.assertTrue(local.exists(Joe_path))
        self.assertEquals(len(local.get_children_info('/')), 2)
        self.assertEquals(remote.get_info(joe_uid).name, 'joe.odt')
        self.assertEquals(remote.get_info(Joe_uid).name, 'Joe.odt')
        local.update_content(joe_path, 'Update content joe')
        local.update_content(Joe_path, 'Update content Joe')
        self.wait_sync(wait_for_async=True)
        # Verify the content has changed
        self.assertEquals(remote.get_content(joe_uid), 'Update content joe')
        self.assertEquals(remote.get_content(Joe_uid), 'Update content Joe')
        # Verify the name are the same
        self.engine_1.stop()
        self.assertEquals(len(local.get_children_info('/')), 2)
        self.assertEquals(len(remote.get_children_info(self.workspace_1)), 2)
        # Simulate the uninstall
        self.engine_1.reinit()
        self.engine_1.start()
        self.wait_sync(wait_for_async=True)
        self.assertEquals(len(local.get_children_info('/')), 2)
        self.assertEquals(len(remote.get_children_info(self.workspace_1)), 2)
        self.assertEquals(remote.get_content(joe_uid), 'Update content joe')
        self.assertEquals(remote.get_content(Joe_uid), 'Update content Joe')

    def test_dedup_folders_reinit(self):
        local = self.local_client_1
        remote = self.remote_document_client_1
        # Create documents in the remote root workspace
        # then synchronize
        test_uid = remote.make_folder('/', 'test')
        Test_uid = remote.make_folder('/', 'Test')
        remote.make_file('/test', 'test.txt', 'plop')
        remote.make_file('/Test', 'test_2.txt', 'plop')
        self.wait_sync(wait_for_async=True)
        childs = local.get_children_info('/')
        if childs[0].name == 'test' or childs[1].name == 'test':
            test_path = '/test'
            Test_path = '/%s' % (self._dedup_name('Test'))
        else:
            test_path = '/%s' % (self._dedup_name('test'))
            Test_path = '/Test'
        self.assertTrue(local.exists(test_path))
        self.assertTrue(local.exists(Test_path))
        self.assertEquals(len(local.get_children_info('/')), 2)
        self.assertEquals(len(local.get_children_info(test_path)), 1)
        self.assertEquals(len(local.get_children_info(Test_path)), 1)
        self.engine_1.stop()
        # Simulate the uninstall
        self.engine_1.reinit()
        self.engine_1.start()
        self.assertEquals(len(local.get_children_info('/')), 2)
        self.assertEquals(len(local.get_children_info(test_path)), 1)
        self.assertEquals(len(local.get_children_info(Test_path)), 1)

    def test_dedup_folders(self):
        local = self.local_client_1
        remote = self.remote_document_client_1
        # Create documents in the remote root workspace
        # then synchronize
        test_uid = remote.make_folder('/', 'test')
        Test_uid = remote.make_folder('/', 'Test')
        remote.make_file('/test', 'test.txt', 'plop')
        remote.make_file('/Test', 'test_2.txt', 'plop')
        self.wait_sync(wait_for_async=True)
        childs = local.get_children_info('/')
        if childs[0].name == 'test' or childs[1].name == 'test':
            test_path = '/test'
            Test_path = '/%s' % (self._dedup_name('Test'))
        else:
            test_path = '/%s' % (self._dedup_name('test'))
            Test_path = '/Test'
        self.assertTrue(local.exists(test_path))
        self.assertTrue(local.exists(Test_path))
        self.assertEquals(len(local.get_children_info('/')), 2)
        self.assertEquals(remote.get_info(test_uid).name, 'test')
        self.assertEquals(remote.get_info(Test_uid).name, 'Test')
        self.assertEquals(len(local.get_children_info(test_path)), 1)
        self.assertEquals(len(local.get_children_info(Test_path)), 1)

    def test_dedup_move_files(self):
        local = self.local_client_1
        remote = self.remote_document_client_1
        remote.make_folder('/', 'test')
        Joe_uid = remote.make_file('/', 'Joe.odt', 'Some content')
        joe_uid = remote.make_file('/test', 'joe.odt', 'Some content')
        Joe_dedup = self._dedup_name('Joe.odt')
        self.wait_sync(wait_for_async=True)
        # Check initial sync
        self.assertTrue(local.exists('/test'))
        self.assertTrue(local.exists('/Joe.odt'))
        self.assertTrue(local.exists('/test/joe.odt'))
        # Move to a folder containing same file to verify the dedup
        remote.move(Joe_uid, '/test')
        self.wait_sync(wait_for_async=True)
        self.assertEquals(remote.get_info(joe_uid).name, 'joe.odt')
        self.assertEquals(remote.get_info(Joe_uid).name, 'Joe.odt')
        self.assertFalse(local.exists('/Joe.odt'))
        self.assertTrue(local.exists('/test/' + Joe_dedup))
        self.assertTrue(local.exists('/test/joe.odt'))
        # Move it back to a non dedup folder
        remote.move(Joe_uid, '/')
        self.wait_sync(wait_for_async=True)
        self.assertEquals(remote.get_info(joe_uid).name, 'joe.odt')
        self.assertEquals(remote.get_info(Joe_uid).name, 'Joe.odt')
        self.assertFalse(local.exists('/test/' + Joe_dedup))
        self.assertTrue(local.exists('/Joe.odt'))
        self.assertTrue(local.exists('/test/joe.odt'))
        # Move again to a dedup folder
        remote.move(Joe_uid, '/test')
        self.wait_sync(wait_for_async=True)
        self.assertEquals(remote.get_info(joe_uid).name, 'joe.odt')
        self.assertEquals(remote.get_info(Joe_uid).name, 'Joe.odt')
        self.assertFalse(local.exists('/Joe.odt'))
        self.assertTrue(local.exists('/test/' + Joe_dedup))
        self.assertTrue(local.exists('/test/joe.odt'))
        # Move locally without renaming
        local.move('/test/' + Joe_dedup, '/')
        self.wait_sync(wait_for_async=True)
        self.assertEquals(remote.get_info(joe_uid).name, 'joe.odt')
        self.assertEquals(remote.get_info(Joe_uid).name, Joe_dedup)
        # Might want go back to the original name
        self.assertTrue(local.exists('/' + Joe_dedup))
        self.assertFalse(local.exists('/test/' + Joe_dedup))
        self.assertTrue(local.exists('/test/joe.odt'))

    def test_dedup_move_folders(self):
        local = self.local_client_1
        remote = self.remote_document_client_1
        test_uid = remote.make_folder('/', 'test')
        Test_uid = remote.make_folder('/test', 'Test')
        Test_dedup = self._dedup_name('Test')
        self.wait_sync(wait_for_async=True)
        # Check initial sync
        self.assertTrue(local.exists('/test'))
        self.assertTrue(local.exists('/test/Test'))
        # Move to a folder containing same file to verify the dedup
        remote.move(Test_uid, '/')
        self.wait_sync(wait_for_async=True)
        self.assertEquals(remote.get_info(test_uid).name, 'test')
        self.assertEquals(remote.get_info(Test_uid).name, 'Test')
        self.assertTrue(local.exists('/test'))
        self.assertTrue(local.exists('/' + Test_dedup))
        # Move it back to a non dedup folder
        remote.move(Test_uid, '/test')
        self.wait_sync(wait_for_async=True)
        self.assertEquals(remote.get_info(test_uid).name, 'test')
        self.assertEquals(remote.get_info(Test_uid).name, 'Test')
        self.assertTrue(local.exists('/test'))
        self.assertTrue(local.exists('/test/Test'))
        # Move again to a dedup folder
        remote.move(Test_uid, '/')
        self.wait_sync(wait_for_async=True)
        self.assertEquals(remote.get_info(test_uid).name, 'test')
        self.assertEquals(remote.get_info(Test_uid).name, 'Test')
        self.assertTrue(local.exists('/' + Test_dedup))
        self.assertTrue(local.exists('/test'))
        # Move locally without renaming
        local.move('/' + Test_dedup, '/test')
        self.wait_sync(wait_for_async=True)
        self.assertEquals(remote.get_info(test_uid).name, 'test')
        self.assertEquals(remote.get_info(Test_uid).name, Test_dedup)
        # Might want go back to the original name
        self.assertTrue(local.exists('/test/' + Test_dedup))
        self.assertFalse(local.exists('/' + Test_dedup))

    def test_uppercase_lowercase_duplicate(self):
        # Duplication should be disable later
        raise SkipTest
        remote = self.remote_document_client_1
        # Test without delay might cause issue on Windows
        self.doc1 = remote.make_folder('/', 'A')
        self.wait_sync()
        self.doc2 = remote.make_folder('/', 'a')
        self.wait_sync()
        self.assertTrue(self.local_client_1.exists('/A'))
        self.assertTrue(self.local_client_1.exists('/a__1'))
        self.local_client_1.delete('/A')
        self.local_client_1.rename('/a__1', 'A')
        self.wait_sync()
        self.assertTrue(self.local_client_1.exists('/A'))
        self.assertFalse(self.local_client_1.exists('/a__1'))
        self.assertTrue(self.remote_document_client_1.exists(self.doc2))
        self.assertFalse(self.remote_document_client_1.exists(self.doc1))
