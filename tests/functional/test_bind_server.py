# coding: utf-8
import pytest

from nxdrive.exceptions import FolderAlreadyUsed


def test_bind_local_folder_already_used(manager_factory, tmp, nuxeo_url, user_factory):
    conf_folder = tmp() / "nuxeo-conf"
    user = user_factory()
    manager, engine = manager_factory()

    with manager:
        # First bind: OK
        manager.bind_server(
            conf_folder, nuxeo_url, user.uid, user.password, start_engine=False
        )

        # Check Engine.export()
        # ... which calls Worker.export()
        #      ... which calls Action.export()
        assert engine.export()

        # Second bind: Error
        with pytest.raises(FolderAlreadyUsed):
            manager.bind_server(
                conf_folder, nuxeo_url, user.uid, user.password, start_engine=False
            )
