import os

import pytest
from nxdrive.exceptions import FolderAlreadyUsed

from .. import ensure_no_exception
from ..markers import not_windows


def test_crash_no_engine_database(manager_factory):
    """
    Drive should not crash when the engine database is removed.  Traceback:

ERROR nxdrive.engine.engine Setting invalid credentials, reason is: found no password nor token in engine configuration
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


@not_windows(reason="PermissionError when trying to delete the file.")
def test_manager_engine_removal(manager_factory):
    """NXDRIVE-1618: Remove inexistant engines from the Manager engines list."""

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
