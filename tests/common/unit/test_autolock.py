"""
Test the Auto-Lock feature used heavily by Direct Edit.
"""

from pathlib import Path
from types import SimpleNamespace
from typing import List, Tuple
from unittest.mock import Mock, patch

import pytest
import psutil

import nxdrive.drive.autolocker
from nxdrive.drive.dao.manager import ManagerDAO
from nxdrive.drive.exceptions import ThreadInterrupt

from ... import ensure_no_exception


@pytest.fixture(scope="function")
def autolock(tmpdir):
    check_interval = 5
    folder = Path(tmpdir / "edit")
    folder.mkdir(parents=True)
    db = folder.parent / "engine.db"
    manager = Mock()
    manager.dao = ManagerDAO(db)
    autolocker = nxdrive.drive.autolocker.ProcessAutoLockerWorker(
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

    with (
        patch.object(nxdrive.drive.autolocker, "get_open_files", new=files),
        patch.object(nxdrive.drive.autolocker, "sleep"),
    ):
        with ensure_no_exception():
            # Proceed for the file1 locking, file2 locking is planned
            autolock._process()
            # Proceed for the file2 locking
            autolock._process()
        assert len(autolock._autolocked) == 2
        assert autolock.dao.get_locked_paths() == [file1, file2]


def _process(pid, name, *, opened=()):
    process = Mock(pid=pid, info={"username": "tester"})
    process.name.return_value = name
    process.open_files.return_value = opened
    return process


def test_get_open_files_windows_filters_processes_and_errors(tmp_path):
    """Only monitored Windows applications should contribute open files."""
    module = nxdrive.drive.autolocker
    document = tmp_path / "document.docx"
    fallback = tmp_path / "fallback.docx"

    monitored = _process(
        10, "WINWORD.EXE", opened=[SimpleNamespace(path=str(document))]
    )
    ignored = _process(
        11, "textedit.exe", opened=[SimpleNamespace(path=str(tmp_path / "ignored"))]
    )
    vanished = _process(12, "excel.exe")
    vanished.open_files.side_effect = psutil.NoSuchProcess(vanished.pid)
    denied = _process(13, "powerpnt.exe")
    denied.open_files.side_effect = psutil.AccessDenied(denied.pid)
    broken = _process(14, "photoshop.exe")
    broken.open_files.side_effect = RuntimeError("process changed")

    with (
        patch.object(module, "WINDOWS", True),
        patch.object(
            module.psutil,
            "process_iter",
            return_value=[monitored, ignored, vanished, denied, broken],
        ) as process_iter,
        patch.object(
            module, "get_other_opened_files", return_value=iter([(99, fallback)])
        ),
    ):
        assert list(module.get_open_files()) == [
            (monitored.pid, document),
            (99, fallback),
        ]

    process_iter.assert_called_once_with(attrs=["pid", "name", "username"])
    process_iter.cache_clear.assert_called_once_with()
    ignored.open_files.assert_not_called()


def test_get_open_files_windows_recovers_from_enumeration_error(tmp_path):
    """A process-enumeration failure must not hide OS-specific fallback results."""
    module = nxdrive.drive.autolocker
    fallback = tmp_path / "fallback.docx"

    with (
        patch.object(module, "WINDOWS", True),
        patch.object(module.psutil, "process_iter", side_effect=MemoryError),
        patch.object(
            module, "get_other_opened_files", return_value=iter([(7, fallback)])
        ),
    ):
        assert list(module.get_open_files()) == [(7, fallback)]


def test_get_open_files_unix_suppresses_process_and_handler_errors(tmp_path):
    """Unix process races should be ignored without touching real processes."""
    module = nxdrive.drive.autolocker
    document = tmp_path / "document.odt"
    fallback = tmp_path / "fallback.odt"

    class UnreadableHandler:
        @property
        def path(self):
            raise OSError("file disappeared")

    readable = _process(
        20,
        "writer",
        opened=[SimpleNamespace(path=str(document)), UnreadableHandler()],
    )
    inaccessible = _process(21, "calc")
    inaccessible.open_files.side_effect = psutil.AccessDenied(inaccessible.pid)

    def processes(*, attrs):
        assert attrs == ["pid"]
        yield readable
        yield inaccessible
        raise OSError("process table unavailable")

    with (
        patch.object(module, "WINDOWS", False),
        patch.object(module.psutil, "process_iter", new=processes),
        patch.object(
            module, "get_other_opened_files", return_value=iter([(8, fallback)])
        ),
    ):
        assert list(module.get_open_files()) == [
            (readable.pid, document),
            (8, fallback),
        ]


def test_poll_emits_orphans_only_on_first_successful_poll(app, autolock):
    locked = [autolock._folder / "orphan.docx"]
    emitted = []
    autolock.dao.get_locked_paths = Mock(return_value=locked)
    autolock._process = Mock()
    autolock.orphanLocks.connect(emitted.append)

    assert autolock._poll() is True
    assert autolock._poll() is True

    assert emitted == [locked]
    assert autolock._first is False
    autolock.dao.get_locked_paths.assert_called_once_with()
    assert autolock._process.call_count == 2


def test_poll_reraises_thread_interrupt(autolock):
    autolock._first = False
    autolock._process = Mock(side_effect=ThreadInterrupt)

    with pytest.raises(ThreadInterrupt):
        autolock._poll()


def test_poll_reports_unhandled_error(autolock):
    autolock._first = False
    autolock._process = Mock(side_effect=RuntimeError("broken poll"))

    with patch.object(nxdrive.drive.autolocker, "log") as log:
        assert autolock._poll() is False

    log.exception.assert_called_once_with("Unhandled error")
