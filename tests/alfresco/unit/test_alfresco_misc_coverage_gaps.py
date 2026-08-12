"""Targeted coverage tests for Alfresco engine, client, filters, and auth."""

from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest
from alfresco.exceptions import ConflictError

from nxdrive.alfresco.client.remote import AlfrescoRemote
from nxdrive.alfresco.engine.engine import AlfrescoEngine
from nxdrive.drive.constants import TransferStatus
from nxdrive.drive.exceptions import UploadPaused
from nxdrive.drive.objects import Upload


def _engine():
    with patch.object(AlfrescoEngine, "__init__", return_value=None):
        engine = AlfrescoEngine.__new__(AlfrescoEngine)
    engine.dao = MagicMock()
    engine.remote = MagicMock()
    engine.local = MagicMock()
    engine.manager = MagicMock()
    engine.uid = "alfresco-coverage-engine"
    engine.server_url = "https://alfresco.example.com/alfresco"
    engine.remote_user = "admin"
    engine.syncStateCleared = MagicMock()
    engine.newConflict = MagicMock()
    return engine


def _remote():
    remote = AlfrescoRemote.__new__(AlfrescoRemote)
    remote.server_url = "https://alfresco.example.com/alfresco"
    remote.client = MagicMock()
    remote.upload_callback = None
    return remote


@pytest.mark.parametrize(
    "failure_target",
    ["filters", "configuration", "signal"],
)
def test_sync_disabled_cleanup_is_best_effort(failure_target):
    engine = _engine()
    engine.dao.get_filters.return_value = ["/Company Home/Hidden"]
    if failure_target == "filters":
        engine.dao.get_filters.side_effect = RuntimeError("filters locked")
    elif failure_target == "configuration":
        engine.dao.delete_config.side_effect = RuntimeError("config locked")
    else:
        engine.syncStateCleared.emit.side_effect = RuntimeError("receiver gone")

    engine._cleanup_after_sync_disabled()

    engine.dao.reinit_states.assert_called_once_with()


def test_conflict_resolver_surfaces_file_when_remote_lookup_fails():
    engine = _engine()
    pair = MagicMock()
    pair.folderish = False
    pair.remote_ref = "document-id"
    pair.local_name = "document.txt"
    pair.local_path = Path("sync/document.txt")
    engine.dao.get_state_from_id.return_value = pair
    engine.remote.get_fs_info.side_effect = OSError("offline")

    engine.conflict_resolver(41)

    engine.newConflict.emit.assert_called_once_with(41)
    engine.manager.osi.send_sync_status.assert_called_once_with(
        pair, engine.local.abspath(pair.local_path)
    )


def test_conflict_resolver_surfaces_folder_when_xattr_lookup_fails():
    engine = _engine()
    pair = MagicMock()
    pair.folderish = True
    pair.remote_ref = "folder-id"
    pair.local_name = "folder"
    pair.local_path = Path("sync/folder")
    engine.dao.get_state_from_id.return_value = pair
    engine.local.get_remote_id.side_effect = OSError("unsupported xattr")

    engine.conflict_resolver(42)

    engine.newConflict.emit.assert_called_once_with(42)
    engine.dao.synchronize_state.assert_not_called()


def test_configuration_without_token_or_ticket_keeps_empty_ticket():
    engine = _engine()
    engine.dao.get_bool.return_value = False
    values = {
        "server_url": "https://alfresco.example.com/alfresco",
        "ui": "web",
        "force_ui": None,
        "remote_user": "admin",
    }
    engine.dao.get_config.side_effect = lambda key, **kwargs: values.get(
        key, kwargs.get("default")
    )
    engine._load_token = MagicMock(return_value=None)
    engine._load_ticket = MagicMock(return_value="")

    engine._load_configuration()

    assert engine._alfresco_ticket == ""


def test_corrupt_ticket_is_ignored():
    engine = _engine()
    engine.dao.get_config.return_value = "encrypted-ticket"

    with patch("nxdrive.drive.utils.decrypt", side_effect=ValueError("corrupt")):
        assert engine._load_ticket() == ""


def _folder_node(name="folder", node_id="folder-id"):
    return SimpleNamespace(
        name=name,
        id=node_id,
        parent_id="parent-id",
        is_folder=True,
        is_file=False,
        modified_at=None,
        created_at=None,
        modified_by_user=None,
        path=None,
    )


def _file_node(name="document.txt", node_id="document-id"):
    return SimpleNamespace(
        name=name,
        id=node_id,
        parent_id="parent-id",
        is_folder=False,
        is_file=True,
        modified_at=None,
        created_at=None,
        modified_by_user=None,
        path=None,
    )


def test_find_child_folder_returns_match_after_nonmatches():
    remote = _remote()
    remote.client.nodes.iter_children.return_value = [
        _file_node(name="target"),
        _folder_node(name="other"),
        _folder_node(name="target", node_id="target-id"),
    ]

    result = remote._find_child_folder("parent-id", "target")

    assert result.id == "target-id"


def test_find_child_folder_returns_none_after_scan_error():
    remote = _remote()
    remote.client.nodes.iter_children.side_effect = OSError("offline")

    assert remote._find_child_folder("parent-id", "target") is None


def test_make_folder_reraises_conflict_when_existing_folder_cannot_be_found():
    remote = _remote()
    conflict = ConflictError("duplicate child")
    remote.create_folder = MagicMock(side_effect=conflict)
    remote._find_child_folder = MagicMock(return_value=None)

    with pytest.raises(ConflictError) as exc_info:
        remote.make_folder("parent-id", "target")

    assert exc_info.value is conflict


def test_stream_update_pause_preserves_upload_row(tmp_path):
    remote = _remote()
    path = tmp_path / "document.txt"
    path.write_text("content", encoding="utf-8")
    upload = Upload(
        19,
        path=path,
        status=TransferStatus.ONGOING,
        engine="engine-id",
        doc_pair=3,
        filesize=7,
    )
    action = MagicMock()
    remote._register_upload = MagicMock(return_value=upload)
    remote._upload_progress = MagicMock(return_value=(MagicMock(), action))
    remote._finish_upload = MagicMock()
    remote.update_content = MagicMock(side_effect=UploadPaused(19))

    with pytest.raises(UploadPaused):
        remote.stream_update("document-id", path)

    action.finish_action.assert_called_once_with()
    remote._finish_upload.assert_not_called()


def test_upload_progress_without_tracked_upload_returns_after_callback(tmp_path):
    remote = _remote()
    path = tmp_path / "document.txt"
    path.write_text("content", encoding="utf-8")
    remote.dao = MagicMock()
    progress, action = remote._upload_progress(None, path)

    progress(1, 7)

    remote.dao.get_transfer_status.assert_not_called()
    remote.dao.set_transfer_progress.assert_not_called()
    action.finish_action()


def test_filter_helpers_handle_blank_and_empty_prefixes():
    from nxdrive.alfresco.sync_filters import _covered_by, _normalise

    assert _normalise("") == ""
    assert _normalise(" / ") == ""
    assert _covered_by("", ("/Company Home",)) is False
    assert _covered_by("/Company Home/Sites", ("", "/Elsewhere")) is False


def test_aims_probe_disables_tls_verification_when_requested():
    from nxdrive.alfresco.auth.oauth2 import discover_aims_config

    client = MagicMock()
    identity = MagicMock()
    identity.openid_configuration_url.return_value = "https://idp/.well-known"
    identity.client_id = "drive"
    identity.audience = "acs"
    identity.public_client = True
    identity.enable_pkce = True
    identity.enable_basic_auth = False
    identity.client_secret = None
    client.device_sync.get_identity_service_config.return_value = identity

    with patch("alfresco.Alfresco", return_value=client):
        result = discover_aims_config("https://alfresco.example.com", verify=False)

    assert client.session.verify is False
    assert result["client_id"] == "drive"


def test_aims_app_config_skips_unsuccessful_first_candidate():
    from nxdrive.alfresco.auth.oauth2 import discover_aims_config

    failed = MagicMock(ok=False)
    successful = MagicMock(ok=True)
    successful.json.return_value = {
        "oauth2": {
            "host": "https://idp.example.com/realms/alfresco",
            "clientId": "drive",
        }
    }
    responses = [failed, failed, successful]

    with patch("alfresco.Alfresco", side_effect=RuntimeError("no SDK")), patch(
        "nxdrive.alfresco.auth.oauth2.requests.get", side_effect=responses
    ):
        result = discover_aims_config("https://alfresco.example.com")

    assert result["client_id"] == "drive"
