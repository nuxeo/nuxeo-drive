"""Coverage for shared DAO edge cases and queue item selection."""

import sqlite3
from pathlib import Path
from queue import Empty, Queue
from types import SimpleNamespace
from unittest.mock import MagicMock, Mock, call

import pytest

from nxdrive.drive.dao import base as dao_base
from nxdrive.drive.dao import manager as manager_dao
from nxdrive.drive.dao.base import AutoRetryConnection, BaseDAO
from nxdrive.drive.dao.manager import ManagerDAO
from nxdrive.drive.engine.queue_manager import QueueItem, QueueManager


def _write_dao():
    cursor = Mock()
    connection = Mock()
    connection.cursor.return_value = cursor
    dao = SimpleNamespace(
        lock=MagicMock(),
        _get_write_connection=Mock(return_value=connection),
    )
    return dao, cursor


def test_manager_notification_update_executes_expected_statement():
    dao, cursor = _write_dao()
    notification = SimpleNamespace(
        level="warning",
        title="Updated",
        description="Details",
        uid="notification-id",
    )

    ManagerDAO.update_notification(dao, notification)

    cursor.execute.assert_called_once_with(
        "UPDATE Notifications"
        "   SET level = ?,"
        "       title = ?,"
        "       description = ?"
        " WHERE uid = ?",
        ("warning", "Updated", "Details", "notification-id"),
    )


def test_manager_engine_path_update_executes_expected_statement(tmp_path):
    dao, cursor = _write_dao()
    path = tmp_path / "sync"

    ManagerDAO.update_engine_path(dao, "engine-id", path)

    cursor.execute.assert_called_once_with(
        "UPDATE Engines SET local_folder = ? WHERE uid = ?", (path, "engine-id")
    )


def test_manager_old_migrations_create_every_legacy_table():
    cursor = Mock()
    dao = SimpleNamespace(set_schema_version=Mock(), store_int=Mock())

    ManagerDAO._migrate_db_old(dao, cursor, 0)

    assert cursor.execute.call_count == 2
    assert "Notifications" in cursor.execute.call_args_list[0].args[0]
    assert "AutoLock" in cursor.execute.call_args_list[1].args[0]
    assert dao.set_schema_version.call_args_list == [
        call(cursor, 2),
        call(cursor, 3),
        call(cursor, 4),
    ]
    dao.store_int.assert_called_once_with(manager_dao.SCHEMA_VERSION, 4)


def test_manager_migration_requires_a_connection():
    dao = SimpleNamespace(conn=None)
    with pytest.raises(RuntimeError, match="Unable to connect"):
        ManagerDAO._migrate_db(dao, 0)


def test_manager_migration_selects_database_downgrade(monkeypatch):
    from nxdrive.drive.dao.migrations import migration_engine

    engine = Mock()
    engine_type = Mock(return_value=engine)
    monkeypatch.setattr(migration_engine, "MigrationEngine", engine_type)
    monkeypatch.setattr(manager_dao, "APP_VERSION", "current")
    monkeypatch.setattr(manager_dao, "versions_history", {"current": 4})
    connection = Mock()
    dao = SimpleNamespace(
        conn=connection,
        in_tx=None,
        old_migrations_max_schema_version=4,
        _migrate_db_old=Mock(),
    )

    ManagerDAO._migrate_db(dao, 7)

    engine_type.assert_called_once()
    assert engine_type.call_args.args[0] is connection
    engine.execute_database_donwgrade.assert_called_once_with(7, 4, 4)
    assert dao.in_tx is None


def test_auto_retry_cursor_retries_then_raises():
    connection = sqlite3.connect(":memory:", factory=AutoRetryConnection)
    try:
        with pytest.raises(sqlite3.OperationalError, match="no such table"):
            connection.cursor().execute("INSERT INTO missing_table VALUES (1)")
    finally:
        connection.close()


def test_base_dao_removes_an_unrecoverable_corrupt_database(monkeypatch, tmp_path):
    database = tmp_path / "corrupt.db"
    database.write_bytes(b"not sqlite")
    connection = Mock()
    connection.cursor.return_value = Mock()

    monkeypatch.setattr(dao_base, "fix_db", Mock(side_effect=sqlite3.DatabaseError))
    monkeypatch.setattr(BaseDAO, "restore_backup", Mock(return_value=False))
    monkeypatch.setattr(BaseDAO, "_create_main_conn", Mock(return_value=connection))
    monkeypatch.setattr(BaseDAO, "_init_db", Mock())
    monkeypatch.setattr(BaseDAO, "set_schema_version", Mock())
    monkeypatch.setattr(BaseDAO, "_migrate_db", Mock(), raising=False)

    dao = BaseDAO(database)

    assert not database.exists()
    assert dao.migration_success is True


def test_base_dao_rejects_a_missing_main_connection(monkeypatch, tmp_path):
    monkeypatch.setattr(BaseDAO, "_create_main_conn", Mock(return_value=None))

    with pytest.raises(RuntimeError, match="Unable to connect"):
        BaseDAO(tmp_path / "missing-connection.db")


def test_base_dao_string_delegates_to_repr(tmp_path):
    dao = SimpleNamespace(db=tmp_path / "database.db")
    assert BaseDAO.__str__(dao) == repr(dao)


def test_force_commit_runs_a_wal_checkpoint(tmp_path):
    dao, cursor = _write_dao()
    dao._journal_mode = "WAL"
    dao.db = tmp_path / "database.db"

    BaseDAO.force_commit(dao)

    cursor.execute.assert_called_once_with("PRAGMA wal_checkpoint(PASSIVE)")


def test_write_connection_recreates_a_missing_transaction_connection():
    connection = object()
    dao = SimpleNamespace(
        in_tx=42,
        conn=None,
        _create_main_conn=Mock(return_value=connection),
    )

    assert BaseDAO._get_write_connection(dao) is connection
    assert dao.conn is connection


def test_read_connection_recreates_same_thread_transaction_connection(monkeypatch):
    connection = object()
    dao = SimpleNamespace(
        in_tx=42,
        conn=None,
        _create_main_conn=Mock(return_value=connection),
        _conns=SimpleNamespace(),
        _tx_lock=MagicMock(),
    )
    monkeypatch.setattr(dao_base, "current_thread_id", Mock(return_value=42))

    assert BaseDAO._get_read_connection(dao) is connection
    assert dao.conn is connection


def test_read_connection_waits_for_another_transaction_thread(monkeypatch):
    connection = object()
    lock = MagicMock()
    dao = SimpleNamespace(
        in_tx=42,
        conn=Mock(),
        _conns=SimpleNamespace(conn=connection),
        _tx_lock=lock,
    )
    monkeypatch.setattr(dao_base, "current_thread_id", Mock(return_value=99))

    assert BaseDAO._get_read_connection(dao) is connection
    lock.__enter__.assert_called_once_with()
    lock.__exit__.assert_called_once_with(None, None, None)


class _QueueHarness:
    _get_local_folder = QueueManager._get_local_folder
    _get_local_file = QueueManager._get_local_file
    _get_remote_folder = QueueManager._get_remote_folder
    _get_remote_file = QueueManager._get_remote_file
    _get_file = QueueManager._get_file
    get_processors_on = QueueManager.get_processors_on

    def __init__(self):
        self._local_folder_queue = Queue()
        self._local_file_queue = Queue()
        self._remote_folder_queue = Queue()
        self._remote_file_queue = Queue()
        self._get_file_lock = MagicMock()
        self._thread_inspection = MagicMock()
        self._on_error_ids = set()
        self._local_folder_thread = None
        self._local_file_thread = None
        self._remote_folder_thread = None
        self._remote_file_thread = None
        self._processors_pool = []
        self.is_processing_file = Mock(return_value=True)

    def _is_on_error(self, row_id):
        return row_id in self._on_error_ids


_GETTERS = [
    ("_get_local_folder", "_local_folder_queue"),
    ("_get_local_file", "_local_file_queue"),
    ("_get_remote_folder", "_remote_folder_queue"),
    ("_get_remote_file", "_remote_file_queue"),
]


@pytest.mark.parametrize("method_name, queue_name", _GETTERS)
def test_queue_getters_return_none_when_queue_reports_empty(method_name, queue_name):
    manager = _QueueHarness()
    assert getattr(manager, method_name)() is None


@pytest.mark.parametrize("method_name, queue_name", _GETTERS)
def test_queue_getters_handle_empty_race(method_name, queue_name):
    manager = _QueueHarness()
    queue = Mock()
    queue.empty.return_value = False
    queue.get.side_effect = Empty
    setattr(manager, queue_name, queue)

    assert getattr(manager, method_name)() is None


@pytest.mark.parametrize("method_name, queue_name", _GETTERS)
def test_queue_getters_ignore_falsy_items(method_name, queue_name):
    manager = _QueueHarness()
    queue = Mock()
    queue.empty.return_value = False
    queue.get.return_value = None
    setattr(manager, queue_name, queue)

    assert getattr(manager, method_name)() is None


@pytest.mark.parametrize("method_name, queue_name", _GETTERS)
def test_queue_getters_recurse_past_items_on_error(method_name, queue_name):
    manager = _QueueHarness()
    queue = getattr(manager, queue_name)
    blocked = QueueItem(1, "folder" in queue_name, "locally_created")
    available = QueueItem(2, "folder" in queue_name, "locally_created")
    queue.put(blocked)
    queue.put(available)
    manager._on_error_ids.add(blocked.id)

    assert getattr(manager, method_name)() is available


def test_combined_file_getter_rechecks_an_error_item():
    manager = _QueueHarness()
    blocked = QueueItem(1, False, "locally_created")
    manager._local_file_queue = Mock()
    manager._remote_file_queue = Mock()
    manager._local_file_queue.empty.return_value = False
    manager._remote_file_queue.empty.return_value = False
    manager._local_file_queue.qsize.return_value = 2
    manager._remote_file_queue.qsize.return_value = 1
    manager._get_local_file = Mock(side_effect=[blocked, None])
    manager._on_error_ids.add(blocked.id)

    assert manager._get_file() is None
    assert manager._get_local_file.call_count == 2


@pytest.mark.parametrize(
    "thread_name",
    ["_local_folder_thread", "_remote_folder_thread", "_remote_file_thread"],
)
def test_get_processors_on_returns_each_dedicated_worker(thread_name):
    manager = _QueueHarness()
    worker = object()
    setattr(manager, thread_name, SimpleNamespace(worker=worker))

    assert manager.get_processors_on(Path("folder")) == [worker]
