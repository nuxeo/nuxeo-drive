import os
import random
from unittest.mock import patch

from nxdrive.constants import NO_SPACE_ERRORS

from .common import OneUserTest


class TestLocalStorageIssue(OneUserTest):
    def test_local_invalid_timestamp(self):
        # Synchronize root workspace
        self.engine_1.start()
        self.wait_sync(wait_for_async=True)
        assert self.local_1.exists("/")
        self.engine_1.stop()
        self.local_1.make_file("/", "Test.txt", content=b"plop")
        os.utime(self.local_1.abspath("/Test.txt"), (0, 999_999_999_999_999))
        self.engine_1.start()
        self.wait_sync()
        children = self.remote_document_client_1.get_children_info(self.workspace)
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
        uid = remote.make_file("/", "test_NG.odt", content=b"Some large content.")

        # We pick a random error because there is no facility
        # to parametrize a method from a class derived from
        # something other than object.
        errno = random.choice(list(NO_SPACE_ERRORS))
        error = OSError(errno, f"(Mock) {os.strerror(errno)}")

        # Synchronize simulating a disk space related error
        bad_remote = self.get_bad_remote()
        bad_remote.make_download_raise(error)

        with patch.object(self.engine_1, "remote", new=bad_remote):
            self.engine_1.start()

            # By default engine will not consider being syncCompleted
            # because of the temporary ignored files
            self.wait_sync(
                wait_for_async=True, fail_if_timeout=False, enforce_errors=False
            )

            # - temporary download file should be created locally but not moved
            # - synchronization should not fail: doc pair should be temporary ignored
            # - and there should be 1 error
            assert (self.engine_1.download_dir / uid).is_dir()
            assert not local.exists("/test_NG.odt")
            errors = self.engine_1.dao.get_errors(limit=0)
            assert len(errors) == 1
            assert errors[0].remote_name == "test_NG.odt"

            assert self.engine_1.is_paused()

            # Create another file in the remote root workspace
            remote.make_file("/", "test_OK.odt", content=b"Some small content.")

        # No more errors starting here
        self.engine_1.resume()
        self.wait_sync(wait_for_async=True, fail_if_timeout=False, enforce_errors=False)

        # Remote file should be created locally
        assert local.exists("/test_OK.odt")

        # Temporary ignored file should still be ignored as delay (60 seconds by default)
        # is not expired and there should still be 1 error
        assert not local.exists("/test_NG.odt")
        errors = self.engine_1.dao.get_errors(limit=0)
        assert len(errors) == 1
        assert errors[0].remote_name == "test_NG.odt"

        # Retry to synchronize the temporary ignored file, but still simulating
        # the same disk space related error
        with patch.object(self.engine_1, "remote", new=bad_remote):
            # Re-queue pairs in error
            self.queue_manager_1.requeue_errors()
            self.wait_sync(fail_if_timeout=False, enforce_errors=False)

            # - temporary download file should be created locally but not moved
            # - doc pair should be temporary ignored again
            # - and there should still be 1 error
            assert (self.engine_1.download_dir / uid).is_dir()
            assert not local.exists("/test_NG.odt")
            errors = self.engine_1.dao.get_errors(limit=0)
            assert len(errors) == 1
            assert errors[0].remote_name == "test_NG.odt"

        # Synchronize without simulating any error, as if space had been made
        # available on device
        self.engine_1.resume()

        # Re-queue pairs in error
        self.queue_manager_1.requeue_errors()
        self.wait_sync(enforce_errors=False)

        # Previously temporary ignored file should be created locally
        # and there should be no more errors left
        assert not (self.engine_1.download_dir / uid).is_dir()
        assert local.exists("/test_NG.odt")
        assert not self.engine_1.dao.get_errors(limit=0)
