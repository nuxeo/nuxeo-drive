import os

import pytest

from nxdrive.exceptions import FolderAlreadyUsed
from nxdrive.options import Options

from .. import ensure_no_exception
from ..markers import not_windows


def test_crash_no_engine_database(manager_factory):
    """
        Drive should not crash when the engine database is removed.  Traceback:

    ERROR nxdrive.engine.engine Setting invalid credentials, reason is: found no password nor token in engine configuration  # noqa
    Traceback (most recent call last):
      File "engine/engine.py", line 661, in stop
        if not self._local_watcher.thread.wait(5000):
      AttributeError: 'Engine' object has no attribute '_local_watcher'
    """

    manager, engine = manager_factory()

    with manager:
        # There is 1 bound engine
        assert manager.engines

        # Simulate the database file removal
        db_file = engine._get_db_file()
        engine.dispose_db()
        os.rename(db_file, f"{db_file}.or")

        # This line must not make the interpreter to crash
        manager.load()

        # There is no bound engine
        assert not manager.engines

        # Restore the file and check all is fixed
        os.rename(f"{db_file}.or", db_file)
        manager.load()
        assert manager.engines


@pytest.mark.parametrize("sync_enabled", [True, False])
@Options.mock()
def test_crash_engine_no_local_folder(manager_factory, sync_enabled):
    """
        Drive should not crash when the engine local folder is removed.  Traceback:

    Traceback (most recent call last):
      File "nxdrive/__main__.py", line 113, in main
      File "nxdrive/commandline.py", line 507, in handle
      File "nxdrive/commandline.py", line 514, in get_manager
      File "nxdrive/manager.py", line 175, in __init__
      File "nxdrive/manager.py", line 377, in load
      File "nxdrive/engine/engine.py", line 144, in __init__
      File "nxdrive/utils.py", line 149, in find_suitable_tmp_dir
      File "pathlib.py", line 1168, in stat
    FileNotFoundError: [Errno 2] No such file or directory: '/home/nuxeo/Drive/Company UAT'
    """
    import shutil

    Options.feature_synchronization = sync_enabled

    manager, engine = manager_factory()

    engine.local.unset_readonly(engine.local_folder)
    if sync_enabled:
        shutil.rmtree(engine.local_folder)
    assert not engine.local_folder.is_dir()

    with manager:
        # Trigger engines reload as it is done in __init__()
        manager.load()


@not_windows(reason="PermissionError when trying to delete the file.")
def test_manager_engine_removal(manager_factory):
    """NXDRIVE-1618: Remove inexistent engines from the Manager engines list."""

    manager, engine = manager_factory()

    # Remove the database file
    os.remove(engine._get_db_file())

    with manager:
        # Trigger engines reload as it is done in __init__()
        manager.load()

        # There should be no engine
        assert not manager.engines


@not_windows(reason="PermissionError when trying to delete the file.")
def test_manager_account_addition_same_folder_used(tmp, manager_factory):
    """NXDRIVE-1783: Handle account addition with already used local folder."""

    home = tmp()
    manager, engine = manager_factory(home=home)

    # Remove the database file
    os.remove(engine._get_db_file())

    with ensure_no_exception(), manager:
        # Instantiate a second manager with its engine using the same home folder.
        # It should not fail on:
        #     sqlite3.IntegrityError: UNIQUE constraint failed: Engines.local_folder
        with pytest.raises(FolderAlreadyUsed):
            manager2, engine2 = manager_factory(home=home)
