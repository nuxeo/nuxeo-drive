# coding: utf-8
from contextlib import suppress
from pathlib import Path
from tempfile import gettempdir

import pytest
from send2trash import send2trash as trash


def create_tree():
    filename = "A" * 100
    path = Path(gettempdir())

    for i in range(5):
        # From the third subfolder, the path is not trashable from Explorer
        path = path / filename
    path = path.with_suffix(".txt")

    dirname = path.parent
    if not dirname.is_dir():
        dirname.mkdir(parents=True)
    path.write_bytes(b"Looong filename!")

    return path


def test_trash_long_file():
    path = create_tree()
    try:
        trash(path)
        assert not path.exists()
    except PermissionError:
        pytest.skip("Cannot trash from different partition.")
    finally:
        with suppress(OSError):
            path.parent.unlink()


def test_trash_long_folder():
    path = create_tree()
    try:
        trash(path)
        assert not path.exists()
    except PermissionError:
        pytest.skip("Cannot trash from different partition.")
    finally:
        with suppress(OSError):
            path.parent.unlink()
