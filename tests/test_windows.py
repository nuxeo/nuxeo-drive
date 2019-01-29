# coding: utf-8
import shutil
import time

import pytest

from nxdrive.constants import WINDOWS
from . import LocalTest
from .common import (
    OS_STAT_MTIME_RESOLUTION,
    REMOTE_MODIFICATION_TIME_RESOLUTION,
    UnitTestCase,
)

if WINDOWS:
    from nxdrive.osi.windows import registry


class TestWindows(UnitTestCase):
    def test_local_replace(self):
        local = LocalTest(self.local_test_folder_1)
        remote = self.remote_document_client_1
        self.engine_1.start()
        self.wait_sync(wait_for_async=True)

        # Create 2 files with the same name but different content
        # in separate folders
        local.make_file("/", "test.odt", content=b"Some content.")
        local.make_folder("/", "folder")
        shutil.copyfile(
            self.local_test_folder_1 / "test.odt",
            self.local_test_folder_1 / "folder" / "test.odt",
        )
        local.update_content("/folder/test.odt", content=b"Updated content.")

        # Copy the newest file to the root workspace and synchronize it
        sync_root = self.local_nxdrive_folder_1 / self.workspace_title
        test_file = self.local_test_folder_1 / "folder" / "test.odt"
        shutil.copyfile(test_file, sync_root / "test.odt")
        self.wait_sync()
        assert remote.exists("/test.odt")
        assert remote.get_content("/test.odt") == b"Updated content."

        # Copy the oldest file to the root workspace and synchronize it.
        # First wait a bit for file time stamps to increase enough.
        time.sleep(OS_STAT_MTIME_RESOLUTION)
        shutil.copyfile(self.local_test_folder_1 / "test.odt", sync_root / "test.odt")
        self.wait_sync()
        assert remote.exists("/test.odt")
        assert remote.get_content("/test.odt") == b"Some content."

    def test_concurrent_file_access(self):
        """Test update/deletion of a locally locked file.

        This is to simulate downstream synchronization of a file opened (thus
        locked) by any program under Windows, typically MS Word.
        The file should be blacklisted and not prevent synchronization of other
        pending items.
        Once the file is unlocked and the cooldown period is over it should be
        synchronized.
        """
        # Bind the server and root workspace
        self.engine_1.start()
        self.wait_sync(wait_for_async=True)

        # Get local and remote clients
        local = self.local_1
        remote = self.remote_document_client_1

        # Create file in the remote root workspace
        remote.make_file("/", "test_update.docx", content=b"Some content to update.")
        remote.make_file("/", "test_delete.docx", content=b"Some content to delete.")

        # Launch first synchronization
        self.wait_sync(wait_for_async=True)
        assert local.exists("/test_update.docx")
        assert local.exists("/test_delete.docx")

        # Open locally synchronized files to lock them and generate a
        # WindowsError when trying to update / delete them
        file1_path = local.get_info("/test_update.docx").filepath
        file2_path = local.get_info("/test_delete.docx").filepath
        with open(file1_path, "rb"), open(file2_path, "rb"):
            # Update /delete existing remote files and create a new remote file
            # Wait for 1 second to make sure the file's last modification time
            # will be different from the pair state's last remote update time
            time.sleep(REMOTE_MODIFICATION_TIME_RESOLUTION)
            remote.update_content("/test_update.docx", b"Updated content.")
            remote.delete("/test_delete.docx")
            remote.make_file("/", "other.docx", content=b"Other content.")

            # Synchronize
            self.wait_sync(
                wait_for_async=True, enforce_errors=False, fail_if_timeout=False
            )
            if WINDOWS:
                # As local file are locked, a WindowsError should occur during the
                # local update process, therefore:
                # - Opened local files should still exist and not have been
                #   modified
                # - Synchronization should not fail: doc pairs should be
                #   blacklisted and other remote modifications should be
                #   locally synchronized
                assert local.exists("/test_update.docx")
                assert (
                    local.get_content("/test_update.docx") == b"Some content to update."
                )
                assert local.exists("/test_delete.docx")
                assert (
                    local.get_content("/test_delete.docx") == b"Some content to delete."
                )
                assert local.exists("/other.docx")
                assert local.get_content("/other.docx") == b"Other content."

                # Synchronize again
                self.wait_sync(enforce_errors=False, fail_if_timeout=False)
                # Blacklisted files should be ignored as delay (60 seconds by
                # default) is not expired, nothing should have changed
                assert local.exists("/test_update.docx")
                assert (
                    local.get_content("/test_update.docx") == b"Some content to update."
                )
                assert local.exists("/test_delete.docx")
                assert (
                    local.get_content("/test_delete.docx") == b"Some content to delete."
                )

        if WINDOWS:
            # Cancel error delay to force retrying synchronization of pairs in error
            self.queue_manager_1.requeue_errors()
            self.wait_sync()

            # Previously blacklisted files should be updated / deleted locally,
            # temporary download file should not be there anymore and there
            # should be no pending items left
        else:
            self.assertNxPart("/", "test_update.docx")

        assert local.exists("/test_update.docx")
        assert local.get_content("/test_update.docx") == b"Updated content."
        assert not local.exists("/test_delete.docx")

    @pytest.mark.skipif(not WINDOWS, reason="Windows only.")
    def test_registry_configuration(self):
        """ Test the configuration stored in the registry. """
        from nxdrive.osi.windows import registry

        osi = self.manager_1.osi
        key = "Software\\Nuxeo\\Drive"

        assert not osi.get_system_configuration()
        self.addCleanup(registry.delete, key)

        # Add new parameters
        registry.write(key, {"update-site-url": "http://no.where"})
        registry.write(key, {"ChAnnEL": "beta"})

        conf = osi.get_system_configuration()
        assert conf["update_site_url"] == "http://no.where"
        assert conf["channel"] == "beta"


@pytest.mark.skipif(not WINDOWS, reason="Windows only.")
def test_registry_create():
    k = f"Software\\Classes\\directory\\shell\\MockedApplicationName"
    try:
        registry.create(k)
        assert registry.exists(k)
    finally:
        assert registry.delete(k)


@pytest.mark.skipif(not WINDOWS, reason="Windows only.")
def test_registry_delete():
    k = f"Software\\Classes\\directory\\shell\\MockedApplicationNameUnknown"
    assert registry.delete(k)


@pytest.mark.skipif(not WINDOWS, reason="Windows only.")
def test_registry_delete_value():
    k = f"Software\\Classes\\directory\\shell\\MockedApplicationNameUnknown"
    v = "nonSenseValue"
    assert registry.delete_value(k, v)


@pytest.mark.skipif(not WINDOWS, reason="Windows only.")
def test_registry_exists():
    k = f"Software\\Classes\\directory\\shell\\MockedApplicationNameUnknown"
    assert not registry.exists(k)


@pytest.mark.skipif(not WINDOWS, reason="Windows only.")
def test_registry_read():
    k = "Software\\MockedApplicationName"
    assert not registry.read(k)
    assert registry.delete(k)


@pytest.mark.skipif(not WINDOWS, reason="Windows only.")
def test_registry_write():
    k1 = "Software\\MockedApplicationName1"
    k2 = "Software\\MockedApplicationName2"
    values = {"a": "foo", "b": "42"}

    try:
        assert registry.write(k1, "bar")
        assert registry.write(k2, values)
        assert not registry.read(f"{k1}\\unknown")
        assert registry.read(k2) == values
    finally:
        assert registry.delete(k1)
        assert registry.delete(k2)
