import os
from unittest.mock import patch

import pytest

from nxdrive.utils import PidLockFile


def test_lock_file(tmp):
    folder = tmp()
    folder.mkdir()
    lock_file = folder / "nxdrive_qt.pid"

    assert not lock_file.is_file()

    lock = PidLockFile(folder, "qt")
    assert not lock.locked

    pid = lock.lock()
    assert pid is None
    assert lock.locked
    assert lock_file.is_file()

    lock.unlock()
    assert lock.locked
    assert not lock_file.is_file()


def test_double_lock(tmp):
    folder = tmp()
    folder.mkdir()
    lock_file = folder / "nxdrive_qt.pid"

    assert not lock_file.is_file()

    lock = PidLockFile(folder, "qt")
    assert not lock.locked

    pid = lock.lock()
    assert pid is None
    assert lock.locked
    assert lock_file.is_file()

    pid = lock.lock()
    assert pid is not None
    assert lock.locked
    assert lock_file.is_file()

    lock.unlock()
    assert lock.locked
    assert not lock_file.is_file()


def test_already_locked(tmp):
    folder = tmp()
    folder.mkdir()
    lock_file = folder / "nxdrive_qt.pid"

    # Inexistent pid
    lock_file.write_text("3857965", encoding="utf-8")

    lock = PidLockFile(folder, "qt")
    pid = lock.lock()
    assert pid is None
    assert lock.locked


def test_already_locked_same_process(tmp):
    folder = tmp()
    folder.mkdir()
    lock_file = folder / "nxdrive_qt.pid"

    # Save the current pid
    lock_file.write_text(str(os.getpid()), encoding="utf-8")

    lock = PidLockFile(folder, "qt")
    pid = lock.lock()
    assert pid == os.getpid()
    assert not lock.locked


@patch("pathlib.Path.unlink")
def test_unlock(mocked_unlink, tmp):
    folder = tmp()
    folder.mkdir()
    lock_file = folder / "nxdrive_qt.pid"

    assert not lock_file.is_file()

    lock = PidLockFile(folder, "qt")

    # Not yet locked
    lock.unlock()

    # Now locked
    lock.lock()

    # Test another OSerror
    mocked_unlink.side_effect = PermissionError("Boom !")
    lock.unlock()


@patch("psutil.Process.create_time")
def test_check_running_process_creation_time_too_high(mocked_create_time, tmp):
    folder = tmp()
    folder.mkdir()

    lock = PidLockFile(folder, "qt")
    lock.lock()

    # Test process creation time
    mocked_create_time.return_value = 999_999_999_999
    assert not lock.check_running()


@patch("pathlib.Path.unlink")
def test_check_running(mocked_unlink, tmp):
    folder = tmp()
    folder.mkdir()
    lock_file = folder / "nxdrive_qt.pid"

    lock = PidLockFile(folder, "qt")
    lock.lock()

    # Set false PID number
    lock_file.write_text("999999999")

    # Test another OSerror
    mocked_unlink.side_effect = PermissionError("Boom !")
    assert lock.check_running() == 999_999_999

    # Set PID data not int
    lock_file.write_text("999-999,999")
    assert lock.check_running() is None


def test_bad_lock_file_content(tmp):
    folder = tmp()
    folder.mkdir()
    lock_file = folder / "nxdrive_qt.pid"

    # Craft a bad lock file
    lock_file.write_text("BOOM", encoding="utf-8")

    lock = PidLockFile(folder, "qt")
    pid = lock.lock()
    assert pid is None
    assert lock_file.is_file()
    assert lock.locked


@patch("os.getpid")
def test_os_getpid_not_int(mocked_getpid, tmp):
    folder = tmp()
    folder.mkdir()

    mocked_getpid.return_value = "Boom !"

    lock = PidLockFile(folder, "qt")
    with pytest.raises(RuntimeError):
        lock.lock()
