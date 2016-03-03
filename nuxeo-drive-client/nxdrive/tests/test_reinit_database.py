import time

from nxdrive.tests.common import OS_STAT_MTIME_RESOLUTION
from nxdrive.tests.common_unit_test import UnitTestCase


class TestReinitDatabase(UnitTestCase):

    def setUp(self):
        super(TestReinitDatabase, self).setUp()

        self.local = self.local_client_1
        self.remote = self.remote_document_client_1

        # Make a folder and a file
        self.test_remote_folder_id = self.remote.make_folder('/', 'Test folder')
        self.remote.make_file('/Test folder', 'Test.txt', 'This is some content')

        # Start engine and wait for synchronization
        self.engine_1.start()
        self.wait_sync(wait_for_async=True)

        # Verify that everything is synchronized
        self.assertTrue(self.local.exists('/Test folder'), 'Local folder should exist')
        self.assertTrue(self.local.exists('/Test folder/Test.txt'), 'Local file should exist')

        # Destroy database
        self._reinit_database()

    def _check_states(self):
        rows = self.engine_1.get_dao().get_states_from_partial_local('/')
        for row in rows:
            self.assertEquals(row.pair_state, 'synchronized')

    def _reinit_database(self):
        # Unbind engine
        self.manager_1.unbind_engine(self.engine_1.get_uid())
        # Re-bind engine
        self.engine_1 = self.manager_1.bind_server(self.local_nxdrive_folder_1, self.nuxeo_url, self.user_1,
                                                   self.password_1, start_engine=False)
        self.engine_1.syncCompleted.connect(self.app.sync_completed)
        self.engine_1.get_remote_watcher().remoteScanFinished.connect(self.app.remote_scan_completed)
        self.engine_1.get_remote_watcher().changesFound.connect(self.app.remote_changes_found)
        self.engine_1.get_remote_watcher().noChangesFound.connect(self.app.no_remote_changes_found)

    def _check_conflict_automatic_resolution(self):
        self.assertEquals(len(self.engine_1.get_dao().get_conflicts()), 0)

    def _check_conflict_detection(self):
        self.assertEquals(len(self.engine_1.get_dao().get_conflicts()), 1)

    def test_synchronize_folderish_and_same_digest(self):
        # Start engine and wait for synchronization
        self.engine_1.start()
        self.wait_remote_scan()
        # Check everything is synchronized
        self._check_states()

    def test_synchronize_remote_change(self):
        # Modify the remote file
        self.remote.update_content('/Test folder/Test.txt', 'Content has changed')
        # Start engine and wait for synchronization
        self.engine_1.start()
        self.wait_sync(wait_for_async=True, timeout=5, fail_if_timeout=False)
        # Check that a conflict is detected
        self._check_conflict_detection()
        file_state = self.engine_1.get_dao().get_state_from_local('/' + self.workspace_title + '/Test folder/Test.txt')
        self.assertIsNotNone(file_state)
        self.assertEqual(file_state.pair_state, 'conflicted')
        # Assert content of the local file has not changed
        self.assertEquals(self.local.get_content('/Test folder/Test.txt'),
                          'This is some content',
                          'Local content should not have changed')

    def test_synchronize_local_change(self):
        # Modify the local file
        time.sleep(OS_STAT_MTIME_RESOLUTION)
        self.local.update_content('/Test folder/Test.txt', 'Content has changed')
        # Start engine and wait for synchronization
        self.engine_1.start()
        self.wait_sync(timeout=5, fail_if_timeout=False)
        # Check that a conflict is detected
        self._check_conflict_detection()
        file_state = self.engine_1.get_dao().get_state_from_local('/' + self.workspace_title + '/Test folder/Test.txt')
        self.assertIsNotNone(file_state)
        self.assertEqual(file_state.pair_state, 'conflicted')
        # Assert content of the remote file has not changed
        self.assertEquals(self.remote.get_content('/Test folder/Test.txt'),
                          'This is some content',
                          'Remote content should not have changed')

    def test_synchronize_remote_and_local_change(self):
        # Modify the remote file
        self.remote.update_content('/Test folder/Test.txt',
                                   'Content has remotely changed')
        # Modify the local file
        time.sleep(OS_STAT_MTIME_RESOLUTION)
        self.local.update_content('/Test folder/Test.txt', 'Content has locally changed')
        # Start engine and wait for synchronization
        self.engine_1.start()
        self.wait_sync(wait_for_async=True, timeout=5, fail_if_timeout=False)
        # Check that a conflict is detected
        self._check_conflict_detection()
        file_state = self.engine_1.get_dao().get_state_from_local('/' + self.workspace_title + '/Test folder/Test.txt')
        self.assertIsNotNone(file_state)
        self.assertEqual(file_state.pair_state, 'conflicted')
        # Assert content of the local and remote files has not changed
        self.assertEquals(self.local.get_content('/Test folder/Test.txt'),
                          'Content has locally changed',
                          'Local content should not have changed')
        self.assertEquals(self.remote.get_content('/Test folder/Test.txt'),
                          'Content has remotely changed',
                          'Remote content should not have changed')
