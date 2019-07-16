from pathlib import Path
from unittest.mock import Mock

from nxdrive.client.local_client import LocalClient
from nxdrive.constants import ROOT


def test_get_path(tmp):
    folder = tmp()
    folder.mkdir()
    local = LocalClient(folder)
    path = folder / "foo.txt"
    path_upper = folder / "FOO.TXT"

    # The path does not exist, it returns ROOT
    assert local.get_path(Path("bar.doc")) == ROOT

    # The path exists, it returns
    assert local.get_path(path) == Path("foo.txt")
    assert local.get_path(path_upper) == Path("FOO.TXT")

    # Path.resolve() raises a PermissionError, it should fallback on .absolute()
    Path.resolve = Mock(side_effect=PermissionError())
    Path.absolute = Mock()
    path_abs = local.get_path(path)
    assert Path.absolute.called

    # Restore the original ehavior and check that .resolved() and .absolute()
    # return the same value.
    Path.resolve.reset_mock()
    assert local.get_path(path) == path_abs


def test_set_get_xattr_file_not_found():
    """If file is not found, there is no value to retrieve."""
    file = Path("file-no-found.txt")

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
