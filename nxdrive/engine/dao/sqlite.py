# coding: utf-8
"""
Query formatting in this file is based on http://www.sqlstyle.guide/
"""
import os
from sqlite3 import (
    connect,
    Connection,
    Cursor,
    DatabaseError,
    IntegrityError,
    OperationalError,
    Row,
)
from contextlib import suppress
from datetime import datetime
from logging import getLogger
from pathlib import Path
from threading import RLock, current_thread, local
from typing import Any, Dict, List, Optional, Tuple, Type, Union, TYPE_CHECKING

from PyQt5.QtCore import QObject, pyqtSignal

from .utils import fix_db
from ...client.local_client import FileInfo
from ...constants import ROOT, WINDOWS
from ...exceptions import UnknownPairState
from ...notification import Notification
from ...objects import DocPair, DocPairs, Filters, RemoteFileInfo, EngineDef

if TYPE_CHECKING:
    from ..queue_manager import QueueManager  # noqa

__all__ = ("ConfigurationDAO", "EngineDAO", "ManagerDAO")

log = getLogger(__name__)

SCHEMA_VERSION = "schema_version"

# Summary status from last known pair of states
# (local_state, remote_state)
PAIR_STATES: Dict[Tuple[str, str], str] = {
    # regular cases
    ("unknown", "unknown"): "unknown",
    ("synchronized", "synchronized"): "synchronized",
    ("created", "unknown"): "locally_created",
    ("unknown", "created"): "remotely_created",
    ("modified", "synchronized"): "locally_modified",
    ("moved", "synchronized"): "locally_moved",
    ("moved", "deleted"): "locally_moved_created",
    ("moved", "modified"): "locally_moved_remotely_modified",
    ("synchronized", "modified"): "remotely_modified",
    ("modified", "unknown"): "locally_modified",
    ("unknown", "modified"): "remotely_modified",
    ("deleted", "synchronized"): "locally_deleted",
    ("synchronized", "deleted"): "remotely_deleted",
    ("deleted", "deleted"): "deleted",
    ("synchronized", "unknown"): "synchronized",
    # conflicts with automatic resolution
    ("created", "deleted"): "locally_created",
    ("deleted", "created"): "remotely_created",
    ("modified", "deleted"): "remotely_deleted",
    ("deleted", "modified"): "remotely_created",
    # conflict cases that need manual resolution
    ("modified", "modified"): "conflicted",
    ("created", "created"): "conflicted",
    ("created", "modified"): "conflicted",
    ("moved", "unknown"): "conflicted",
    ("moved", "moved"): "conflicted",
    # conflict cases that have been manually resolved
    ("resolved", "unknown"): "locally_resolved",
    ("resolved", "synchronized"): "synchronized",
    ("created", "synchronized"): "synchronized",
    ("unknown", "synchronized"): "synchronized",
    # inconsistent cases
    ("unknown", "deleted"): "unknown_deleted",
    ("deleted", "unknown"): "deleted_unknown",
    # Ignored documents
    ("unsynchronized", "unknown"): "unsynchronized",
    ("unsynchronized", "created"): "unsynchronized",
    ("unsynchronized", "modified"): "unsynchronized",
    ("unsynchronized", "moved"): "unsynchronized",
    ("unsynchronized", "deleted"): "remotely_deleted",
}


def prepare_args(data: Tuple[Union[Path, str], ...]) -> Tuple[str, ...]:
    """ Convert Path objects to str before insertion into database. """

    data = list(data)  # type: ignore
    for i in range(len(data)):
        if isinstance(data[i], Path):
            path = str(data[i])
            path = "" if path == "." else path
            if not path.startswith("/"):
                path = "/" + path
            data[i] = path  # type: ignore
    return tuple(data)  # type: ignore


def str_to_path(data: str) -> Optional[Path]:
    """ Convert str to Path after querying the database. """
    return None if data == "" else Path(data.lstrip("/"))


class AutoRetryCursor(Cursor):
    def execute(self, *args: str, **kwargs: Any) -> Cursor:
        if len(args) > 1:
            # Convert all Path objects to str
            args = list(args)  # type: ignore
            args[1] = prepare_args(args[1])  # type: ignore
            args = tuple(args)
        count = 1
        while True:
            count += 1
            try:
                return super().execute(*args, **kwargs)
            except OperationalError as exc:
                log.debug(
                    f"Retry locked database #{count}, args={args!r}, kwargs={kwargs!r}"
                )
                if count > 5:
                    raise exc


class AutoRetryConnection(Connection):
    def cursor(self, factory: Type[Cursor] = None) -> Cursor:
        factory = factory or AutoRetryCursor
        return super().cursor(factory)


class ConfigurationDAO(QObject):

    _state_factory = DocPair

    def __init__(self, db: Path) -> None:
        super().__init__()
        log.debug(f"Create DAO on {db!r}")
        self._db = db
        exists = self._db.is_file()

        if exists:
            # Fix potential file corruption
            try:
                fix_db(self._db)
            except DatabaseError:
                # The file is too damaged, just recreate it from scratch.
                # Sync data will not be re-downloaded nor deleted, but a full
                # scan will be done.
                new_name = f"{self._db.name}_{str(int(datetime.now().timestamp()))}"
                self._db.rename(self._db.with_name(new_name))
                exists = False

        self.schema_version = self.get_schema_version()
        self.in_tx = None
        self._tx_lock = RLock()
        self._lock = RLock()
        self._conn: Optional[Connection] = None
        self._connections: List[Connection] = []
        self._conns = local()
        self._create_main_conn()
        if not self._conn:
            raise RuntimeError("Unable to connect to database.")
        c = self._conn.cursor()
        self._init_db(c)
        if exists:
            res = c.execute(
                "SELECT value FROM Configuration WHERE name = ?", (SCHEMA_VERSION,)
            ).fetchone()
            schema = int(res[0]) if res else 0
            if schema != self.schema_version:
                self._migrate_db(c, schema)
        else:
            c.execute(
                "INSERT INTO Configuration (name, value) VALUES (?, ?)",
                (SCHEMA_VERSION, self.schema_version),
            )

    def get_schema_version(self) -> int:
        return 1

    def get_db(self) -> Path:
        return self._db

    def _migrate_table(self, cursor: Cursor, name: str) -> None:
        # Add the last_transfer
        tmpname = f"{name}Migration"

        # In case of a bad/unfinished migration
        cursor.execute(f"DROP TABLE IF EXISTS {tmpname}")

        cursor.execute(f"ALTER TABLE {name} RENAME TO {tmpname}")
        # Because Windows don't release the table, force the creation
        self._create_table(cursor, name, force=True)
        target_cols = self._get_columns(cursor, name)
        source_cols = self._get_columns(cursor, tmpname)
        cols = ", ".join(set(target_cols).intersection(source_cols))
        cursor.execute(f"INSERT INTO {name} ({cols}) SELECT {cols} FROM {tmpname}")
        cursor.execute(f"DROP TABLE {tmpname}")

    def _create_table(self, cursor: Cursor, name: str, force: bool = False) -> None:
        if name == "Configuration":
            self._create_configuration_table(cursor)

    def _get_columns(self, cursor: Cursor, table: str) -> List[Any]:
        return [
            col.name
            for col in cursor.execute(f"PRAGMA table_info('{table}')").fetchall()
        ]

    def _migrate_db(self, cursor: Cursor, version: int) -> None:
        if version < 1:
            self.update_config(SCHEMA_VERSION, 1)

    def _init_db(self, cursor: Cursor) -> None:
        # http://www.stevemcarthur.co.uk/blog/post/some-kind-of-disk-io-error-occurred-sqlite
        cursor.execute("PRAGMA journal_mode = MEMORY")
        self._create_configuration_table(cursor)

    def _create_configuration_table(self, cursor: Cursor) -> None:
        cursor.execute(
            "CREATE TABLE if not exists Configuration ("
            "    name    VARCHAR NOT NULL,"
            "    value   VARCHAR,"
            "    PRIMARY KEY (name)"
            ")"
        )

    def _create_main_conn(self) -> None:
        log.debug(
            f"Create main connexion on {self._db!r} "
            f"(dir_exists={self._db.parent.exists()}, "
            f"file_exists={self._db.exists()})"
        )
        self._conn = connect(
            str(self._db),
            check_same_thread=False,
            factory=AutoRetryConnection,
            isolation_level=None,
        )
        self._conn.row_factory = self._state_factory
        self._connections.append(self._conn)

    def dispose(self) -> None:
        log.debug(f"Disposing SQLite database {self.get_db()!r}")
        for con in self._connections:
            con.close()
        del self._connections
        del self._conn

    def _get_write_connection(self) -> Connection:
        if self.in_tx:
            if self._conn is None:
                self._create_main_conn()
            return self._conn
        return self._get_read_connection()

    def _get_read_connection(self) -> Connection:
        # If in transaction
        if self.in_tx is not None:
            if current_thread().ident != self.in_tx:
                log.trace("In transaction wait for read connection")
                # Wait for the thread in transaction to finished
                with self._tx_lock:
                    pass
            else:
                # Return the write connection
                return self._conn

        if getattr(self._conns, "_conn", None) is None:
            # Dont check same thread for closing purpose
            self._conns._conn = connect(
                str(self._db),
                check_same_thread=False,
                factory=AutoRetryConnection,
                isolation_level=None,
            )
            self._conns._conn.row_factory = self._state_factory
            self._connections.append(self._conns._conn)

        return self._conns._conn

    def _delete_config(self, cursor: Cursor, name: str) -> None:
        cursor.execute("DELETE FROM Configuration WHERE name = ?", (name,))

    def delete_config(self, name: str) -> None:
        with self._lock:
            con = self._get_write_connection()
            c = con.cursor()
            self._delete_config(c, name)

    def update_config(self, name: str, value: Any) -> None:
        # We cannot use this anymore because it will end on a DatabaseError.
        # Will re-activate with NXDRIVE-1205
        # if self.get_config(name) == value:
        #     return

        with self._lock:
            con = self._get_write_connection()
            c = con.cursor()
            c.execute(
                "UPDATE OR IGNORE Configuration"
                "             SET value = ?"
                "           WHERE name = ?",
                (value, name),
            )
            c.execute(
                "INSERT OR IGNORE INTO Configuration (value, name) VALUES (?, ?)",
                (value, name),
            )

    def get_config(self, name: str, default: Any = None) -> Any:
        c = self._get_read_connection().cursor()
        obj = c.execute(
            "SELECT value FROM Configuration WHERE name = ?", (name,)
        ).fetchone()
        if not obj or not obj.value:
            return default
        return obj.value


class ManagerDAO(ConfigurationDAO):
    def get_schema_version(self) -> int:
        return 2

    def _init_db(self, cursor: Cursor) -> None:
        super()._init_db(cursor)
        cursor.execute(
            "CREATE TABLE if not exists Engines ("
            "    uid          VARCHAR,"
            "    engine       VARCHAR NOT NULL,"
            "    name         VARCHAR,"
            "    local_folder VARCHAR NOT NULL UNIQUE,"
            "    PRIMARY KEY (uid)"
            ")"
        )
        cursor.execute(
            "CREATE TABLE if not exists Notifications ("
            "    uid         VARCHAR UNIQUE,"
            "    engine      VARCHAR,"
            "    level       VARCHAR,"
            "    title       VARCHAR,"
            "    description VARCHAR,"
            "    action      VARCHAR,"
            "    flags       INT,"
            "    PRIMARY KEY (uid)"
            ")"
        )
        cursor.execute(
            "CREATE TABLE if not exists AutoLock ("
            "    path      VARCHAR,"
            "    remote_id VARCHAR,"
            "    process   INT,"
            "    PRIMARY KEY(path)"
            ")"
        )

    def insert_notification(self, notification: Notification) -> None:
        with self._lock:
            con = self._get_write_connection()
            c = con.cursor()
            c.execute(
                "INSERT INTO Notifications "
                "(uid, engine, level, title, description, action, flags) "
                "VALUES (?, ?, ?, ?, ?, ?, ?)",
                (
                    notification.uid,
                    notification.engine_uid,
                    notification.level,
                    notification.title,
                    notification.description,
                    notification.action,
                    notification.flags,
                ),
            )

    def unlock_path(self, path: Path) -> None:
        with self._lock:
            con = self._get_write_connection()
            c = con.cursor()
            c.execute("DELETE FROM AutoLock WHERE path = ?", (path,))

    def get_locks(self) -> List[Row]:
        con = self._get_read_connection()
        c = con.cursor()
        return c.execute("SELECT * FROM AutoLock").fetchall()

    def get_locked_paths(self) -> List[Path]:
        paths = []
        for lock in self.get_locks():
            path = str_to_path(lock["path"])
            if path:
                paths.append(path)
        return paths

    def lock_path(self, path: Path, process: int, doc_id: str) -> None:
        with self._lock:
            con = self._get_write_connection()
            c = con.cursor()
            try:
                c.execute(
                    "INSERT INTO AutoLock (path, process, remote_id) "
                    "VALUES (?, ?, ?)",
                    (path, process, doc_id),
                )
            except IntegrityError:
                # Already there just update the process
                c.execute(
                    "UPDATE AutoLock"
                    "   SET process = ?,"
                    "       remote_id = ?"
                    " WHERE path = ?",
                    (process, doc_id, path),
                )

    def update_notification(self, notification: Notification) -> None:
        with self._lock:
            con = self._get_write_connection()
            c = con.cursor()
            c.execute(
                "UPDATE Notifications"
                "   SET level = ?,"
                "       title = ?,"
                "       description = ?"
                " WHERE uid = ?",
                (
                    notification.level,
                    notification.title,
                    notification.description,
                    notification.uid,
                ),
            )

    def get_notifications(self, discarded: bool = True) -> List[Row]:
        # Flags used:
        #    1 = Notification.FLAG_DISCARD
        c = self._get_read_connection().cursor()
        req = "SELECT * FROM Notifications WHERE (flags & 1) = 0"
        if discarded:
            req = "SELECT * FROM Notifications"

        return c.execute(req).fetchall()

    def discard_notification(self, uid: str) -> None:
        # Flags used:
        #    1 = Notification.FLAG_DISCARD
        #    4 = Notification.FLAG_DISCARDABLE
        with self._lock:
            con = self._get_write_connection()
            c = con.cursor()
            c.execute(
                "UPDATE Notifications"
                "   SET flags = (flags | 1)"
                " WHERE uid = ?"
                "   AND (flags & 4) = 4",
                (uid,),
            )

    def remove_notification(self, uid: str) -> None:
        with self._lock:
            con = self._get_write_connection()
            c = con.cursor()
            c.execute("DELETE FROM Notifications WHERE uid = ?", (uid,))

    def _migrate_db(self, cursor: Cursor, version: int) -> None:
        if version < 2:
            cursor.execute(
                "CREATE TABLE if not exists Notifications ("
                "    uid         VARCHAR,"
                "    engine      VARCHAR,"
                "    level       VARCHAR,"
                "    title       VARCHAR,"
                "    description VARCHAR,"
                "    action      VARCHAR,"
                "    flags       INT,"
                "    PRIMARY KEY (uid)"
                ")"
            )
            self.update_config(SCHEMA_VERSION, 2)
        if version < 3:
            cursor.execute(
                "CREATE TABLE if not exists AutoLock ("
                "    path      VARCHAR,"
                "    remote_id VARCHAR,"
                "    process   INT,"
                "    PRIMARY KEY (path)"
                ")"
            )
            self.update_config(SCHEMA_VERSION, 3)

    def get_engines(self) -> List[EngineDef]:
        c = self._get_read_connection().cursor()
        return c.execute("SELECT * FROM Engines").fetchall()

    def update_engine_path(self, engine: str, path: Path) -> None:
        with self._lock:
            con = self._get_write_connection()
            c = con.cursor()
            c.execute(
                "UPDATE Engines SET local_folder = ? WHERE uid = ?", (path, engine)
            )

    def add_engine(self, engine: str, path: Path, key: str, name: str) -> EngineDef:
        with self._lock:
            con = self._get_write_connection()
            c = con.cursor()
            c.execute(
                "INSERT INTO Engines (local_folder, engine, uid, name) "
                "VALUES (?, ?, ?, ?)",
                (path, engine, key, name),
            )
            return c.execute("SELECT * FROM Engines WHERE uid = ?", (key,)).fetchone()

    def delete_engine(self, uid: str) -> None:
        with self._lock:
            con = self._get_write_connection()
            c = con.cursor()
            c.execute("DELETE FROM Engines WHERE uid = ?", (uid,))


class EngineDAO(ConfigurationDAO):

    _queue_manager: Optional["QueueManager"] = None

    newConflict = pyqtSignal(object)

    def __init__(self, db: Path, state_factory: Type[DocPair] = None) -> None:
        if state_factory:
            self._state_factory = state_factory

        super().__init__(db)

        self._items_count = 0
        self._items_count = self.get_syncing_count()
        self._filters = self.get_filters()
        self.reinit_processors()

    def get_schema_version(self) -> int:
        return 4

    def _migrate_state(self, cursor: Cursor) -> None:
        try:
            self._migrate_table(cursor, "States")
        except IntegrityError:
            # If we cannot smoothly migrate harder migration
            cursor.execute("DROP TABLE if exists StatesMigration")
            self._reinit_states(cursor)

    def _migrate_db(self, cursor: Cursor, version: int) -> None:
        if version < 1:
            self._migrate_state(cursor)
            cursor.execute(
                "UPDATE States"
                "   SET last_transfer = 'upload'"
                " WHERE last_local_updated < last_remote_updated"
                "   AND folderish = 0"
            )
            cursor.execute(
                "UPDATE States"
                "   SET last_transfer = 'download'"
                " WHERE last_local_updated > last_remote_updated"
                "   AND folderish = 0"
            )
            self.update_config(SCHEMA_VERSION, 1)
        if version < 2:
            cursor.execute(
                "CREATE TABLE if not exists ToRemoteScan ("
                "    path STRING NOT NULL,"
                "    PRIMARY KEY (path)"
                ")"
            )
            self.update_config(SCHEMA_VERSION, 2)
        if version < 3:
            self._migrate_state(cursor)
            self.update_config(SCHEMA_VERSION, 3)
        if version < 4:
            self._migrate_state(cursor)
            cursor.execute("UPDATE States SET creation_date = last_remote_updated")
            self.update_config(SCHEMA_VERSION, 4)

    def _create_table(self, cursor: Cursor, name: str, force: bool = False) -> None:
        if name == "States":
            self._create_state_table(cursor, force)
        else:
            super()._create_table(cursor, name, force)

    @staticmethod
    def _create_state_table(cursor: Cursor, force: bool = False) -> None:
        statement = "" if force else "if not exists"
        # Cannot force UNIQUE for a local_path as a duplicate can have
        # virtually the same path until they are resolved by Processor
        # Should improve that
        cursor.execute(
            f"CREATE TABLE {statement} States ("
            "    id                      INTEGER    NOT NULL,"
            "    last_local_updated      TIMESTAMP,"
            "    last_remote_updated     TIMESTAMP,"
            "    local_digest            VARCHAR,"
            "    remote_digest           VARCHAR,"
            "    local_path              VARCHAR,"
            "    remote_ref              VARCHAR,"
            "    local_parent_path       VARCHAR,"
            "    remote_parent_ref       VARCHAR,"
            "    remote_parent_path      VARCHAR,"
            "    local_name              VARCHAR,"
            "    remote_name             VARCHAR,"
            "    size                    INTEGER    DEFAULT (0),"
            "    folderish               INTEGER,"
            "    local_state             VARCHAR    DEFAULT('unknown'),"
            "    remote_state            VARCHAR    DEFAULT('unknown'),"
            "    pair_state              VARCHAR    DEFAULT('unknown'),"
            "    remote_can_rename       INTEGER,"
            "    remote_can_delete       INTEGER,"
            "    remote_can_update       INTEGER,"
            "    remote_can_create_child INTEGER,"
            "    last_remote_modifier    VARCHAR,"
            "    last_sync_date          TIMESTAMP,"
            "    error_count             INTEGER    DEFAULT (0),"
            "    last_sync_error_date    TIMESTAMP,"
            "    last_error              VARCHAR,"
            "    last_error_details      TEXT,"
            "    version                 INTEGER    DEFAULT (0),"
            "    processor               INTEGER    DEFAULT (0),"
            "    last_transfer           VARCHAR,"
            "    creation_date           TIMESTAMP,"
            "    PRIMARY KEY (id),"
            "    UNIQUE(remote_ref, remote_parent_ref),"
            "    UNIQUE(remote_ref, local_path))"
        )

    def _init_db(self, cursor: Cursor) -> None:
        super()._init_db(cursor)
        for table in {"Filters", "RemoteScan", "ToRemoteScan"}:
            cursor.execute(
                f"CREATE TABLE if not exists {table} ("
                "   path STRING NOT NULL,"
                "   PRIMARY KEY (path)"
                ")"
            )
        self._create_state_table(cursor)

    def acquire_state(self, thread_id: Optional[int], row_id: int) -> Optional[DocPair]:
        if thread_id is not None and self.acquire_processor(thread_id, row_id):
            # Avoid any lock for this call by using the write connection
            try:
                return self.get_state_from_id(row_id, from_write=True)
            except:
                self.release_processor(thread_id)
                raise
        raise OperationalError("Cannot acquire")

    def release_state(self, thread_id: Optional[int]) -> None:
        if thread_id is not None:
            self.release_processor(thread_id)

    def release_processor(self, processor_id: int) -> bool:
        with self._lock:
            con = self._get_write_connection()
            c = con.cursor()
            # TO_REVIEW Might go back to primary key id
            c.execute(
                "UPDATE States  SET processor = 0 WHERE processor = ?", (processor_id,)
            )
        return c.rowcount > 0

    def acquire_processor(self, thread_id: int, row_id: int) -> bool:
        with self._lock:
            con = self._get_write_connection()
            c = con.cursor()
            c.execute(
                "UPDATE States"
                "   SET processor = ?"
                " WHERE id = ?"
                "   AND processor IN (0, ?)",
                (thread_id, row_id, thread_id),
            )
        return c.rowcount == 1

    def _reinit_states(self, cursor: Cursor) -> None:
        cursor.execute("DROP TABLE States")
        self._create_state_table(cursor, force=True)
        for config in (
            "remote_last_sync_date",
            "remote_last_event_log_id",
            "remote_last_event_last_root_definitions",
            "remote_last_full_scan",
            "last_sync_date",
        ):
            self._delete_config(cursor, config)

    def reinit_states(self) -> None:
        with self._lock:
            con = self._get_write_connection()
            c = con.cursor()
            self._reinit_states(c)
            con.execute("VACUUM")

    def reinit_processors(self) -> None:
        with self._lock:
            con = self._get_write_connection()
            c = con.cursor()
            c.execute("UPDATE States SET processor = 0")
            c.execute(
                "UPDATE States"
                "   SET error_count = 0,"
                "       last_sync_error_date = NULL,"
                "       last_error = NULL"
                " WHERE pair_state = 'synchronized'"
            )
            con.execute("VACUUM")

    def delete_remote_state(self, doc_pair: DocPair) -> None:
        with self._lock:
            con = self._get_write_connection()
            c = con.cursor()
            update = (
                "UPDATE States"
                "   SET remote_state = 'deleted',"
                "       pair_state = ?"
            )
            c.execute(f"{update} WHERE id = ?", ("remotely_deleted", doc_pair.id))
            if doc_pair.folderish:
                c.execute(
                    update + " " + self._get_recursive_remote_condition(doc_pair),
                    ("parent_remotely_deleted",),
                )
            # Only queue parent
            self._queue_pair_state(doc_pair.id, doc_pair.folderish, "remotely_deleted")

    def delete_local_state(self, doc_pair: DocPair) -> None:
        try:
            with self._lock:
                con = self._get_write_connection()
                c = con.cursor()
                update = (
                    "UPDATE States"
                    "   SET local_state = 'deleted',"
                    "       pair_state = ?"
                )
                c.execute(f"{update} WHERE id = ?", ("locally_deleted", doc_pair.id))
                if doc_pair.folderish:
                    c.execute(
                        update + " " + self._get_recursive_condition(doc_pair),
                        ("locally_deleted",),
                    )
        finally:
            if self._queue_manager:
                self._queue_manager.interrupt_processors_on(
                    doc_pair.local_path, exact_match=False
                )

            # Only queue parent
            self._queue_pair_state(
                int(doc_pair.id), bool(doc_pair.folderish), "locally_deleted"
            )

    def insert_local_state(self, info: FileInfo, parent_path: Optional[Path]) -> int:
        pair_state = PAIR_STATES[("created", "unknown")]
        digest = info.get_digest()
        with self._lock:
            con = self._get_write_connection()
            c = con.cursor()
            c.execute(
                "INSERT INTO States "
                "(last_local_updated, local_digest, local_path, "
                "local_parent_path, local_name, folderish, size, "
                "local_state, remote_state, pair_state) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, 'created', 'unknown', ?)",
                (
                    info.last_modification_time,
                    digest,
                    info.path,
                    parent_path,
                    info.path.name,
                    info.folderish,
                    info.size,
                    pair_state,
                ),
            )
            row_id = c.lastrowid
            parent = c.execute(
                "SELECT * FROM States WHERE local_path = ?", (parent_path,)
            ).fetchone()
            # Don't queue if parent is not yet created
            if (parent is None and parent_path is None) or (
                parent and parent.pair_state != "locally_created"
            ):
                self._queue_pair_state(row_id, info.folderish, pair_state)
            self._items_count += 1
        return row_id

    def get_last_files(
        self, number: int, direction: str = "", duration: int = None
    ) -> DocPairs:
        """
        Return the last files transferred.

        The number is the limit number of files returned.
        The direction is used to filter the results depending on
        the nature of the transfer (upload or a download).
        If the duration is not None, then the results only include
        the files transferred between now and now - duration.
        """
        c = self._get_read_connection().cursor()
        conditions = {
            "remote": "AND last_transfer = 'upload'",
            "local": "AND last_transfer = 'download'",
        }
        dir_condition = conditions.get(direction, "")
        time_condition = (
            f"AND datetime(last_sync_date, '+{duration} minutes') > datetime('now')"
            if duration
            else ""
        )
        return c.execute(
            "SELECT *"
            "  FROM States"
            " WHERE pair_state = 'synchronized'"
            f"  AND folderish = 0 {dir_condition} {time_condition}"
            " ORDER BY last_sync_date DESC "
            f"LIMIT {number}"
        ).fetchall()

    def get_last_files_count(self, direction: str = "", duration: int = None) -> int:
        """
        Return the count of the last files transferred.

        The direction is used to filter the results depending on
        the nature of the transfer (upload or a download).
        If the duration is not None, then the results only include
        the files transferred between now and now - duration.
        """
        conditions = {
            "remote": "AND last_transfer = 'upload'",
            "local": "AND last_transfer = 'download'",
        }
        dir_condition = conditions.get(direction, "")
        time_condition = (
            f"AND datetime(last_sync_date, '+{duration} minutes') > datetime('now')"
            if duration
            else ""
        )
        return self.get_count(
            f"pair_state = 'synchronized' AND folderish = 0 {dir_condition} {time_condition}"
        )

    def _get_to_sync_condition(self) -> str:
        return "pair_state != 'synchronized' AND pair_state != 'unsynchronized'"

    def register_queue_manager(self, manager: "QueueManager") -> None:
        # Prevent any update while init queue
        with self._lock:
            self._queue_manager = manager
            con = self._get_write_connection()
            c = con.cursor()
            # Order by path to be sure to process parents before childs
            pairs: List[DocPair] = c.execute(
                "SELECT *"
                "  FROM States "
                f"WHERE {self._get_to_sync_condition()}"
                " ORDER BY local_path ASC"
            ).fetchall()
            folders = dict()
            for pair in pairs:
                # Add all the folders
                if pair.folderish:
                    folders[pair.local_path] = True
                if self._queue_manager and pair.local_parent_path not in folders:
                    self._queue_manager.push_ref(
                        pair.id, pair.folderish, pair.pair_state
                    )
        # Dont block everything if queue manager fail
        # TODO As the error should be fatal not sure we need this

    def _queue_pair_state(
        self, row_id: int, folderish: bool, pair_state: str, pair: DocPair = None
    ) -> None:
        if self._queue_manager and pair_state not in {"synchronized", "unsynchronized"}:
            if pair_state == "conflicted":
                log.trace(f"Emit newConflict with: {row_id}, pair={pair!r}")
                self.newConflict.emit(row_id)
            else:
                log.trace(f"Push to queue: {pair_state}, pair={pair!r}")
                self._queue_manager.push_ref(row_id, folderish, pair_state)
        else:
            log.trace(f"Will not push pair: {pair_state}, pair={pair!r}")

    def _get_pair_state(self, row: DocPair) -> str:
        state = PAIR_STATES.get((row.local_state, row.remote_state))
        if state is None:
            raise UnknownPairState(row.local_state, row.remote_state)
        return state

    def update_last_transfer(self, row_id: int, transfer: str) -> None:
        with self._lock:
            con = self._get_write_connection()
            c = con.cursor()
            c.execute(
                "UPDATE States SET last_transfer = ? WHERE id = ?", (transfer, row_id)
            )

    def get_dedupe_pair(self, name: str, parent: str, row_id: int) -> Optional[DocPair]:
        c = self._get_read_connection().cursor()
        return c.execute(
            "SELECT *"
            "  FROM States"
            " WHERE id != ?"
            "   AND local_name = ?"
            "   AND remote_parent_ref = ?",
            (row_id, name, parent),
        ).fetchone()

    def update_local_state(
        self, row: DocPair, info: FileInfo, versioned: bool = True, queue: bool = True
    ) -> None:
        row.pair_state = self._get_pair_state(row)
        log.trace(f"Updating local state for row={row!r} with info={info!r}")

        version = ""
        if versioned:
            version = ", version = version + 1"
            log.trace(f"Increasing version to {row.version + 1} for pair {row!r}")

        parent_path = info.path.parent
        with self._lock:
            con = self._get_write_connection()
            c = con.cursor()
            c.execute(
                "UPDATE States"
                "   SET last_local_updated = ?,"
                "       local_digest = ?,"
                "       local_path = ?,"
                "       local_parent_path = ?, "
                "       local_name = ?, "
                "       local_state = ?,"
                "       size = ?,"
                "       remote_state = ?, "
                f"       pair_state = ? {version}"
                " WHERE id = ?",
                (
                    info.last_modification_time,
                    row.local_digest,
                    info.path,
                    parent_path,
                    info.path.name,
                    row.local_state,
                    info.size,
                    row.remote_state,
                    row.pair_state,
                    row.id,
                ),
            )
            if queue:
                parent = c.execute(
                    "SELECT * FROM States WHERE local_path = ?", (parent_path,)
                ).fetchone()
                # Don't queue if parent is not yet created
                if (not parent and not parent_path) or (
                    parent and parent.local_state != "created"
                ):
                    self._queue_pair_state(
                        row.id, info.folderish, row.pair_state, pair=row
                    )

    def update_local_modification_time(self, row: DocPair, info: FileInfo) -> None:
        with self._lock:
            con = self._get_write_connection()
            c = con.cursor()
            c.execute(
                "UPDATE States SET last_local_updated = ? WHERE id = ?",
                (info.last_modification_time, row.id),
            )

    def get_valid_duplicate_file(self, digest: str) -> Optional[DocPair]:
        c = self._get_read_connection().cursor()
        return c.execute(
            "SELECT *"
            "  FROM States"
            " WHERE remote_digest = ?"
            "   AND pair_state = 'synchronized'",
            (digest,),
        ).fetchone()

    def get_remote_descendants(self, path: str) -> DocPairs:
        c = self._get_read_connection().cursor()
        return c.execute(
            "SELECT * FROM States WHERE remote_parent_path LIKE ?", (f"{path}%",)
        ).fetchall()

    def get_remote_descendants_from_ref(self, ref: str) -> DocPairs:
        c = self._get_read_connection().cursor()
        return c.execute(
            "SELECT * FROM States WHERE remote_parent_path LIKE ?", (f"%{ref}%",)
        ).fetchall()

    def get_remote_children(self, ref: str) -> DocPairs:
        c = self._get_read_connection().cursor()
        return c.execute(
            "SELECT * FROM States WHERE remote_parent_ref = ?", (ref,)
        ).fetchall()

    def get_new_remote_children(self, ref: str) -> DocPairs:
        c = self._get_read_connection().cursor()
        return c.execute(
            "SELECT *"
            "  FROM States"
            " WHERE remote_parent_ref = ?"
            "   AND remote_state = 'created'"
            "   AND local_state = 'unknown'",
            (ref,),
        ).fetchall()

    def get_unsynchronized_count(self) -> int:
        return self.get_count("pair_state = 'unsynchronized'")

    def get_conflict_count(self) -> int:
        return self.get_count("pair_state = 'conflicted'")

    def get_error_count(self, threshold: int = 3) -> int:
        return self.get_count(f"error_count > {threshold}")

    def get_syncing_count(self, threshold: int = 3) -> int:
        count = self.get_count(
            "     pair_state != 'synchronized' "
            " AND pair_state != 'conflicted' "
            " AND pair_state != 'unsynchronized' "
            f"AND error_count < {threshold}"
        )
        if self._items_count != count:
            log.trace(
                f"Cache Syncing count incorrect should be {count} was {self._items_count}"
            )
            self._items_count = count
        return count

    def get_sync_count(self, filetype: str = None) -> int:
        conditions = {"file": "AND folderish = 0", "folder": "AND folderish = 1"}
        condition = conditions.get(filetype or "", "")
        return self.get_count(f"pair_state = 'synchronized' {condition}")

    def get_count(self, condition: str = None) -> int:
        query = "SELECT COUNT(*) as count FROM States"
        if condition:
            query = f"{query} WHERE {condition}"
        c = self._get_read_connection().cursor()
        return c.execute(query).fetchone().count

    def get_global_size(self) -> int:
        c = self._get_read_connection().cursor()
        total = (
            c.execute(
                "SELECT SUM(size) as sum"
                "  FROM States"
                " WHERE folderish = 0"
                "   AND pair_state = 'synchronized'"
            )
            .fetchone()
            .sum
        )
        # `total` may be `None` if there is not synced files,
        # so we ensure to have an int at the end
        return total or 0

    def get_unsynchronizeds(self) -> DocPairs:
        c = self._get_read_connection().cursor()
        return c.execute(
            "SELECT * FROM States WHERE pair_state = 'unsynchronized'"
        ).fetchall()

    def get_conflicts(self) -> DocPairs:
        c = self._get_read_connection().cursor()
        return c.execute(
            "SELECT * FROM States WHERE pair_state = 'conflicted'"
        ).fetchall()

    def get_errors(self, limit: int = 3) -> DocPairs:
        c = self._get_read_connection().cursor()
        return c.execute(
            "SELECT * FROM States WHERE error_count > ?", (limit,)
        ).fetchall()

    def get_local_children(self, path: Path) -> DocPairs:
        c = self._get_read_connection().cursor()
        return c.execute(
            "SELECT * FROM States WHERE local_parent_path = ?", (path,)
        ).fetchall()

    def get_states_from_partial_local(
        self, path: Path, strict: bool = True
    ) -> DocPairs:
        c = self._get_read_connection().cursor()

        path = "/%" if path == ROOT else f"/{path}{'/' if strict else ''}%"
        return c.execute(
            "SELECT * FROM States WHERE local_path LIKE ?", (path,)
        ).fetchall()

    def get_first_state_from_partial_remote(self, ref: str) -> Optional[DocPair]:
        c = self._get_read_connection().cursor()
        return c.execute(
            "SELECT *"
            "  FROM States"
            " WHERE remote_ref LIKE ? "
            " ORDER BY last_remote_updated ASC"
            " LIMIT 1",
            (f"%{ref}",),
        ).fetchone()

    def get_normal_state_from_remote(self, ref: str) -> Optional[DocPair]:
        # TODO Select the only states that is not a collection
        states = self.get_states_from_remote(ref)
        return states[0] if states else None

    def get_state_from_remote_with_path(self, ref: str, path: str) -> Optional[DocPair]:
        # remote_path root is empty, should refactor this
        path = "" if path == "/" else path
        c = self._get_read_connection().cursor()
        return c.execute(
            "SELECT *"
            "  FROM States"
            " WHERE remote_ref = ?"
            "   AND remote_parent_path = ?",
            (ref, path),
        ).fetchone()

    def get_states_from_remote(self, ref: str) -> DocPairs:
        c = self._get_read_connection().cursor()
        return c.execute("SELECT * FROM States WHERE remote_ref = ?", (ref,)).fetchall()

    def get_state_from_id(
        self, row_id: int, from_write: bool = False
    ) -> Optional[DocPair]:
        if from_write:
            self._lock.acquire()
            c = self._get_write_connection().cursor()
        else:
            c = self._get_read_connection().cursor()

        try:
            state = c.execute("SELECT * FROM States WHERE id = ?", (row_id,)).fetchone()
        finally:
            if from_write:
                self._lock.release()
        return state

    def _get_recursive_condition(self, doc_pair: DocPair) -> str:
        path = "/" + str(doc_pair.local_path)
        res = (
            f" WHERE (local_parent_path LIKE '{path}/%'"
            f"        OR local_parent_path = '{path}')"
        )
        if doc_pair.remote_ref:
            path = self._escape(doc_pair.remote_parent_path + "/" + doc_pair.remote_ref)
            res += f" AND remote_parent_path LIKE '{path}%'"
        return res

    def _get_recursive_remote_condition(self, doc_pair: DocPair) -> str:
        path = self._escape(doc_pair.remote_parent_path + "/" + doc_pair.remote_name)
        return (
            f" WHERE remote_parent_path LIKE '{path}/%'"
            f"    OR remote_parent_path = '{path}'"
        )

    def update_remote_parent_path(self, doc_pair: DocPair, new_path: str) -> None:
        with self._lock:
            con = self._get_write_connection()
            c = con.cursor()
            if doc_pair.folderish:
                count = str(
                    len(doc_pair.remote_parent_path + "/" + doc_pair.remote_ref) + 1
                )
                path = new_path + "/" + doc_pair.remote_ref
                query = (
                    "UPDATE States"
                    f"  SET remote_parent_path = '{path}'"
                    f"      || substr(remote_parent_path, {count})"
                    + self._get_recursive_remote_condition(doc_pair)
                )

                log.trace(f"Update remote_parent_path {query!r}")
                c.execute(query)
            c.execute(
                "UPDATE States SET remote_parent_path = ? WHERE id = ?",
                (new_path, doc_pair.id),
            )

    def update_local_parent_path(
        self, doc_pair: DocPair, new_name: str, new_path: Path
    ) -> None:
        with self._lock:
            con = self._get_write_connection()
            c = con.cursor()
            if doc_pair.folderish:
                path = "/" + str(new_path / new_name)
                count = str(len(str(doc_pair.local_path)) + 2)
                query = (
                    "UPDATE States"
                    f"  SET local_parent_path = '{path}'"
                    f"      || substr(local_parent_path, {count}),"
                    f"         local_path = '{path}'"
                    "       || substr(local_path, "
                    + count
                    + ") "
                    + self._get_recursive_condition(doc_pair)
                )
                c.execute(query)
            # Dont need to update the path as it is refresh later
            c.execute(
                "UPDATE States SET local_parent_path = ? WHERE id = ?",
                (new_path, doc_pair.id),
            )

    def mark_descendants_remotely_created(self, doc_pair: DocPair) -> None:
        with self._lock:
            con = self._get_write_connection()
            c = con.cursor()
            update = (
                "UPDATE States"
                "   SET local_digest = NULL,"
                "       last_local_updated = NULL,"
                "       local_name = NULL,"
                "       remote_state = 'created',"
                "       pair_state = 'remotely_created'"
            )
            c.execute(f"{update} WHERE id = {doc_pair.id}")
            if doc_pair.folderish:
                c.execute(f"{update} {self._get_recursive_condition(doc_pair)}")
            self._queue_pair_state(doc_pair.id, doc_pair.folderish, doc_pair.pair_state)

    def remove_state(self, doc_pair: DocPair, remote_recursion: bool = False) -> None:
        with self._lock:
            con = self._get_write_connection()
            c = con.cursor()
            c.execute("DELETE FROM States WHERE id = ?", (doc_pair.id,))
            if doc_pair.folderish:
                if remote_recursion:
                    condition = self._get_recursive_remote_condition(doc_pair)
                else:
                    condition = self._get_recursive_condition(doc_pair)
                c.execute("DELETE FROM States " + condition)

    def get_state_from_local(self, path: Path) -> Optional[DocPair]:
        c = self._get_read_connection().cursor()
        return c.execute(
            "SELECT * FROM States WHERE local_path = ?", (path,)
        ).fetchone()

    def insert_remote_state(
        self,
        info: RemoteFileInfo,
        remote_parent_path: str,
        local_path: Path,
        local_parent_path: Path,
    ) -> int:
        pair_state = PAIR_STATES[("unknown", "created")]
        with self._lock:
            con = self._get_write_connection()
            c = con.cursor()
            c.execute(
                "INSERT INTO States "
                "(remote_ref, remote_parent_ref, remote_parent_path, "
                "remote_name, last_remote_updated, remote_can_rename, "
                "remote_can_delete, remote_can_update, "
                "remote_can_create_child, last_remote_modifier, "
                "remote_digest, folderish, last_remote_modifier, "
                "local_path, local_parent_path, remote_state, "
                "local_state, pair_state, local_name, creation_date) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, "
                "'created', 'unknown', ?, ?, ?)",
                (
                    info.uid,
                    info.parent_uid,
                    remote_parent_path,
                    info.name,
                    info.last_modification_time,
                    info.can_rename,
                    info.can_delete,
                    info.can_update,
                    info.can_create_child,
                    info.last_contributor,
                    info.digest,
                    info.folderish,
                    info.last_contributor,
                    local_path,
                    local_parent_path,
                    pair_state,
                    info.name,
                    info.creation_time,
                ),
            )
            row_id = c.lastrowid

            # Check if parent is not in creation
            parent = c.execute(
                "SELECT * FROM States WHERE remote_ref = ?", (info.parent_uid,)
            ).fetchone()
            if (parent is None and local_parent_path == ROOT) or (
                parent and parent.pair_state != "remotely_created"
            ):
                self._queue_pair_state(row_id, info.folderish, pair_state)
            self._items_count += 1
        return row_id

    def queue_children(self, row: DocPair) -> None:
        with self._lock:
            con = self._get_write_connection()
            c = con.cursor()
            children: List[DocPair] = c.execute(
                "SELECT *"
                "  FROM States"
                " WHERE remote_parent_ref = ?"
                "    OR local_parent_path = ?"
                "   AND " + self._get_to_sync_condition(),
                (row.remote_ref, row.local_path),
            ).fetchall()
            log.debug(f"Queuing {len(children)} children of {row}")
            for child in children:
                self._queue_pair_state(child.id, child.folderish, child.pair_state)

    def increase_error(
        self, row: DocPair, error: str, details: str = None, incr: int = 1
    ) -> None:
        error_date = datetime.utcnow()
        with self._lock:
            con = self._get_write_connection()
            c = con.cursor()
            c.execute(
                "UPDATE States"
                "   SET last_error = ?,"
                "       last_sync_error_date = ?,"
                "       error_count = error_count + ?,"
                "       last_error_details = ?"
                " WHERE id = ?",
                (error, error_date, incr, details, row.id),
            )
        row.last_error = error
        row.error_count += incr

    def reset_error(self, row: DocPair, last_error: str = None) -> None:
        with self._lock:
            con = self._get_write_connection()
            c = con.cursor()
            c.execute(
                "UPDATE States"
                "   SET last_error = ?,"
                "       last_error_details = NULL,"
                "       last_sync_error_date = NULL,"
                "       error_count = 0"
                " WHERE id = ?",
                (last_error, row.id),
            )
            self._queue_pair_state(row.id, row.folderish, row.pair_state)
            self._items_count += 1
        row.last_error = None
        row.error_count = 0

    def _force_sync(self, row: DocPair, local: str, remote: str, pair: str) -> bool:
        with self._lock:
            con = self._get_write_connection()
            c = con.cursor()
            c.execute(
                "UPDATE States"
                "   SET local_state = ?,"
                "       remote_state = ?,"
                "       pair_state = ?,"
                "       last_error = NULL,"
                "       last_sync_error_date = NULL,"
                "       error_count = 0"
                " WHERE id = ?"
                "   AND version = ?",
                (local, remote, pair, row.id, row.version),
            )
            self._queue_pair_state(row.id, row.folderish, pair)
        if c.rowcount == 1:
            self._items_count += 1
            return True
        return False

    def force_remote(self, row: DocPair) -> bool:
        return self._force_sync(row, "synchronized", "modified", "remotely_modified")

    def force_local(self, row: DocPair) -> bool:
        return self._force_sync(row, "resolved", "unknown", "locally_resolved")

    def set_conflict_state(self, row: DocPair) -> bool:
        with self._lock:
            con = self._get_write_connection()
            c = con.cursor()
            c.execute(
                "UPDATE States SET pair_state = ? WHERE id = ?", ("conflicted", row.id)
            )
            self.newConflict.emit(row.id)
        if c.rowcount == 1:
            self._items_count -= 1
            return True
        return False

    def unsynchronize_state(
        self, row: DocPair, last_error: str = None, ignore: bool = False
    ) -> None:
        local_state = "local_state = 'unsynchronized'," if ignore else ""
        with self._lock:
            con = self._get_write_connection()
            c = con.cursor()
            c.execute(
                "UPDATE States"
                "   SET pair_state = 'unsynchronized',"
                f"      {local_state}"
                "       last_sync_date = ?,"
                "       processor = 0,"
                "       last_error = ?,"
                "       error_count = 0,"
                "       last_sync_error_date = NULL"
                " WHERE id = ?",
                (datetime.utcnow(), last_error, row.id),
            )

    def unset_unsychronised(self, row: DocPair) -> None:
        """Used to unfilter documents that were flagged read-only in a previous sync.
        All children will be locally rescanned to keep synced with the server."""
        row.local_state = "created"
        row.remote_state = "unknown"
        row.pair_state = self._get_pair_state(row)
        with self._lock:
            con = self._get_write_connection()
            c = con.cursor()
            c.execute(
                "UPDATE States"
                "   SET local_state = ?,"
                "       remote_state = ?,"
                "       pair_state = ?,"
                "       last_sync_date = ?,"
                "       error_count = 0,"
                "       last_sync_error_date = NULL,"
                "       last_error = NULL"
                " WHERE local_path LIKE ?",
                (
                    row.local_state,
                    row.remote_state,
                    row.pair_state,
                    datetime.utcnow(),
                    "/" + str(row.local_path) + "%",
                ),
            )

    def synchronize_state(
        self, row: DocPair, version: int = None, dynamic_states: bool = False
    ) -> bool:
        if version is None:
            version = row.version
        log.trace(
            f"Try to synchronize state for [local_path={row.local_path!r}, "
            f"remote_name={row.remote_name!r}, version={row.version}] "
            f"with version={version} and dynamic_states={dynamic_states!r}"
        )

        # Set default states to synchronized, if wanted
        if not dynamic_states:
            row.local_state = row.remote_state = "synchronized"
        row.pair_state = self._get_pair_state(row)

        with self._lock:
            con = self._get_write_connection()
            c = con.cursor()
            c.execute(
                "UPDATE States"
                "   SET local_state = ?,"
                "       remote_state = ?,"
                "       pair_state = ?,"
                "       local_digest = ?,"
                "       last_sync_date = ?,"
                "       processor = 0,"
                "       last_error = NULL,"
                "       last_error_details = NULL,"
                "       error_count = 0,"
                "       last_sync_error_date = NULL"
                " WHERE id = ?"
                "   AND version = ?",
                (
                    row.local_state,
                    row.remote_state,
                    row.pair_state,
                    row.local_digest,
                    datetime.utcnow(),
                    row.id,
                    version,
                ),
            )
        result = c.rowcount == 1

        # Retry without version for folder
        if not result and row.folderish:
            with self._lock:
                con = self._get_write_connection()
                c = con.cursor()
                c.execute(
                    "UPDATE States"
                    "   SET local_state = ?,"
                    "       remote_state = ?,"
                    "       pair_state = ?,"
                    "       last_sync_date = ?,"
                    "       processor = 0,"
                    "       last_error = NULL,"
                    "       error_count = 0,"
                    "       last_sync_error_date = NULL"
                    " WHERE id = ?"
                    "   AND local_path = ?"
                    "   AND remote_name = ?"
                    "   AND remote_ref = ?"
                    "   AND remote_parent_ref = ?",
                    (
                        row.local_state,
                        row.remote_state,
                        row.pair_state,
                        datetime.utcnow(),
                        row.id,
                        row.local_path,
                        row.remote_name,
                        row.remote_ref,
                        row.remote_parent_ref,
                    ),
                )
            result = c.rowcount == 1

        if not result:
            log.trace(f"Was not able to synchronize state: {row!r}")
            c = self._get_read_connection().cursor()
            row2: DocPair = c.execute(
                "SELECT * FROM States WHERE id = ?", (row.id,)
            ).fetchone()
            if row2 is None:
                log.trace("No more row")
            else:
                log.trace(f"Current row={row2!r} (version={row2.version!r})")
            log.trace(f"Previous row={row!r} (version={row.version!r})")
        elif row.folderish:
            self.queue_children(row)

        return result

    def update_remote_state(
        self,
        row: DocPair,
        info: RemoteFileInfo,
        remote_parent_path: str = None,
        versioned: bool = True,
        queue: bool = True,
        force_update: bool = False,
        no_digest: bool = False,
    ) -> None:
        row.pair_state = self._get_pair_state(row)
        if remote_parent_path is None:
            remote_parent_path = row.remote_parent_path

        # Check if it really needs an update
        if (
            row.remote_ref == info.uid
            and info.parent_uid == row.remote_parent_ref
            and remote_parent_path == row.remote_parent_path
            and info.name == row.remote_name
            and info.can_rename == row.remote_can_rename
            and info.can_delete == row.remote_can_delete
            and info.can_update == row.remote_can_update
            and info.can_create_child == row.remote_can_create_child
        ):
            bname = os.path.basename(row.local_path)
            if bname == info.name or (WINDOWS and bname.strip() == info.name.strip()):
                # It looks similar
                if info.digest in (row.local_digest, row.remote_digest):
                    row.remote_state = "synchronized"
                    row.pair_state = self._get_pair_state(row)
                if info.digest == row.remote_digest and not force_update:
                    log.trace(
                        "Not updating remote state (not dirty) "
                        f"for row={row!r} with info={info!r}"
                    )
                    return

        log.trace(
            f"Updating remote state for row={row!r} with info={info!r} "
            f"(force={force_update!r})"
        )

        if (
            row.pair_state not in {"conflicted", "remotely_created"}
            and row.folderish
            and row.local_name
            and row.local_name != info.name
            and row.local_state != "resolved"
        ):
            # We check the current pair_state to not interfer with conflicted
            # documents (a move on both sides) nor with newly remotely
            # created ones.
            row.remote_state = "modified"
            row.pair_state = self._get_pair_state(row)

        with self._lock:
            con = self._get_write_connection()
            c = con.cursor()
            query = (
                "UPDATE States"
                "   SET remote_ref = ?,"
                "       remote_parent_ref = ?,"
                "       remote_parent_path = ?,"
                "       remote_name = ?,"
                "       last_remote_updated = ?,"
                "       remote_can_rename = ?,"
                "       remote_can_delete = ?,"
                "       remote_can_update = ?,"
                "       remote_can_create_child = ?,"
                "       last_remote_modifier = ?,"
                "       local_state = ?,"
                "       remote_state = ?,"
                "       pair_state = ?"
            )

            if not no_digest and info.digest is not None:
                query += f", remote_digest = '{info.digest}'"

            if versioned:
                query += ", version = version+1"
                log.trace(f"Increasing version to {row.version + 1} for pair {row!r}")

            query += " WHERE id = ?"
            c.execute(
                query,
                (
                    info.uid,
                    info.parent_uid,
                    remote_parent_path,
                    info.name,
                    info.last_modification_time,
                    info.can_rename,
                    info.can_delete,
                    info.can_update,
                    info.can_create_child,
                    info.last_contributor,
                    row.local_state,
                    row.remote_state,
                    row.pair_state,
                    row.id,
                ),
            )
            if queue:
                # Check if parent is not in creation
                parent = c.execute(
                    "SELECT * FROM States WHERE remote_ref = ?", (info.parent_uid,)
                ).fetchone()
                # Parent can be None if the parent is filtered
                if (
                    parent and parent.pair_state != "remotely_created"
                ) or parent is None:
                    self._queue_pair_state(row.id, info.folderish, row.pair_state)

    def _clean_filter_path(self, path: str) -> str:
        if not path.endswith("/"):
            path += "/"
        return path

    def add_path_to_scan(self, path: str) -> None:
        path = self._clean_filter_path(path)
        with self._lock, suppress(IntegrityError):
            con = self._get_write_connection()
            c = con.cursor()
            # Remove any subchilds as it is gonna be scanned anyway
            c.execute("DELETE FROM ToRemoteScan WHERE path LIKE ?", (path + "%",))
            c.execute("INSERT INTO ToRemoteScan (path) VALUES (?)", (path,))

    def delete_path_to_scan(self, path: str) -> None:
        path = self._clean_filter_path(path)
        with self._lock, suppress(IntegrityError):
            con = self._get_write_connection()
            c = con.cursor()
            c.execute("DELETE FROM ToRemoteScan WHERE path = ?", (path,))

    def get_paths_to_scan(self) -> List[str]:
        c = self._get_read_connection().cursor()
        return [
            item.path for item in c.execute("SELECT * FROM ToRemoteScan").fetchall()
        ]

    def add_path_scanned(self, path: str) -> None:
        path = self._clean_filter_path(path)
        with self._lock, suppress(IntegrityError):
            con = self._get_write_connection()
            c = con.cursor()
            c.execute("INSERT INTO RemoteScan (path) VALUES (?)", (path,))

    def clean_scanned(self) -> None:
        with self._lock:
            con = self._get_write_connection()
            c = con.cursor()
            c.execute("DELETE FROM RemoteScan")

    def is_path_scanned(self, path: str) -> bool:
        path = self._clean_filter_path(path)
        c = self._get_read_connection().cursor()
        row = c.execute(
            "SELECT COUNT(path) FROM RemoteScan WHERE path = ? LIMIT 1", (path,)
        ).fetchone()
        return row[0] > 0

    def is_filter(self, path: str) -> bool:
        path = self._clean_filter_path(path)
        return any(path.startswith(_filter) for _filter in self._filters)

    def get_filters(self) -> Filters:
        c = self._get_read_connection().cursor()
        return [entry.path for entry in c.execute("SELECT * FROM Filters").fetchall()]

    def add_filter(self, path: str) -> None:
        if self.is_filter(path):
            return

        path = self._clean_filter_path(path)
        log.trace(f"Add filter on {path!r}")

        with self._lock:
            con = self._get_write_connection()
            c = con.cursor()
            # Delete any subfilters
            c.execute("DELETE FROM Filters WHERE path LIKE ?", (path + "%",))

            # Prevent any rescan
            c.execute("DELETE FROM ToRemoteScan WHERE path LIKE ?", (path + "%",))

            # Add it
            c.execute("INSERT INTO Filters (path) VALUES (?)", (path,))

            # TODO: Add this path as remotely_deleted?

            self._filters = self.get_filters()
            self._items_count = self.get_syncing_count()

    def remove_filter(self, path: str) -> None:
        path = self._clean_filter_path(path)
        log.trace(f"Remove filter on {path!r}")
        with self._lock:
            con = self._get_write_connection()
            c = con.cursor()
            c.execute("DELETE FROM Filters WHERE path LIKE ?", (path + "%",))
            self._filters = self.get_filters()
            self._items_count = self.get_syncing_count()

    @staticmethod
    def _escape(text: str) -> str:
        return text.replace("'", "''")
