"""Unit tests for :mod:`nxdrive.alfresco.client.remote`.

These are pure unit tests — the underlying ``alfresco.Alfresco`` client
is mocked so no network is touched.
"""

from unittest.mock import MagicMock, patch

import pytest


@pytest.fixture()
def _client_patch():
    """Patch out the heavy ``alfresco.Alfresco`` constructor.

    Also stub :mod:`alfresco.auth` handlers so we don't need to build
    real ``BasicAuth`` / ``TicketAuth`` objects with valid arguments.
    """
    with patch("nxdrive.alfresco.client.remote.Alfresco") as fake_alfresco, patch(
        "nxdrive.alfresco.client.remote.BasicAuth", return_value=object()
    ), patch("nxdrive.alfresco.client.remote.TicketAuth", return_value=object()):
        fake_alfresco.return_value = MagicMock(
            session=MagicMock(headers={}),
        )
        yield fake_alfresco


class TestConstructor:
    """Cover the various auth strategies encoded in ``__init__``."""

    def test_basic_auth_when_no_credentials(self, _client_patch) -> None:
        from nxdrive.alfresco.client.remote import AlfrescoRemote

        remote = AlfrescoRemote(
            "https://alfresco.example.com/alfresco",
            "admin",
            "device-1",
            "1.0.0",
        )
        assert remote.server_url == "https://alfresco.example.com/alfresco"
        assert remote.user_id == "admin"
        assert remote.device_id == "device-1"
        assert remote.version == "1.0.0"

    def test_positive_timeout_is_preserved(self, _client_patch) -> None:
        from nxdrive.alfresco.client.remote import AlfrescoRemote

        remote = AlfrescoRemote(
            "https://alfresco.example.com/alfresco",
            "admin",
            "device-1",
            "1.0.0",
            timeout=60,
        )
        assert remote.timeout == 60

    def test_non_positive_timeout_defaults_to_30(self, _client_patch) -> None:
        from nxdrive.alfresco.client.remote import AlfrescoRemote

        remote = AlfrescoRemote(
            "https://alfresco.example.com/alfresco",
            "admin",
            "device-1",
            "1.0.0",
            timeout=0,
        )
        assert remote.timeout == 30

    def test_base_url_strips_trailing_alfresco(self, _client_patch) -> None:
        """The vendor client re-adds ``/alfresco/api/...`` so we must
        strip that suffix from the caller-supplied URL to avoid a
        doubled path segment.
        """
        from nxdrive.alfresco.client.remote import AlfrescoRemote

        AlfrescoRemote(
            "https://alfresco.example.com/alfresco",
            "admin",
            "device-1",
            "1.0.0",
        )
        # The Alfresco class was called with the trimmed URL.
        call_kwargs = _client_patch.call_args.kwargs
        assert call_kwargs["url"] == "https://alfresco.example.com"

    def test_ticket_auth_when_alfresco_ticket_passed(self, _client_patch) -> None:
        from nxdrive.alfresco.client import remote as remote_mod
        from nxdrive.alfresco.client.remote import AlfrescoRemote

        with patch.object(
            remote_mod.TicketAuth, "from_ticket", return_value=object()
        ) as from_ticket:
            AlfrescoRemote(
                "https://alfresco.example.com/alfresco",
                "admin",
                "device-1",
                "1.0.0",
                alfresco_ticket="TICKET-abc",
            )
        from_ticket.assert_called_once_with("admin", "TICKET-abc")

    def test_string_token_uses_oauth2_bearer(self, _client_patch) -> None:
        from nxdrive.alfresco.client import remote as remote_mod
        from nxdrive.alfresco.client.remote import AlfrescoRemote

        with patch.object(
            remote_mod.OAuth2Auth, "from_token", return_value=object()
        ) as from_token:
            AlfrescoRemote(
                "https://alfresco.example.com/alfresco",
                "admin",
                "device-1",
                "1.0.0",
                token="bearer-string",
            )
        from_token.assert_called_once_with(access_token="bearer-string")


class TestRepr:
    """`__repr__` should be a stable one-liner containing url + user_id."""

    def test_repr_contains_url_and_user(self, _client_patch) -> None:
        from urllib.parse import urlparse

        from nxdrive.alfresco.client.remote import AlfrescoRemote

        url = "https://alfresco.example.com/alfresco"
        remote = AlfrescoRemote(
            url,
            "admin",
            "device-1",
            "1.2.3",
        )
        rendered = repr(remote)
        assert rendered.startswith("<AlfrescoRemote ")
        assert "admin" in rendered
        # Validate the full hostname from the URL appears in the repr
        expected_host = urlparse(url).hostname
        assert expected_host is not None
        assert expected_host == "alfresco.example.com"
        assert expected_host in rendered


class TestNoOpMetricsAndTasks:
    """The nested no-op stubs exist so the engine can call metrics/tasks
    without knowing whether the flavor supports them.
    """

    def test_metrics_send_does_not_raise(self) -> None:
        from nxdrive.alfresco.client.remote import _NoOpMetrics

        _NoOpMetrics().send()
        _NoOpMetrics().push_sync_event()
        _NoOpMetrics().force_poll()
        _NoOpMetrics().start()

    def test_tasks_get_returns_empty_list(self) -> None:
        from nxdrive.alfresco.client.remote import _NoOpTasks

        assert _NoOpTasks().get() == []
        assert _NoOpTasks().get("uid", limit=10) == []


class TestClose:
    """``close()`` must not raise when the underlying client is missing."""

    def test_close_is_safe(self, _client_patch) -> None:
        from nxdrive.alfresco.client.remote import AlfrescoRemote

        remote = AlfrescoRemote(
            "https://alfresco.example.com/alfresco",
            "admin",
            "device-1",
            "1.0.0",
        )
        # Should not raise.
        remote.close()


# ---------------------------------------------------------------------------
# Additional unit tests for uncovered methods
# ---------------------------------------------------------------------------


def _build_remote(_client_patch):
    """Helper: construct a remote with mocked Alfresco client."""
    from nxdrive.alfresco.client.remote import AlfrescoRemote

    return AlfrescoRemote(
        "https://alfresco.example.com/alfresco",
        "admin",
        "device-1",
        "1.0.0",
    )


class TestCheckCredentials:
    def test_returns_raw_person_dict(self, _client_patch) -> None:
        remote = _build_remote(_client_patch)
        person = MagicMock()
        person._raw = {"id": "admin", "firstName": "Admin"}
        remote.client.people.get.return_value = person

        result = remote.check_credentials()
        assert result == {"id": "admin", "firstName": "Admin"}
        remote.client.people.get.assert_called_once_with("-me-")


class TestUpdateToken:
    def test_dict_token_rebuilds_oauth2(self, _client_patch) -> None:
        remote = _build_remote(_client_patch)
        token = {
            "access_token": "new_access",
            "refresh_token": "new_refresh",
            "expires_at": "9999999999",
            "token_url": "https://idp/token",
            "client_id": "drive",
            "client_secret": None,
        }
        remote.update_token(token)
        # Auth should have been replaced
        assert remote.auth is not None
        assert remote.client.session.auth is remote.auth

    def test_string_token_rebuilds_oauth2(self, _client_patch) -> None:
        remote = _build_remote(_client_patch)
        with patch(
            "nxdrive.alfresco.client.remote.OAuth2Auth.from_token",
            return_value=MagicMock(),
        ) as mock_ft:
            remote.update_token("bearer-xyz")
        mock_ft.assert_called_once_with(access_token="bearer-xyz")

    def test_none_token_is_ignored(self, _client_patch) -> None:
        remote = _build_remote(_client_patch)
        old_auth = remote.auth
        remote.update_token(None)
        assert remote.auth is old_auth

    def test_empty_string_is_ignored(self, _client_patch) -> None:
        remote = _build_remote(_client_patch)
        old_auth = remote.auth
        remote.update_token("")
        assert remote.auth is old_auth


class TestNodeOperations:
    def test_get_node_delegates(self, _client_patch) -> None:
        remote = _build_remote(_client_patch)
        remote.client.nodes.get.return_value = "node-obj"
        result = remote.get_node("abc-123", include=["path"])
        remote.client.nodes.get.assert_called_once_with("abc-123", include=["path"])
        assert result == "node-obj"

    def test_get_children_delegates(self, _client_patch) -> None:
        remote = _build_remote(_client_patch)
        remote.client.nodes.list_children.return_value = ["c1", "c2"]
        result = remote.get_children("parent-id", max_items=50)
        remote.client.nodes.list_children.assert_called_once_with(
            "parent-id", max_items=50
        )
        assert result == ["c1", "c2"]

    def test_get_content_delegates(self, _client_patch) -> None:
        remote = _build_remote(_client_patch)
        remote.client.nodes.get_content.return_value = b"hello"
        assert remote.get_content("node-1") == b"hello"

    def test_upload_delegates(self, _client_patch) -> None:
        remote = _build_remote(_client_patch)
        remote.client.nodes.upload.return_value = "new-node"
        result = remote.upload("parent-1", "/tmp/file.txt", name="file.txt")
        remote.client.nodes.upload.assert_called_once_with(
            "parent-1", file_path="/tmp/file.txt", name="file.txt"
        )
        assert result == "new-node"

    def test_update_content_delegates(self, _client_patch) -> None:
        remote = _build_remote(_client_patch)
        remote.client.nodes.update_content.return_value = "updated"
        result = remote.update_content("node-1", "/tmp/new.txt")
        assert result == "updated"

    def test_create_folder_delegates(self, _client_patch) -> None:
        remote = _build_remote(_client_patch)
        remote.client.nodes.create_folder.return_value = "folder-node"
        result = remote.create_folder("parent-1", "NewFolder")
        remote.client.nodes.create_folder.assert_called_once_with(
            "parent-1", "NewFolder"
        )
        assert result == "folder-node"

    def test_delete_delegates(self, _client_patch) -> None:
        remote = _build_remote(_client_patch)
        remote.delete("node-1", permanent=True)
        remote.client.nodes.delete.assert_called_once_with("node-1", permanent=True)

    def test_copy_delegates(self, _client_patch) -> None:
        remote = _build_remote(_client_patch)
        remote.client.nodes.copy.return_value = "copy-node"
        result = remote.copy("src", "dest", name="copy.txt")
        remote.client.nodes.copy.assert_called_once_with("src", "dest", name="copy.txt")
        assert result == "copy-node"


class TestNodeToRemoteFileInfo:
    def test_builds_correct_remote_file_info(self, _client_patch) -> None:
        from datetime import datetime, timezone

        from nxdrive.alfresco.client.remote import AlfrescoRemote

        node = MagicMock()
        node.name = "Report.pdf"
        node.id = "abc-123"
        node.parent_id = "parent-456"
        node.is_folder = False
        node.is_file = True
        node.modified_at = datetime(2024, 6, 1, tzinfo=timezone.utc)
        node.created_at = datetime(2024, 1, 1, tzinfo=timezone.utc)
        node.modified_by_user = {"id": "admin"}
        node.path = {
            "elements": [
                {"name": "Company Home"},
                {"name": "Sites"},
            ]
        }

        info = AlfrescoRemote._node_to_remote_file_info(node)
        assert info.name == "Report.pdf"
        assert info.uid == "abc-123"
        assert info.parent_uid == "parent-456"
        assert info.path == "/Company Home/Sites/Report.pdf"
        assert info.folderish is False
        assert info.can_update is True
        assert info.can_create_child is False
        assert info.last_contributor == "admin"

    def test_path_without_elements(self, _client_patch) -> None:
        from nxdrive.alfresco.client.remote import AlfrescoRemote

        node = MagicMock()
        node.name = "Doc.txt"
        node.id = "x"
        node.parent_id = ""
        node.is_folder = False
        node.is_file = True
        node.modified_at = None
        node.created_at = None
        node.modified_by_user = None
        node.path = None

        info = AlfrescoRemote._node_to_remote_file_info(node)
        assert info.path == "/Doc.txt"
        assert info.last_contributor is None


class TestRenameAndMove:
    def test_rename_returns_remote_file_info(self, _client_patch) -> None:
        remote = _build_remote(_client_patch)
        updated_node = MagicMock()
        updated_node.name = "NewName.txt"
        updated_node.id = "node-1"
        updated_node.parent_id = "p"
        updated_node.is_folder = False
        updated_node.is_file = True
        updated_node.modified_at = None
        updated_node.created_at = None
        updated_node.modified_by_user = None
        updated_node.path = None
        remote.client.nodes.update.return_value = updated_node

        info = remote.rename("node-1", "NewName.txt")
        remote.client.nodes.update.assert_called_once_with(
            "node-1", {"name": "NewName.txt"}
        )
        assert info.name == "NewName.txt"

    def test_move_returns_remote_file_info(self, _client_patch) -> None:
        remote = _build_remote(_client_patch)
        moved_node = MagicMock()
        moved_node.name = "File.txt"
        moved_node.id = "node-1"
        moved_node.parent_id = "new-parent"
        moved_node.is_folder = False
        moved_node.is_file = True
        moved_node.modified_at = None
        moved_node.created_at = None
        moved_node.modified_by_user = None
        moved_node.path = None
        remote.client.nodes.move.return_value = moved_node

        info = remote.move("node-1", "new-parent", name="File.txt")
        remote.client.nodes.move.assert_called_once_with(
            "node-1", "new-parent", name="File.txt"
        )
        assert info.parent_uid == "new-parent"


class TestGetFsInfo:
    def test_success_returns_info(self, _client_patch) -> None:
        remote = _build_remote(_client_patch)
        node = MagicMock()
        node.name = "Test.doc"
        node.id = "n1"
        node.parent_id = "p1"
        node.is_folder = False
        node.is_file = True
        node.modified_at = None
        node.created_at = None
        node.modified_by_user = None
        node.path = None
        node.digest = "abc123"
        node.digest_algorithm = "MD5"
        remote.client.nodes.get.return_value = node

        info = remote.get_fs_info("n1")
        assert info.uid == "n1"
        assert info.digest == "abc123"
        assert info.digest_algorithm == "md5"

    def test_missing_raises_not_found(self, _client_patch) -> None:
        from nxdrive.drive.exceptions import NotFound

        remote = _build_remote(_client_patch)
        remote.client.nodes.get.side_effect = Exception("404")

        with pytest.raises(NotFound):
            remote.get_fs_info("missing-id")


class TestGetFsChildren:
    def test_filters_excluded_top_folders(self, _client_patch) -> None:
        remote = _build_remote(_client_patch)
        # Create two nodes: one system folder, one normal
        normal = MagicMock()
        normal.name = "MyFolder"
        normal.id = "n1"
        normal.parent_id = "root"
        normal.is_folder = True
        normal.is_file = False
        normal.modified_at = None
        normal.created_at = None
        normal.modified_by_user = None
        normal.path = {"elements": [{"name": "Company Home"}]}

        system = MagicMock()
        system.name = "Data Dictionary"
        system.id = "n2"
        system.parent_id = "root"
        system.is_folder = True
        system.is_file = False
        system.modified_at = None
        system.created_at = None
        system.modified_by_user = None
        system.path = {"elements": [{"name": "Company Home"}]}

        remote.client.nodes.iter_children.return_value = [normal, system]

        infos = remote.get_fs_children("root-id", filtered=False)
        # Data Dictionary should be excluded by is_top_folder_excluded
        names = [i.name for i in infos]
        assert "MyFolder" in names
        assert "Data Dictionary" not in names


class TestMakeFolder:
    def test_success(self, _client_patch) -> None:
        remote = _build_remote(_client_patch)
        folder_node = MagicMock()
        folder_node.name = "NewDir"
        folder_node.id = "new-id"
        folder_node.parent_id = "parent"
        folder_node.is_folder = True
        folder_node.is_file = False
        folder_node.modified_at = None
        folder_node.created_at = None
        folder_node.modified_by_user = None
        folder_node.path = None
        remote.client.nodes.create_folder.return_value = folder_node

        info = remote.make_folder("parent", "NewDir")
        assert info.uid == "new-id"
        assert info.folderish is True

    def test_conflict_adopts_existing(self, _client_patch) -> None:
        from alfresco.exceptions import ConflictError

        remote = _build_remote(_client_patch)
        remote.client.nodes.create_folder.side_effect = ConflictError("duplicate")

        existing = MagicMock()
        existing.name = "Existing"
        existing.id = "existing-id"
        existing.parent_id = "parent"
        existing.is_folder = True
        existing.is_file = False
        existing.modified_at = None
        existing.created_at = None
        existing.modified_by_user = None
        existing.path = None
        remote.client.nodes.iter_children.return_value = [existing]

        info = remote.make_folder("parent", "Existing")
        assert info.uid == "existing-id"


class TestStreamFile:
    def test_creates_new_file(self, _client_patch) -> None:
        from pathlib import Path

        remote = _build_remote(_client_patch)
        new_node = MagicMock()
        new_node.name = "test.txt"
        new_node.id = "new-file-id"
        new_node.parent_id = "parent"
        new_node.is_folder = False
        new_node.is_file = True
        new_node.modified_at = None
        new_node.created_at = None
        new_node.modified_by_user = None
        new_node.path = None
        remote.client.nodes.upload.return_value = new_node
        remote.client.nodes.iter_children.return_value = []  # no dups

        with patch(
            "nxdrive.alfresco.client.remote.compute_digest", return_value="md5hash"
        ):
            info = remote.stream_file("parent", Path("/tmp/test.txt"))

        assert info.uid == "new-file-id"
        assert info.digest == "md5hash"

    def test_conflict_raises_remote_conflict(self, _client_patch) -> None:
        from pathlib import Path

        from alfresco.exceptions import ConflictError

        from nxdrive.drive.exceptions import RemoteConflict

        remote = _build_remote(_client_patch)
        remote.client.nodes.iter_children.return_value = []
        remote.client.nodes.upload.side_effect = ConflictError("dup")

        with pytest.raises(RemoteConflict):
            remote.stream_file("parent", Path("/tmp/test.txt"))


class TestStreamUpdate:
    def test_updates_content(self, _client_patch) -> None:
        from pathlib import Path

        remote = _build_remote(_client_patch)
        updated_node = MagicMock()
        updated_node.name = "doc.txt"
        updated_node.id = "node-1"
        updated_node.parent_id = "p"
        updated_node.is_folder = False
        updated_node.is_file = True
        updated_node.modified_at = None
        updated_node.created_at = None
        updated_node.modified_by_user = None
        updated_node.path = None
        remote.client.nodes.update_content.return_value = updated_node

        with patch("nxdrive.alfresco.client.remote.compute_digest", return_value="d1"):
            info = remote.stream_update("node-1", Path("/tmp/doc.txt"))

        assert info.digest == "d1"

    def test_conflict_raises_remote_conflict(self, _client_patch) -> None:
        from pathlib import Path

        from alfresco.exceptions import ConflictError

        from nxdrive.drive.exceptions import RemoteConflict

        remote = _build_remote(_client_patch)
        remote.client.nodes.update_content.side_effect = ConflictError("conflict")

        with pytest.raises(RemoteConflict):
            remote.stream_update("node-1", Path("/tmp/doc.txt"))


class TestGetInfo:
    def test_returns_info_with_trashed_flag(self, _client_patch) -> None:
        remote = _build_remote(_client_patch)
        node = MagicMock()
        node.name = "Trash.doc"
        node.id = "t1"
        node.parent_id = "p"
        node.is_folder = False
        node.is_file = True
        node.modified_at = None
        node.created_at = None
        node.modified_by_user = None
        node.path = None
        node.is_trashed = True
        node._raw = {}
        remote.client.nodes.get.return_value = node

        info = remote.get_info("t1")
        assert info.uid == "t1"
        assert info.is_trashed is True

    def test_missing_returns_none_when_not_raising(self, _client_patch) -> None:
        remote = _build_remote(_client_patch)
        remote.client.nodes.get.side_effect = Exception("gone")

        result = remote.get_info("bad-id", raise_if_missing=False)
        assert result is None

    def test_missing_raises_when_raise_if_missing(self, _client_patch) -> None:
        from nxdrive.drive.exceptions import NotFound

        remote = _build_remote(_client_patch)
        remote.client.nodes.get.side_effect = Exception("gone")

        with pytest.raises(NotFound):
            remote.get_info("bad-id", raise_if_missing=True)


class TestMove2:
    def test_moves_and_renames(self, _client_patch) -> None:
        remote = _build_remote(_client_patch)
        result_node = MagicMock()
        result_node._raw = {"id": "n1", "name": "renamed.txt"}
        remote.client.nodes.move.return_value = result_node

        result = remote.move2("n1", "new-parent", "renamed.txt")
        remote.client.nodes.move.assert_called_once_with(
            "n1", "new-parent", name="renamed.txt"
        )
        assert result == {"id": "n1", "name": "renamed.txt"}

    def test_empty_parent_ref_returns_empty_dict(self, _client_patch) -> None:
        remote = _build_remote(_client_patch)
        result = remote.move2("n1", "", "name.txt")
        assert result == {}
        remote.client.nodes.move.assert_not_called()


class TestUndelete:
    def test_delegates_to_trashcan(self, _client_patch) -> None:
        remote = _build_remote(_client_patch)
        remote.undelete("node-1")
        remote.client.trashcan.restore.assert_called_once_with("node-1")

    def test_exception_does_not_propagate(self, _client_patch) -> None:
        remote = _build_remote(_client_patch)
        remote.client.trashcan.restore.side_effect = Exception("fail")
        # Should not raise
        remote.undelete("node-1")


class TestMiscMethods:
    def test_revoke_token_is_noop(self, _client_patch) -> None:
        remote = _build_remote(_client_patch)
        remote.revoke_token()  # Should not raise

    def test_get_server_configuration_returns_empty(self, _client_patch) -> None:
        remote = _build_remote(_client_patch)
        assert remote.get_server_configuration() == {}

    def test_cancel_batch_is_noop(self, _client_patch) -> None:
        remote = _build_remote(_client_patch)
        remote.cancel_batch({"batch_id": "123"})  # Should not raise

    def test_is_filtered_without_dao(self, _client_patch) -> None:
        remote = _build_remote(_client_patch)
        assert remote.is_filtered("/some/path") is False

    def test_search_delegates(self, _client_patch) -> None:
        remote = _build_remote(_client_patch)
        remote.client.search.afts.return_value = ["result"]
        assert remote.search("query") == ["result"]


class TestGetDiscovery:
    def test_caches_result(self, _client_patch) -> None:
        remote = _build_remote(_client_patch)
        resp = MagicMock()
        resp.json.return_value = {"version": "7.4"}
        resp.raise_for_status = MagicMock()
        remote.client.session.get.return_value = resp

        # First call fetches
        result1 = remote.get_discovery()
        # Second call uses cache
        result2 = remote.get_discovery()
        assert result1 == {"version": "7.4"}
        assert result2 == {"version": "7.4"}
        remote.client.session.get.assert_called_once()


class TestDownloadContent:
    def test_writes_file_and_verifies_digest(self, _client_patch, tmp_path) -> None:
        remote = _build_remote(_client_patch)
        remote.client.nodes.get_content.return_value = b"file data"

        target = tmp_path / "sub" / "file.txt"
        with patch(
            "nxdrive.alfresco.client.remote.compute_digest", return_value="good"
        ):
            remote.download_content(
                "n1",
                str(target),
                expected_digest="good",
                digest_algorithm="md5",
            )
        assert target.read_bytes() == b"file data"

    def test_deletes_on_checksum_mismatch(self, _client_patch, tmp_path) -> None:
        from alfresco.exceptions import AlfrescoError

        remote = _build_remote(_client_patch)
        remote.client.nodes.get_content.return_value = b"data"

        target = tmp_path / "file.txt"
        with patch("nxdrive.alfresco.client.remote.compute_digest", return_value="bad"):
            with pytest.raises(AlfrescoError, match="Checksum mismatch"):
                remote.download_content(
                    "n1",
                    str(target),
                    expected_digest="expected",
                    digest_algorithm="md5",
                )
        assert not target.exists()


class TestOAuthTokenInit:
    """Test OAuth2 token dict initialization in constructor."""

    def test_dict_token_with_future_expiry(self, _client_patch) -> None:
        import time

        from nxdrive.alfresco.client.remote import AlfrescoRemote

        token = {
            "access_token": "access",
            "refresh_token": "refresh",
            "expires_at": str(time.time() + 3600),
            "token_url": "https://idp/token",
            "client_id": "drive",
            "client_secret": None,
        }
        with patch(
            "nxdrive.alfresco.client.remote.RefreshingOAuth2Auth.from_token",
            return_value=MagicMock(),
        ) as mock_ft:
            AlfrescoRemote(
                "https://acs.example.com/alfresco",
                "admin",
                "device-1",
                "1.0.0",
                token=token,
            )
        # expires_in should be > 0
        call_kwargs = mock_ft.call_args.kwargs
        assert call_kwargs["expires_in"] > 0
        assert call_kwargs["access_token"] == "access"
        assert call_kwargs["refresh_token"] == "refresh"

    def test_dict_token_with_past_expiry(self, _client_patch) -> None:
        import time

        from nxdrive.alfresco.client.remote import AlfrescoRemote

        token = {
            "access_token": "access",
            "refresh_token": "refresh",
            "expires_at": str(time.time() - 100),
            "token_url": "https://idp/token",
            "client_id": "drive",
            "client_secret": None,
        }
        with patch(
            "nxdrive.alfresco.client.remote.RefreshingOAuth2Auth.from_token",
            return_value=MagicMock(),
        ) as mock_ft:
            AlfrescoRemote(
                "https://acs.example.com/alfresco",
                "admin",
                "device-1",
                "1.0.0",
                token=token,
            )
        # Expired → should pass expires_in=1
        call_kwargs = mock_ft.call_args.kwargs
        assert call_kwargs["expires_in"] == 1

    def test_password_auth(self, _client_patch) -> None:
        from nxdrive.alfresco.client.remote import AlfrescoRemote

        with patch(
            "nxdrive.alfresco.client.remote.TicketAuth",
            return_value=MagicMock(),
        ) as mock_ta:
            AlfrescoRemote(
                "https://acs.example.com/alfresco",
                "admin",
                "device-1",
                "1.0.0",
                password="secret",
            )
        mock_ta.assert_called_once_with("admin", "secret")


class TestRegisterUpload:
    def test_registers_upload_row(self, _client_patch) -> None:
        from pathlib import Path

        remote = _build_remote(_client_patch)
        dao = MagicMock()
        dao.get_upload.return_value = None
        remote.dao = dao

        with patch("nxdrive.alfresco.client.remote.Path") as mock_path:
            mock_path.return_value.stat.return_value.st_size = 1024
            remote._register_upload(Path("/tmp/file.txt"), doc_pair_id=1)

        dao.save_upload.assert_called_once()

    def test_no_dao_is_noop(self, _client_patch) -> None:
        remote = _build_remote(_client_patch)
        # No dao attribute
        if hasattr(remote, "dao"):
            del remote.dao
        # Should not raise
        from pathlib import Path

        remote._register_upload(Path("/tmp/file.txt"))

    def test_existing_upload_skipped(self, _client_patch) -> None:
        from pathlib import Path

        remote = _build_remote(_client_patch)
        dao = MagicMock()
        dao.get_upload.return_value = MagicMock()  # Already exists
        remote.dao = dao
        remote._register_upload(Path("/tmp/file.txt"))
        dao.save_upload.assert_not_called()


class TestFinishUpload:
    def test_removes_transfer(self, _client_patch) -> None:
        from pathlib import Path

        remote = _build_remote(_client_patch)
        dao = MagicMock()
        remote.dao = dao
        remote._finish_upload(Path("/tmp/file.txt"))
        dao.remove_transfer.assert_called_once_with(
            "upload", path=Path("/tmp/file.txt")
        )

    def test_no_dao_is_noop(self, _client_patch) -> None:
        from pathlib import Path

        remote = _build_remote(_client_patch)
        if hasattr(remote, "dao"):
            del remote.dao
        remote._finish_upload(Path("/tmp/file.txt"))  # Should not raise


class TestIsFiltered:
    def test_with_dao_delegates(self, _client_patch) -> None:
        remote = _build_remote(_client_patch)
        dao = MagicMock()
        dao.is_filter.return_value = True
        remote.dao = dao
        assert remote.is_filtered("/path") is True
        dao.is_filter.assert_called_once_with("/path")

    def test_filtered_false_passes_through(self, _client_patch) -> None:
        remote = _build_remote(_client_patch)
        dao = MagicMock()
        remote.dao = dao
        assert remote.is_filtered("/path", filtered=False) is False


class TestGetFsInfoDigestFallback:
    def test_uses_node_digest_when_available(self, _client_patch) -> None:
        remote = _build_remote(_client_patch)
        node = MagicMock()
        node.name = "file.txt"
        node.id = "n1"
        node.parent_id = "p"
        node.is_folder = False
        node.is_file = True
        node.modified_at = None
        node.created_at = None
        node.modified_by_user = None
        node.path = None
        node.digest = "server_digest"
        node.digest_algorithm = "SHA256"
        remote.client.nodes.get.return_value = node

        info = remote.get_fs_info("n1")
        assert info.digest == "server_digest"
        assert info.digest_algorithm == "sha256"

    def test_falls_back_to_dao_pair(self, _client_patch) -> None:
        remote = _build_remote(_client_patch)
        node = MagicMock()
        node.name = "file.txt"
        node.id = "n1"
        node.parent_id = "p"
        node.is_folder = False
        node.is_file = True
        node.modified_at = None
        node.created_at = None
        node.modified_by_user = None
        node.path = None
        node.digest = None
        node.digest_algorithm = None
        remote.client.nodes.get.return_value = node

        dao = MagicMock()
        pair_mock = MagicMock()
        pair_mock.remote_digest = "db_digest"
        dao.get_normal_state_from_remote.return_value = pair_mock
        remote.dao = dao

        info = remote.get_fs_info("n1")
        assert info.digest == "db_digest"
        assert info.digest_algorithm == "md5"


class TestFetch:
    def test_returns_raw_dict(self, _client_patch) -> None:
        remote = _build_remote(_client_patch)
        node = MagicMock()
        node._raw = {"id": "n1", "name": "doc.txt"}
        node.name = "doc.txt"
        node.id = "n1"
        node.parent_id = "p"
        node.is_folder = False
        node.is_file = True
        node.modified_at = None
        node.created_at = None
        node.modified_by_user = None
        node.path = None
        remote.client.nodes.get.return_value = node

        result = remote.fetch("n1")
        assert result == {"id": "n1", "name": "doc.txt"}

    def test_missing_raises_not_found(self, _client_patch) -> None:
        from nxdrive.drive.exceptions import NotFound

        remote = _build_remote(_client_patch)
        remote.client.nodes.get.side_effect = Exception("gone")

        with pytest.raises(NotFound):
            remote.fetch("bad")


# --- NEW TESTS BELOW ---


class TestStreamContentExtended:
    """Additional stream_content tests: progress callback and DownloadPaused."""

    def test_stream_content_registers_and_removes_download(
        self, _client_patch, tmp_path
    ) -> None:
        from pathlib import Path

        remote = _build_remote(_client_patch)
        dao = MagicMock()
        dao.get_download.return_value = None
        # After save_download, return a download with uid
        download_obj = MagicMock()
        download_obj.uid = 42
        download_obj.filesize = 0
        download_obj.status = None
        dao.get_download.side_effect = [None, download_obj, download_obj]
        remote.dao = dao

        file_out = tmp_path / "output.bin"
        remote.client.nodes.download_to = MagicMock()

        remote.stream_content(
            "node-1",
            Path("/sync/file.bin"),
            file_out,
            engine_uid="eng-1",
            doc_pair_id=7,
        )

        dao.save_download.assert_called_once()
        dao.remove_transfer.assert_called_once_with(
            "download", path=Path("/sync/file.bin")
        )

    def test_stream_content_download_paused_propagates(
        self, _client_patch, tmp_path
    ) -> None:
        from pathlib import Path

        from nxdrive.drive.exceptions import DownloadPaused

        remote = _build_remote(_client_patch)
        dao = MagicMock()
        download_obj = MagicMock()
        download_obj.uid = 1
        download_obj.filesize = 0
        dao.get_download.return_value = download_obj
        remote.dao = dao

        file_out = tmp_path / "output.bin"
        remote.client.nodes.download_to.side_effect = DownloadPaused(1)

        with pytest.raises(DownloadPaused):
            remote.stream_content("node-1", Path("/sync/file.bin"), file_out)

        # Should NOT remove transfer on pause
        dao.remove_transfer.assert_not_called()

    def test_stream_content_error_removes_download(
        self, _client_patch, tmp_path
    ) -> None:
        from pathlib import Path

        remote = _build_remote(_client_patch)
        dao = MagicMock()
        download_obj = MagicMock()
        download_obj.uid = 1
        download_obj.filesize = 0
        dao.get_download.return_value = download_obj
        remote.dao = dao

        file_out = tmp_path / "output.bin"
        remote.client.nodes.download_to.side_effect = RuntimeError("network")

        with pytest.raises(RuntimeError, match="network"):
            remote.stream_content("node-1", Path("/sync/file.bin"), file_out)

        dao.remove_transfer.assert_called_once_with(
            "download", path=Path("/sync/file.bin")
        )

    def test_stream_content_digest_mismatch_raises_corrupted(
        self, _client_patch, tmp_path
    ) -> None:
        from pathlib import Path

        from alfresco.exceptions import CorruptedFile

        remote = _build_remote(_client_patch)
        dao = MagicMock()
        dao.get_download.return_value = None
        remote.dao = dao

        file_out = tmp_path / "output.bin"
        remote.client.nodes.download_to = MagicMock()

        fs_item_info = MagicMock()
        fs_item_info.digest = "expected_hash"
        fs_item_info.digest_algorithm = "md5"

        with patch(
            "nxdrive.alfresco.client.remote.compute_digest",
            return_value="wrong_hash",
        ):
            with pytest.raises(CorruptedFile):
                remote.stream_content(
                    "node-1",
                    Path("/sync/file.bin"),
                    file_out,
                    fs_item_info=fs_item_info,
                )

    def test_stream_content_digest_match_succeeds(
        self, _client_patch, tmp_path
    ) -> None:
        from pathlib import Path

        remote = _build_remote(_client_patch)
        dao = MagicMock()
        dao.get_download.return_value = None
        remote.dao = dao

        file_out = tmp_path / "output.bin"
        remote.client.nodes.download_to = MagicMock()

        fs_item_info = MagicMock()
        fs_item_info.digest = "good_hash"
        fs_item_info.digest_algorithm = "md5"

        with patch(
            "nxdrive.alfresco.client.remote.compute_digest",
            return_value="good_hash",
        ):
            result = remote.stream_content(
                "node-1",
                Path("/sync/file.bin"),
                file_out,
                fs_item_info=fs_item_info,
            )
        assert result == file_out

    def test_stream_content_no_dao_skips_download_tracking(
        self, _client_patch, tmp_path
    ) -> None:
        from pathlib import Path

        remote = _build_remote(_client_patch)
        if hasattr(remote, "dao"):
            del remote.dao

        file_out = tmp_path / "output.bin"
        remote.client.nodes.download_to = MagicMock()

        result = remote.stream_content("node-1", Path("/sync/file.bin"), file_out)
        assert result == file_out


class TestStreamFileExtended:
    """Additional stream_file tests: existing node update and ConflictError."""

    def test_existing_node_triggers_update(self, _client_patch) -> None:
        from pathlib import Path

        remote = _build_remote(_client_patch)

        existing_child = MagicMock()
        existing_child.name = "report.txt"
        existing_child.id = "existing-id"
        existing_child.is_file = True
        existing_child.is_folder = False
        remote.client.nodes.iter_children.return_value = [existing_child]

        updated_node = MagicMock()
        updated_node.name = "report.txt"
        updated_node.id = "existing-id"
        updated_node.parent_id = "parent"
        updated_node.is_folder = False
        updated_node.is_file = True
        updated_node.modified_at = None
        updated_node.created_at = None
        updated_node.modified_by_user = None
        updated_node.path = None
        remote.client.nodes.update_content.return_value = updated_node

        with patch(
            "nxdrive.alfresco.client.remote.compute_digest", return_value="md5hash"
        ):
            info = remote.stream_file(
                "parent", Path("/tmp/report.txt"), filename="report.txt"
            )

        assert info.uid == "existing-id"
        assert info.digest == "md5hash"
        remote.client.nodes.update_content.assert_called_once()
        remote.client.nodes.upload.assert_not_called()

    def test_conflict_error_during_upload_raises_remote_conflict(
        self, _client_patch
    ) -> None:
        from pathlib import Path

        from alfresco.exceptions import ConflictError

        from nxdrive.drive.exceptions import RemoteConflict

        remote = _build_remote(_client_patch)
        remote.client.nodes.iter_children.return_value = []
        remote.client.nodes.upload.side_effect = ConflictError("409")

        with pytest.raises(RemoteConflict):
            remote.stream_file("parent", Path("/tmp/file.txt"), filename="file.txt")


class TestGetFilesystemRootInfo:
    def test_returns_remote_file_info(self, _client_patch) -> None:
        remote = _build_remote(_client_patch)
        root_node = MagicMock()
        root_node.name = "Company Home"
        root_node.id = "root-id"
        root_node.parent_id = ""
        root_node.is_folder = True
        root_node.is_file = False
        root_node.modified_at = None
        root_node.created_at = None
        root_node.modified_by_user = None
        root_node.path = {"elements": []}
        remote.client.nodes.get.return_value = root_node

        info = remote.get_filesystem_root_info()
        assert info.uid == "root-id"
        assert info.folderish is True
        remote.client.nodes.get.assert_called_once_with("-root-", include=["path"])


class TestNodeToRemoteFileInfoExtended:
    """Additional _node_to_remote_file_info edge cases."""

    def test_empty_path_elements(self, _client_patch) -> None:
        from nxdrive.alfresco.client.remote import AlfrescoRemote

        node = MagicMock()
        node.name = "Root"
        node.id = "root-id"
        node.parent_id = ""
        node.is_folder = True
        node.is_file = False
        node.modified_at = None
        node.created_at = None
        node.modified_by_user = None
        node.path = {"elements": []}

        info = AlfrescoRemote._node_to_remote_file_info(node)
        assert info.path == "/Root"

    def test_no_parent_id(self, _client_patch) -> None:
        from nxdrive.alfresco.client.remote import AlfrescoRemote

        node = MagicMock()
        node.name = "Orphan"
        node.id = "orphan-id"
        node.parent_id = None
        node.is_folder = False
        node.is_file = True
        node.modified_at = None
        node.created_at = None
        node.modified_by_user = {"id": "user1"}
        node.path = None

        info = AlfrescoRemote._node_to_remote_file_info(node)
        assert info.parent_uid == ""
        assert info.last_contributor == "user1"


class TestGetFsInfoDigestFallbackExtended:
    """Additional get_fs_info digest fallback tests."""

    def test_no_dao_no_fallback(self, _client_patch) -> None:
        remote = _build_remote(_client_patch)
        if hasattr(remote, "dao"):
            del remote.dao

        node = MagicMock()
        node.name = "file.txt"
        node.id = "n1"
        node.parent_id = "p"
        node.is_folder = False
        node.is_file = True
        node.modified_at = None
        node.created_at = None
        node.modified_by_user = None
        node.path = None
        node.digest = None
        node.digest_algorithm = None
        remote.client.nodes.get.return_value = node

        info = remote.get_fs_info("n1")
        assert info.digest is None

    def test_dao_pair_without_digest_leaves_none(self, _client_patch) -> None:
        remote = _build_remote(_client_patch)
        node = MagicMock()
        node.name = "file.txt"
        node.id = "n1"
        node.parent_id = "p"
        node.is_folder = False
        node.is_file = True
        node.modified_at = None
        node.created_at = None
        node.modified_by_user = None
        node.path = None
        node.digest = None
        node.digest_algorithm = None
        remote.client.nodes.get.return_value = node

        dao = MagicMock()
        pair_mock = MagicMock()
        pair_mock.remote_digest = None
        dao.get_normal_state_from_remote.return_value = pair_mock
        remote.dao = dao

        info = remote.get_fs_info("n1")
        assert info.digest is None


class TestGetFsChildrenExtended:
    """Additional get_fs_children tests."""

    def test_with_dao_filter(self, _client_patch) -> None:
        remote = _build_remote(_client_patch)
        normal = MagicMock()
        normal.name = "Visible"
        normal.id = "n1"
        normal.parent_id = "root"
        normal.is_folder = True
        normal.is_file = False
        normal.modified_at = None
        normal.created_at = None
        normal.modified_by_user = None
        normal.path = {"elements": [{"name": "Company Home"}]}

        filtered_node = MagicMock()
        filtered_node.name = "Hidden"
        filtered_node.id = "n2"
        filtered_node.parent_id = "root"
        filtered_node.is_folder = True
        filtered_node.is_file = False
        filtered_node.modified_at = None
        filtered_node.created_at = None
        filtered_node.modified_by_user = None
        filtered_node.path = {"elements": [{"name": "Company Home"}]}

        remote.client.nodes.iter_children.return_value = [normal, filtered_node]
        dao = MagicMock()
        dao.is_filter.side_effect = lambda path: "Hidden" in path
        remote.dao = dao

        infos = remote.get_fs_children("root-id", filtered=True)
        names = [i.name for i in infos]
        assert "Visible" in names
        assert "Hidden" not in names


class TestIsFilteredExtended:
    """Additional is_filtered tests."""

    def test_without_dao_returns_false(self, _client_patch) -> None:
        remote = _build_remote(_client_patch)
        if hasattr(remote, "dao"):
            del remote.dao
        assert remote.is_filtered("/some/path") is False
