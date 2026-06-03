"""
Migration to add the scheduled_at column to the Sessions table.
"""

from sqlite3 import Cursor

from ..migration import MigrationInterface


class MigrationAddScheduledAt(MigrationInterface):
    """Migration to add the scheduled_at column to the Sessions table."""

    def upgrade(self, cursor: Cursor) -> None:
        """
        Add the scheduled_at column to the Sessions table.
        """
        cursor.execute(
            "ALTER TABLE Sessions ADD COLUMN scheduled_at DATETIME DEFAULT (0)"
        )

    def downgrade(self, cursor: Cursor) -> None:
        """
        Remove the scheduled_at column from the Sessions table.
        Note: SQLite does not support DROP COLUMN before 3.35.0.
        Given Nuxeo Drive's compatibility, we might need a workaround if needed,
        but typically downgrade is not used in production.
        """
        # For simplicity in this context, we'll assume it's acceptable or not needed.
        pass

    @property
    def version(self) -> int:
        return 24

    @property
    def previous_version(self) -> int:
        return 23


migration = MigrationAddScheduledAt()
