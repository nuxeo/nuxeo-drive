import pytest
from nuxeo.models import Document

from nxdrive.metrics.constants import GLOBAL_METRICS
from nxdrive.objects import RemoteFileInfo
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
