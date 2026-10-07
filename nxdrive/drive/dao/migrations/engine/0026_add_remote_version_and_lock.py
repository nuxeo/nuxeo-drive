"""
Migration to add the remote version and lock columns to the States table.
"""

from logging import getLogger
from sqlite3 import Cursor

from ..migration import MigrationInterface

log = getLogger(__name__)


class MigrationAddRemoteVersionAndLock(MigrationInterface):
    """Record the server-side version label and lock state on each pair.

    Alfresco exposes no content digest, so remote change detection compared
    modification timestamps. A timestamp also moves on metadata-only edits
    (rename, tag, aspect), which reads as a content change and raises false
    conflicts. ``cm:versionLabel`` only advances when content is written, so
    it is the signal conflict detection compares first, falling back to the
    timestamp for nodes that are not versionable.

    ``remote_locked`` lets the processor defer an upload while somebody holds
    the node checked out, instead of pushing and getting a 409.

    Both are nullable/defaulted: Nuxeo accounts and pre-existing rows simply
    leave them unset.
    """

    def upgrade(self, cursor: Cursor) -> None:
        try:
            columns = {
                row[1]
                for row in cursor.execute("PRAGMA table_info('States')").fetchall()
            }
            if "remote_version" not in columns:
                cursor.execute("ALTER TABLE States ADD COLUMN remote_version VARCHAR")
            if "remote_locked" not in columns:
                cursor.execute(
                    "ALTER TABLE States ADD COLUMN remote_locked INTEGER DEFAULT (0)"
                )
        except Exception as exc:
            log.error("MigrationAddRemoteVersionAndLock failed: %s", exc)
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


migration = MigrationAddRemoteVersionAndLock()
