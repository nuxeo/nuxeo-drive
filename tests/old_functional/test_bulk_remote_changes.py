"""
Technical Background: GetChildren API can throw error
    due to network issues or server load.
    GetChildren API is also called when processing remote events.

Issue: When processing remote event, a error in GetChildren API
    (for a folder) call results in drive failing to process the
    remaining remote events in the queue.

Fix: Handle the error in GetChildren API gracefully and re-queue
    same folder again for another remote scan

Testing: This issue can be testing by simulating network of the API
    using a mock framework:
    1. Emulate the GetChildren API error by mocking the
       Remote.get_fs_children method
    2. The mocked method will raise an exception on demand
       to simulate the server side / network errors

Note: searching for the following regular expression in log file
    will filter the manual test case:
    STEP:|VERIFY:|Error:
"""

from logging import getLogger
from time import sleep
from unittest.mock import patch

from nuxeo.utils import version_lt
from requests import ConnectionError

from nxdrive.client.remote_client import Remote
from nxdrive.objects import RemoteFileInfo

from .common import TEST_DEFAULT_DELAY, TwoUsersTest

log = getLogger(__name__)


class TestBulkRemoteChanges(TwoUsersTest):
    """
    Test Bulk Remote Changes when network error happen in get_children_info()
    will simulate network error when required.  test_many_changes method will
    make server side changes, simulate error for GetChildren API and still
    verify if all remote changes are successfully synced.
    """

    def test_many_changes(self):
        """
        Objective: The objective is to make a lot of remote changes (including a folder
        modified) and wait for nuxeo-drive to successfully sync even if network error
        happens.

        1. Configure drive and wait for sync
        2. Create 3 folders folder1, folder2 and shared
        3. Create files inside the 3 folders: folder1/file1.txt, folder2/file2.txt,
            shared/readme1.txt, shared/readme2.txt
        4. Wait for 3 folders, 4 files to sync to local PC
        5. Check the 3 folders and 4 files are synced to local PC
        6. Trigger simulation of network error for GetChildren API using the mock
           (2 successive failures)
        7. Do the following changes in DM side in same order:
            I.   Create 'folder1/sample1.txt'
            II.  Delete 'shared' folder, and immediately restore 'shared' folder
            IV.  Restore 'shared/readme1.txt'
            V.   Create 'shared/readme3.txt'
            VI.  Create 'folder2/sample2.txt'
        8. Wait for remote changes to sync for unaffected folders folder1 and folder2
        9. Check that folder1/sample1.txt, folder2/sample2.txt are synced to local PC
        10. Sleep for two remote scan attempts (to compensate for two network failures)
        11. Check if two files 'shared/readme1.txt' and 'shared/readme3.txt' are synced
        to local PC.
        """
        local = self.local_1
        remote = self.remote_document_client_1
        network_error = 2

        self.engine_1.start()
        self.wait_sync(wait_for_async=True)

        # create some folders on the server
        folder1 = remote.make_folder(self.workspace, "folder1")
        folder2 = remote.make_folder(self.workspace, "folder2")
        shared = remote.make_folder(self.workspace, "shared")

        remote.make_file(folder1, "file1.txt", content=b"This is a sample file1")
        remote.make_file(folder2, "file2.txt", content=b"This is a sample file2")
        readme1 = remote.make_file(
            shared, "readme1.txt", content=b"This is a readme file"
        )
        remote.make_file(shared, "readme2.txt", content=b"This is a readme file")

        self.wait_sync(wait_for_async=True)

        assert local.exists("/folder1")
        assert local.exists("/folder2")
        assert local.exists("/shared")
        assert local.exists("/folder1/file1.txt")
        assert local.exists("/folder2/file2.txt")
        assert local.exists("/shared/readme1.txt")
        assert local.exists("/shared/readme2.txt")

        def get_children_info(self, *args, **kwargs):
            nonlocal network_error
            if network_error > 0:
                network_error -= 1
                # Simulate a network error during the call to NuxeoDrive.GetChildren
                raise ConnectionError(
                    "Network error simulated for NuxeoDrive.GetChildren"
                )
            return Remote.get_fs_children(self.engine_1.remote, *args, **kwargs)

        def mock_method_factory(original):
            def wrapped_method(data):
                data["canScrollDescendants"] = True
                return original(data)

            return wrapped_method

        with patch.object(
            remote, "get_children_info", new=get_children_info
        ), patch.object(
            RemoteFileInfo,
            "from_dict",
            wraps=mock_method_factory(RemoteFileInfo.from_dict),
        ):
            # Simulate network error for GetChildren API twice
            # This is to ensure Drive will eventually recover even after multiple
            # failures of GetChildren API.
            remote.make_file(
                folder1, "sample1.txt", content=b"This is a another sample file1"
            )
            self.remote_2.register_as_root(shared)

            # Delete folder 'shared'
            remote.delete(shared)
            self.wait_sync(wait_for_async=True)

            # Restore folder 'shared' from trash
            remote.undelete(shared)
            if version_lt(remote.client.server_version, "10.2"):
                remote.undelete(readme1)
            self.wait_sync(wait_for_async=True)

            remote.make_file(
                shared, "readme3.txt", content=b"This is a another shared file"
            )
            remote.make_file(
                folder2, "sample2.txt", content=b"This is a another sample file2"
            )

            self.wait_sync(wait_for_async=True)
            assert local.exists("/folder2/sample2.txt")
            assert local.exists("/folder1/sample1.txt")

            # Although sync failed for one folder, GetChangeSummary will return
            # zero event in successive calls.  We need to wait two remote scans,
            # so sleep for TEST_DEFAULT_DELAY * 2
            sleep(TEST_DEFAULT_DELAY * 2)
            assert local.exists("/shared/readme1.txt")
            assert local.exists("/shared/readme3.txt")
