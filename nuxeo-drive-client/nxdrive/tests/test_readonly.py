import os
import time
import sys

from nxdrive.tests.common_unit_test import UnitTestCase
from nose.plugins.skip import SkipTest


class TestReadOnly(UnitTestCase):

    def setUp(self):
        super(TestReadOnly, self).setUp()
        self.engine_1.start()
        self.wait_sync()
        self.engine_1.stop()

    def _set_readonly_permission(self, user, doc_path, grant):
        op_input = "doc:" + doc_path
        if grant:
            self.root_remote_client.execute("Document.SetACE",
                op_input=op_input,
                user=user,
                permission="Read")
            self.root_remote_client.block_inheritance(doc_path,
                                                      overwrite=False)
        else:
            self.root_remote_client.execute("Document.SetACE",
                op_input=op_input,
                user=user,
                permission="Write",
                grant="true")

    def test_rename_readonly_file(self):
        raise SkipTest("WIP in https://jira.nuxeo.com/browse/NXDRIVE-170")
        local = self.local_client_1
        remote = self.remote_document_client_1
        # Create documents in the remote root workspace
        # then synchronize
        remote.make_folder('/', 'Test folder')
        remote.make_file('/Test folder', 'joe.odt', 'Some content')
        remote.make_file('/Test folder', 'jack.odt', 'Some content')
        remote.make_folder('/Test folder', 'Sub folder 1')
        remote.make_file('/Test folder/Sub folder 1', 'sub file 1.txt',
                         'Content')
        self._set_readonly_permission("nuxeoDriveTestUser_user_1",
                    self.TEST_WORKSPACE_PATH + '/Test folder', True)
        self.engine_1.start()
        self.wait_sync()
        self.assertTrue(local.exists('/Test folder'))
        self.assertTrue(local.exists('/Test folder/joe.odt'))
        self.assertTrue(local.exists('/Test folder/jack.odt'))
        self.assertTrue(local.exists('/Test folder/Sub folder 1'))
        self.assertTrue(local.exists(
                                '/Test folder/Sub folder 1/sub file 1.txt'))

        # Local changes
        time.sleep(self.OS_STAT_MTIME_RESOLUTION)
        # Create new file
        # Fake the readonly forcing
        local.unset_readonly('/Test folder')
        local.make_file('/Test folder', 'local.odt', 'New local content')
        # Create new folder with files
        local.make_folder('/Test folder', 'Local sub folder 2')
        local.make_file('/Test folder/Local sub folder 2',
                        'local sub file 2.txt', 'Other local content')
        # Update file
        local.unset_readonly('/Test folder/joe.odt')
        local.update_content('/Test folder/joe.odt',
                             'Some locally updated content')
        local.set_readonly('/Test folder/joe.odt')
        local.set_readonly('/Test folder')

        # TODO Might rollback if rollback only !
        self.assertFalse(remote.exists('/Test folder/local.odt'))
        self.assertFalse(remote.exists('/Test folder/Local sub folder 2'))
        self.assertFalse(remote.exists(
                    '/Test folder/Local sub folder 2/local sub file 2.txt'))
        self.assertTrue(local.exists('/Test folder/local.odt'))

        delete_folder = '/Test folder/Sub folder 1'
        # Force to remove readonly
        local.unset_readonly(delete_folder)
        local.unset_readonly('/Test folder')
        local.delete(delete_folder)
        local.set_readonly('/Test folder')
        # Should recreate ?
        self.wait_sync()
        self.assertTrue(remote.exists(delete_folder))
        self.assertTrue(local.exists(delete_folder))

    def touch(self, fname):
        try:
            with open(fname, 'w') as f:
                f.write('Test')
        except:
            return False
        return True

    def test_readonly_user_access(self):
        if os.sys.platform == 'win32':
            raise SkipTest('Readonly folder let new file creation')
        # Should not be able to create content in root folder
        fname = os.path.join(self.local_nxdrive_folder_1, 'test.txt')
        self.assertFalse(self.touch(fname),
                        "Should not be able to create in ROOT folder")
        fname = os.path.join(self.sync_root_folder_1, 'test.txt')
        self.assertTrue(self.touch(fname),
                        "Should be able to create in SYNCROOT folder")
        fname = os.path.join(self.sync_root_folder_1, 'Test folder',
                                'test.txt')
        self.assertFalse(self.touch(fname),
                        "Should be able to create in SYNCROOT folder")
        fname = os.path.join(self.sync_root_folder_1, 'Test folder',
                                'Sub folder 1', 'test.txt')
        self.assertFalse(self.touch(fname),
                        "Should be able to create in SYNCROOT folder")

    def test_file_readonly_change(self):
        if os.sys.platform == 'win32':
            raise SkipTest('Readonly folder let new file creation')
        else:
            raise SkipTest("WIP in https://jira.nuxeo.com/browse/NXDRIVE-170")
        local = self.local_client_1
        remote = self.remote_document_client_1
        # Create documents in the remote root workspace
        # then synchronize
        remote.make_folder('/', 'Test folder')
        remote.make_file('/Test folder', 'joe.odt', 'Some content')
        remote.make_file('/Test folder', 'jack.odt', 'Some content')
        remote.make_folder('/Test folder', 'Sub folder 1')
        remote.make_file('/Test folder/Sub folder 1', 'sub file 1.txt',
                         'Content')
        self._set_readonly_permission("nuxeoDriveTestUser_user_1",
                    self.TEST_WORKSPACE_PATH + '/Test folder', True)
        self.engine_1.start()
        self.wait_sync()
        self.assertTrue(local.exists('/Test folder'))
        self.assertTrue(local.exists('/Test folder/joe.odt'))
        self.assertTrue(local.exists('/Test folder/jack.odt'))
        self.assertTrue(local.exists('/Test folder/Sub folder 1'))
        self.assertTrue(local.exists(
                                '/Test folder/Sub folder 1/sub file 1.txt'))

        # Remove the readonly
        self._set_readonly_permission("nuxeoDriveTestUser_user_1",
                    self.TEST_WORKSPACE_PATH + '/Test folder', False)
        self.wait_sync()
        fname = os.path.join(self.sync_root_folder_1, 'Test folder',
                                'test.txt')
        fname2 = os.path.join(self.sync_root_folder_1, 'Test folder',
                                'Sub folder 1', 'test.txt')
        # Check it works
        self.assertTrue(self.touch(fname))
        self.assertTrue(self.touch(fname2))

        # First remove the files
        os.remove(fname)
        os.remove(fname2)
        # Put it back readonly
        self._set_readonly_permission("nuxeoDriveTestUser_user_1",
                    self.TEST_WORKSPACE_PATH + '/Test folder', True)
        self.wait_sync()

        # Check it works
        self.assertFalse(self.touch(fname))
        self.assertFalse(self.touch(fname2))
