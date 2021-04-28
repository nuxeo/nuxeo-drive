from unittest.mock import patch

import pytest

from nxdrive.engine.engine import Engine
from nxdrive.exceptions import FolderAlreadyUsed


def test_bind_local_folder_already_used(manager_factory, tmp, nuxeo_url, user_factory):
    conf_folder = tmp() / "nuxeo-conf"
    user = user_factory()
    manager, engine = manager_factory()

    with manager:
        # First bind: OK
        manager.bind_server(
            conf_folder,
            nuxeo_url,
            user.uid,
            password=user.properties["password"],
            start_engine=False,
        )

        # Check Engine.export()
        # ... which calls Worker.export()
        #      ... which calls Action.export()
        assert engine.export()

        # Second bind: Error
        with pytest.raises(FolderAlreadyUsed):
            manager.bind_server(
                conf_folder,
                nuxeo_url,
                user.uid,
                password=user.properties["password"],
                start_engine=False,
            )


def test_bind_failure_database_removal(manager_factory, tmp, nuxeo_url, user_factory):
    local_folder = tmp()
    user = user_factory()

    def bind_failure(self, *args, **kwargs):
        raise TypeError("Mock'ed error")

    with manager_factory(with_engine=False) as manager:
        # There is no database for now
        assert not list(manager.home.glob("ndrive_*"))

        # Try to bind the account, it will fail
        with patch.object(Engine, "bind", new=bind_failure), pytest.raises(TypeError):
            manager.bind_server(
                local_folder,
                nuxeo_url,
                user.uid,
                password=user.properties["password"],
                start_engine=False,
            )

        # Check that no databases files are left behind
        assert not list(manager.home.glob("ndrive_*"))
