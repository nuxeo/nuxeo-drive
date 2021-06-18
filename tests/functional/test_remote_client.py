import pytest
from nuxeo.models import Document

from nxdrive.metrics.constants import GLOBAL_METRICS
from nxdrive.options import Options


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
