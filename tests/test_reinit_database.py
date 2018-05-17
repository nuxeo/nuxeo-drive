# coding: utf-8
import time

from .common import OS_STAT_MTIME_RESOLUTION
from .common_unit_test import UnitTestCase


class TestReinitDatabase(UnitTestCase):

    def setUp(self):
        self.local = self.local_1
        self.remote = self.remote_document_client_1

        # Make a folder and a file
        self.remote.make_folder('/', 'Test folder')
        self.remote.make_file('/Test folder', 'Test.txt',
                              'This is some content')

        # Start engine and wait for synchronization
        self.engine_1.start()
        self.wait_sync(wait_for_async=True)

        # Verify that everything is synchronized
        assert self.local.exists('/Test folder')
        assert self.local.exists('/Test folder/Test.txt')

        # Destroy database
        self.unbind_engine(1)
        self.bind_engine(1, start_engine=False)

    def _check_states(self):
        rows = self.engine_1.get_dao().get_states_from_partial_local('/')
        for row in rows:
            assert row.pair_state == 'synchronized'

    def _check_conflict_detection(self):
        assert len(self.engine_1.get_dao().get_conflicts()) == 1

    def test_synchronize_folderish_and_same_digest(self):
        # Start engine and wait for synchronization
        self.engine_1.start()
        self.wait_remote_scan()

        # Check everything is synchronized
        self._check_states()

    def test_synchronize_remote_change(self):
        # Modify the remote file
        self.remote.update_content('/Test folder/Test.txt',
                                   'Content has changed')

        # Start engine and wait for synchronization
        self.engine_1.start()
        self.wait_sync(wait_for_async=True, timeout=5, fail_if_timeout=False)

        # Check that a conflict is detected
        self._check_conflict_detection()
        file_state = self.engine_1.get_dao().get_state_from_local(
            '/' + self.workspace_title + '/Test folder/Test.txt')
        assert file_state
        assert file_state.pair_state == 'conflicted'

        # Assert content of the local file has not changed
        content = self.local.get_content('/Test folder/Test.txt')
        assert content == 'This is some content'

    def test_synchronize_local_change(self):
        # Modify the local file
        time.sleep(OS_STAT_MTIME_RESOLUTION)
        self.local.update_content('/Test folder/Test.txt',
                                  'Content has changed')

        # Start engine and wait for synchronization
        self.engine_1.start()
        self.wait_sync(timeout=5, fail_if_timeout=False)

        # Check that a conflict is detected
        self._check_conflict_detection()
        file_state = self.engine_1.get_dao().get_state_from_local(
            '/' + self.workspace_title + '/Test folder/Test.txt')
        assert file_state
        assert file_state.pair_state == 'conflicted'

        # Assert content of the remote file has not changed
        content = self.remote.get_content('/Test folder/Test.txt')
        assert content == 'This is some content'

    def test_synchronize_remote_and_local_change(self):
        # Modify the remote file
        self.remote.update_content('/Test folder/Test.txt',
                                   'Content has remotely changed')

        # Modify the local file
        time.sleep(OS_STAT_MTIME_RESOLUTION)
        self.local.update_content('/Test folder/Test.txt',
                                  'Content has locally changed')

        # Start engine and wait for synchronization
        self.engine_1.start()
        self.wait_sync(wait_for_async=True, timeout=5, fail_if_timeout=False)

        # Check that a conflict is detected
        self._check_conflict_detection()
        file_state = self.engine_1.get_dao().get_state_from_local(
            '/' + self.workspace_title + '/Test folder/Test.txt')
        assert file_state
        assert file_state.pair_state == 'conflicted'

        # Assert content of the local and remote files has not changed
        content = self.local.get_content('/Test folder/Test.txt')
        assert content == 'Content has locally changed'
        content = self.remote.get_content('/Test folder/Test.txt')
        assert content == 'Content has remotely changed'
