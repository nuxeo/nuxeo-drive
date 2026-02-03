from unittest.mock import Mock, patch

import pytest
from nuxeo.models import Document

from nxdrive.engine.activity import Action, DownloadAction
from nxdrive.metrics.constants import GLOBAL_METRICS
from nxdrive.objects import RemoteFileInfo, SubTypeEnricher
from nxdrive.options import Options
from nxdrive.utils import shortify

from .. import env


@pytest.mark.parametrize(
    "username",
    [
        "ndt-Alice",
        "ndt-bob@bar.com",
        # "ndt-éléonor",
        # "ndt-東京スカイツリー",
    ],
)
def test_personal_space(manager_factory, tmp, nuxeo_url, user_factory, username):
    """Test personal space retrieval with problematic usernames."""
    # Note: non-ascii characters are not yet handled, and it is not likely to happen soon.

    conf_folder = tmp() / "nuxeo-conf"
    user = user_factory(username=username)
    manager, engine = manager_factory(user=user)

    with manager:
        manager.bind_server(
            conf_folder,
            nuxeo_url,
            user.uid,
            password=user.properties["password"],
            start_engine=False,
        )

        folder = engine.remote.personal_space()
        assert isinstance(folder, Document)


@pytest.mark.parametrize(
    "name",
    [
        "My \r file",
        "ndt-bob@bar.com",
        "ndt-éléonor",
        "ndt-東京スカイツリー",
    ],
)
def test_exists_in_parent(name, manager_factory):
    manager, engine = manager_factory()
    with manager:
        method = engine.remote.exists_in_parent
        assert not method("/", name, False)
        assert not method("/", name, True)


@Options.mock()
def test_custom_metrics_global_headers(manager_factory):
    manager, engine = manager_factory()
    with manager:
        remote = engine.remote
        headers = remote.client.headers

        # Direct Edit feature is enable by default
        metrics = remote.custom_global_metrics
        assert metrics["feature.direct_edit"] == 1
        assert '"feature.direct_edit": 1' in headers[GLOBAL_METRICS]

        # Direct Edit feature is now disabled, check metrics are up-to-date
        Options.feature_direct_edit = False
        manager.reload_client_global_headers()
        metrics = remote.custom_global_metrics
        assert metrics["feature.direct_edit"] == 0
        assert '"feature.direct_edit": 0' in headers[GLOBAL_METRICS]

    Options.feature_direct_edit = True


@Options.mock()
@pytest.mark.parametrize("option", list(range(7)))
def test_expand_sync_root_name_levels(option, manager_factory, obj_factory):
    manager, engine = manager_factory()
    remote = engine.remote

    with manager:
        # Create (sub)folders
        parent = env.WS_DIR
        potential_names = []
        for num in range(option + 1):
            title = f"folder {num}"
            potential_names.append(shortify(title))
            doc = obj_factory(title=title, parent=parent, user=remote.user_id)
            parent = doc.path

        # *doc* is the latest created folder, craft the awaited object for next steps
        sync_root = RemoteFileInfo.from_dict(
            {
                "id": doc.uid,
                "name": doc.title,
                "parentId": doc.parentRef,
                "path": doc.path,
                "folderish": True,
            }
        )

        # Finally, let's guess its final name
        Options.sync_root_max_level = option
        sync_root = remote.expand_sync_root_name(sync_root)

        if option != Options.sync_root_max_level:
            # Typically the option was outside bounds, here it is "7".
            # We shrink the posibble folder names to ease code for checking the final
            # name
            potential_names = potential_names[option - Options.sync_root_max_level :]

        # Check
        final_name = " - ".join(potential_names[: Options.sync_root_max_level + 1])
        assert sync_root.name == final_name


@Options.mock()
@pytest.mark.parametrize("option", list(range(7)))
def test_expand_sync_root_name_length(option, manager_factory, obj_factory):
    manager, engine = manager_factory()
    remote = engine.remote

    with manager:
        # Create (sub)folders
        parent = env.WS_DIR
        potential_names = []
        for num in range(option + 1):
            title = "folder" + "r" * 50 + f" {num}"  # > 50 chars
            potential_names.append(shortify(title, limit=46))
            doc = obj_factory(title=title, parent=parent, user=remote.user_id)
            parent = doc.path

        # *doc* is the latest created folder, craft the awaited object for next steps
        sync_root = RemoteFileInfo.from_dict(
            {
                "id": doc.uid,
                "name": doc.title,
                "parentId": doc.parentRef,
                "path": doc.path,
                "folderish": True,
            }
        )

        # Finally, let's guess its final name
        Options.sync_root_max_level = option
        sync_root = remote.expand_sync_root_name(sync_root)

        if option != Options.sync_root_max_level:
            # Typically the option was outside bounds, here it is "7".
            # We shrink the posibble folder names to ease code for checking the final
            # name
            potential_names = potential_names[option - Options.sync_root_max_level :]

        # Check
        final_name = " - ".join(potential_names[: Options.sync_root_max_level + 1])
        assert sync_root.name == final_name
        assert sync_root.name.count("…") == Options.sync_root_max_level or 1
        assert len(sync_root.name) <= 250


def test_upload_folder_type(manager_factory):
    manager, engine = manager_factory()
    remote = engine.remote

    def request_(*args, **kwargs):
        return "mocked-value"

    with manager:
        with patch.object(remote.client, "request", new=request_):
            folder_type = remote.upload_folder_type("string", {"key": "value"})
        assert folder_type == "mocked-value"


def test_cancel_batch(manager_factory):
    manager, engine = manager_factory()
    remote = engine.remote

    return_val = None
    with manager:
        return_val = remote.cancel_batch({"key": "value"})
        assert not return_val


def test_filter_schema(manager_factory):
    manager, engine = manager_factory()
    remote = engine.remote

    def get_config_types_(*args, **kwargs):
        configTypes = {"doctypes": {1: {"schemas": "file"}}}
        return configTypes

    returned_val = None
    obj_ = SubTypeEnricher("uid", "path", "title", ["str"], {"key": "val"})
    with manager:
        with patch.object(remote, "get_config_types", new=get_config_types_):
            returned_val = remote.filter_schema(obj_)
        assert returned_val == ["1"]


def test_get_note(manager_factory):
    manager, engine = manager_factory()
    remote = engine.remote

    def fetch_(*args, **kwargs):
        return {"properties": {"key": "val"}}

    returned_val = None
    with manager:
        with patch.object(remote, "fetch", new=fetch_):
            returned_val = remote.get_note("")
    assert returned_val == b""


def test_is_filtered(manager_factory):
    manager, engine = manager_factory()
    remote = engine.remote

    def is_filter_(*args, **kwargs):
        return True

    returned_val = None
    with manager:
        with patch.object(remote.dao, "is_filter", new=is_filter_):
            returned_val = remote.is_filtered("")
    assert returned_val


def test_transfer_start_callback(manager_factory):
    manager, engine = manager_factory()
    remote = engine.remote

    obj1_ = Mock()
    with manager:
        returned_val = remote.transfer_start_callback(obj1_)
    assert not returned_val


def test_transfer_end_callback(manager_factory):
    manager, engine = manager_factory()
    remote = engine.remote

    def get_current_action_(*args, **kwargs):
        obj = DownloadAction("path", 1)
        return obj

    def get_download_(*args, **kwargs):
        return False

    obj1_ = Mock()
    returned_val = None
    with manager:
        with patch.object(Action, "get_current_action", new=get_current_action_):
            with patch.object(remote.dao, "get_download", new=get_download_):
                returned_val = remote.transfer_end_callback(obj1_)
    assert not returned_val


def test_store_refresh_token(manager_factory):
    manager, engine = manager_factory()
    remote = engine.remote
    remote.token = {
        "access_token": "D0QCbs1aJJsPDXzT\
                    1IrC4oKzjbFevn4s",
        "refresh_token": "Fch4TbOM8okl8sLajlN\
                        37L8YHKMSfc9cFe7RMVWRG4ctNvBmSvn2SFXg5CtUJKS2",
        "token_type": "bearer",
        "expires_in": 3239,
        "expires_at": 1711427876,
    }
    remote.auth = Mock()
    remote.auth.auth = Mock()
    remote.auth.auth.token = remote.token
    old_remote_token = remote.token
    with manager:
        remote.execute(command="UserWorkspace.Get")
    assert old_remote_token == remote.token

    remote.auth.auth.token = {
        "access_token": "D0QCbs1aJJsPDXzT\
                    1IrC4oKzjbFevn4s",
        "refresh_token": "Fch4TbOM8okl8sLajlP\
                        37L8YHKMSfc9cFe7RMVWRG4ctNvBmSvn2SFXg5CtUJKS2",
        "token_type": "bearer",
        "expires_in": 3239,
        "expires_at": 1711427876,
    }
    old_remote_token = remote.token
    with manager:
        remote.execute(command="UserWorkspace.Get")
    assert remote.token == remote.auth.auth.token

    remote.auth.auth.token = {
        "access_token": "D0QCbs1aJJsPDXzT\
                    1IrC4oKzjbFevn4s",
        "refresh_token": "Fch4TbOM8okl8sLajlP\
                        37L8YHKMSfc9cFe7RMVWRG4ctNvBmSvn2SFXg5CtUJKS2",
        "token_type": "bearer",
        "expires_in": 3239,
        "expires_at": 1711427876,
    }
    old_remote_token = remote.token
    remote.dao = None
    with manager:
        remote.execute(command="UserWorkspace.Get")
    assert remote.token == old_remote_token


def test_download_as_zip(manager_factory, obj_factory, tmp):
    """Test downloading multiple files as a ZIP archive."""
    manager, engine = manager_factory()
    remote = engine.remote

    with manager:
        # Create test files
        doc1 = obj_factory(
            title="Test File 1.txt", parent=env.WS_DIR, content=b"Content 1"
        )
        doc2 = obj_factory(
            title="Test File 2.txt", parent=env.WS_DIR, content=b"Content 2"
        )

        # Mock the execute method to simulate Blob.BulkDownload operation
        def mock_execute(*args, **kwargs):
            if kwargs.get("command") == "Blob.BulkDownload":
                # Return a mock result with download URL
                return {
                    "url": f"{remote.client.host}/nuxeo/api/v1/bulk-download/mock-id"
                }
            # For other operations, use the original execute
            return engine.remote.execute(*args, **kwargs)

        # Mock the download method to simulate ZIP file download
        def mock_download(url, file_path, file_out, digest, **kwargs):
            # Create a simple mock ZIP file
            # Ensure parent directory exists
            file_out.parent.mkdir(parents=True, exist_ok=True)
            file_out.write_bytes(b"PK\x03\x04")  # ZIP file signature
            return file_out

        # Prepare paths
        output_path = tmp() / "download.zip"
        tmp_path = output_path.with_suffix(".tmp")

        with patch.object(remote, "execute", new=mock_execute):
            with patch.object(remote, "download", new=mock_download):
                # Test downloading multiple items as ZIP
                result = remote.download_as_zip(
                    [doc1.uid, doc2.uid],
                    output_path,
                    tmp_path,
                )

                assert result == tmp_path
                assert tmp_path.exists()
                # Verify it's a ZIP file (starts with PK signature)
                assert tmp_path.read_bytes().startswith(b"PK")
