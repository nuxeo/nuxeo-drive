# coding: utf-8
"""
Query formatting in this file is based on http://www.sqlstyle.guide/
"""
import os
import sqlite3
from contextlib import suppress
from datetime import datetime
from logging import getLogger
from threading import RLock, current_thread, local
from typing import Any, List, Optional, Tuple

from PyQt5.QtCore import QObject, pyqtSignal

from .utils import fix_db
from ...constants import WINDOWS
from ...objects import DocPair, DocPairs, Filters, NuxeoDocumentInfo

__all__ = ("ConfigurationDAO", "EngineDAO", "ManagerDAO", "StateRow")

log = getLogger(__name__)

SCHEMA_VERSION = "schema_version"

# Summary status from last known pair of states
# (local_state, remote_state)
PAIR_STATES = {
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
    # inconsistent cases
    ("unknown", "deleted"): "unknown_deleted",
    ("deleted", "unknown"): "deleted_unknown",
}


class AutoRetryCursor(sqlite3.Cursor):
    def execute(self, *args: str, **kwargs: Any) -> sqlite3.Cursor:
        count = 1
        while True:
            count += 1
            try:
                return super().execute(*args, **kwargs)
            except sqlite3.OperationalError as exc:
                log.debug(
                    "Retry locked database #%d, args=%r, kwargs=%r", count, args, kwargs
                )
                if count > 5:
                    raise exc


class AutoRetryConnection(sqlite3.Connection):
    def cursor(self, **kwargs: Any) -> sqlite3.Cursor:
        return super().cursor(AutoRetryCursor)


class StateRow(sqlite3.Row):
    def __repr__(self) -> str:
        return (
            "<{name}[{cls.id!r}]"
            " local_path={cls.local_path!r},"
            " remote_ref={cls.remote_ref!r},"
            " local_state={cls.local_state!r},"
            " remote_state={cls.remote_state!r},"
            " pair_state={cls.pair_state!r},"
            " filter_path={cls.path!r}"
            ">"
        ).format(name=type(self).__name__, cls=self)

    def __getattr__(self, name: str) -> Optional[str]:
        with suppress(IndexError):
            return self[name]

    def is_readonly(self) -> bool:
        if self.folderish:
            return self.remote_can_create_child == 0
        return (
            self.remote_can_delete & self.remote_can_rename & self.remote_can_update
        ) == 0

    def update_state(self, local_state: str = None, remote_state: str = None) -> None:
        if local_state is not None:
            self.local_state = local_state
        if remote_state is not None:
            self.remote_state = remote_state


class ConfigurationDAO(QObject):

    _conn = None
    _state_factory = StateRow

    def __init__(self, db: str) -> None:
        super().__init__()
        log.debug("Create DAO on %r", db)
        self._db = db
        exists = os.path.isfile(self._db)

        if exists:
            # Fix potential file corruption
            try:
                fix_db(self._db)
            except sqlite3.DatabaseError:
                # The file is too damaged, just recreate it from scratch.
                # Sync data will not be re-downloaded nor deleted, but a full
                # scan will be done.
                os.rename(
                    self._db, self._db + "_" + str(int(datetime.now().timestamp()))
                )
                exists = False

        self.schema_version = self.get_schema_version()
        self.in_tx = None
        self._tx_lock = RLock()
        self._lock = RLock()
        self._connections = []
        self._conns = local()
        self._create_main_conn()
        c = self._conn.cursor()
        self._init_db(c)
        if exists:
            res = c.execute(
                "SELECT value " "  FROM Configuration " " WHERE name = ?",
                (SCHEMA_VERSION,),
            ).fetchone()
            schema = int(res[0]) if res else 0
            if schema != self.schema_version:
                self._migrate_db(c, schema)
        else:
            c.execute(
                "INSERT INTO Configuration (name, value) " "VALUES (?, ?)",
                (SCHEMA_VERSION, self.schema_version),
            )

    def get_schema_version(self) -> int:
        return 1

    def get_db(self) -> str:
        return self._db

    def _migrate_table(self, cursor: sqlite3.Cursor, name: str) -> None:
        # Add the last_transfer
        tmpname = "{}Migration".format(name)

        # In case of a bad/unfinished migration
        cursor.execute("DROP TABLE IF EXISTS {}".format(tmpname))

        cursor.execute("ALTER TABLE {} RENAME TO {}".format(name, tmpname))
        # Because Windows don't release the table, force the creation
        self._create_table(cursor, name, force=True)
        target_cols = self._get_columns(cursor, name)
        source_cols = self._get_columns(cursor, tmpname)
        cols = ", ".join(set(target_cols).intersection(source_cols))
        cursor.execute(
            "INSERT INTO {} ({}) "
            "SELECT {}"
            "  FROM {}".format(name, cols, cols, tmpname)
        )
        cursor.execute("DROP TABLE {}".format(tmpname))

    def _create_table(
        self, cursor: sqlite3.Cursor, name: str, force: bool = False
    ) -> None:
        if name == "Configuration":
            self._create_configuration_table(cursor)

    def _get_columns(self, cursor: sqlite3.Cursor, table: str) -> List[Any]:
        return [
            col.name
            for col in cursor.execute(
                "PRAGMA table_info('{}')".format(table)
            ).fetchall()
        ]

    def _migrate_db(self, cursor: sqlite3.Cursor, version: int) -> None:
        if version < 1:
            self.update_config(SCHEMA_VERSION, 1)

    def _init_db(self, cursor: sqlite3.Cursor) -> None:
        # http://www.stevemcarthur.co.uk/blog/post/some-kind-of-disk-io-error-occurred-sqlite
        cursor.execute("PRAGMA journal_mode = MEMORY")
        self._create_configuration_table(cursor)

    def _create_configuration_table(self, cursor: sqlite3.Cursor) -> None:
        cursor.execute(
            "CREATE TABLE if not exists Configuration ("
            "    name    VARCHAR NOT NULL,"
            "    value   VARCHAR,"
            "    PRIMARY KEY (name)"
            ")"
        )

    def _create_main_conn(self) -> None:
        log.debug(
            "Create main connexion on %r (dir_exists=%r, file_exists=%r)",
            self._db,
            os.path.exists(os.path.dirname(self._db)),
            os.path.exists(self._db),
        )
        self._conn = sqlite3.connect(
            self._db,
            check_same_thread=False,
            factory=AutoRetryConnection,
            isolation_level=None,
        )
        self._conn.row_factory = self._state_factory
        self._connections.append(self._conn)

    def dispose(self) -> None:
        log.debug("Disposing SQLite database %r", self.get_db())
        for con in self._connections:
            con.close()
        del self._connections
        del self._conn

    def _get_write_connection(self) -> sqlite3.Connection:
        if self.in_tx:
            if self._conn is None:
                self._create_main_conn()
            return self._conn
        return self._get_read_connection()

    def _get_read_connection(self) -> sqlite3.Connection:
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
            self._conns._conn = sqlite3.connect(
                self._db,
                check_same_thread=False,
                factory=AutoRetryConnection,
                isolation_level=None,
            )
            self._conns._conn.row_factory = self._state_factory
            self._connections.append(self._conns._conn)

        return self._conns._conn

    def _delete_config(self, cursor: sqlite3.Cursor, name: str) -> None:
        cursor.execute("DELETE FROM Configuration" "       WHERE name = ?", (name,))

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
                "INSERT OR IGNORE INTO Configuration (value, name) " "VALUES (?, ?)",
                (value, name),
            )

    def get_config(self, name: str, default: Any = None) -> Any:
        c = self._get_read_connection().cursor()
        obj = c.execute(
            "SELECT value" "  FROM Configuration" " WHERE name = ?", (name,)
        ).fetchone()
        if not obj or not obj.value:
            return default
        return obj.value


class ManagerDAO(ConfigurationDAO):
    def get_schema_version(self) -> int:
        return 2

    def _init_db(self, cursor: sqlite3.Cursor) -> None:
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

    def insert_notification(self, notification: "Notification") -> None:
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

    def unlock_path(self, path: str) -> None:
        with self._lock:
            con = self._get_write_connection()
            c = con.cursor()
            c.execute("DELETE FROM AutoLock WHERE path = ?", (path,))

    def get_locked_paths(self) -> List[Tuple[str]]:
        con = self._get_read_connection()
        c = con.cursor()
        return c.execute("SELECT * FROM AutoLock").fetchall()

    def lock_path(self, path: str, process: int, doc_id: str) -> None:
        with self._lock:
            con = self._get_write_connection()
            c = con.cursor()
            try:
                c.execute(
                    "INSERT INTO AutoLock (path, process, remote_id) "
                    "VALUES (?, ?, ?)",
                    (path, process, doc_id),
                )
            except sqlite3.IntegrityError:
                # Already there just update the process
                c.execute(
                    "UPDATE AutoLock"
                    "   SET process = ?,"
                    "       remote_id = ?"
                    " WHERE path = ?",
                    (process, doc_id, path),
                )

    def update_notification(self, notification: "Notification") -> None:
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

    def get_notifications(self, discarded: bool = True) -> List[Tuple[str, ...]]:
        # Flags used:
        #    1 = Notification.FLAG_DISCARD
        c = self._get_read_connection().cursor()
        req = "SELECT *" "  FROM Notifications" " WHERE (flags & 1) = 0"
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

    def _migrate_db(self, cursor: sqlite3.Cursor, version: int) -> None:
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

    def get_engines(self) -> List[Tuple[str, ...]]:
        c = self._get_read_connection().cursor()
        return c.execute("SELECT * FROM Engines").fetchall()

    def update_engine_path(self, engine: str, path: str) -> None:
        with self._lock:
            con = self._get_write_connection()
            c = con.cursor()
            c.execute(
                "UPDATE Engines" "   SET local_folder = ?" " WHERE uid = ?",
                (path, engine),
            )

    def add_engine(
        self, engine: str, path: str, key: str, name: str
    ) -> Optional[Tuple[str]]:
        with self._lock:
            con = self._get_write_connection()
            c = con.cursor()
            c.execute(
                "INSERT INTO Engines (local_folder, engine, uid, name) "
                "VALUES (?, ?, ?, ?)",
                (path, engine, key, name),
            )
            result = c.execute(
                "SELECT *" "  FROM Engines" " WHERE uid = ?", (key,)
            ).fetchone()
            return result

    def delete_engine(self, uid: str) -> None:
        with self._lock:
            con = self._get_write_connection()
            c = con.cursor()
            c.execute("DELETE FROM Engines WHERE uid = ?", (uid,))


class EngineDAO(ConfigurationDAO):
    newConflict = pyqtSignal(object)

    def __init__(self, db: str, state_factory: sqlite3.Row = None) -> None:
        if state_factory:
            self._state_factory = state_factory

        super().__init__(db)

        self._queue_manager = None
        self._items_count = 0
        self._items_count = self.get_syncing_count()
        self._filters = self.get_filters()
        self.reinit_processors()

    def get_schema_version(self) -> int:
        return 4

    def _migrate_state(self, cursor: sqlite3.Cursor) -> None:
        try:
            self._migrate_table(cursor, "States")
        except sqlite3.IntegrityError:
            # If we cannot smoothly migrate harder migration
            cursor.execute("DROP TABLE if exists StatesMigration")
            self._reinit_states(cursor)

    def _migrate_db(self, cursor: sqlite3.Cursor, version: int) -> None:
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
            cursor.execute("UPDATE States" "   SET creation_date = last_remote_updated")
            self.update_config(SCHEMA_VERSION, 4)

    def _create_table(
        self, cursor: sqlite3.Cursor, name: str, force: bool = False
    ) -> None:
        if name == "States":
            self._create_state_table(cursor, force)
        else:
            super()._create_table(cursor, name, force)

    @staticmethod
    def _create_state_table(cursor: sqlite3.Cursor, force: bool = False) -> None:
        statement = "" if force else "if not exists"
        # Cannot force UNIQUE for a local_path as a duplicate can have
        # virtually the same path until they are resolved by Processor
        # Should improve that
        cursor.execute(
            "CREATE TABLE {} States ("
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
            "    UNIQUE(remote_ref, local_path))".format(statement)
        )

    def _init_db(self, cursor: sqlite3.Cursor) -> None:
        super()._init_db(cursor)
        for table in ("Filters", "RemoteScan", "ToRemoteScan"):
            cursor.execute(
                "CREATE TABLE if not exists {} ("
                "   path STRING NOT NULL,"
                "   PRIMARY KEY (path)"
                ")".format(table)
            )
        self._create_state_table(cursor)

    def acquire_state(self, thread_id: int, row_id: int) -> Optional[DocPair]:
        if self.acquire_processor(thread_id, row_id):
            # Avoid any lock for this call by using the write connection
            try:
                return self.get_state_from_id(row_id, from_write=True)
            except:
                self.release_processor(thread_id)
                raise
        raise sqlite3.OperationalError("Cannot acquire")

    def release_state(self, thread_id: int) -> None:
        self.release_processor(thread_id)

    def release_processor(self, processor_id: int) -> bool:
        with self._lock:
            con = self._get_write_connection()
            c = con.cursor()
            # TO_REVIEW Might go back to primary key id
            c.execute(
                "UPDATE States" "   SET processor = 0" " WHERE processor = ?",
                (processor_id,),
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

    def _reinit_states(self, cursor: sqlite3.Cursor) -> None:
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
            c.execute("UPDATE States" "   SET processor = 0")
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
            c.execute(
                "{} WHERE id = ?".format(update), ("remotely_deleted", doc_pair.id)
            )
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
                c.execute(
                    "{} WHERE id = ?".format(update), ("locally_deleted", doc_pair.id)
                )
                if doc_pair.folderish:
                    c.execute(
                        update + " " + self._get_recursive_condition(doc_pair),
                        ("locally_deleted",),
                    )
        finally:
            self._queue_manager.interrupt_processors_on(
                doc_pair.local_path, exact_match=False
            )

            # Only queue parent
            self._queue_pair_state(doc_pair.id, doc_pair.folderish, "locally_deleted")

    def insert_local_state(self, info: NuxeoDocumentInfo, parent_path: str) -> int:
        pair_state = PAIR_STATES.get(("created", "unknown"))
        digest = info.get_digest()
        with self._lock:
            con = self._get_write_connection()
            c = con.cursor()
            name = os.path.basename(info.path)
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
                    name,
                    info.folderish,
                    info.size,
                    pair_state,
                ),
            )
            row_id = c.lastrowid
            parent = c.execute(
                "SELECT *" "  FROM States" " WHERE local_path = ?", (parent_path,)
            ).fetchone()
            # Don't queue if parent is not yet created
            if (parent is None and parent_path == "") or (
                parent and parent.pair_state != "locally_created"
            ):
                self._queue_pair_state(row_id, info.folderish, pair_state)
            self._items_count += 1
        return row_id

    def get_last_files(self, number: int, direction: str = "") -> DocPairs:
        c = self._get_read_connection().cursor()
        conditions = {
            "remote": "AND last_transfer = 'upload'",
            "local": "AND last_transfer = 'download'",
        }
        condition = conditions.get(direction, "")
        return c.execute(
            "SELECT *"
            "  FROM States"
            " WHERE pair_state = 'synchronized'"
            "   AND folderish = 0 {} "
            " ORDER BY last_sync_date DESC"
            " LIMIT {}".format(condition, number)
        ).fetchall()

    def _get_to_sync_condition(self) -> str:
        return "pair_state != 'synchronized' " "AND pair_state != 'unsynchronized'"

    def register_queue_manager(self, manager: "Manager") -> None:
        # Prevent any update while init queue
        with self._lock:
            self._queue_manager = manager
            con = self._get_write_connection()
            c = con.cursor()
            # Order by path to be sure to process parents before childs
            pairs = c.execute(
                "SELECT *"
                "  FROM States"
                " WHERE {}"
                " ORDER BY local_path ASC".format(self._get_to_sync_condition())
            ).fetchall()
            folders = dict()
            for pair in pairs:
                # Add all the folders
                if pair.folderish:
                    folders[pair.local_path] = True
                if pair.local_parent_path not in folders:
                    self._queue_manager.push_ref(
                        pair.id, pair.folderish, pair.pair_state
                    )
        # Dont block everything if queue manager fail
        # TODO As the error should be fatal not sure we need this

    def _queue_pair_state(
        self,
        row_id: int,
        folderish: bool,
        pair_state: str,
        pair: NuxeoDocumentInfo = None,
    ) -> None:
        if self._queue_manager and pair_state not in ("synchronized", "unsynchronized"):
            if pair_state == "conflicted":
                log.trace("Emit newConflict with: %r, pair=%r", row_id, pair)
                self.newConflict.emit(row_id)
            else:
                log.trace("Push to queue: %s, pair=%r", pair_state, pair)
                self._queue_manager.push_ref(row_id, folderish, pair_state)
        else:
            log.trace("Will not push pair: %s, pair=%r", pair_state, pair)

    def _get_pair_state(self, row):
        return PAIR_STATES.get((row.local_state, row.remote_state))

    def update_last_transfer(self, row_id: int, transfer: str) -> None:
        with self._lock:
            con = self._get_write_connection()
            c = con.cursor()
            c.execute(
                "UPDATE States" "   SET last_transfer = ?" " WHERE id = ?",
                (transfer, row_id),
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

    def remove_local_path(self, row_id: int) -> None:
        with self._lock:
            con = self._get_write_connection()
            c = con.cursor()
            c.execute(
                "UPDATE States" "   SET local_path = ''" " WHERE id = ?", (row_id,)
            )

    def update_local_state(
        self,
        row: NuxeoDocumentInfo,
        info: NuxeoDocumentInfo,
        versioned: bool = True,
        queue: bool = True,
    ) -> None:
        row.pair_state = self._get_pair_state(row)
        log.trace("Updating local state for row=%r with info=%r", row, info)

        version = ""
        if versioned:
            version = ", version = version + 1"
            log.trace("Increasing version to %d for pair %r", row.version + 1, row)

        parent_path = os.path.dirname(info.path)
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
                "       pair_state = ? {version}"
                " WHERE id = ?".format(version=version),
                (
                    info.last_modification_time,
                    row.local_digest,
                    info.path,
                    parent_path,
                    os.path.basename(info.path),
                    row.local_state,
                    info.size,
                    row.remote_state,
                    row.pair_state,
                    row.id,
                ),
            )
            if queue:
                parent = c.execute(
                    "SELECT *" "  FROM States" " WHERE local_path = ?", (parent_path,)
                ).fetchone()
                # Don't queue if parent is not yet created
                if (not parent and not parent_path) or (
                    parent and parent.local_state != "created"
                ):
                    self._queue_pair_state(
                        row.id, info.folderish, row.pair_state, pair=row
                    )

    def update_local_modification_time(
        self, row: NuxeoDocumentInfo, info: NuxeoDocumentInfo
    ) -> None:
        with self._lock:
            con = self._get_write_connection()
            c = con.cursor()
            c.execute(
                "UPDATE States" "   SET last_local_updated = ?" " WHERE id = ?",
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
            "SELECT *" "  FROM States" " WHERE remote_parent_path LIKE ?",
            ("{}%".format(path),),
        ).fetchall()

    def get_remote_descendants_from_ref(self, ref: str) -> DocPairs:
        c = self._get_read_connection().cursor()
        return c.execute(
            "SELECT *" "  FROM States" " WHERE remote_parent_path LIKE ?",
            ("%{}%".format(ref),),
        ).fetchall()

    def get_remote_children(self, ref: str) -> DocPairs:
        c = self._get_read_connection().cursor()
        return c.execute(
            "SELECT *" "  FROM States" " WHERE remote_parent_ref = ?", (ref,)
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
        return self.get_count("error_count > {}".format(threshold))

    def get_syncing_count(self, threshold: int = 3) -> int:
        count = self.get_count(
            "    pair_state != 'synchronized' "
            "AND pair_state != 'conflicted' "
            "AND pair_state != 'unsynchronized' "
            "AND error_count < {}".format(threshold)
        )
        if self._items_count != count:
            log.trace(
                "Cache Syncing count incorrect should be %d was %d",
                count,
                self._items_count,
            )
            self._items_count = count
        return count

    def get_sync_count(self, filetype: str = None) -> int:
        conditions = {"file": "AND folderish = 0", "folder": "AND folderish = 1"}
        condition = conditions.get(filetype, "")
        return self.get_count("pair_state = 'synchronized' {}".format(condition))

    def get_count(self, condition: str = None) -> int:
        query = "SELECT COUNT(*) as count" "  FROM States"
        if condition:
            query = "{} WHERE {}".format(query, condition)
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
            "SELECT *" "  FROM States" " WHERE pair_state = 'unsynchronized'"
        ).fetchall()

    def get_conflicts(self) -> DocPairs:
        c = self._get_read_connection().cursor()
        return c.execute(
            "SELECT *" "  FROM States" " WHERE pair_state = 'conflicted'"
        ).fetchall()

    def get_errors(self, limit: int = 3) -> DocPairs:
        c = self._get_read_connection().cursor()
        return c.execute(
            "SELECT *" "  FROM States" " WHERE error_count > ?", (limit,)
        ).fetchall()

    def get_local_children(self, path: str) -> DocPairs:
        c = self._get_read_connection().cursor()
        return c.execute(
            "SELECT *" "  FROM States" " WHERE local_parent_path = ?", (path,)
        ).fetchall()

    def get_states_from_partial_local(self, path: str) -> DocPairs:
        c = self._get_read_connection().cursor()
        return c.execute(
            "SELECT *" "  FROM States" " WHERE local_path LIKE ?", ("{}%".format(path),)
        ).fetchall()

    def get_first_state_from_partial_remote(self, ref: str) -> Optional[DocPair]:
        c = self._get_read_connection().cursor()
        return c.execute(
            "SELECT *"
            "  FROM States"
            " WHERE remote_ref LIKE ? "
            " ORDER BY last_remote_updated ASC"
            " LIMIT 1",
            ("%{}".format(ref),),
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
        return c.execute(
            "SELECT *" "  FROM States" " WHERE remote_ref = ?", (ref,)
        ).fetchall()

    def get_state_from_id(
        self, row_id: int, from_write: bool = False
    ) -> Optional[DocPair]:
        if from_write:
            from_write = False
        try:
            if from_write:
                self._lock.acquire()
                c = self._get_write_connection().cursor()
            else:
                c = self._get_read_connection().cursor()
            state = c.execute(
                "SELECT *" "  FROM States" " WHERE id = ?", (row_id,)
            ).fetchone()
        finally:
            if from_write:
                self._lock.release()
        return state

    def _get_recursive_condition(self, doc_pair: NuxeoDocumentInfo) -> str:
        path = self._escape(doc_pair.local_path)
        res = (
            " WHERE (local_parent_path LIKE '" + path + "/%'"
            "        OR local_parent_path = '" + path + "')"
        )
        if doc_pair.remote_ref:
            path = self._escape(doc_pair.remote_parent_path + "/" + doc_pair.remote_ref)
            res += " AND remote_parent_path LIKE '" + path + "%'"
        return res

    def _get_recursive_remote_condition(self, doc_pair: NuxeoDocumentInfo) -> str:
        path = self._escape(doc_pair.remote_parent_path + "/" + doc_pair.remote_name)
        return (
            " WHERE remote_parent_path LIKE '" + path + "/%'"
            "    OR remote_parent_path = '" + path + "'"
        )

    def update_remote_parent_path(
        self, doc_pair: NuxeoDocumentInfo, new_path: str
    ) -> None:
        with self._lock:
            con = self._get_write_connection()
            c = con.cursor()
            if doc_pair.folderish:
                count = str(
                    len(doc_pair.remote_parent_path + "/" + doc_pair.remote_ref) + 1
                )
                path = self._escape(new_path + "/" + doc_pair.remote_ref)
                query = (
                    "UPDATE States"
                    "   SET remote_parent_path = '" + path + "'"
                    "     || substr(remote_parent_path, "
                    + count
                    + ")"
                    + self._get_recursive_remote_condition(doc_pair)
                )

                log.trace("Update remote_parent_path %r", query)
                c.execute(query)
            c.execute(
                "UPDATE States" "   SET remote_parent_path = ?" " WHERE id = ?",
                (new_path, doc_pair.id),
            )

    def update_local_parent_path(
        self, doc_pair: NuxeoDocumentInfo, new_name: str, new_path: str
    ) -> None:
        with self._lock:
            con = self._get_write_connection()
            c = con.cursor()
            if doc_pair.folderish:
                if new_path == "/":
                    new_path = ""
                path = self._escape(new_path + "/" + new_name)
                count = str(len(doc_pair.local_path) + 1)
                query = (
                    "UPDATE States"
                    "   SET local_parent_path = '" + path + "'"
                    "       || substr(local_parent_path, " + count + "),"
                    "          local_path = '" + path + "'"
                    "       || substr(local_path, "
                    + count
                    + ") "
                    + self._get_recursive_condition(doc_pair)
                )
                c.execute(query)
            # Dont need to update the path as it is refresh later
            c.execute(
                "UPDATE States" "   SET local_parent_path = ?" " WHERE id = ?",
                (new_path, doc_pair.id),
            )

    def mark_descendants_remotely_created(self, doc_pair: NuxeoDocumentInfo) -> None:
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
            c.execute("{} WHERE id = {}".format(update, str(doc_pair.id)))
            if doc_pair.folderish:
                c.execute(
                    "{} {}".format(update, self._get_recursive_condition(doc_pair))
                )
            self._queue_pair_state(doc_pair.id, doc_pair.folderish, doc_pair.pair_state)

    def remove_state(
        self, doc_pair: NuxeoDocumentInfo, remote_recursion: bool = False
    ) -> None:
        with self._lock:
            con = self._get_write_connection()
            c = con.cursor()
            c.execute("DELETE FROM States" " WHERE id = ?", (doc_pair.id,))
            if doc_pair.folderish:
                if remote_recursion:
                    condition = self._get_recursive_remote_condition(doc_pair)
                else:
                    condition = self._get_recursive_condition(doc_pair)
                c.execute("DELETE FROM States " + condition)

    def get_state_from_local(self, path: str) -> Optional[DocPair]:
        c = self._get_read_connection().cursor()
        return c.execute(
            "SELECT *" "  FROM States" " WHERE local_path = ?", (path,)
        ).fetchone()

    def insert_remote_state(
        self,
        info: NuxeoDocumentInfo,
        remote_parent_path: str,
        local_path: str,
        local_parent_path: str,
    ) -> int:
        pair_state = PAIR_STATES.get(("unknown", "created"))
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
                "SELECT *" "  FROM States" " WHERE remote_ref = ?", (info.parent_uid,)
            ).fetchone()
            if (parent is None and local_parent_path == "") or (
                parent and parent.pair_state != "remotely_created"
            ):
                self._queue_pair_state(row_id, info.folderish, pair_state)
            self._items_count += 1
        return row_id

    def queue_children(self, row: NuxeoDocumentInfo) -> None:
        with self._lock:
            con = self._get_write_connection()
            c = con.cursor()
            children = c.execute(
                "SELECT *"
                "  FROM States"
                " WHERE remote_parent_ref = ?"
                "    OR local_parent_path = ?"
                "   AND " + self._get_to_sync_condition(),
                (row.remote_ref, row.local_path),
            ).fetchall()
            log.debug("Queuing %d children of %r", len(children), row)
            for child in children:
                self._queue_pair_state(child.id, child.folderish, child.pair_state)

    def increase_error(
        self, row: NuxeoDocumentInfo, error: str, details: str = None, incr: int = 1
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

    def reset_error(self, row: NuxeoDocumentInfo, last_error: str = None) -> None:
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

    def _force_sync(
        self, row: NuxeoDocumentInfo, local: str, remote: str, pair: str
    ) -> bool:
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

    def force_remote(self, row: List[Tuple[DocPair]]) -> bool:
        return self._force_sync(row, "synchronized", "modified", "remotely_modified")

    def force_local(self, row: NuxeoDocumentInfo) -> bool:
        return self._force_sync(row, "resolved", "unknown", "locally_resolved")

    def set_conflict_state(self, row: List[Tuple[DocPair]]) -> bool:
        with self._lock:
            con = self._get_write_connection()
            c = con.cursor()
            c.execute(
                "UPDATE States" "   SET pair_state = ?" " WHERE id = ?",
                ("conflicted", row.id),
            )
            self.newConflict.emit(row.id)
        if c.rowcount == 1:
            self._items_count -= 1
            return True
        return False

    def unsynchronize_state(
        self, row: NuxeoDocumentInfo, last_error: str = None
    ) -> None:
        with self._lock:
            con = self._get_write_connection()
            c = con.cursor()
            c.execute(
                "UPDATE States"
                "   SET pair_state = ?,"
                "       last_sync_date = ?,"
                "       processor = 0,"
                "       last_error = ?,"
                "       error_count = 0,"
                "       last_sync_error_date = NULL"
                " WHERE id = ?",
                ("unsynchronized", datetime.utcnow(), last_error, row.id),
            )

    def synchronize_state(
        self, row: NuxeoDocumentInfo, version: int = None, dynamic_states: bool = False
    ) -> bool:
        if version is None:
            version = row.version
        log.trace(
            "Try to synchronize state for [local_path=%r, "
            "remote_name=%r, version=%s] with version=%s "
            "and dynamic_states=%r",
            row.local_path,
            row.remote_name,
            row.version,
            version,
            dynamic_states,
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
            log.trace("Was not able to synchronize state: %r", row)
            c = self._get_read_connection().cursor()
            row2 = c.execute(
                "SELECT *" "  FROM States" " WHERE id = ?", (row.id,)
            ).fetchone()
            if row2 is None:
                log.trace("No more row")
            else:
                log.trace("Current row=%r (version=%r)", row2, row2.version)
            log.trace("Previous row=%r (version=%r)", row, row.version)
        elif row.folderish:
            self.queue_children(row)

        return result

    def update_remote_state(
        self,
        row: NuxeoDocumentInfo,
        info: NuxeoDocumentInfo,
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
                        "Not updating remote state (not dirty)"
                        " for row=%r with info=%r",
                        row,
                        info,
                    )
                    return

        log.trace(
            "Updating remote state for row=%r with info=%r (force=%r)",
            row,
            info,
            force_update,
        )

        if (
            row.pair_state not in ("conflicted", "remotely_created")
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
                query += ", remote_digest = '{}'".format(info.digest)

            if versioned:
                query += ", version = version+1"
                log.trace("Increasing version to %d for pair %r", row.version + 1, row)

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
                    "SELECT *" "  FROM States" " WHERE remote_ref = ?",
                    (info.parent_uid,),
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
        with self._lock, suppress(sqlite3.IntegrityError):
            con = self._get_write_connection()
            c = con.cursor()
            # Remove any subchilds as it is gonna be scanned anyway
            c.execute("DELETE FROM ToRemoteScan" " WHERE path LIKE ?", (path + "%",))
            c.execute("INSERT INTO ToRemoteScan (path) " "VALUES (?)", (path,))

    def delete_path_to_scan(self, path: str) -> str:
        path = self._clean_filter_path(path)
        with self._lock, suppress(sqlite3.IntegrityError):
            con = self._get_write_connection()
            c = con.cursor()
            c.execute("DELETE FROM ToRemoteScan" " WHERE path = ?", (path,))

    def get_paths_to_scan(self) -> List[Tuple[str, ...]]:
        c = self._get_read_connection().cursor()
        return c.execute("SELECT *" "  FROM ToRemoteScan").fetchall()

    def add_path_scanned(self, path: str) -> None:
        path = self._clean_filter_path(path)
        with self._lock, suppress(sqlite3.IntegrityError):
            con = self._get_write_connection()
            c = con.cursor()
            c.execute("INSERT INTO RemoteScan (path) " "VALUES (?)", (path,))

    def clean_scanned(self) -> None:
        with self._lock:
            con = self._get_write_connection()
            c = con.cursor()
            c.execute("DELETE FROM RemoteScan")

    def is_path_scanned(self, path: str) -> bool:
        path = self._clean_filter_path(path)
        c = self._get_read_connection().cursor()
        row = c.execute(
            "SELECT COUNT(path)" "  FROM RemoteScan" " WHERE path = ?" " LIMIT 1",
            (path,),
        ).fetchone()
        return row[0] > 0

    @staticmethod
    def get_batch_sync_ignore() -> str:
        return (
            "AND (pair_state != 'unsynchronized' "
            "AND pair_state != 'conflicted') "
            "AND folderish = 0 "
        )

    def _get_adjacent_sync_file(
        self, ref: str, comp: str, order: str, sync_mode: str = None
    ) -> Optional[DocPair]:
        state = self.get_normal_state_from_remote(ref)
        if state is None:
            return None

        mode = "AND last_transfer='{}' ".format(sync_mode) if sync_mode else ""
        c = self._get_read_connection().cursor()
        return c.execute(
            "SELECT *"
            "  FROM States"
            " WHERE last_sync_date {} ?"
            " {}{} "
            " ORDER BY last_sync_date {}"
            " LIMIT 1".format(comp, mode, self.get_batch_sync_ignore(), order),
            (state.last_sync_date,),
        ).fetchone()

    def get_previous_sync_file(
        self, ref: str, sync_mode: str = None
    ) -> Optional[DocPair]:
        return self._get_adjacent_sync_file(ref, ">", "ASC", sync_mode)

    def get_next_sync_file(self, ref: str, sync_mode: str = None) -> Optional[DocPair]:
        return self._get_adjacent_sync_file(ref, "<", "DESC", sync_mode)

    def _get_adjacent_folder_file(
        self, ref: str, comp: str, order: str
    ) -> Optional[DocPair]:
        state = self.get_normal_state_from_remote(ref)
        c = self._get_read_connection().cursor()
        return c.execute(
            "SELECT *"
            "  FROM States"
            " WHERE remote_parent_ref = ?"
            "   AND remote_name {} ?"
            "   AND folderish = 0"
            " ORDER BY remote_name {}"
            " LIMIT 1".format(comp, order),
            (state.remote_parent_ref, state.remote_name),
        ).fetchone()

    def get_next_folder_file(self, ref: str) -> Optional[DocPair]:
        return self._get_adjacent_folder_file(ref, ">", "ASC")

    def get_previous_folder_file(self, ref: str) -> Optional[DocPair]:
        return self._get_adjacent_folder_file(ref, "<", "DESC")

    def is_filter(self, path: str) -> bool:
        path = self._clean_filter_path(path)
        return any(path.startswith(doc.path) for doc in self._filters)

    def get_filters(self) -> Filters:
        c = self._get_read_connection().cursor()
        return c.execute("SELECT *" "  FROM Filters").fetchall()

    def add_filter(self, path: str) -> None:
        if self.is_filter(path):
            return

        path = self._clean_filter_path(path)
        log.trace("Add filter on %r", path)

        with self._lock:
            con = self._get_write_connection()
            c = con.cursor()
            # Delete any subfilters
            c.execute("DELETE FROM Filters WHERE path LIKE ?", (path + "%",))

            # Prevent any rescan
            c.execute("DELETE FROM ToRemoteScan" " WHERE path LIKE ?", (path + "%",))

            # Add it
            c.execute("INSERT INTO Filters (path) VALUES (?)", (path,))

            # TODO: Add this path as remotely_deleted?

            self._filters = self.get_filters()
            self._items_count = self.get_syncing_count()

    def remove_filter(self, path: str) -> None:
        path = self._clean_filter_path(path)
        with self._lock:
            con = self._get_write_connection()
            c = con.cursor()
            c.execute("DELETE FROM Filters" " WHERE path LIKE ?", (path + "%",))
            self._filters = self.get_filters()
            self._items_count = self.get_syncing_count()

    @staticmethod
    def _escape(text: str) -> str:
        return text.replace("'", "''")
