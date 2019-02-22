# coding: utf-8
import os
import shutil

from nxdrive.engine.queue_manager import QueueManager
from nxdrive.manager import Manager


# Add Manager and QueueManager features for tests
def dispose_all(self) -> None:
    for engine in self.get_engines().values():
        engine.dispose_db()
    self.dispose_db()


def unbind_all(self) -> None:
    if not self._engines:
        self.load()
    for engine in self._engine_definitions:
        self.unbind_engine(engine.uid)


def requeue_errors(self) -> None:
    with self._error_lock:
        for doc_pair in self._on_error_queue.values():
            doc_pair.error_next_try = 0


def _basename(path):
    """
    Patch shutil._basename for pathlib compatibility.

    TODO: remove when https://bugs.python.org/issue32689 is fixed (Python 3.7.3 or newer)
    """
    if isinstance(path, os.PathLike):
        return path.name

    sep = os.path.sep + (os.path.altsep or "")
    return os.path.basename(path.rstrip(sep))


Manager.dispose_all = dispose_all
Manager.unbind_all = unbind_all
QueueManager.requeue_errors = requeue_errors
shutil._basename = _basename

# Remove feature for tests
Manager._create_server_config_updater = lambda *args: None
