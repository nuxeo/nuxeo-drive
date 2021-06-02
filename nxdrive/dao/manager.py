"""
Query formatting in this file is based on http://www.sqlstyle.guide/
"""
from logging import getLogger
from pathlib import Path
from sqlite3 import Cursor, IntegrityError, Row
from typing import List

from ..notification import Notification
from ..objects import EngineDef
from . import SCHEMA_VERSION
from .base import BaseDAO

log = getLogger(__name__)


class ManagerDAO(BaseDAO):

    schema_version = 4
    _state_factory = EngineDef

    # WAL not needed as we write less often and it may have issues on GNU/Linux (NXDRIVE-2524)
    _journal_mode: str = "DELETE"

    def _init_db(self, cursor: Cursor, /) -> None:
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

    def insert_notification(self, notification: Notification, /) -> None:
        with self.lock:
            c = self._get_write_connection().cursor()
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

    def unlock_path(self, path: Path, /) -> None:
        with self.lock:
            c = self._get_write_connection().cursor()
            c.execute("DELETE FROM AutoLock WHERE path = ?", (path,))

    def get_locks(self) -> List[Row]:
        c = self._get_read_connection().cursor()
        return c.execute("SELECT * FROM AutoLock").fetchall()

    def get_locked_paths(self) -> List[Path]:
        return [Path(lock["path"]) for lock in self.get_locks()]

    def lock_path(self, path: Path, process: int, doc_id: str, /) -> None:
        with self.lock:
            c = self._get_write_connection().cursor()
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

    def update_notification(self, notification: Notification, /) -> None:
        with self.lock:
            c = self._get_write_connection().cursor()
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

    def get_notifications(self, *, discarded: bool = True) -> List[Row]:
        # Flags used:
        #    1 = Notification.FLAG_DISCARD
        c = self._get_read_connection().cursor()
        req = "SELECT * FROM Notifications WHERE (flags & 1) = 0"
        if discarded:
            req = "SELECT * FROM Notifications"

        return c.execute(req).fetchall()

    def discard_notification(self, uid: str, /) -> None:
        # Flags used:
        #    1 = Notification.FLAG_DISCARD
        #    4 = Notification.FLAG_DISCARDABLE
        with self.lock:
            c = self._get_write_connection().cursor()
            c.execute(
                "UPDATE Notifications"
                "   SET flags = (flags | 1)"
                " WHERE uid = ?"
                "   AND (flags & 4) = 4",
                (uid,),
            )

    def remove_notification(self, uid: str, /) -> None:
        with self.lock:
            c = self._get_write_connection().cursor()
            c.execute("DELETE FROM Notifications WHERE uid = ?", (uid,))

    def _migrate_db(self, cursor: Cursor, version: int, /) -> None:
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
            self.set_schema_version(cursor, 2)
        if version < 3:
            cursor.execute(
                "CREATE TABLE if not exists AutoLock ("
                "    path      VARCHAR,"
                "    remote_id VARCHAR,"
                "    process   INT,"
                "    PRIMARY KEY (path)"
                ")"
            )
            self.set_schema_version(cursor, 3)
        if version < 4:
            self.store_int(SCHEMA_VERSION, 4)
            self.set_schema_version(cursor, 4)

    def get_engines(self) -> List[EngineDef]:
        c = self._get_read_connection().cursor()
        return c.execute("SELECT * FROM Engines").fetchall()

    def update_engine_path(self, engine: str, path: Path, /) -> None:
        with self.lock:
            c = self._get_write_connection().cursor()
            c.execute(
                "UPDATE Engines SET local_folder = ? WHERE uid = ?", (path, engine)
            )

    def add_engine(self, engine: str, path: Path, key: str, name: str, /) -> EngineDef:
        with self.lock:
            c = self._get_write_connection().cursor()
            c.execute(
                "INSERT INTO Engines (local_folder, engine, uid, name) "
                "VALUES (?, ?, ?, ?)",
                (path, engine, key, name),
            )
            engine_def: EngineDef = c.execute(
                "SELECT * FROM Engines WHERE uid = ?", (key,)
            ).fetchone()
            return engine_def

    def delete_engine(self, uid: str, /) -> None:
        with self.lock:
            c = self._get_write_connection().cursor()
            c.execute("DELETE FROM Engines WHERE uid = ?", (uid,))
