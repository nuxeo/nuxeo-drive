# coding: utf-8
import os
import os.path
from contextlib import suppress
from tempfile import gettempdir

import pytest
from send2trash import send2trash as trash

from nxdrive.constants import WINDOWS


def create_tree():
    filename = "A" * 100
    if WINDOWS:
        parent = "\\\\?\\"
    else:
        parent = ""
    parent += os.path.join(gettempdir(), filename)
    path = os.path.join(
        parent,
        filename,
        filename,  # From there, the path is not trashable from Explorer
        filename,
        filename + ".txt",
    )

    dirname = os.path.dirname(path)
    if not os.path.isdir(dirname):
        os.makedirs(dirname)
    with open(path, "wb") as writer:
        writer.write(b"Looong filename!")
    return path


def test_trash_long_file():
    path = create_tree()
    parent = os.path.dirname(path)
    try:
        trash(path)
        assert not os.path.exists(path)
    except PermissionError:
        pytest.skip("Cannot trash from different partition.")
    finally:
        with suppress(OSError):
            os.remove(parent)


def test_trash_long_folder():
    path = create_tree()
    parent = os.path.dirname(path)
    try:
        trash(path)
        assert not os.path.exists(path)
    except PermissionError:
        pytest.skip("Cannot trash from different partition.")
    finally:
        with suppress(OSError):
            os.remove(parent)
