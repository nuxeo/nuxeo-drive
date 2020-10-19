import pathlib
from time import sleep

from nxdrive.client.local import LocalClient
from nxdrive.constants import ROOT


def test_get_path(tmp_path):
    local = LocalClient(tmp_path)
    path = tmp_path / "foo.txt"
    path_upper = tmp_path / "FOO.TXT"

    # The path does not exist, it returns ROOT
    assert local.get_path(pathlib.Path("bar.doc")) == ROOT

    # The path exists, it returns
    assert local.get_path(path) == pathlib.Path("foo.txt")
    assert local.get_path(path_upper) == pathlib.Path("FOO.TXT")


def test_xattr_crud(tmp_path):
    """CRUD tests."""

    local = LocalClient(tmp_path)
    file = tmp_path / "File 1.txt"
    file.write_bytes(b"baz\n")

    ref = file.name

    # Create
    local.set_remote_id(ref, "𝖀𝖓𝖎𝖈𝖔𝖉𝖊")
    local.set_remote_id(ref, "TEST", name="foo")

    # Read
    local.get_remote_id(ref) == "𝖀𝖓𝖎𝖈𝖔𝖉𝖊"
    local.get_remote_id(ref, name="foo") == "TEST"
    local.get_remote_id(ref, name="inexistent") == ""

    # Update
    local.set_remote_id(ref, "𝖀𝖓𝖎𝖈𝖔𝖉𝖊 with Space")
    local.set_remote_id(ref, "TEST2", name="foo")
    local.get_remote_id(ref) == "𝖀𝖓𝖎𝖈𝖔𝖉𝖊 with Space"
    local.get_remote_id(ref, name="foo") == "TEST2"

    # Delete
    local.remove_remote_id(ref)
    local.remove_remote_id(ref, name="foo")
    local.remove_remote_id(ref, name="inexistent")
    local.get_remote_id(ref) == ""
    local.get_remote_id(ref, name="foo") == ""


def test_xattr_mtime(tmp_path):
    """Ensure that playing with xattr does not change the file mtime."""

    local = LocalClient(tmp_path)
    file = tmp_path / "File 2.txt"
    file.write_bytes(b"baz\n")

    ref = file.name
    path = local.abspath(ref)
    mtime = int(path.stat().st_mtime)
    sleep(1)
    local.set_remote_id(ref, "TEST")
    assert mtime == int(path.stat().st_mtime)
    sleep(1)
    local.remove_remote_id(ref)
    assert mtime == int(path.stat().st_mtime)


def test_xattr_error_invalid_start_byte(tmp_path):
    """Ensure this will never happen again:
    UnicodeDecodeError: 'utf-8' codec can't decode byte 0x80 in position 8: invalid start byte
    """
    local = LocalClient(tmp_path)
    file = tmp_path / "test-xattr.txt"
    file.write_text("bla" * 3)

    raw_value, result_needed = b"fdrpMACS\x80", "fdrpMACS"
    local.set_path_remote_id(file, raw_value)
    assert local.get_path_remote_id(file) == result_needed
