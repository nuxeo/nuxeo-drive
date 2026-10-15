"""
Migration to add the remote lock column to the States table.
"""

from logging import getLogger
from sqlite3 import Cursor

from ..migration import MigrationInterface

log = getLogger(__name__)


class MigrationAddRemoteLock(MigrationInterface):
    """Record the server-side lock state on each pair.

    ``remote_locked`` lets the processor defer an upload while somebody holds
    the node checked out, instead of pushing and getting a 409.

    Defaulted, so Nuxeo accounts and pre-existing rows simply leave it unset.
    """

    def upgrade(self, cursor: Cursor) -> None:
        try:
            columns = {
                row[1]
                for row in cursor.execute("PRAGMA table_info('States')").fetchall()
            }
            if "remote_locked" not in columns:
                cursor.execute(
                    "ALTER TABLE States ADD COLUMN remote_locked INTEGER DEFAULT (0)"
                )
        except Exception as exc:
            log.error("MigrationAddRemoteLock failed: %s", exc)
            raise

    def downgrade(self, cursor: Cursor) -> None:
        """No-op: SQLite before 3.35.0 cannot drop a column, and unused
        nullable columns are harmless."""

    @property
    def version(self) -> int:
        return 26

    @property
    def previous_version(self) -> int:
        return 25


migration = MigrationAddRemoteLock()
