import os

from nxdrive.utils import PidLockFile


def test_lock_file(tmp):
    folder = tmp()
    folder.mkdir(parents=True)
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
    folder.mkdir(parents=True)
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
    folder.mkdir(parents=True)
    lock_file = folder / "nxdrive_qt.pid"

    # Inexistant pid
    lock_file.write_text("3857965", encoding="utf-8")

    lock = PidLockFile(folder, "qt")
    pid = lock.lock()
    assert pid is None
    assert lock.locked


def test_already_locked_same_process(tmp):
    folder = tmp()
    folder.mkdir(parents=True)
    lock_file = folder / "nxdrive_qt.pid"

    # Save the current pid
    lock_file.write_text(str(os.getpid()), encoding="utf-8")

    lock = PidLockFile(folder, "qt")
    pid = lock.lock()
    assert pid == os.getpid()
    assert not lock.locked


def test_bad_lock_file_content(tmp):
    folder = tmp()
    folder.mkdir(parents=True)
    lock_file = folder / "nxdrive_qt.pid"

    # Craft a bad lock file
    lock_file.write_text("BOOM", encoding="utf-8")

    lock = PidLockFile(folder, "qt")
    pid = lock.lock()
    assert pid is None
    assert lock_file.is_file()
    assert lock.locked
