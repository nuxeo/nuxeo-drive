# coding: utf-8
import os

import pytest

from . import RemoteTest
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

    @pytest.mark.randombug("NXDRIVE-818", mode="BYPASS")
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
        self.engine_1.remote = RemoteTest(
            pytest.nuxeo_url,
            self.user_1,
            "nxdrive-test-administrator-device",
            pytest.version,
            password=self.password_1,
        )
        error = OSError("No space left on device")
        self.engine_1.remote.make_download_raise(error)
        self.engine_1.start()
        # By default engine will not consider being syncCompleted
        # because of the blacklist
        self.wait_sync(
            wait_for_async=True, timeout=10, fail_if_timeout=False, enforce_errors=False
        )
        # Temporary download file (.nxpart) should be created locally
        # but not renamed then removed
        # Synchronization should not fail: doc pair should be
        # blacklisted and there should be 1 error
        self.assertNxPart("/", "test_KO.odt")
        assert not local.exists("/test_KO.odt")
        states_in_error = self.engine_1.get_dao().get_errors(limit=0)
        assert len(states_in_error) == 1
        assert states_in_error[0].remote_name == "test_KO.odt"

        # Create another file in the remote root workspace
        remote.make_file("/", "test_OK.odt", content=b"Some small content.")

        # Synchronize without simulating any error
        self.engine_1.remote.make_download_raise(None)
        self.wait_sync(
            wait_for_async=True, timeout=10, fail_if_timeout=False, enforce_errors=False
        )
        # Remote file should be created locally
        assert local.exists("/test_OK.odt")
        # Blacklisted file should be ignored as delay (60 seconds by default)
        # is not expired and there should still be 1 error
        assert not local.exists("/test_KO.odt")
        states_in_error = self.engine_1.get_dao().get_errors(limit=0)
        assert len(states_in_error) == 1
        assert states_in_error[0].remote_name == "test_KO.odt"

        # Retry to synchronize blacklisted file still simulating
        # a "No space left on device" error
        self.engine_1.remote.make_download_raise(error)
        # Re-queue pairs in error
        self.queue_manager_1.requeue_errors()
        self.wait_sync(timeout=10, fail_if_timeout=False, enforce_errors=False)
        # Doc pair should be blacklisted again
        # and there should still be 1 error
        self.assertNxPart("/", "test_KO.odt")
        assert not local.exists("/test_KO.odt")
        states_in_error = self.engine_1.get_dao().get_errors(limit=0)
        assert len(states_in_error) == 1
        assert states_in_error[0].remote_name == "test_KO.odt"

        # Synchronize without simulating any error, as if space had been made
        # available on device
        self.engine_1.remote.make_download_raise(None)
        # Re-queue pairs in error
        self.queue_manager_1.requeue_errors()
        self.wait_sync(enforce_errors=False)
        # Previously blacklisted file should be created locally
        # and there should be no more errors left
        self.assertNxPart("/", "test_KO.odt")
        assert local.exists("/test_KO.odt")
        states_in_error = self.engine_1.get_dao().get_errors(limit=0)
        assert not states_in_error
