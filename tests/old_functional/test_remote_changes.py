# coding: utf-8
from unittest.mock import patch

import pytest

from .common import SYNC_ROOT_FAC_ID, OneUserTest


class TestRemoteChanges(OneUserTest):
    def setup_method(self, method):
        super().setup_method(method, register_roots=False)

        self.last_event_log_id = 0
        self.last_root_definitions = ""
        # Initialize last event log id (lower bound)
        self.get_changes()

    def get_changes(self):
        self.wait()
        summary = self.remote_1.get_changes(
            self.last_root_definitions, log_id=self.last_event_log_id
        )
        if "upperBound" in summary:
            self.last_event_log_id = summary["upperBound"]
        self.last_root_definitions = summary["activeSynchronizationRootDefinitions"]
        return summary

    @pytest.mark.randombug("NXDRIVE-1565: Needed for the server is lagging")
    def test_changes_without_active_roots(self):
        summary = self.get_changes()
        assert not summary["hasTooManyChanges"]
        assert not summary["fileSystemChanges"]
        assert not summary["activeSynchronizationRootDefinitions"]
        first_timestamp = summary["syncDate"]
        assert first_timestamp > 0
        first_event_log_id = 0
        if "upperBound" in summary:
            first_event_log_id = summary["upperBound"]
            assert first_event_log_id >= 0

        summary = self.get_changes()
        assert not summary["hasTooManyChanges"]
        assert not summary["fileSystemChanges"]
        assert not summary["activeSynchronizationRootDefinitions"]
        second_time_stamp = summary["syncDate"]
        assert second_time_stamp >= first_timestamp
        if "upperBound" in summary:
            second_event_log_id = summary["upperBound"]
            assert second_event_log_id >= first_event_log_id

    @pytest.mark.randombug("NXDRIVE-1565: Needed for the server is lagging")
    def test_changes_root_registrations(self):
        # Lets create some folders in Nuxeo
        remote = self.remote_document_client_1
        folder_1 = remote.make_folder(self.workspace, "Folder 1")
        folder_2 = remote.make_folder(self.workspace, "Folder 2")
        remote.make_folder(folder_2, "Folder 2.2")

        # Check no changes without any registered roots
        summary = self.get_changes()
        assert not summary["hasTooManyChanges"]
        assert not summary["activeSynchronizationRootDefinitions"]
        assert not summary["fileSystemChanges"]

        # Let's register one of the previously created folders as sync root
        remote.register_as_root(folder_1)

        summary = self.get_changes()
        assert not summary["hasTooManyChanges"]
        root_defs = summary["activeSynchronizationRootDefinitions"].split(",")
        assert len(root_defs) == 1
        assert root_defs[0].startswith("default:")
        assert len(summary["fileSystemChanges"]) == 1

        change = summary["fileSystemChanges"][0]
        assert change["fileSystemItemName"] == "Folder 1"
        assert change["repositoryId"] == "default"
        assert change["docUuid"] == folder_1

        # Let's register the second root
        remote.register_as_root(folder_2)

        summary = self.get_changes()
        assert not summary["hasTooManyChanges"]
        root_defs = summary["activeSynchronizationRootDefinitions"].split(",")
        assert len(root_defs) == 2
        assert root_defs[0].startswith("default:")
        assert root_defs[1].startswith("default:")
        assert len(summary["fileSystemChanges"]) == 1
        change = summary["fileSystemChanges"][0]
        assert change["fileSystemItemName"] == "Folder 2"
        assert change["repositoryId"] == "default"
        assert change["docUuid"] == folder_2

        # Let's do nothing and refetch the changes
        summary = self.get_changes()
        assert not summary["hasTooManyChanges"]
        root_defs = summary["activeSynchronizationRootDefinitions"].split(",")
        assert len(root_defs) == 2
        assert root_defs[0].startswith("default:")
        assert root_defs[1].startswith("default:")
        assert not len(summary["fileSystemChanges"])

        # Let's unregister both roots at the same time
        remote.unregister_as_root(folder_1)
        remote.unregister_as_root(folder_2)

        summary = self.get_changes()

        assert not summary["hasTooManyChanges"]
        assert not summary["activeSynchronizationRootDefinitions"]
        assert len(summary["fileSystemChanges"]) == 2

        change = summary["fileSystemChanges"][0]
        assert change["eventId"] == "deleted"
        assert not change["fileSystemItemName"]
        assert change["repositoryId"] == "default"
        assert change["docUuid"] == folder_2

        change = summary["fileSystemChanges"][1]
        assert change["eventId"] == "deleted"
        assert not change["fileSystemItemName"]
        assert change["repositoryId"] == "default"
        assert change["docUuid"] == folder_1

        # Let's do nothing and refetch the changes
        summary = self.get_changes()
        assert not summary["hasTooManyChanges"]
        assert not summary["activeSynchronizationRootDefinitions"]
        assert not len(summary["fileSystemChanges"])

    @pytest.mark.randombug("NXDRIVE-1565: Needed for the server is lagging")
    def test_sync_root_parent_registration(self):
        # Create a folder
        remote = self.remote_document_client_1
        folder_1 = remote.make_folder(self.workspace, "Folder 1")
        self.get_changes()

        # Mark Folder 1 as a sync root
        remote.register_as_root(folder_1)

        summary = self.get_changes()
        assert len(summary["fileSystemChanges"]) == 1

        change = summary["fileSystemChanges"][0]
        assert change["eventId"] == "rootRegistered"
        assert change["fileSystemItemName"] == "Folder 1"
        assert change["fileSystemItemId"] == f"{SYNC_ROOT_FAC_ID}{folder_1}"

        # Mark parent folder as a sync root, should unregister Folder 1
        remote.register_as_root(self.workspace)

        summary = self.get_changes()
        assert len(summary["fileSystemChanges"]) == 2

        for change in summary["fileSystemChanges"]:
            if change["eventId"] == "rootRegistered":
                assert change["fileSystemItemName"] == self.workspace_title
                assert (
                    change["fileSystemItemId"] == f"{SYNC_ROOT_FAC_ID}{self.workspace}"
                )
                assert change["fileSystemItem"] is not None
            elif change["eventId"] == "deleted":
                assert not change["fileSystemItemName"]
                assert change["fileSystemItemId"] == f"default#{folder_1}"
                assert not change["fileSystemItem"]
            else:
                self.fail(f"Unexpected event: {change['eventId']!r}")

    @pytest.mark.randombug("NXDRIVE-1565: Needed for the server is lagging")
    def test_lock_unlock_events(self):
        remote = self.remote_document_client_1
        remote.register_as_root(self.workspace)
        doc_id = remote.make_file(
            self.workspace, "TestLocking.txt", content=b"File content"
        )
        self.get_changes()

        remote.lock(doc_id)
        summary = self.get_changes()
        assert len(summary["fileSystemChanges"]) == 1

        change = summary["fileSystemChanges"][0]
        assert change["eventId"] == "documentLocked"
        assert change["docUuid"] == doc_id
        assert change["fileSystemItemName"] == "TestLocking.txt"

        remote.unlock(doc_id)
        summary = self.get_changes()
        assert len(summary["fileSystemChanges"]) == 1

        change = summary["fileSystemChanges"][0]
        assert change["eventId"] == "documentUnlocked"
        assert change["docUuid"] == doc_id
        assert change["fileSystemItemName"] == "TestLocking.txt"

    def test_wrong_server_reply(self):
        """
        A response that is not a dictionary or that does not contain
        the right entries should not raise an exception.
        It should not modify the attributes we use to track the last
        synchronization either.
        """

        def not_dict(*args, **kwargs):
            return "not dict"

        def wrong_dict(*args, **kwargs):
            return {"wrong": "dict"}

        sync_date = self.engine_1._remote_watcher._last_sync_date

        with patch.object(self.engine_1.remote, "get_changes", new=not_dict):
            assert not self.engine_1._remote_watcher._get_changes()
            assert self.engine_1._remote_watcher._last_sync_date == sync_date

        with patch.object(self.engine_1.remote, "get_changes", new=wrong_dict):
            assert not self.engine_1._remote_watcher._get_changes()
            assert self.engine_1._remote_watcher._last_sync_date == sync_date
