"""
Query formatting in this file is based on http://www.sqlstyle.guide/
"""
import sys
from contextlib import suppress
from logging import getLogger
from pathlib import Path
from sqlite3 import Connection, Cursor, DatabaseError, OperationalError, Row, connect
from threading import RLock, local
from typing import Any, Iterable, List, Optional, Type

from ..constants import NO_SPACE_ERRORS
from ..objects import DocPair
from ..qt.imports import QObject
from ..utils import current_thread_id
from . import SCHEMA_VERSION
from .utils import fix_db, restore_backup, save_backup

log = getLogger(__name__)


class AutoRetryCursor(Cursor):
    def execute(self, sql: str, parameters: Iterable[Any] = ()) -> Cursor:
        count = 1
        while True:
            count += 1
            try:
                return super().execute(sql, parameters)
            except OperationalError as exc:
                log.info(
                    f"Retry locked database #{count}, {sql=}, {parameters=}",
                    exc_info=True,
                )
                if count > 5:
                    raise exc


class AutoRetryConnection(Connection):
    def cursor(self, factory: Type[Cursor] = None) -> Cursor:
        factory = factory or AutoRetryCursor
        return super().cursor(factory)


class BaseDAO(QObject):

    _state_factory: Type[Row] = DocPair
    _journal_mode: str = "WAL"

    def __init__(self, db: Path, /) -> None:
        super().__init__()

        self.db = db
        self.lock = RLock()

        log.info(f"Create {type(self).__name__} on {self.db!r}")

        exists = self.db.is_file()
        if exists:
            # Fix potential file corruption
            try:
                fix_db(self.db)
            except DatabaseError:
                # The file is too damaged, we'll try and restore a backup.
                exists = self.restore_backup()
                if not exists:
                    self.db.unlink(missing_ok=True)

        self._engine_uid = self.db.stem.replace("ndrive_", "")
        self.in_tx = None
        self._tx_lock = RLock()
        self.conn: Optional[Connection] = None
        self._conns = local()
        self._create_main_conn()
        if not self.conn:
            raise RuntimeError("Unable to connect to database.")
        c = self.conn.cursor()
        self._init_db(c)
        if exists:
            schema = self.get_schema_version(c, exists)
            if schema != self.schema_version:
                self._migrate_db(c, schema)
        else:
            self.set_schema_version(c, self.schema_version)

    def __repr__(self) -> str:
        return f"<{type(self).__name__} db={self.db!r}, exists={self.db.exists()}>"

    def __str__(self) -> str:
        return repr(self)

    def force_commit(self) -> None:
        """
        Since the journal is WAL, database changes are saved only every 1,000 page changes.
        (cf https://www.sqlite.org/compile.html#default_wal_autocheckpoint
        and https://www.sqlite.org/c3ref/wal_checkpoint_v2.html)
        This method can be used to force committing changes to the main database. To use wisely.
        """
        if self._journal_mode != "WAL":
            return

        log.debug(f"Forcing WAL checkpoint on {self.db!r}")
        with self.lock:
            c = self._get_write_connection().cursor()
            c.execute("PRAGMA wal_checkpoint(PASSIVE)")

    def restore_backup(self) -> bool:
        try:
            with self.lock:
                return restore_backup(self.db)
        except OSError as exc:
            if exc.errno in NO_SPACE_ERRORS:
                # We cannot do anything without more disk space!
                log.warning(f"[OS] Unable to restore {self.db}", exc_info=True)
                raise
            log.exception(f"[OS] Unable to restore {self.db}")
            sys.excepthook(*sys.exc_info())
        except Exception:
            log.exception(f"Unable to restore {self.db}")
            sys.excepthook(*sys.exc_info())
        return False

    def save_backup(self) -> bool:
        try:
            with self.lock:
                return save_backup(self.db)
        except OSError as exc:
            if exc.errno in NO_SPACE_ERRORS:
                # Not being able to create a backup is critical,
                # but we should not make the application to stop either
                log.warning(f"[OS] Unable to backup {self.db}", exc_info=True)
            else:
                log.exception(f"[OS] Unable to backup {self.db}")
                sys.excepthook(*sys.exc_info())
        except Exception:
            log.exception(f"Unable to backup {self.db}")
            sys.excepthook(*sys.exc_info())
        return False

    def get_schema_version(self, cursor: Cursor, db_exists: bool) -> int:
        """
        Get the schema version stored in the database.
        Will fetch the information from a PRAGMA or the old storage variable.
        """
        res = cursor.execute("PRAGMA user_version").fetchone()
        version = int(res[0]) if res else 0

        if version == 0 and db_exists:
            # Backward compatibility
            res = cursor.execute(
                "SELECT value FROM Configuration WHERE name = ?", (SCHEMA_VERSION,)
            ).fetchone()
            version = int(res[0]) if res else 0

        return version

    def set_schema_version(self, cursor: Cursor, version: int) -> None:
        """
        Set the schema *version* in the *user_version* PRAGMA.
        """
        cursor.execute(f"PRAGMA user_version = {version}")

    def _migrate_table(self, cursor: Cursor, name: str, /) -> None:
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

    def _create_table(
        self, cursor: Cursor, name: str, /, *, force: bool = False
    ) -> None:
        if name == "Configuration":
            self._create_configuration_table(cursor)

    def _get_columns(self, cursor: Cursor, table: str, /) -> List[Any]:
        return [
            col.name
            for col in cursor.execute(f"PRAGMA table_info('{table}')").fetchall()
        ]

    def _init_db(self, cursor: Cursor, /) -> None:
        cursor.execute(f"PRAGMA journal_mode = {self._journal_mode}")
        cursor.execute("PRAGMA temp_store = MEMORY")
        self._create_configuration_table(cursor)

    def _create_configuration_table(self, cursor: Cursor, /) -> None:
        cursor.execute(
            "CREATE TABLE if not exists Configuration ("
            "    name    VARCHAR NOT NULL,"
            "    value   VARCHAR,"
            "    PRIMARY KEY (name)"
            ")"
        )

    def _create_main_conn(self) -> None:
        log.info(
            f"Create main connection on {self.db!r} "
            f"(dir_exists={self.db.parent.exists()}, "
            f"file_exists={self.db.exists()})"
        )
        self.conn = connect(
            str(self.db),
            check_same_thread=False,  # Don't check same thread for closing purpose
            factory=AutoRetryConnection,
            isolation_level=None,  # Autocommit mode
            timeout=10,
        )
        self.conn.row_factory = self._state_factory

    def dispose(self) -> None:
        log.info(f"Disposing SQLite database {self.db!r}")
        if hasattr(self._conns, "conn"):
            self._conns.conn.close()
            del self._conns.conn
        if self.conn:
            self.conn.close()

    def _get_write_connection(self) -> Connection:
        if self.in_tx:
            if self.conn is None:
                self._create_main_conn()
            return self.conn
        return self._get_read_connection()

    def _get_read_connection(self) -> Connection:
        # If in transaction
        if self.in_tx is not None:
            if current_thread_id() == self.in_tx:
                # Return the write connection
                return self.conn

            log.debug("In transaction wait for read connection")
            # Wait for the thread in transaction to finished
            with self._tx_lock:
                pass

        if not hasattr(self._conns, "conn"):
            self._conns.conn = connect(
                str(self.db),
                check_same_thread=False,  # Don't check same thread for closing purpose
                factory=AutoRetryConnection,
                isolation_level=None,  # Autocommit mode
                timeout=10,
            )
            self._conns.conn.row_factory = self._state_factory

        return self._conns.conn  # type: ignore

    def _delete_config(self, cursor: Cursor, name: str, /) -> None:
        cursor.execute("DELETE FROM Configuration WHERE name = ?", (name,))

    def delete_config(self, name: str, /) -> None:
        with self.lock:
            c = self._get_write_connection().cursor()
            self._delete_config(c, name)

    def update_config(self, name: str, value: Any, /) -> None:
        # We cannot use this anymore because it will end on a DatabaseError.
        # Will re-activate with NXDRIVE-1205
        # if self.get_config(name) == value:
        #     return

        with self.lock:
            c = self._get_write_connection().cursor()
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

    def store_bool(self, name: str, value: bool, /) -> None:
        """Store a boolean parameter."""

        self.update_config(name, bool(value))

    def store_int(self, name: str, value: int, /) -> None:
        """Store an integer parameter."""

        self.update_config(name, int(value))

    def get_config(self, name: str, /, *, default: Any = None) -> Any:
        c = self._get_read_connection().cursor()
        obj = c.execute(
            "SELECT value FROM Configuration WHERE name = ?", (name,)
        ).fetchone()
        if not (obj and obj.value):
            return default
        return obj.value

    def get_bool(self, name: str, /, *, default: bool = False) -> bool:
        """Retrieve a parameter of boolean type."""

        with suppress(Exception):
            val = self.get_config(name, default=default)
            return bool(int(val))

        return default if isinstance(default, bool) else False

    def get_int(self, name: str, /, *, default: int = 0) -> int:
        """Retrieve a parameter of integer type."""

        with suppress(Exception):
            val = self.get_config(name, default=default)
            return int(val)

        return default if isinstance(default, int) else 0
