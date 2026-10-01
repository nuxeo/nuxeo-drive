"""
Migration to add the node_id column to the Filters table.
"""

from logging import getLogger
from sqlite3 import Cursor

from ..migration import MigrationInterface

log = getLogger(__name__)


class MigrationAddFilterNodeId(MigrationInterface):
    """Record the server-side node id alongside each filtered path.

    Filters are keyed by human-readable path, which is all the scan-time
    prefix matching needs. Resolving a path back to a single node — when a
    filter is removed — additionally needs its id, since the path namespace
    and the ``States.remote_ref`` namespace (node ids) do not overlap.

    Nullable: filters added outside the folder picker (and every Nuxeo
    account) simply leave it unset.
    """

    def upgrade(self, cursor: Cursor) -> None:
        try:
            columns = {
                row[1]
                for row in cursor.execute("PRAGMA table_info('Filters')").fetchall()
            }
            if "node_id" in columns:
                return

            cursor.execute("ALTER TABLE Filters ADD COLUMN node_id VARCHAR")
        except Exception as exc:
            log.error("MigrationAddFilterNodeId failed: %s", exc)
            raise

    def downgrade(self, cursor: Cursor) -> None:
        """No-op: SQLite before 3.35.0 cannot drop a column, and an unused
        nullable column is harmless."""

    @property
    def version(self) -> int:
        return 25

    @property
    def previous_version(self) -> int:
        return 24


migration = MigrationAddFilterNodeId()
