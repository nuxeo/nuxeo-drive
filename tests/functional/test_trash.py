from pathlib import Path

import pytest

from nxdrive.client.local import LocalClient
from nxdrive.constants import WINDOWS


def create_tree(tmp):
    filename = "A" * 100
    root = Path(("\\\\?\\" if WINDOWS else "") + str(tmp()))

    path = root
    for _ in range(5):
        # From the third subfolder, the path is not trashable from Explorer
        path = path / filename
    path = path.with_suffix(".txt")

    dirname = path.parent
    if not dirname.is_dir():
        dirname.mkdir(parents=True)
    path.write_bytes(b"Looong filename!")

    return root, path


def test_trash_long_file(tmp):
    local = LocalClient(tmp())
    root, path = create_tree(tmp)

    try:
        local.trash(path)
        assert not path.exists()
    except PermissionError:
        pytest.skip("Cannot trash from different partition.")


def test_trash_long_folder(tmp):
    local = LocalClient(tmp())
    root, path = create_tree(tmp)

    try:
        local.trash(path.parent)
        assert not path.parent.exists()
    except PermissionError:
        pytest.skip("Cannot trash from different partition.")

    try:
        local.trash(root)
        assert not root.exists()
    except PermissionError:
        pytest.skip("Cannot trash from different partition.")
