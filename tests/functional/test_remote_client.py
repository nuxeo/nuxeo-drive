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
