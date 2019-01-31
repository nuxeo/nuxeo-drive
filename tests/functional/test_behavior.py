import os


def test_crash_no_engine_database(manager_factory):
    """
    Drive should not crash when the engine database is removed.  Traceback:

ERROR nxdrive.engine.engine Setting invalid credentials, reason is: found no password nor token in engine configuration
Traceback (most recent call last):
File "engine/engine.py", line 661, in stop
if not self._local_watcher.get_thread().wait(5000):
AttributeError: 'Engine' object has no attribute '_local_watcher'
    """

    manager, engine = manager_factory()

    with manager:
        # There is no bound engine
        assert manager._engines

        # Simulate the database file removal
        db_file = engine._get_db_file()
        engine.dispose_db()
        os.rename(db_file, f"{db_file}.or")

        # This line must not make the interpreter to crash
        manager.load()

        # There is no bound engine
        assert not manager._engines

        # Restore the file and check all is fixed
        os.rename(f"{db_file}.or", db_file)
        manager.load()
        assert manager._engines
