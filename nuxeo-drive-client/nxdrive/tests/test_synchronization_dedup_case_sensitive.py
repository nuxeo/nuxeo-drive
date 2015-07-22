import os

from nxdrive.tests.common_unit_test import UnitTestCase
from nxdrive.logging_config import get_logger

log = get_logger(__name__)


class TestDedupSensitiveCaseSync(UnitTestCase):

    def setUp(self):
        super(TestDedupSensitiveCaseSync, self).setUp()
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
        self.assertEquals(len(local.get_children_info('/')), 2)
        self.assertEquals(remote.get_info(joe_uid).name, 'joe.odt')
        self.assertEquals(remote.get_info(joe2_uid).name, 'joe.odt')
        local.update_content(joe_path, 'Update content 1')
        local.update_content(joe2_path, 'Update content 2')
        self.wait_sync(wait_for_async=True)
        # Verify the content has changed
        self.assertEquals(remote.get_content(joe_uid), 'Update content 1')
        self.assertEquals(remote.get_content(joe2_uid), 'Update content 2')
        # Verify the name are the same
        self.assertEquals(remote.get_info(joe_uid).name, 'joe.odt')
        self.assertEquals(remote.get_info(joe2_uid).name, 'joe.odt')
        local.delete(joe_path)
        self.wait_sync(wait_for_async=True)
        self.assertTrue(remote.exists(joe2_uid))
        self.assertFalse(remote.exists(joe_uid))
        self.assertTrue(local.exists(joe2_path))

    def test_dedup_folders(self):
        local = self.local_client_1
        remote = self.remote_document_client_1
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
        self.assertEquals(len(local.get_children_info('/')), 2)
        self.assertEquals(remote.get_info(test_uid).name, 'test')
        self.assertEquals(remote.get_info(test2_uid).name, 'test')

    def test_dedup_move_files(self):
        local = self.local_client_1
        remote = self.remote_document_client_1
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
        self.assertEquals(remote.get_info(joe_uid).name, 'joe.odt')
        self.assertEquals(remote.get_info(joe2_uid).name, 'joe.odt')
        self.assertTrue(local.exists('/test/' + joe2_dedup))
        self.assertTrue(local.exists('/test/joe.odt'))
        # Move it back to a non dedup folder
        remote.move(joe2_uid, '/')
        self.wait_sync(wait_for_async=True)
        self.assertEquals(remote.get_info(joe_uid).name, 'joe.odt')
        self.assertEquals(remote.get_info(joe2_uid).name, 'joe.odt')
        self.assertTrue(local.exists('/joe.odt'))
        self.assertTrue(local.exists('/test/joe.odt'))
        # Move again to a dedup folder
        remote.move(joe2_uid, '/test')
        self.wait_sync(wait_for_async=True)
        self.assertEquals(remote.get_info(joe_uid).name, 'joe.odt')
        self.assertEquals(remote.get_info(joe2_uid).name, 'joe.odt')
        self.assertTrue(local.exists('/test/' + joe2_dedup))
        self.assertTrue(local.exists('/test/joe.odt'))
        # Move locally without renaming
        local.move('/test/' + joe2_dedup, '/')
        self.wait_sync(wait_for_async=True)
        self.assertEquals(remote.get_info(joe_uid).name, 'joe.odt')
        self.assertEquals(remote.get_info(joe2_uid).name, joe2_dedup)
        # Might want go back to the original name
        self.assertTrue(local.exists('/' + joe2_dedup))
        self.assertTrue(local.exists('/test/joe.odt'))

    def test_dedup_move_folders(self):
        local = self.local_client_1
        remote = self.remote_document_client_1
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
        self.assertEquals(remote.get_info(test_uid).name, 'test')
        self.assertEquals(remote.get_info(test2_uid).name, 'test')
        self.assertTrue(local.exists('/test'))
        self.assertTrue(local.exists('/' + test2_dedup))
        # Move it back to a non dedup folder
        remote.move(test2_uid, '/test')
        self.wait_sync(wait_for_async=True)
        self.assertEquals(remote.get_info(test_uid).name, 'test')
        self.assertEquals(remote.get_info(test2_uid).name, 'test')
        self.assertTrue(local.exists('/test'))
        self.assertTrue(local.exists('/test/test'))
        # Move again to a dedup folder
        remote.move(test2_uid, '/')
        self.wait_sync(wait_for_async=True)
        self.assertEquals(remote.get_info(test_uid).name, 'test')
        self.assertEquals(remote.get_info(test2_uid).name, 'test')
        self.assertTrue(local.exists('/' + test2_dedup))
        self.assertTrue(local.exists('/test'))
        # Move locally without renaming
        local.move('/' + test2_dedup, '/test')
        self.wait_sync(wait_for_async=True)
        self.assertEquals(remote.get_info(test_uid).name, 'test')
        self.assertEquals(remote.get_info(test2_uid).name, test2_dedup)
        # Might want go back to the original name
        self.assertTrue(local.exists('/test/' + test2_dedup))
        self.assertFalse(local.exists('/' + test2_dedup))
