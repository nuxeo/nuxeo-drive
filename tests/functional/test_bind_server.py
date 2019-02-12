# coding: utf-8
import pytest

from nxdrive.exceptions import FolderAlreadyUsed


def test_bind_local_folder_already_used(manager_factory, tmp, nuxeo_url, user_factory):
    conf_folder = tmp() / "nuxeo-conf"
    user = user_factory()
    manager = manager_factory(with_engine=False)

    # First bind: OK
    manager.bind_server(
        conf_folder, nuxeo_url, user.uid, user.password, start_engine=False
    )

    # Second bind: Error
    with pytest.raises(FolderAlreadyUsed):
        manager.bind_server(
            conf_folder, nuxeo_url, user.uid, user.password, start_engine=False
        )
