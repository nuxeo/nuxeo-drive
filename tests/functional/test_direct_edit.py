import shutil

import pytest


@pytest.fixture()
def direct_edit(manager_factory):
    manager, _ = manager_factory()

    with manager:
        manager.direct_edit._folder.mkdir()
        yield manager.direct_edit


def test_cleanup_no_local_folder(direct_edit):
    """If local folder does not exist, it should be created."""

    shutil.rmtree(direct_edit._folder)
    assert not direct_edit._folder.is_dir()

    direct_edit._cleanup()
    assert direct_edit._folder.is_dir()


def test_cleanup_file(direct_edit):
    """There should be not files, but in that case, just ignore them."""

    file = direct_edit._folder / "this is a file.txt"
    file.touch()
    file.write_text("bla" * 3)
    assert file.is_file()

    direct_edit._cleanup()

    # The file should still be present as it is ignored by the clean-up
    assert file.is_file()


def test_cleanup_bad_folder_name(direct_edit):
    """Subfolders must be named with valid document UID. Ignore others."""

    folder = direct_edit._folder / "bad folder name"
    folder.mkdir()
    assert folder.is_dir()

    direct_edit._cleanup()

    # The folder should still be present as it is ignored by the clean-up
    assert folder.is_dir()


def test_direct_edit_metrics(direct_edit):
    assert isinstance(direct_edit.get_metrics(), dict)
