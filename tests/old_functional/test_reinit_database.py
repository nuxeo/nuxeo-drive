import time
from pathlib import Path

from .common import OS_STAT_MTIME_RESOLUTION, OneUserTest


class TestReinitDatabase(OneUserTest):
    def setUp(self):
        self.local = self.local_1
        self.remote = self.remote_document_client_1

        # Make a folder and a file
        self.remote.make_folder("/", "Test folder")
        self.file = self.remote.make_file(
            "/Test folder", "Test.txt", content=b"This is some content"
        )

        # Start engine and wait for synchronization
        self.engine_1.start()
        self.wait_sync(wait_for_async=True)

        assert self.local.exists("/Test folder")
        assert self.local.exists("/Test folder/Test.txt")

        # Destroy database but keep synced files as we just need to test the database
        self.unbind_engine(1, purge=False)
        self.bind_engine(1, start_engine=False)

    def _check_states(self):
        rows = self.engine_1.dao.get_states_from_partial_local(Path())
        for row in rows:
            assert row.pair_state == "synchronized"

    def _check_conflict_detection(self):
        assert len(self.engine_1.dao.get_conflicts()) == 1

    def test_synchronize_folderish_and_same_digest(self):
        # Start engine and wait for synchronization
        self.engine_1.start()
        self.wait_sync(wait_for_async=True)

        # Check everything is synchronized
        self._check_states()

    def test_synchronize_remote_change(self):
        # Modify the remote file
        self.remote.update(self.file, properties={"note:note": "Content has changed"})

        # Start engine and wait for synchronization
        self.engine_1.start()
        self.wait_sync(wait_for_async=True, timeout=5, fail_if_timeout=False)

        # Check that a conflict is detected
        self._check_conflict_detection()
        file_state = self.engine_1.dao.get_state_from_local(
            Path(self.workspace_title) / "Test folder/Test.txt"
        )
        assert file_state
        assert file_state.pair_state == "conflicted"

        # Assert content of the local file has not changed
        content = self.local.get_content("/Test folder/Test.txt")
        assert content == b"This is some content"

    def test_synchronize_local_change(self):
        # Modify the local file
        time.sleep(OS_STAT_MTIME_RESOLUTION)
        self.local.update_content("/Test folder/Test.txt", b"Content has changed")

        # Start engine and wait for synchronization
        self.engine_1.start()
        self.wait_sync(timeout=5, fail_if_timeout=False)

        # Check that a conflict is detected
        self._check_conflict_detection()
        file_state = self.engine_1.dao.get_state_from_local(
            Path(self.workspace_title) / "Test folder/Test.txt"
        )
        assert file_state
        assert file_state.pair_state == "conflicted"

        # Assert content of the remote file has not changed
        content = self.remote.get_note(self.file)
        assert content == b"This is some content"

    def test_synchronize_remote_and_local_change(self):
        # Modify the remote file
        self.remote.update(
            self.file, properties={"note:note": "Content has remotely changed"}
        )

        # Modify the local file
        time.sleep(OS_STAT_MTIME_RESOLUTION)
        self.local.update_content(
            "/Test folder/Test.txt", b"Content has locally changed"
        )

        # Start engine and wait for synchronization
        self.engine_1.start()
        self.wait_sync(wait_for_async=True, timeout=5, fail_if_timeout=False)

        # Check that a conflict is detected
        self._check_conflict_detection()
        file_state = self.engine_1.dao.get_state_from_local(
            Path(self.workspace_title) / "Test folder/Test.txt"
        )
        assert file_state
        assert file_state.pair_state == "conflicted"

        # Assert content of the local and remote files has not changed
        content = self.local.get_content("/Test folder/Test.txt")
        assert content == b"Content has locally changed"
        content = self.remote.get_note(self.file)
        assert content == b"Content has remotely changed"
