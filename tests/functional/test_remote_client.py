# coding: utf-8
import pytest
from nuxeo.models import Document


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
            conf_folder, nuxeo_url, user.uid, user.password, start_engine=False
        )

        folder = engine.remote.personal_space()
        assert isinstance(folder, Document)
