from pathlib import Path

from nxdrive.client.local_client import LocalClient


def test_set_get_xattr_file_not_found(tmp):
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
