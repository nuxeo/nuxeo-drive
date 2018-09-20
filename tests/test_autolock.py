# coding: utf-8
"""
Test the Auto-Lock feature used heavily by Direct Edit.
"""
from typing import Dict, List, Tuple
from unittest.mock import Mock, patch

import pytest

import nxdrive.autolocker


class DAO:
    """Minimal ManagerDAO for a working Auto-Lock."""

    # {path: (process, doc_id)}
    paths: Dict[str, Tuple[int, str]] = {}

    def get_locked_paths(self) -> List[str]:
        return list(self.paths.keys())

    def lock_path(self, path: str, process: int, doc_id: str) -> None:
        self.paths[path] = (process, doc_id)

    def unlock_path(self, path: str) -> None:
        self.paths.pop(path, None)


@pytest.fixture(scope="function")
def autolock(tmpdir):
    check_interval = 5
    return nxdrive.autolocker.ProcessAutoLockerWorker(
        check_interval, DAO(), str(tmpdir)
    )


def test_autolock(autolock, tmpdir):
    """Start the worker and simulate files to (un)lock."""
    autolock._thread.start()
    autolock._poll()

    # Unlock an orphaned document
    autolock.orphan_unlocked("foo.txt")

    # Simulate watched files
    autolock.set_autolock("already_locked.ods", Mock())
    autolock.set_autolock("abc こん ツリー/2.ods", Mock())

    def files() -> List[Tuple[int, str]]:
        # Watched file to unlock
        yield 4, "already_locked.ods"
        # Check if the next command does nothing as the file is already watched
        autolock.set_autolock("already_locked.ods", Mock())

        # New watched file
        yield 42, str(tmpdir / "myfile.doc")

        # File not monitored, e.g. not in the watched folder
        yield 7071, "He-Who-Must-Not-Be-Named.lock"

    with patch.object(nxdrive.autolocker, "get_open_files", new=files):
        autolock._poll()

    autolock.stop()
