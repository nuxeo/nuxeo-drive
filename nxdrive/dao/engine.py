"""
Query formatting in this file is based on http://www.sqlstyle.guide/
"""
import json
import os
import shutil
from contextlib import suppress
from datetime import datetime
from logging import getLogger
from os.path import basename
from pathlib import Path
from sqlite3 import Cursor, IntegrityError, OperationalError
from typing import (
    TYPE_CHECKING,
    Any,
    Callable,
    Dict,
    Generator,
    List,
    Optional,
    Tuple,
    Union,
)

from nuxeo.utils import get_digest_algorithm

from ..client.local import FileInfo
from ..constants import ROOT, UNACCESSIBLE_HASH, WINDOWS, TransferStatus
from ..exceptions import UnknownPairState
from ..objects import (
    DocPair,
    DocPairs,
    Download,
    Filters,
    RemoteFileInfo,
    Session,
    Upload,
)
from ..options import Options
from ..qt.imports import pyqtSignal
from . import SCHEMA_VERSION
from .adapters import adapt_path
from .base import BaseDAO

if TYPE_CHECKING:
    from ..queue_manager import QueueManager  # noqa

log = getLogger(__name__)

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
    ("deleted", "moved"): "remotely_created",
    # conflict cases that need manual resolution
    ("modified", "created"): "conflicted",
    ("modified", "modified"): "conflicted",
    ("created", "created"): "conflicted",
    ("created", "modified"): "conflicted",
    ("moved", "unknown"): "conflicted",
    ("moved", "moved"): "conflicted",
    ("moved", "created"): "conflicted",
    ("resolved", "modified"): "conflicted",
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
    ("unsynchronized", "synchronized"): "unsynchronized",
    ("unsynchronized", "deleted"): "remotely_deleted",
    # Direct Transfer
    ("direct", "unknown"): "direct_transfer",
    ("direct", "todo"): "",
}


class EngineDAO(BaseDAO):

    schema_version = 21
    newConflict = pyqtSignal(object)
    transferUpdated = pyqtSignal()
    directTransferUpdated = pyqtSignal()
    sessionUpdated = pyqtSignal(bool)

    def __init__(self, db: Path, /) -> None:
        super().__init__(db)

        self.queue_manager: Optional["QueueManager"] = None
        self._items_count = 0
        self.get_syncing_count()
        self._filters = self.get_filters()
        self.reinit_processors()

    def _migrate_state(self, cursor: Cursor, /) -> None:
        try:
            self._migrate_table(cursor, "States")
        except IntegrityError:
            # If we cannot smoothly migrate harder migration
            cursor.execute("DROP TABLE if exists StatesMigration")
            self._reinit_states(cursor)

    def _migrate_db(self, cursor: Cursor, version: int, /) -> None:
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
            self.set_schema_version(cursor, 1)
        if version < 2:
            cursor.execute(
                "CREATE TABLE if not exists ToRemoteScan ("
                "    path STRING NOT NULL,"
                "    PRIMARY KEY (path)"
                ")"
            )
            self.set_schema_version(cursor, 2)
        if version < 3:
            self._migrate_state(cursor)
            self.set_schema_version(cursor, 3)
        if version < 4:
            self._migrate_state(cursor)
            cursor.execute("UPDATE States SET creation_date = last_remote_updated")
            self.set_schema_version(cursor, 4)
        if version < 5:
            self._create_transfer_tables(cursor)
            self.set_schema_version(cursor, 5)
        if version < 6:
            # Add the *filesize* field to the Downloads table,
            # used to display download metrics in the systray menu.
            self._append_to_table(
                cursor, "Downloads", ("filesize", "INTEGER", "DEFAULT", "0")
            )
            self.set_schema_version(cursor, 6)
        if version < 7:
            # Remove the no-more-used *idx* field of Uploads.
            # SQLite does not support column deletion, we need to recreate
            # a new one and insert back old data.

            # Make a copy of the table
            cursor.execute("ALTER TABLE Uploads RENAME TO Uploads_backup;")

            # Create again the table, with up-to-date columns
            self._create_transfer_tables(cursor)

            # Insert back old uploads with up-to-date fields
            for upload in cursor.execute("SELECT * FROM Uploads_backup"):
                # With the new Amazon S3 capability, the *batch* filed needs to be updated.
                # It was a simple batch ID (str), this is now batch details (a serialized dict).
                batch = json.dumps(
                    {"batchId": upload["batch"], "upload_idx": upload["idx"]}
                )
                cursor.execute(
                    "UPDATE Uploads SET batch = ? WHERE uid = ?", (batch, upload["uid"])
                )

            # Delete the table
            cursor.execute("DROP TABLE Uploads_backup;")

            self.set_schema_version(cursor, 7)
        if version < 8:
            if WINDOWS:
                # Update the tmpname column to add the long path prefix on Windows
                cursor.execute(
                    "UPDATE Downloads"
                    "   SET tmpname = '//?/' || tmpname"
                    " WHERE tmpname NOT LIKE '//?/%'"
                )
            self.set_schema_version(cursor, 8)

        if version < 9:
            # Change Downloads.path and Uploads.path database field types.
            # SQLite does not support column type update, we need to recreate
            # a new one and insert back old data.

            # Make a copy of the Upload and Download table
            cursor.execute("ALTER TABLE Uploads RENAME TO Uploads_backup;")
            cursor.execute("ALTER TABLE Downloads RENAME TO Downloads_backup;")

            # Create again the tables, with up-to-date columns
            self._create_transfer_tables(cursor)

            # Append eventual missing fields added in later migrations.
            self._append_to_table(
                cursor,
                "Uploads_backup",
                ("is_direct_transfer", "INTEGER", "DEFAULT", "0"),
            )
            self._append_to_table(
                cursor,
                "Uploads_backup",
                ("remote_parent_path", "VARCHAR", "DEFAULT", "NULL"),
            )
            self._append_to_table(
                cursor,
                "Uploads_backup",
                ("remote_parent_ref", "VARCHAR", "DEFAULT", "NULL"),
            )
            self._append_to_table(
                cursor, "Uploads_backup", ("filesize", "INTEGER", "DEFAULT", "0")
            )

            # Insert back old datas with up-to-date fields types
            sql = (
                "INSERT INTO Uploads"
                " (uid, path, status, engine, is_direct_edit, progress, doc_pair, batch, chunk_size)"
                " VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)"
            )
            for row in cursor.execute("SELECT * FROM Uploads_backup"):
                upload_values = (
                    row.uid,
                    row.path,
                    row.status,
                    row.engine,
                    row.is_direct_edit,
                    row.is_direct_transfer,
                    row.progress,
                    row.filesize,
                    row.doc_pair,
                    row.batch,
                    row.chunk_size,
                    row.remote_parent_path,
                    row.remote_parent_ref,
                )
                cursor.execute(sql, upload_values)

            sql = (
                "INSERT INTO Downloads"
                " (uid, path, status, engine, is_direct_edit, progress, filesize, doc_pair, tmpname, url)"
                " VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)"
            )
            for row in cursor.execute("SELECT * FROM Downloads_backup"):
                download_values = (
                    row.uid,
                    row.path,
                    row.status,
                    row.engine,
                    row.is_direct_edit,
                    row.progress,
                    row.filesize,
                    row.doc_pair,
                    row.tmpname,
                    row.url,
                )
                cursor.execute(sql, download_values)

            # Delete the backup tables
            cursor.execute("DROP TABLE Uploads_backup;")
            cursor.execute("DROP TABLE Downloads_backup;")

            self.set_schema_version(cursor, 9)

        if version < 10:
            # Remove States with bad digests.
            # Remove Downloads linked to these States.

            for doc_pair in cursor.execute(
                "SELECT * FROM States WHERE remote_digest IS NOT NULL;"
            ):
                digest = doc_pair["remote_digest"]
                if not get_digest_algorithm(digest):
                    remote_ref = doc_pair["remote_ref"]
                    id = doc_pair["id"]

                    download = self.get_download(doc_pair=id)
                    if download and download.tmpname:
                        # Clean-up the TMP file
                        with suppress(OSError):
                            shutil.rmtree(download.tmpname.parent)
                    cursor.execute("DELETE FROM Downloads WHERE doc_pair = ?", (id,))

                    self.remove_state(doc_pair)
                    log.debug(
                        f"Deleted unsyncable state {id}, remote_ref={remote_ref!r}, remote_digest={digest!r}"
                    )

            self.set_schema_version(cursor, 10)

        if version < 11:
            # Add the *is_direct_transfer* field to the Uploads table,
            # used to display items in the Direct Transfer window.
            self._append_to_table(
                cursor, "Uploads", ("is_direct_transfer", "INTEGER", "DEFAULT", "0")
            )
            self.set_schema_version(cursor, 11)

        if version < 12:
            # Add *remote_parent_path* and *remote_parent_ref* fields to the Uploads table,
            # used to display items in the Direct Transfer window.
            self._append_to_table(
                cursor, "Uploads", ("remote_parent_path", "VARCHAR", "DEFAULT", "NULL")
            )
            self._append_to_table(
                cursor, "Uploads", ("remote_parent_ref", "VARCHAR", "DEFAULT", "NULL")
            )
            self.set_schema_version(cursor, 12)

        if version < 13:
            # Add the *filesize* field to the Uploads table,
            # used to display items in the Direct Transfer window.
            self._append_to_table(
                cursor, "Uploads", ("filesize", "INTEGER", "DEFAULT", "0")
            )
            self.set_schema_version(cursor, 13)

        if version < 14:
            # Add the *duplicate_behavior* field to the States table,
            # used by the Direct Transfer feature.
            self._append_to_table(
                cursor,
                "States",
                ("duplicate_behavior", "VARCHAR", "DEFAULT", "'create'"),
            )
            self.set_schema_version(cursor, 14)

        if version < 15:
            # Add the *session* field to the States table.
            # Create the Session table and init with existing transfers.
            # Used by the Direct Transfer feature.
            self._create_sessions_table(cursor)
            self._append_to_table(
                cursor,
                "States",
                ("session", "INTEGER", "DEFAULT", "0"),
            )
            dt_count = self.get_dt_items_count()
            if dt_count > 0:
                cursor.execute(
                    "INSERT INTO Sessions (total, status) " "VALUES (?, ?)",
                    (dt_count, TransferStatus.ONGOING.value),
                )
            cursor.execute(
                f"UPDATE States SET session = {cursor.lastrowid} WHERE local_state = 'direct'"
            )
            self.set_schema_version(cursor, 15)

        if version < 16:
            # Add the *engine* field to the Sessions table
            # Add the *created_on* field to the Sessions table
            # Add the *completed_on* field to the Sessions table
            # Add the *description* field to the Sessions table
            # Add the *planned_items* field to the Sessions table
            # used by the Direct Transfer feature.

            self._append_to_table(
                cursor,
                "Sessions",
                ("engine", "VARCHAR", "DEFAULT", f"'{self._engine_uid}'"),
            )
            self._append_to_table(
                cursor,
                "Sessions",
                ("created_on", "DATE"),
            )
            self._append_to_table(
                cursor,
                "Sessions",
                ("completed_on", "DATETIME"),
            )
            self._append_to_table(
                cursor,
                "Sessions",
                ("description", "VARCHAR", "DEFAULT", "''"),
            )
            self._append_to_table(
                cursor,
                "Sessions",
                ("planned_items", "INTEGER"),
            )
            cursor.execute(
                "UPDATE Sessions SET created_on = CURRENT_TIMESTAMP, planned_items = total"
            )
            self.set_schema_version(cursor, 16)

        if version < 17:
            # Remove the UNIQUE constraint on paths for Uploads table.

            # Copy the Uploads and Downloads table.
            cursor.execute("ALTER TABLE Uploads RENAME TO Uploads_backup;")
            cursor.execute("ALTER TABLE Downloads RENAME TO Downloads_backup;")

            # Create again the table, with up-to-date column
            self._create_transfer_tables(cursor)

            # Insert back old datas with up-to-date constraints
            sql = (
                "INSERT INTO Uploads"
                " (uid, path, status, engine, is_direct_edit, is_direct_transfer, progress, filesize, doc_pair,"
                "  batch, chunk_size, remote_parent_path, remote_parent_ref)"
                " VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)"
            )
            for row in cursor.execute("SELECT * FROM Uploads_backup"):
                upload_values = (
                    row.uid,
                    row.path,
                    row.status,
                    row.engine,
                    row.is_direct_edit,
                    row.is_direct_transfer,
                    row.progress,
                    row.filesize,
                    row.doc_pair,
                    row.batch,
                    row.chunk_size,
                    row.remote_parent_path,
                    row.remote_parent_ref,
                )
                cursor.execute(sql, upload_values)

            sql = (
                "INSERT INTO Downloads"
                " (uid, path, status, engine, is_direct_edit, progress, filesize, doc_pair, tmpname, url)"
                " VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)"
            )
            for row in cursor.execute("SELECT * FROM Downloads_backup"):
                download_values = (
                    row.uid,
                    row.path,
                    row.status,
                    row.engine,
                    row.is_direct_edit,
                    row.progress,
                    row.filesize,
                    row.doc_pair,
                    row.tmpname,
                    row.url,
                )
                cursor.execute(sql, download_values)

            # Delete the backup tables
            cursor.execute("DROP TABLE Uploads_backup;")
            cursor.execute("DROP TABLE Downloads_backup;")

            self.set_schema_version(cursor, 17)

        if version < 18:
            # Replace all backslashes from local paths in States.
            if WINDOWS:
                cursor.execute(
                    "UPDATE States SET local_path = REPLACE(local_path, '\\', '/'),"
                    " local_parent_path = REPLACE(local_parent_path, '\\', '/')"
                )

            self.set_schema_version(cursor, 18)

        if version < 19:
            # Create the SessionItems table.

            self._create_session_items_table(cursor)
            self.set_schema_version(cursor, 19)

        if version < 20:
            # Add the *request_uid* field to the Uploads table
            self._append_to_table(
                cursor, "Uploads", ("request_uid", "VARCHAR", "DEFAULT", "NULL")
            )
            self.set_schema_version(cursor, 20)

        if version < 21:
            self.store_int(SCHEMA_VERSION, 21)
            self.set_schema_version(cursor, 21)

    def _create_table(
        self, cursor: Cursor, name: str, /, *, force: bool = False
    ) -> None:
        if name == "States":
            self._create_state_table(cursor, force=force)
        else:
            super()._create_table(cursor, name, force=force)

    @staticmethod
    def _create_transfer_tables(cursor: Cursor, /) -> None:
        cursor.execute(
            "CREATE TABLE if not exists Downloads ("
            "    uid            INTEGER     NOT NULL,"
            "    path           VARCHAR     UNIQUE,"
            "    status         INTEGER,"
            "    engine         VARCHAR     DEFAULT NULL,"
            "    is_direct_edit INTEGER     DEFAULT 0,"
            "    progress       REAL,"
            "    filesize       INTEGER     DEFAULT 0,"
            "    doc_pair       INTEGER     UNIQUE,"
            "    tmpname        VARCHAR,"
            "    url            VARCHAR,"
            "    PRIMARY KEY (uid)"
            ")"
        )
        cursor.execute(
            "CREATE TABLE if not exists Uploads ("
            "    uid                INTEGER     NOT NULL,"
            "    path               VARCHAR,"
            "    status             INTEGER,"
            "    engine             VARCHAR     DEFAULT NULL,"
            "    is_direct_edit     INTEGER     DEFAULT 0,"
            "    is_direct_transfer INTEGER     DEFAULT 0,"
            "    progress           REAL,"
            "    filesize           INTEGER     DEFAULT 0,"
            "    doc_pair           INTEGER     UNIQUE,"
            "    batch              VARCHAR,"
            "    chunk_size         INTEGER,"
            "    remote_parent_path VARCHAR     DEFAULT NULL,"
            "    remote_parent_ref  VARCHAR     DEFAULT NULL,"
            "    request_uid        VARCHAR     DEFAULT NULL,"
            "    PRIMARY KEY (uid)"
            ")"
        )

    @staticmethod
    def _create_sessions_table(cursor: Cursor, /) -> None:
        """Create the Sessions table."""
        cursor.execute(
            "CREATE TABLE if not exists Sessions ("
            "    uid            INTEGER     NOT NULL,"
            "    status         INTEGER,"
            "    remote_ref     VARCHAR,"
            "    remote_path    VARCHAR,"
            "    uploaded       INTEGER     DEFAULT (0),"
            "    total          INTEGER,"
            "    engine         VARCHAR     DEFAULT '',"
            "    created_on     DATETIME    NOT NULL    DEFAULT CURRENT_TIMESTAMP,"
            "    completed_on   DATETIME,"
            "    description    VARCHAR     DEFAULT '',"
            "    planned_items  INTEGER,"
            "    PRIMARY KEY (uid)"
            ")"
        )

    @staticmethod
    def _create_session_items_table(cursor: Cursor, /) -> None:
        """Create the SessionItems table."""
        cursor.execute(
            "CREATE TABLE if not exists SessionItems ("
            "    session_id     INTEGER     NOT NULL,"
            "    data           VARCHAR     NOT NULL)"
        )

    @staticmethod
    def _create_state_table(cursor: Cursor, /, *, force: bool = False) -> None:
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
            "    duplicate_behavior      VARCHAR    DEFAULT ('create'),"
            "    session                 INTEGER    DEFAULT (0),"
            "    PRIMARY KEY (id),"
            "    UNIQUE(remote_ref, remote_parent_ref),"
            "    UNIQUE(remote_ref, local_path))"
        )

    def _append_to_table(
        self, cursor: Cursor, table: str, field_data: Tuple[str, ...], /
    ) -> None:
        """Create the new field/column if it does not already exist."""
        field = field_data[0]
        if field in self._get_columns(cursor, table):
            return

        # Add the missing field
        cursor.execute(f"ALTER TABLE {table} ADD COLUMN {' '.join(field_data)};")

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
        self._create_transfer_tables(cursor)
        self._create_sessions_table(cursor)
        self._create_session_items_table(cursor)

    def acquire_state(
        self, thread_id: Optional[int], row_id: int, /
    ) -> Optional[DocPair]:
        if thread_id is not None and self.acquire_processor(thread_id, row_id):
            # Avoid any lock for this call by using the write connection
            try:
                return self.get_state_from_id(row_id, from_write=True)
            except Exception:
                self.release_processor(thread_id)
                raise
        raise OperationalError("Cannot acquire")

    def release_state(self, thread_id: Optional[int], /) -> None:
        if thread_id is None:
            return
        try:
            self.release_processor(thread_id)
        except OperationalError:
            log.warning(f"Cannot release processor {thread_id}", exc_info=True)

    def release_processor(self, processor_id: int, /) -> bool:
        with self.lock:
            c = self._get_write_connection().cursor()
            # TO_REVIEW Might go back to primary key id
            c.execute(
                "UPDATE States  SET processor = 0 WHERE processor = ?", (processor_id,)
            )
            log.debug(f"Released processor {processor_id}")
            return bool(c.rowcount > 0)

    def acquire_processor(self, thread_id: int, row_id: int, /) -> bool:
        with self.lock:
            c = self._get_write_connection().cursor()
            c.execute(
                "UPDATE States"
                "   SET processor = ?"
                " WHERE id = ?"
                "   AND processor IN (0, ?)",
                (thread_id, row_id, thread_id),
            )
            return bool(c.rowcount == 1)

    def _reinit_states(self, cursor: Cursor, /) -> None:
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
        with self.lock:
            con = self._get_write_connection()
            c = con.cursor()
            self._reinit_states(c)
            con.execute("VACUUM")

    def reinit_processors(self) -> None:
        with self.lock:
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

    def delete_remote_state(self, doc_pair: DocPair, /) -> None:
        with self.lock:
            c = self._get_write_connection().cursor()
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

    def delete_local_state(self, doc_pair: DocPair, /) -> None:
        try:
            with self.lock:
                c = self._get_write_connection().cursor()
                sql = "UPDATE States SET local_state = 'deleted', pair_state = 'locally_deleted'"
                c.execute(f"{sql} WHERE id = ?", (doc_pair.id,))
                if doc_pair.folderish:
                    c.execute(f"{sql} {self._get_recursive_condition(doc_pair)}")
        finally:
            if self.queue_manager:
                self.queue_manager.interrupt_processors_on(
                    doc_pair.local_path, exact_match=False
                )

            # Only queue parent
            self._queue_pair_state(
                int(doc_pair.id), bool(doc_pair.folderish), "locally_deleted"
            )

    def insert_local_state(
        self,
        info: FileInfo,
        parent_path: Optional[Path],
        /,
    ) -> int:
        digest = None
        if not info.folderish:
            if info.size >= Options.big_file * 1024 * 1024:
                # We can't compute the digest of big files now as it will
                # be done later when the entire file is fully copied.
                # For instance, on my machine (32GB RAM, 8 cores, Intel NUC)
                # it takes 23 minutes for 100 GB and 7 minute for 50 GB.
                # This is way too much effort to compute it several times.
                digest = UNACCESSIBLE_HASH
            else:
                digest = info.get_digest()

        with self.lock:
            c = self._get_write_connection().cursor()
            pair_state = PAIR_STATES[("created", "unknown")]

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
            row_id: int = c.lastrowid
            parent = (
                c.execute(
                    "SELECT * FROM States WHERE local_path = ?", (parent_path,)
                ).fetchone()
                if parent_path
                else None
            )

            # Don't queue if parent is not yet created
            if (parent is None and parent_path is None) or (
                parent and parent.pair_state != "locally_created"
            ):
                self._queue_pair_state(row_id, info.folderish, pair_state)

            self._items_count += 1

            return row_id

    def plan_many_direct_transfer_items(
        self, items: Tuple[Any, ...], session: int, /
    ) -> int:
        """
        Add new Direct Transfer *items*.
        This is an optimized method that will insert all *items* in one go.
        It is recommended to now exceed 500 *items* for each call of this method.
        """
        with self.lock:
            c = self._get_write_connection().cursor()

            # This will be needed later
            sql = "SELECT max(ROWID) FROM States"
            current_max_row_id = c.execute(sql).fetchone()[0] or 0

            # Insert data in one shot
            query = (
                "INSERT INTO States "
                "(local_path, local_parent_path, local_name, folderish, size, "
                "remote_parent_path, remote_parent_ref, duplicate_behavior, "
                "local_state, remote_state, pair_state, session)"
                f"VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'direct', ?, 'direct_transfer', {session})"
            )
            c.executemany(query, items)
            return current_max_row_id

    def queue_many_direct_transfer_items(self, current_max_row_id: int, /) -> None:
        """Add new Direct Transfer pairs to the queue."""
        if not self.queue_manager:
            return

        with self.lock:
            c = self._get_write_connection().cursor()

            # Send new pairs into the queue manager
            query = "SELECT * FROM States WHERE ROWID > ? AND local_state = 'direct' ORDER BY ROWID ASC"
            for new_pair in c.execute(query, (current_max_row_id,)):
                self.queue_manager.push(new_pair)
                self._items_count += 1

    def get_last_files(
        self, number: int, /, *, direction: str = "", duration: int = None
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

    def get_last_files_count(self, *, direction: str = "", duration: int = None) -> int:
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
        return "pair_state NOT IN ('synchronized', 'unsynchronized')"

    def register_queue_manager(self, manager: "QueueManager", /) -> None:
        """Register the queue manager and add all *pairs* to handle into the queue."""

        with self.lock:
            self.queue_manager = manager

            c = self._get_write_connection().cursor()

            # Order by path to be sure to process parents before children.
            # Note: filter out Direct Transfer pairs when the associated session is not ongoing
            #       (it will generate potentially a lot of work for nothing as such pairs
            #        will be skipped in the Processor then)
            query = (
                "SELECT * FROM States"
                f"   WHERE {self._get_to_sync_condition()}"
                "      AND (session = 0"  # Pure synchronization transfers
                "           OR session IN (SELECT uid FROM Sessions WHERE status = ?))"
                " ORDER BY local_path ASC"
            )
            pairs = c.execute(query, (TransferStatus.ONGOING.value,)).fetchall()

            folders = {}
            for pair in pairs:
                # Add all the folders
                if pair.folderish:
                    folders[pair.local_path] = True
                if pair.local_parent_path not in folders:
                    self.queue_manager.push_ref(
                        pair.id, pair.folderish, pair.pair_state
                    )

    def _queue_pair_state(
        self, row_id: int, folderish: bool, pair_state: str, /, *, pair: DocPair = None
    ) -> None:
        if self.queue_manager and pair_state not in {"synchronized", "unsynchronized"}:
            if pair_state == "conflicted":
                log.debug(f"Emit newConflict with: {row_id}, pair={pair!r}")
                self.newConflict.emit(row_id)
            else:
                log.debug(f"Push to queue: {pair_state}, pair={pair!r}")
                self.queue_manager.push_ref(row_id, folderish, pair_state)
        else:
            log.debug(f"Will not push pair: {pair_state}, pair={pair!r}")

    def _get_pair_state(self, row: DocPair, /) -> str:
        state = PAIR_STATES.get((row.local_state, row.remote_state))
        if state is None:
            raise UnknownPairState(row.local_state, row.remote_state)
        return state

    def update_last_transfer(self, row_id: int, transfer: str, /) -> None:
        with self.lock:
            c = self._get_write_connection().cursor()
            c.execute(
                "UPDATE States SET last_transfer = ? WHERE id = ?", (transfer, row_id)
            )

    def update_remote_name(self, row_id: int, remote_name: str, /) -> None:
        with self.lock:
            c = self._get_write_connection().cursor()
            c.execute(
                "UPDATE States SET remote_name = ? WHERE id = ?", (remote_name, row_id)
            )

    def get_dedupe_pair(
        self, name: str, parent: str, row_id: int, /
    ) -> Optional[DocPair]:
        c = self._get_read_connection().cursor()
        doc_pair: Optional[DocPair] = c.execute(
            "SELECT *"
            "  FROM States"
            " WHERE id != ?"
            "   AND local_name = ?"
            "   AND remote_parent_ref = ?",
            (row_id, name, parent),
        ).fetchone()
        return doc_pair

    def update_local_state(
        self,
        row: DocPair,
        info: FileInfo,
        /,
        *,
        versioned: bool = True,
        queue: bool = True,
    ) -> None:
        row.pair_state = self._get_pair_state(row)
        log.debug(f"Updating local state for row={row!r} with info={info!r}")

        version = ""
        if versioned:
            version = ", version = version + 1"
            log.debug(f"Increasing version to {row.version + 1} for pair {row!r}")

        with self.lock:
            parent_path = info.path.parent
            c = self._get_write_connection().cursor()
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
                if not (parent or parent_path) or (
                    parent and parent.local_state != "created"
                ):
                    self._queue_pair_state(
                        row.id, info.folderish, row.pair_state, pair=row
                    )

    def update_local_modification_time(self, row: DocPair, info: FileInfo, /) -> None:
        with self.lock:
            c = self._get_write_connection().cursor()
            c.execute(
                "UPDATE States SET last_local_updated = ? WHERE id = ?",
                (info.last_modification_time, row.id),
            )

    def get_valid_duplicate_file(self, digest: str, /) -> Optional[DocPair]:
        """Find a file already synced with the same digest as the given *digest*."""
        c = self._get_read_connection().cursor()
        doc_pair: Optional[DocPair] = c.execute(
            "SELECT *"
            "  FROM States"
            " WHERE local_digest = ?"
            "   AND remote_digest = ?"
            "   AND pair_state = 'synchronized'",
            (digest, digest),
        ).fetchone()
        return doc_pair

    def get_remote_descendants(self, path: str, /) -> DocPairs:
        c = self._get_read_connection().cursor()
        return c.execute(
            "SELECT * FROM States WHERE remote_parent_path LIKE ?", (f"{path}%",)
        ).fetchall()

    def get_remote_descendants_from_ref(self, ref: str, /) -> DocPairs:
        c = self._get_read_connection().cursor()
        return c.execute(
            "SELECT * FROM States WHERE remote_parent_path LIKE ?", (f"%{ref}%",)
        ).fetchall()

    def get_remote_children(self, ref: str, /) -> DocPairs:
        c = self._get_read_connection().cursor()
        return c.execute(
            "SELECT * FROM States WHERE remote_parent_ref = ?", (ref,)
        ).fetchall()

    def get_new_remote_children(self, ref: str, /) -> DocPairs:
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

    def get_error_count(self, *, threshold: int = 3) -> int:
        return self.get_count(f"error_count > {threshold}")

    def get_syncing_count(self, *, threshold: int = 3) -> int:
        count = self.get_count(
            "     pair_state != 'synchronized' "
            " AND pair_state != 'conflicted' "
            " AND pair_state != 'unsynchronized' "
            f"AND error_count < {threshold}"
        )
        if self._items_count != count:
            log.debug(
                f"Cache syncing count updated from {self._items_count} to {count}"
            )
            self._items_count = count
        return count

    def get_sync_count(self, *, filetype: str = None) -> int:
        conditions = {"file": "AND folderish = 0", "folder": "AND folderish = 1"}
        condition = conditions.get(filetype or "", "")
        return self.get_count(f"pair_state = 'synchronized' {condition}")

    def get_dt_items_count(self) -> int:
        return self.get_count("local_state = 'direct'")

    def get_count(self, condition: str, *, table: str = "States") -> int:
        query = f"SELECT COUNT(*) as count FROM {table}"
        if condition:
            query = f"{query} WHERE {condition}"
        c = self._get_read_connection().cursor()
        return int(c.execute(query).fetchone().count)

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

    def get_errors(self, *, limit: int = 3) -> DocPairs:
        c = self._get_read_connection().cursor()
        return c.execute(
            "SELECT * FROM States WHERE error_count > ?", (limit,)
        ).fetchall()

    def get_local_children(self, path: Path, /) -> DocPairs:
        c = self._get_read_connection().cursor()
        return c.execute(
            "SELECT * FROM States WHERE local_parent_path = ?", (path,)
        ).fetchall()

    def get_states_from_partial_local(
        self, path: Path, /, *, strict: bool = True
    ) -> DocPairs:
        c = self._get_read_connection().cursor()

        local_path = adapt_path(path)
        if local_path[-1] != "/" and strict:
            local_path += "/"
        local_path += "%"

        return c.execute(
            "SELECT * FROM States WHERE local_path LIKE ?", (local_path,)
        ).fetchall()

    def get_first_state_from_partial_remote(self, ref: str, /) -> Optional[DocPair]:
        c = self._get_read_connection().cursor()
        doc_pair: DocPair = c.execute(
            "SELECT *"
            "  FROM States"
            " WHERE remote_ref LIKE ? "
            " ORDER BY last_remote_updated ASC"
            " LIMIT 1",
            (f"%{ref}",),
        ).fetchone()
        return doc_pair

    def get_normal_state_from_remote(self, ref: str, /) -> Optional[DocPair]:
        # TODO Select the only states that is not a collection
        states = self.get_states_from_remote(ref)
        return states[0] if states else None

    def get_state_from_remote_with_path(
        self, ref: str, path: str, /
    ) -> Optional[DocPair]:
        # remote_path root is empty, should refactor this
        path = "" if path == "/" else path
        c = self._get_read_connection().cursor()
        doc_pair: Optional[DocPair] = c.execute(
            "SELECT *"
            "  FROM States"
            " WHERE remote_ref = ?"
            "   AND remote_parent_path = ?",
            (ref, path),
        ).fetchone()
        return doc_pair

    def get_states_from_remote(self, ref: str, /) -> DocPairs:
        c = self._get_read_connection().cursor()
        return c.execute("SELECT * FROM States WHERE remote_ref = ?", (ref,)).fetchall()

    def get_state_from_id(
        self, row_id: int, /, *, from_write: bool = False
    ) -> Optional[DocPair]:
        if from_write:
            self.lock.acquire()
            c = self._get_write_connection().cursor()
        else:
            c = self._get_read_connection().cursor()

        try:
            doc_pair: Optional[DocPair] = c.execute(
                "SELECT * FROM States WHERE id = ?", (row_id,)
            ).fetchone()
            return doc_pair
        finally:
            if from_write:
                self.lock.release()

    def _get_recursive_condition(self, doc_pair: DocPair, /) -> str:
        path = self._escape(adapt_path(doc_pair.local_path))
        res = (
            f" WHERE (local_parent_path LIKE '{path}/%'"
            f"        OR local_parent_path = '{path}')"
        )
        if doc_pair.remote_ref:
            path = self._escape(f"{doc_pair.remote_parent_path}/{doc_pair.remote_ref}")
            res += f" AND remote_parent_path LIKE '{path}%'"
        return res

    def _get_recursive_remote_condition(self, doc_pair: DocPair, /) -> str:
        path = self._escape(f"{doc_pair.remote_parent_path}/{doc_pair.remote_ref}")
        return (
            f" WHERE remote_parent_path LIKE '{path}/%'"
            f"    OR remote_parent_path = '{path}'"
        )

    def replace_local_paths(self, old_path: Path, new_path: Path) -> None:
        """
        Replace all local path occurrences of *old_path* to *new_path*.
        Paths are modified to only impact exactly a full folder path
        (including starting and ending slashes).
        """

        old = f"{adapt_path(old_path)}/"
        new = f"{adapt_path(new_path)}/"
        log.debug(f"Updating all local paths from {old!r} to {new!r}")

        with self.lock:
            c = self._get_write_connection().cursor()
            query = (
                "UPDATE States"
                "  SET local_parent_path = replace(local_parent_path, ?, ?),"
                "      local_path = replace(local_path, ? , ?) "
                "WHERE local_parent_path LIKE ? OR local_path LIKE ?"
            )
            c.execute(query, (old, new, old, new, f"{old}%", f"{old}%"))

    def update_remote_parent_path(self, doc_pair: DocPair, new_path: str, /) -> None:
        with self.lock:
            c = self._get_write_connection().cursor()
            if doc_pair.folderish:
                count = len(
                    self._escape(f"{doc_pair.remote_parent_path}/{doc_pair.remote_ref}")
                )
                path = self._escape(f"{new_path}/{doc_pair.remote_ref}")
                query = (
                    "UPDATE States"
                    f"  SET remote_parent_path = '{path}'"
                    f"      || substr(remote_parent_path, {count + 1})"
                    + self._get_recursive_remote_condition(doc_pair)
                )

                log.debug(f"Update remote_parent_path {query!r}")
                c.execute(query)
            c.execute(
                "UPDATE States SET remote_parent_path = ? WHERE id = ?",
                (new_path, doc_pair.id),
            )

    def update_local_parent_path(
        self, doc_pair: DocPair, new_name: str, new_path: Path, /
    ) -> None:
        with self.lock:
            c = self._get_write_connection().cursor()
            if doc_pair.folderish:
                path = self._escape(adapt_path(new_path / new_name))
                count = len(self._escape(adapt_path(doc_pair.local_path)))
                query = (
                    "UPDATE States"
                    f"  SET local_parent_path = '{path}'"
                    f"      || substr(local_parent_path, {count + 2}),"
                    f"         local_path = '{path}'"
                    f"      || substr(local_path, {count + 2}) "
                    + self._get_recursive_condition(doc_pair)
                )
                c.execute(query)
            # Don't need to update the path as it is refresh later
            c.execute(
                "UPDATE States SET local_parent_path = ? WHERE id = ?",
                (new_path, doc_pair.id),
            )

    def update_remote_parent_path_dt(
        self,
        local_parent_path: Path,
        remote_parent_path: str,
        remote_parent_ref: str,
        /,
    ) -> None:
        """
        Used in Direct Transfer to update remote_parent_path and remote_state of a folder's children.
        """
        with self.lock:
            c = self._get_write_connection().cursor()
            doc_pairs = c.execute(
                "SELECT * FROM States WHERE local_state = 'direct' AND remote_state = 'todo'"
                " AND local_parent_path = ?",
                (local_parent_path,),
            ).fetchall()

            c.execute(
                "UPDATE States SET remote_state = 'unknown', remote_parent_path = ?,"
                " remote_parent_ref = ?, processor = 0"
                " WHERE local_state = 'direct' AND remote_state = 'todo' AND local_parent_path = ?",
                (remote_parent_path, remote_parent_ref, local_parent_path),
            )

            for doc_pair in doc_pairs:
                doc_pair.remote_parent_path = remote_parent_path
                doc_pair.remote_state = "unknown"
                self.queue_manager.push(doc_pair)  # type: ignore

    def mark_descendants_remotely_created(self, doc_pair: DocPair, /) -> None:
        with self.lock:
            c = self._get_write_connection().cursor()
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

    def remove_state(
        self,
        doc_pair: DocPair,
        /,
        *,
        remote_recursion: bool = False,
        recursive: bool = True,
    ) -> None:
        with self.lock:
            c = self._get_write_connection().cursor()
            c.execute("DELETE FROM States WHERE id = ?", (doc_pair.id,))
            if recursive and doc_pair.folderish:
                if remote_recursion:
                    condition = self._get_recursive_remote_condition(doc_pair)
                else:
                    condition = self._get_recursive_condition(doc_pair)
                c.execute("DELETE FROM States " + condition)

    def remove_state_children(
        self, doc_pair: DocPair, /, *, remote_recursion: bool = False
    ) -> None:
        with self.lock:
            c = self._get_write_connection().cursor()
            if remote_recursion:
                condition = self._get_recursive_remote_condition(doc_pair)
            else:
                condition = self._get_recursive_condition(doc_pair)
            c.execute("DELETE FROM States " + condition)

    def get_state_from_local(self, path: Path, /) -> Optional[DocPair]:
        c = self._get_read_connection().cursor()
        doc_pair: Optional[DocPair] = c.execute(
            "SELECT * FROM States WHERE local_path = ?", (path,)
        ).fetchone()
        return doc_pair

    def insert_remote_state(
        self,
        info: RemoteFileInfo,
        remote_parent_path: str,
        local_path: Path,
        local_parent_path: Path,
        /,
    ) -> int:
        with self.lock:
            c = self._get_write_connection().cursor()
            pair_state = PAIR_STATES[("unknown", "created")]
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
            row_id: int = c.lastrowid

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

    def queue_children(self, row: DocPair, /) -> None:
        with self.lock:
            c = self._get_write_connection().cursor()
            children: List[DocPair] = c.execute(
                "SELECT *"
                "  FROM States"
                " WHERE remote_parent_ref = ?"
                "    OR local_parent_path = ?"
                "   AND " + self._get_to_sync_condition(),
                (row.remote_ref, row.local_path),
            ).fetchall()
            if children:
                log.info(f"Queuing {len(children)} children of {row}")
                for child in children:
                    self._queue_pair_state(child.id, child.folderish, child.pair_state)

    def increase_error(
        self, row: DocPair, error: str, /, *, details: str = None, incr: int = 1
    ) -> None:
        with self.lock:
            error_date = datetime.utcnow()
            c = self._get_write_connection().cursor()
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

    def reset_error(self, row: DocPair, /, *, last_error: str = None) -> None:
        with self.lock:
            c = self._get_write_connection().cursor()
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

    def _force_sync(self, row: DocPair, local: str, remote: str, pair: str, /) -> bool:
        with self.lock:
            c = self._get_write_connection().cursor()
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

    def force_remote(self, row: DocPair, /) -> bool:
        return self._force_sync(row, "synchronized", "modified", "remotely_modified")

    def force_remote_creation(self, row: DocPair, /) -> bool:
        return self._force_sync(row, "unknown", "created", "remotely_created")

    def force_local(self, row: DocPair, /) -> bool:
        return self._force_sync(row, "resolved", "unknown", "locally_resolved")

    def set_conflict_state(self, row: DocPair, /) -> bool:
        with self.lock:
            c = self._get_write_connection().cursor()
            c.execute(
                "UPDATE States SET pair_state = ? WHERE id = ?", ("conflicted", row.id)
            )
            self.newConflict.emit(row.id)
            if c.rowcount == 1:
                self._items_count -= 1
                return True
        return False

    def unsynchronize_state(
        self, row: DocPair, last_error: str, /, *, ignore: bool = False
    ) -> None:
        local_state = "local_state = 'unsynchronized'," if ignore else ""
        with self.lock:
            c = self._get_write_connection().cursor()
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

    def unset_unsychronised(self, row: DocPair, /) -> None:
        """Used to unfilter documents that were flagged read-only in a previous sync.
        All children will be locally rescanned to keep synced with the server."""
        row.local_state = "created"
        row.remote_state = "unknown"
        row.pair_state = self._get_pair_state(row)
        with self.lock:
            c = self._get_write_connection().cursor()
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
                    f"{adapt_path(row.local_path)}%",
                ),
            )

    def synchronize_state(
        self, row: DocPair, /, *, version: int = None, dynamic_states: bool = False
    ) -> bool:
        if version is None:
            version = row.version
        log.debug(
            f"Try to synchronize state for [local_path={row.local_path!r}, "
            f"remote_name={row.remote_name!r}, version={row.version}] "
            f"with version={version} and dynamic_states={dynamic_states!r}"
        )

        # Set default states to synchronized, if wanted
        if not dynamic_states:
            row.local_state = row.remote_state = "synchronized"
        row.pair_state = self._get_pair_state(row)

        with self.lock:
            c = self._get_write_connection().cursor()
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
            result = bool(c.rowcount == 1)

            # Retry without version for folder
            if not result and row.folderish:
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
            result = bool(c.rowcount == 1)

            if not result:
                log.debug(f"Was not able to synchronize state: {row!r}")
                row2: DocPair = c.execute(
                    "SELECT * FROM States WHERE id = ?", (row.id,)
                ).fetchone()
                if row2 is None:
                    log.debug("No more row")
                else:
                    log.debug(f"Current row={row2!r} (version={row2.version!r})")
                log.debug(f"Previous row={row!r} (version={row.version!r})")
            elif row.folderish:
                self.queue_children(row)

            return result

    def update_remote_state(
        self,
        row: DocPair,
        info: RemoteFileInfo,
        /,
        *,
        remote_parent_path: str = None,
        versioned: bool = True,
        queue: bool = True,
        force_update: bool = False,
        no_digest: bool = False,
    ) -> bool:
        row.pair_state = self._get_pair_state(row)
        if remote_parent_path is None:
            remote_parent_path = row.remote_parent_path

        # Check if it really needs an update
        if (
            row.remote_ref == info.uid
            and row.remote_parent_ref == info.parent_uid
            and row.remote_parent_path == remote_parent_path
            and row.remote_name == info.name
            and row.remote_can_rename == info.can_rename
            and row.remote_can_delete == info.can_delete
            and row.remote_can_update == info.can_update
            and row.remote_can_create_child == info.can_create_child
        ):
            bname = os.path.basename(row.local_path)
            if bname == info.name or (WINDOWS and bname.strip() == info.name.strip()):
                # It looks similar
                if info.digest in (row.local_digest, row.remote_digest):
                    row.remote_state = "synchronized"
                    row.pair_state = self._get_pair_state(row)
                if info.digest == row.remote_digest and not force_update:
                    log.debug(
                        "Not updating remote state (not dirty) "
                        f"for row={row!r} with info={info!r}"
                    )
                    return False

        log.debug(
            f"Updating remote state for row={row!r} with info={info!r} "
            f"(force={force_update!r})"
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

        with self.lock:
            c = self._get_write_connection().cursor()
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

            if not no_digest and info.digest:
                query += f", remote_digest = '{self._escape(info.digest)}'"

            if versioned:
                query += ", version = version+1"
                log.debug(f"Increasing version to {row.version + 1} for pair {row!r}")

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
        return True

    def _clean_filter_path(self, path: str, /) -> str:
        if not path.endswith("/"):
            path += "/"
        return path

    def add_path_to_scan(self, path: str, /) -> None:
        path = self._clean_filter_path(path)
        with self.lock, suppress(IntegrityError):
            c = self._get_write_connection().cursor()
            # Remove any subchildren as it is gonna be scanned anyway
            c.execute("DELETE FROM ToRemoteScan WHERE path LIKE ?", (f"{path}%",))
            c.execute("INSERT INTO ToRemoteScan (path) VALUES (?)", (path,))

    def delete_path_to_scan(self, path: str, /) -> None:
        path = self._clean_filter_path(path)
        with self.lock, suppress(IntegrityError):
            c = self._get_write_connection().cursor()
            c.execute("DELETE FROM ToRemoteScan WHERE path = ?", (path,))

    def get_paths_to_scan(self) -> List[str]:
        c = self._get_read_connection().cursor()
        return [
            item.path for item in c.execute("SELECT * FROM ToRemoteScan").fetchall()
        ]

    def add_path_scanned(self, path: str, /) -> None:
        path = self._clean_filter_path(path)
        with self.lock, suppress(IntegrityError):
            c = self._get_write_connection().cursor()
            c.execute("INSERT INTO RemoteScan (path) VALUES (?)", (path,))

    def clean_scanned(self) -> None:
        with self.lock:
            c = self._get_write_connection().cursor()
            c.execute("DELETE FROM RemoteScan")

    def is_path_scanned(self, path: str, /) -> bool:
        path = self._clean_filter_path(path)
        c = self._get_read_connection().cursor()
        row = c.execute(
            "SELECT COUNT(path) FROM RemoteScan WHERE path = ? LIMIT 1", (path,)
        ).fetchone()
        return bool(row[0] > 0)

    def is_filter(self, path: str, /) -> bool:
        path = self._clean_filter_path(path)
        return any(path.startswith(_filter) for _filter in self._filters)

    def get_filters(self) -> Filters:
        c = self._get_read_connection().cursor()
        return [entry.path for entry in c.execute("SELECT * FROM Filters").fetchall()]

    def add_filter(self, path: str, /) -> None:
        if self.is_filter(path):
            return

        path = self._clean_filter_path(path)
        log.debug(f"Add filter on {path!r}")

        with self.lock:
            c = self._get_write_connection().cursor()
            # Delete any subfilters
            c.execute("DELETE FROM Filters WHERE path LIKE ?", (f"{path}%",))

            # Prevent any rescan
            c.execute("DELETE FROM ToRemoteScan WHERE path LIKE ?", (f"{path}%",))

            # Add it
            c.execute("INSERT INTO Filters (path) VALUES (?)", (path,))

            # TODO: Add this path as remotely_deleted?

            self._filters = self.get_filters()
            self.get_syncing_count()

    def remove_filter(self, path: str, /) -> None:
        path = self._clean_filter_path(path)
        log.debug(f"Remove filter on {path!r}")
        with self.lock:
            c = self._get_write_connection().cursor()
            c.execute("DELETE FROM Filters WHERE path LIKE ?", (f"{path}%",))
            self._filters = self.get_filters()
            self.get_syncing_count()

    def get_downloads(self) -> Generator[Download, None, None]:
        c = self._get_read_connection().cursor()
        for res in c.execute("SELECT * FROM Downloads").fetchall():
            try:
                status = TransferStatus(res.status)
            except ValueError:
                # Most likely a NXDRIVE-1901 case
                status = TransferStatus.DONE

            yield Download(
                res.uid,
                Path(res.path),
                status,
                res.engine,
                is_direct_edit=res.is_direct_edit,
                progress=res.progress,
                filesize=res.filesize,
                doc_pair=res.doc_pair,
                tmpname=Path(res.tmpname),
                url=res.url,
            )

    def get_uploads(self) -> Generator[Upload, None, None]:
        c = self._get_read_connection().cursor()
        for res in c.execute(
            "SELECT * FROM Uploads WHERE is_direct_transfer = 0"
        ).fetchall():
            try:
                status = TransferStatus(res.status)
            except ValueError:
                # Most likely a NXDRIVE-1901 case
                status = TransferStatus.DONE

            yield Upload(
                res.uid,
                Path(res.path),
                status,
                res.engine,
                is_direct_edit=res.is_direct_edit,
                progress=res.progress,
                filesize=res.filesize,
                doc_pair=res.doc_pair,
                batch=json.loads(res.batch),
                chunk_size=res.chunk_size or 0,
                request_uid=res.request_uid,
            )

    def get_dt_uploads(self) -> Generator[Upload, None, None]:
        """Retrieve all Direct Transfer items (only needed details)."""
        c = self._get_read_connection().cursor()
        for res in c.execute(
            "SELECT * FROM Uploads WHERE is_direct_transfer = 1"
        ).fetchall():
            yield Upload(
                res.uid,
                Path(res.path),
                TransferStatus(res.status),
                res.engine,
                batch=json.loads(res.batch),
                chunk_size=res.chunk_size or 0,
                doc_pair=res.doc_pair,
                filesize=res.filesize,
                is_direct_transfer=True,
                progress=res.progress,
                remote_parent_path=res.remote_parent_path,
                remote_parent_ref=res.remote_parent_ref,
                request_uid=res.request_uid,
            )

    def get_dt_uploads_raw(
        self, *, limit: int = 1, chunked: bool = False
    ) -> List[Dict[str, Any]]:
        """
        Retrieve all Direct Transfer items.
        Return a simple dict to improve GUI performances (instead of Upload objects).
        """
        c = self._get_read_connection().cursor()

        if chunked:
            sql = f"SELECT * FROM Uploads WHERE is_direct_transfer = 1 AND filesize > chunk_size LIMIT {limit}"
        else:
            sql = f"SELECT * FROM Uploads WHERE is_direct_transfer = 1 LIMIT {limit}"

        return [
            {
                "uid": res.uid,
                "name": basename(res.path),  # More efficient than Path(res.path).name
                "filesize": res.filesize,
                "status": TransferStatus(res.status),
                "engine": res.engine,
                "progress": res.progress or 0.0,
                "doc_pair": res.doc_pair,
                "remote_parent_path": res.remote_parent_path,
                "remote_parent_ref": res.remote_parent_ref,
            }
            for res in c.execute(sql).fetchall()
        ]

    def get_active_sessions_raw(self) -> List[Dict[str, Any]]:
        """
        Return all active Direct Transfer sessions.
        Actives Direct Transfer sessions have the status ONGOING or PAUSED.
        Return a simple dict to improve GUI performances.
        """
        c = self._get_read_connection().cursor()
        return [
            {
                "uid": res.uid,
                "status": TransferStatus(res.status),
                "remote_path": res.remote_path,
                "remote_ref": res.remote_ref,
                "uploaded": res.uploaded,
                "total": res.total,
                "engine": res.engine,
                "created_on": res.created_on,
                "completed_on": res.completed_on,
                "description": res.description,
                "planned_items": res.planned_items,
            }
            for res in c.execute(
                "SELECT * FROM Sessions WHERE status IN (?, ?)",
                (TransferStatus.ONGOING.value, TransferStatus.PAUSED.value),
            ).fetchall()
        ]

    def get_completed_sessions_raw(self, *, limit: int = 1) -> List[Dict[str, Any]]:
        """
        Return all completed Direct Transfer sessions.
        Completed Direct Transfer sessions have the status DONE or CANCELLED.
        Return a simple dict to improve GUI performances.
        """
        c = self._get_read_connection().cursor()
        return [
            {
                "uid": res.uid,
                "status": TransferStatus(res.status),
                "remote_path": res.remote_path,
                "remote_ref": res.remote_ref,
                "uploaded": res.uploaded,
                "total": res.total,
                "engine": res.engine,
                "created_on": res.created_on,
                "completed_on": res.completed_on,
                "description": res.description,
                "planned_items": res.planned_items,
            }
            for res in c.execute(
                "SELECT * FROM Sessions WHERE status IN (?, ?) ORDER BY completed_on DESC LIMIT ?",
                (TransferStatus.DONE.value, TransferStatus.CANCELLED.value, limit),
            ).fetchall()
        ]

    def get_session(self, uid: int, /) -> Optional[Session]:
        """
        Get a session by its uid.
        """
        c = self._get_read_connection().cursor()
        res = c.execute("SELECT * FROM Sessions WHERE uid = ?", (uid,)).fetchone()
        return (
            Session(
                res.uid,
                res.remote_path,
                res.remote_ref,
                TransferStatus(res.status),
                res.uploaded,
                res.total,
                res.engine,
                res.created_on,
                res.completed_on,
                res.description,
                res.planned_items,
            )
            if res
            else None
        )

    def create_session(
        self,
        remote_path: str,
        remote_ref: str,
        total: int,
        engine_uid: str,
        description: str,
        /,
    ) -> int:
        """Create a new session. Return the session ID."""
        with self.lock:
            c = self._get_write_connection().cursor()
            c.execute(
                "INSERT INTO Sessions (remote_path, remote_ref, total, status, engine, description, planned_items) "
                "VALUES (?, ?, ?, ?, ?, ?, ?)",
                (
                    remote_path,
                    remote_ref,
                    total,
                    TransferStatus.ONGOING.value,
                    engine_uid,
                    description,
                    total,
                ),
            )
            self.sessionUpdated.emit(False)
            return int(c.lastrowid)

    def update_session(self, uid: int, /) -> Optional[Session]:
        """
        Increment the Session *uploaded_items* count.
        Update the status if all files are uploaded.
        """
        with self.lock:
            session = self.get_session(uid)
            if not session:
                return None

            session.uploaded_items += 1
            if session.uploaded_items == session.total_items:
                session.status = TransferStatus.DONE
                sql = "UPDATE Sessions SET uploaded = ?, status = ?, completed_on = CURRENT_TIMESTAMP WHERE uid = ?"
            else:
                sql = "UPDATE Sessions SET uploaded = ?, status = ? WHERE uid = ?"

            c = self._get_write_connection().cursor()
            c.execute(sql, (session.uploaded_items, session.status.value, session.uid))
            self.sessionUpdated.emit(False)
            return session

    def change_session_status(self, uid: int, status: TransferStatus, /) -> None:
        """Update the session status with *status*."""
        with self.lock:
            session = self.get_session(uid)
            if not session:
                return None

            c = self._get_write_connection().cursor()
            c.execute(
                "UPDATE Sessions SET status = ? WHERE uid = ?",
                (status.value, session.uid),
            )
            self.sessionUpdated.emit(False)

    def decrease_session_counts(self, uid: int, /) -> Optional[Session]:
        """
        Decrease the Session *total_items* and *planned_items* counts.
        Update the status if all files are uploaded.
        """
        with self.lock:
            session = self.get_session(uid)
            if not session:
                return None

            session.total_items = max(0, session.total_items - 1)
            session.planned_items = max(0, session.planned_items - 1)
            if session.uploaded_items == session.total_items:
                session.status = (
                    TransferStatus.DONE
                    if session.total_items
                    else TransferStatus.CANCELLED
                )
                sql = (
                    "UPDATE Sessions SET"
                    " planned_items = ?, total = ?, status = ?, completed_on = CURRENT_TIMESTAMP"
                    " WHERE uid = ?"
                )
            else:
                sql = "UPDATE Sessions SET planned_items = ?, total = ?, status = ? WHERE uid = ?"

            c = self._get_write_connection().cursor()
            c.execute(
                sql,
                (
                    session.planned_items,
                    session.total_items,
                    session.status.value,
                    session.uid,
                ),
            )
            self.sessionUpdated.emit(False)
            return session

    def save_session_item(self, session_id: int, item: Dict[str, Any]) -> None:
        """Save the session uploaded item data into the SessionItems table."""

        with self.lock:
            c = self._get_write_connection().cursor()
            c.execute(
                "INSERT INTO SessionItems (session_id, data) VALUES (?, ?)",
                (
                    session_id,
                    json.dumps(item),
                ),
            )

    def get_session_items(self, session_id: int) -> List[Dict[str, Any]]:
        """Get all SessionItems linked to *session_id*."""

        c = self._get_read_connection().cursor()
        sql = "SELECT data FROM SessionItems WHERE session_id = ?"

        return [
            json.loads(res.data) for res in c.execute(sql, (session_id,)).fetchall()
        ]

    def get_downloads_with_status(self, status: TransferStatus, /) -> List[Download]:
        return [d for d in self.get_downloads() if d.status == status]

    def get_uploads_with_status(self, status: TransferStatus, /) -> List[Upload]:
        return self._get_uploads_with_status_and_func(self.get_uploads, status)

    def get_dt_uploads_with_status(self, status: TransferStatus, /) -> List[Upload]:
        return self._get_uploads_with_status_and_func(self.get_dt_uploads, status)

    def _get_uploads_with_status_and_func(
        self, func: Callable, status: TransferStatus, /
    ) -> List[Upload]:
        return [u for u in func() if u.status == status]

    def get_download(
        self, *, uid: int = None, path: Path = None, doc_pair: int = None
    ) -> Optional[Download]:
        value: Any
        if uid:
            key, value = "uid", uid
        elif path:
            key, value = "path", path
        elif doc_pair:
            key, value = "doc_pair", doc_pair
        else:
            return None

        res = [d for d in self.get_downloads() if getattr(d, key) == value]
        return res[0] if res else None

    def get_upload(self, **kwargs: Any) -> Optional[Upload]:
        return self._get_upload_with_func(self.get_uploads, **kwargs)

    def get_dt_upload(self, **kwargs: Any) -> Optional[Upload]:
        return self._get_upload_with_func(self.get_dt_uploads, **kwargs)

    def _get_upload_with_func(
        self,
        func: Callable,
        /,
        *,
        uid: int = None,
        path: Path = None,
        doc_pair: int = None,
    ) -> Optional[Upload]:
        value: Any
        if uid:
            key, value = "uid", uid
        elif doc_pair:
            key, value = "doc_pair", doc_pair
        elif path:
            key, value = "path", path
        else:
            return None

        res = [u for u in func() if getattr(u, key) == value]
        return res[0] if res else None

    def save_download(self, download: Download, /) -> None:
        """New download."""
        with self.lock:
            c = self._get_write_connection().cursor()
            sql = (
                "INSERT INTO Downloads "
                "(path, status, engine, doc_pair, filesize, is_direct_edit, tmpname, url)"
                " VALUES (?, ?, ?, ?, ?, ?, ?, ?)"
            )
            values = (
                download.path,
                download.status.value,
                download.engine,
                download.doc_pair,
                download.filesize,
                download.is_direct_edit,
                download.tmpname,
                download.url,
            )
            c.execute(sql, values)
            self.transferUpdated.emit()

    def save_upload(self, upload: Upload, /) -> None:
        """New upload."""
        with self.lock:
            # Remove non-serializable data, never used elsewhere
            batch = {k: v for k, v in upload.batch.items() if k != "blobs"}

            values = (
                upload.path,
                upload.status.value,
                upload.engine,
                upload.is_direct_edit,
                upload.is_direct_transfer,
                upload.filesize,
                json.dumps(batch),
                upload.chunk_size,
                upload.remote_parent_path,
                upload.remote_parent_ref,
                upload.doc_pair,
                upload.request_uid,
            )
            c = self._get_write_connection().cursor()
            sql = (
                "INSERT INTO Uploads "
                "(path, status, engine, is_direct_edit, is_direct_transfer, filesize, batch, chunk_size,"
                " remote_parent_path, remote_parent_ref, doc_pair, request_uid)"
                " VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)"
            )
            c.execute(sql, values)

            # Important: update the upload UID attr
            upload.uid = int(c.execute("SELECT last_insert_rowid()").fetchone()[0])

            if upload.is_direct_transfer:
                self.directTransferUpdated.emit()
            else:
                self.transferUpdated.emit()

    def save_dt_upload(self, upload: Upload, /) -> None:
        """
        New Direct Transfer upload.
        Will have the same status as it's session.
        """
        with self.lock:
            # Remove non-serializable data, never used elsewhere
            batch = {k: v for k, v in upload.batch.items() if k != "blobs"}

            values = (
                upload.path,
                upload.doc_pair,
                # Default value if IFNULL is validated, meaning that the linked state has been removed.
                TransferStatus.CANCELLED.value,
                upload.engine,
                upload.is_direct_edit,
                upload.is_direct_transfer,
                upload.filesize,
                json.dumps(batch),
                upload.chunk_size,
                upload.remote_parent_path,
                upload.remote_parent_ref,
                upload.doc_pair,
                upload.request_uid,
            )
            c = self._get_write_connection().cursor()
            sql = (
                "INSERT INTO Uploads "
                "(path, status, engine, is_direct_edit, is_direct_transfer, filesize, batch, chunk_size,"
                " remote_parent_path, remote_parent_ref, doc_pair, request_uid)"
                " VALUES (?, IFNULL((SELECT s.status FROM States st INNER JOIN Sessions s ON st.session = s.uid "
                "AND st.id = ?), ?), ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)"
            )
            c.execute(sql, values)

            # Important: update the upload UID and status attr
            upload.uid = int(c.execute("SELECT last_insert_rowid()").fetchone()[0])
            res = self.get_dt_upload(uid=upload.uid)
            # Upload may be deleted right after creation by session cancel.
            upload.status = res.status if res else TransferStatus.CANCELLED
            self.directTransferUpdated.emit()

    def update_upload(self, upload: Upload, /) -> None:
        """Update a upload."""
        with self.lock:
            # Remove non-serializable data, never used elsewhere
            batch = {k: v for k, v in upload.batch.items() if k != "blobs"}

            c = self._get_write_connection().cursor()
            sql = "UPDATE Uploads SET batch = ? WHERE uid = ?"
            c.execute(sql, (json.dumps(batch), upload.uid))

    def pause_transfer(
        self,
        nature: str,
        uid: int,
        progress: float,
        /,
        *,
        is_direct_transfer: bool = False,
    ) -> None:
        with self.lock:
            c = self._get_write_connection().cursor()
            table = f"{nature.title()}s"  # Downloads/Uploads
            c.execute(
                f"UPDATE {table} SET status = ?, progress = ? WHERE uid = ?",
                (TransferStatus.PAUSED.value, progress, uid),
            )
            if is_direct_transfer:
                self.directTransferUpdated.emit()
            else:
                self.transferUpdated.emit()

    def suspend_transfers(self) -> None:
        with self.lock:
            c = self._get_write_connection().cursor()
            c.execute(
                "UPDATE Downloads SET status = ? WHERE status = ?",
                (TransferStatus.SUSPENDED.value, TransferStatus.ONGOING.value),
            )
            rows = c.rowcount
            c.execute(
                "UPDATE Uploads SET status = ? WHERE status = ?",
                (TransferStatus.SUSPENDED.value, TransferStatus.ONGOING.value),
            )

            if rows + c.rowcount == 0:
                return

            self.transferUpdated.emit()
            self.directTransferUpdated.emit()

    def resume_transfer(
        self, nature: str, uid: int, /, *, is_direct_transfer: bool = False
    ) -> None:
        with self.lock:
            c = self._get_write_connection().cursor()
            table = f"{nature.title()}s"  # Downloads/Uploads
            c.execute(
                f"UPDATE {table} SET status = ? WHERE uid = ?",
                (TransferStatus.ONGOING.value, uid),
            )
            if is_direct_transfer:
                self.directTransferUpdated.emit()
            else:
                self.transferUpdated.emit()

    def resume_session(self, uid: int, /) -> None:
        """Resume all transfers for given session."""
        if not self.queue_manager:
            return

        with self.lock:
            c = self._get_write_connection().cursor()

            # Adapt the upload status of transfers that were already started when the session was paused
            c.execute(
                "UPDATE Uploads SET status = ? WHERE doc_pair IN (SELECT id FROM States WHERE session = ?)",
                (TransferStatus.ONGOING.value, uid),
            )

            # Get ongoing transfers first, to let them resuming before any other not-yet-handled transfers
            rows = c.execute(
                "SELECT * FROM States WHERE id IN"
                " (SELECT doc_pair FROM Uploads WHERE doc_pair IN (SELECT id FROM States WHERE session = ?))",
                (uid,),
            ).fetchall()

            # Then, get not-yet-handled transfers
            rows.extend(
                c.execute(
                    "SELECT * FROM States"
                    "        WHERE session = ?"
                    "          AND id NOT IN"
                    " (SELECT doc_pair FROM Uploads WHERE doc_pair IN (SELECT id FROM States WHERE session = ?))",
                    (uid, uid),
                ).fetchall()
            )

            # Finally, push all transfers in the queue
            for doc_pair in rows:
                self.queue_manager.push(doc_pair)
            self.directTransferUpdated.emit()

    def pause_session(self, uid: int, /) -> None:
        """Pause all transfers for given session."""
        with self.lock:
            c = self._get_write_connection().cursor()
            self.change_session_status(uid, TransferStatus.PAUSED)
            c.execute(
                "UPDATE Uploads SET status = ? WHERE doc_pair IN (SELECT id FROM States WHERE session = ?)",
                (TransferStatus.PAUSED.value, uid),
            )
            self.directTransferUpdated.emit()

    def cancel_session(self, uid: int, /) -> List[Dict[str, Any]]:
        """
        Cancel all transfers for given session.
        Return the list of impacted batches to be able to cancel them later.
        """
        with self.lock:
            c = self._get_write_connection().cursor()
            batchs = [
                json.loads(res.batch)
                for res in c.execute(
                    "SELECT * FROM Uploads WHERE doc_pair IN (SELECT id FROM States WHERE session = ?)",
                    (uid,),
                ).fetchall()
            ]
            c.execute(
                "DELETE FROM Uploads WHERE doc_pair IN (SELECT id FROM States WHERE session = ?)",
                (uid,),
            )
            c.execute("DELETE FROM States WHERE session = ?", (uid,))
            c.execute(
                "UPDATE Sessions SET total = uploaded, status = ? ,"
                " completed_on = CURRENT_TIMESTAMP WHERE uid = ?",
                (
                    TransferStatus.CANCELLED.value,
                    uid,
                ),
            )
            self.directTransferUpdated.emit()
            self.sessionUpdated.emit(False)
            return batchs

    def set_transfer_doc(
        self, nature: str, transfer_uid: int, engine_uid: str, doc_pair_uid: int, /
    ) -> None:
        with self.lock:
            c = self._get_write_connection().cursor()
            table = f"{nature.title()}s"  # Downloads/Uploads
            c.execute(
                f"UPDATE {table} SET doc_pair = ?, engine = ? WHERE uid = ?",
                (doc_pair_uid, engine_uid, transfer_uid),
            )

    def set_transfer_progress(
        self, nature: str, transfer: Union[Download, Upload], /
    ) -> None:
        """Update the 'progress' field of a given *transfer*."""
        with self.lock:
            c = self._get_write_connection().cursor()
            table = f"{nature.title()}s"  # Downloads/Uploads
            c.execute(
                f"UPDATE {table} SET progress = ? WHERE uid = ?",
                (transfer.progress, transfer.uid),
            )

    def set_transfer_status(
        self, nature: str, transfer: Union[Download, Upload], /
    ) -> None:
        """Update the 'status' field of a given *transfer*."""
        with self.lock:
            c = self._get_write_connection().cursor()
            table = f"{nature.title()}s"  # Downloads/Uploads
            c.execute(
                f"UPDATE {table} SET status = ? WHERE uid = ?",
                (transfer.status.value, transfer.uid),
            )
            self.directTransferUpdated.emit()

    def remove_transfer(
        self,
        nature: str,
        /,
        *,
        doc_pair: Optional[int] = None,
        path: Optional[Path] = None,
        is_direct_transfer: bool = False,
    ) -> None:
        with self.lock:
            c = self._get_write_connection().cursor()
            table = f"{nature.title()}s"  # Downloads/Uploads

            # Handling *doc_pair* first to allow to pass both *doc_pair* and *path*
            # and forcing the priority on *doc_pair*.
            if doc_pair is not None:
                c.execute(f"DELETE FROM {table} WHERE doc_pair = ?", (doc_pair,))
            elif path:
                c.execute(f"DELETE FROM {table} WHERE path = ?", (path,))
            else:
                # Should never happen
                log.error(
                    f"remove_transfert({nature!r}, {doc_pair!r}, {path!r}, {is_direct_transfer!r})"
                )
                return

            if c.rowcount == 0:
                return

            if is_direct_transfer:
                self.directTransferUpdated.emit()
            else:
                self.transferUpdated.emit()

    @staticmethod
    def _escape(text: str, /) -> str:
        return text.replace("'", "''")
