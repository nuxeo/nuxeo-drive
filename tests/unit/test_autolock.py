"""
Test the Auto-Lock feature used heavily by Direct Edit.
"""
from pathlib import Path
from typing import List, Tuple
from unittest.mock import Mock, patch

import pytest

import nxdrive.autolocker
from nxdrive.dao.manager import ManagerDAO

from .. import ensure_no_exception


@pytest.fixture(scope="function")
def autolock(tmpdir):
    check_interval = 5
    folder = Path(tmpdir / "edit")
    folder.mkdir(parents=True)
    db = folder.parent / "engine.db"
    manager = Mock()
    manager.dao = ManagerDAO(db)
    autolocker = nxdrive.autolocker.ProcessAutoLockerWorker(
        check_interval, manager, folder
    )
    autolocker.direct_edit = Mock()
    return autolocker


def test_autolock(app, autolock, tmpdir):
    """Start the worker and simulate files to (un)lock."""
    # Unlock an orphaned document
    autolock.orphan_unlocked(autolock._folder / "foo.txt")

    # Simulate watched files
    file1 = autolock._folder / "already_locked.ods"
    file1.touch()
    autolock.set_autolock(file1, Mock())
    autolock.set_autolock(autolock._folder / "abc こん ツリー.ods", Mock())

    # Another file, not yet watched
    file2 = autolock._folder / "myfile.doc"

    def tmp_file(name: str) -> Path:
        file = autolock._folder / name
        file.touch()
        return file

    def files() -> List[Tuple[int, Path]]:
        # Watched file to unlock
        yield 4, file1  # 1

        # Check if the next command does nothing as the file is already watched
        autolock.set_autolock(file1, Mock())

        # New watched file
        file2.touch()
        yield 42, file2  # 2
        # Its temporary sibling should be ignored
        yield 42, tmp_file("~$myfile.doc")

        # Another ignored suffixe
        yield 42, tmp_file("fichier.lock")

        # File not monitored, e.g. not in the watched folder
        not_watched = autolock._folder.parent / "He-Who-Must-Not-Be-Named.lock"
        not_watched.touch()
        yield 7071, not_watched

    with patch.object(nxdrive.autolocker, "get_open_files", new=files):
        with ensure_no_exception():
            # Proceed for the file1 locking, file2 locking is planned
            autolock._process()
            # Proceed for the file2 locking
            autolock._process()
        assert len(autolock._autolocked) == 2
        assert autolock.dao.get_locked_paths() == [file1, file2]


def test_get_open_files():
    """Just check get_open_files() works."""
    files = list(nxdrive.autolocker.get_open_files())

    # Print files for debug purpose, in case the test fails
    for f in files:
        print(f)

    assert files
