# coding: utf-8
from unittest.mock import patch

from .common import UnitTestCase


class TestRemoteChanges(UnitTestCase):
    def setUpApp(self, *args):
        super().setUpApp(register_roots=False)

    def setUp(self):
        super().setUp()
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
        raw_root_defs = summary["activeSynchronizationRootDefinitions"]
        assert not raw_root_defs
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
        raw_root_defs = summary["activeSynchronizationRootDefinitions"]
        assert not raw_root_defs
        assert not len(summary["fileSystemChanges"])

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
        assert (
            change["fileSystemItemId"]
            == "defaultSyncRootFolderItemFactory#default#%s" % folder_1
        )

        # Mark parent folder as a sync root, should unregister Folder 1
        remote.register_as_root(self.workspace)
        summary = self.get_changes()
        assert len(summary["fileSystemChanges"]) == 2

        for change in summary["fileSystemChanges"]:
            if change["eventId"] == "rootRegistered":
                assert change["fileSystemItemName"] == "Nuxeo Drive Test Workspace"
                assert (
                    change["fileSystemItemId"]
                    == "defaultSyncRootFolderItemFactory#default#%s" % self.workspace
                )
                assert change["fileSystemItem"] is not None
            elif change["eventId"] == "deleted":
                assert not change["fileSystemItemName"]
                assert change["fileSystemItemId"] == "default#%s" % folder_1
                assert not change["fileSystemItem"]
            else:
                self.fail("Unexpected event %r" % change["eventId"])

    def test_lock_unlock_events(self):
        remote = self.remote_document_client_1
        remote.register_as_root(self.workspace_1)
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
        def get_changes(*args, **kwargs):
            return {"wrong": "dict"}

        with patch.object(self.engine_1.remote, "get_changes", new=get_changes):
            # Should not throw an exception
            assert not self.engine_1._remote_watcher._get_changes()
