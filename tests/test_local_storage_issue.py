# coding: utf-8
import errno
import os
from unittest.mock import patch

from .common import UnitTestCase


class TestLocalStorageSpaceIssue(UnitTestCase):
    def test_local_invalid_timestamp(self):
        # Synchronize root workspace
        self.engine_1.start()
        self.wait_sync(wait_for_async=True)
        assert self.local_1.exists("/")
        self.engine_1.stop()
        self.local_1.make_file("/", "Test.txt", content=b"plop")
        os.utime(self.local_1.abspath("/Test.txt"), (0, 999999999999999))
        self.engine_1.start()
        self.wait_sync()
        children = self.remote_document_client_1.get_children_info(self.workspace_1)
        assert len(children) == 1
        assert children[0].name == "Test.txt"

    def test_synchronize_no_space_left_on_device(self):
        local = self.local_1
        remote = self.remote_document_client_1

        # Synchronize root workspace
        self.engine_1.start()
        self.wait_sync(wait_for_async=True)
        assert local.exists("/")
        self.engine_1.stop()

        # Create a file in the remote root workspace
        remote.make_file("/", "test_KO.odt", content=b"Some large content.")

        # Synchronize simulating a "No space left on device" error
        bad_remote = self.get_bad_remote()
        error = OSError(errno.ENOSPC, "(Mock) No space left on device")
        bad_remote.make_download_raise(error)

        with patch.object(self.engine_1, "remote", new=bad_remote):
            self.engine_1.start()

            # By default engine will not consider being syncCompleted
            # because of the blacklist
            self.wait_sync(
                wait_for_async=True, fail_if_timeout=False, enforce_errors=False
            )

            # Temporary download file (.nxpart) should be created locally
            # but not renamed then removed
            # Synchronization should not fail: doc pair should be
            # blacklisted and there should be 1 error
            self.assertNxPart("/", "test_KO.odt")
            assert not local.exists("/test_KO.odt")
            errors = self.engine_1.get_dao().get_errors(limit=0)
            assert len(errors) == 1
            assert errors[0].remote_name == "test_KO.odt"

            assert self.engine_1.is_paused()

            # Create another file in the remote root workspace
            remote.make_file("/", "test_OK.odt", content=b"Some small content.")

        # No more errors starting here
        self.engine_1.resume()
        self.wait_sync(wait_for_async=True, fail_if_timeout=False, enforce_errors=False)

        # Remote file should be created locally
        assert local.exists("/test_OK.odt")

        # Blacklisted file should be ignored as delay (60 seconds by default)
        # is not expired and there should still be 1 error
        assert not local.exists("/test_KO.odt")
        errors = self.engine_1.get_dao().get_errors(limit=0)
        assert len(errors) == 1
        assert errors[0].remote_name == "test_KO.odt"

        # Retry to synchronize blacklisted file still simulating
        # a "No space left on device" error
        with patch.object(self.engine_1, "remote", new=bad_remote):
            # Re-queue pairs in error
            self.queue_manager_1.requeue_errors()
            self.wait_sync(fail_if_timeout=False, enforce_errors=False)

            # Doc pair should be blacklisted again
            # and there should still be 1 error
            self.assertNxPart("/", "test_KO.odt")
            assert not local.exists("/test_KO.odt")
            errors = self.engine_1.get_dao().get_errors(limit=0)
            assert len(errors) == 1
            assert errors[0].remote_name == "test_KO.odt"

        # Synchronize without simulating any error, as if space had been made
        # available on device
        self.engine_1.resume()

        # Re-queue pairs in error
        self.queue_manager_1.requeue_errors()
        self.wait_sync(enforce_errors=False)

        # Previously blacklisted file should be created locally
        # and there should be no more errors left
        self.assertNxPart("/", "test_KO.odt")
        assert local.exists("/test_KO.odt")
        assert not self.engine_1.get_dao().get_errors(limit=0)
