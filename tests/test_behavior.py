import os

from .common import UnitTestCase


class TestBehavior(UnitTestCase):
    def test_crash_no_engine_database(self):
        """
        Drive should not crash when the engine database is removed.  Traceback:

ERROR nxdrive.engine.engine Setting invalid credentials, reason is: found no password nor token in engine configuration
Traceback (most recent call last):
File "engine/engine.py", line 661, in stop
    if not self._local_watcher.get_thread().wait(5000):
AttributeError: 'Engine' object has no attribute '_local_watcher'
        """

        # Simulate the database file removal
        db_file = self.engine_1._get_db_file()
        self.engine_1.dispose_db()
        os.rename(db_file, f"{db_file}.or")

        # This line must not make the interpreter to crash
        self.manager_1.load()

        # There is no bound engine
        assert not self.manager_1._engines

        # Restore the file and check all is fixed
        os.rename(f"{db_file}.or", db_file)
        self.manager_1.load()
        assert self.manager_1._engines
