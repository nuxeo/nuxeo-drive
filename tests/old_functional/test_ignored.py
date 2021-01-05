from pathlib import Path

from .common import OneUserTest


class TestIgnored(OneUserTest):
    def test_ignore_file(self):
        local = self.local_1
        remote = self.remote_document_client_1
        dao = self.engine_1.dao

        self.engine_1.start()
        self.wait_sync(wait_for_async=True)

        remote.make_file("/", "abcde.txt", content=b"Some content.")
        remote.make_file("/", "abcde.txt", content=b"Some other content.")

        self.wait_sync(wait_for_async=True)
        assert local.exists("/abcde.txt")
        # Check we only have one file locally
        assert len(dao.get_local_children(Path("/"))) == 1
        # Check that there is an error
        errors = dao.get_errors()
        assert len(errors) == 1
        error_id = errors[0].id

        # Ignore the error
        self.engine_1.ignore_pair(error_id, errors[0].last_error)

        self.wait_sync(wait_for_async=True)

        # Check there are no errors
        assert not dao.get_errors()
        # Check there is an ignored file
        unsynceds = dao.get_unsynchronizeds()
        assert len(unsynceds) == 1
        # Check that the ignored file is the same as the error that appeared previously
        assert unsynceds[0].id == error_id

        # Force the engine to do a full scan again
        self.engine_1._remote_watcher._last_remote_full_scan = None
        self.wait_sync(wait_for_async=True)

        # Check that there are no errors back
        assert not dao.get_errors()
        assert dao.get_unsynchronized_count() == 1
