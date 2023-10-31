from sqlite3 import Cursor

from ..migration import MigrationInterface


class MigrationInitial(MigrationInterface):
    def upgrade(self, cursor: Cursor) -> None:
        """
        Update the Sessions table.
        """
        self._update_sessions_table(cursor)

    def downgrade(self, cursor: Cursor) -> None:
        """Update the Sessions table."""
        # Drop Column scheduled_on to Sessions table
        cursor.execute("ALTER TABLE Sessions DROP COLUMN scheduled_on")

    @property
    def version(self) -> int:
        return 23

    @property
    def previous_version(self) -> int:
        return 22

    @staticmethod
    def _update_sessions_table(cursor: Cursor) -> None:
        """Update the Sessions table."""
        cursor.execute(
            "ALTER TABLE Sessions ADD scheduled_on DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP"
        )


migration = MigrationInitial()
