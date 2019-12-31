import pathlib
import shutil
from unittest.mock import patch
from uuid import uuid4

import pytest
from nxdrive.client.local import LocalClient
from nxdrive.constants import ROOT, WINDOWS

from .. import env


def test_get_path(tmp):
    folder = tmp()
    folder.mkdir()
    local = LocalClient(folder)
    path = folder / "foo.txt"
    path_upper = folder / "FOO.TXT"

    # The path does not exist, it returns ROOT
    assert local.get_path(pathlib.Path("bar.doc")) == ROOT

    # The path exists, it returns
    assert local.get_path(path) == pathlib.Path("foo.txt")
    assert local.get_path(path_upper) == pathlib.Path("FOO.TXT")


@patch("pathlib.Path.resolve")
@patch("pathlib.Path.absolute")
def test_get_path_permission_error(mocked_resolve, mocked_absolute, tmp):
    folder = tmp()
    folder.mkdir()
    local = LocalClient(folder)
    path = folder / "foo.txt"

    # Path.resolve() raises a PermissionError, it should fallback on .absolute()
    mocked_resolve.side_effect = PermissionError()
    path_abs = local.get_path(path)
    assert mocked_absolute.called

    # Restore the original ehavior and check that .resolved() and .absolute()
    # return the same value.
    mocked_resolve.reset_mock()
    assert local.get_path(path) == path_abs


def test_set_get_xattr_file_not_found():
    """If file is not found, there is no value to retrieve."""
    file = pathlib.Path("file-no-found.txt")

    # This call should not fail
    LocalClient.set_path_remote_id(file, "something")

    # And this one should return an empty string
    assert LocalClient.get_path_remote_id(file) == ""


def test_set_get_xattr_invalid_start_byte(tmp):
    """
    Ensure this will never happen again:
        UnicodeDecodeError: 'utf-8' codec can't decode byte 0x80 in position 8: invalid start byte
    """
    folder = tmp()
    folder.mkdir()

    file = folder / "test-xattr.txt"
    file.write_text("bla" * 3)

    raw_value, result_needed = b"fdrpMACS\x80", "fdrpMACS"
    LocalClient.set_path_remote_id(file, raw_value)
    assert LocalClient.get_path_remote_id(file) == result_needed


@pytest.mark.skipif(not WINDOWS, reason="Windows only")
def test_rename_with_different_partitions(manager_factory):
    """Ensure we can rename a file between different partitions."""
    second_partoche = pathlib.Path(env.SECOND_PARTITION)
    if not second_partoche.is_dir():
        pytest.skip(f"There is no such {second_partoche!r} partition.")

    local_folder = second_partoche / str(uuid4())
    manager, engine = manager_factory(local_folder=local_folder)
    local = engine.local

    try:
        with manager:
            # Ensure folders are on different partitions
            assert manager.home.drive != local.base_folder.drive

            # Relax permissions for the rest of the test
            local.unset_readonly(engine.local_folder)

            # Create a file
            (engine.local_folder / "file Lower.txt").write_text("azerty")

            # Change the case
            local.rename(pathlib.Path("file Lower.txt"), "File LOWER.txt")

            # The file should have its case modified
            children = local.get_children_info(ROOT)
            assert len(children) == 1
            assert children[0].name == "File LOWER.txt"
    finally:
        local.unset_readonly(engine.local_folder)
        shutil.rmtree(local_folder)
