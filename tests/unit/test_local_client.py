from time import sleep

from nxdrive.client.local import LocalClient


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
