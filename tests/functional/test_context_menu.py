import pytest

from nxdrive.options import Options


def test_ctx_menu_entry_inexistent_file(manager_factory):
    manager, engine = manager_factory()
    with manager:
        with pytest.raises(ValueError):
            manager.get_metadata_infos("/an inexistent folder/a file.bin")


@Options.mock()
def test_ctx_menu_entries(manager_factory):
    Options.feature_synchronization = True

    manager, engine = manager_factory()
    with manager:
        local = engine.local

        # Create the test file
        folder = local.make_folder(local.base_folder, "a folder")
        file = folder / "a file.bin"
        file.write_bytes(b"something")
        local.set_path_remote_id(file, "fake-doc-id")

        # "Copy share link" entry, it will test copy/paste clipboard stuff
        url = manager.ctx_copy_share_link(file)
        assert url.startswith("http")
        assert "token" not in url
        assert manager.osi.cb_get() == url

        # "Access online" entry
        url = manager.get_metadata_infos(file)
        assert url.startswith("http")
        assert "token" not in url

        # "Edit metadata" entry
        url_edit = manager.get_metadata_infos(file, edit=True)
        assert url.startswith("http")
        if engine.wui == "web":
            assert url_edit == url
        else:
            # JSF has a different view
            assert url_edit != url
        assert "token" not in url
