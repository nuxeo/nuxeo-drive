from unittest.mock import Mock, patch

import pytest
from nuxeo.models import Document

from nxdrive.engine.activity import Action, DownloadAction, UploadAction
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

    def get_current_action__(*args, **kwargs):
        obj = UploadAction("path", 1)
        return obj

    def set_transfer_progress_(*args, **kwargs):
        return

    def get_download_(*args, **kwargs):
        mocked_download_obj_ = Mock()
        mocked_download_obj_.name = "mocked-download-obj"
        mocked_download_obj_.progress = 80
        mocked_download_obj_.status = 2
        return mocked_download_obj_

    def get_upload_(*args, **kwargs):
        mocked_upload_obj_ = Mock()
        mocked_upload_obj_.name = "mocked-upload-obj"
        mocked_upload_obj_.progress = 80
        mocked_upload_obj_.status = 2
        return mocked_upload_obj_

    obj1_ = Mock()
    with manager:
        with patch.object(Action, "get_current_action", new=get_current_action_):
            with patch.object(remote.dao, "get_download", new=get_download_):
                with patch.object(
                    remote.dao, "set_transfer_progress", new=set_transfer_progress_
                ):
                    with pytest.raises(Exception) as err:
                        remote.transfer_end_callback(obj1_)
                        assert err
        with patch.object(Action, "get_current_action", new=get_current_action__):
            with patch.object(remote.dao, "get_upload", new=get_upload_):
                with pytest.raises(Exception) as err:
                    remote.transfer_end_callback(obj1_)
                    assert err
