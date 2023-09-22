from sqlite3 import Cursor

from ..migration import MigrationInterface


class MigrationInitial(MigrationInterface):
    def upgrade(self, cursor: Cursor) -> None:
        """
        Update the Uploads table.
        """
        self._update_uploads_table(cursor)

    def downgrade(self, cursor: Cursor) -> None:
        """Update the Uploads table."""
        # Drop Column transfer_status from Uploads table
        cursor.execute("ALTER TABLE Uploads DROP COLUMN transfer_status")

    @property
    def version(self) -> int:
        return 23

    @property
    def previous_version(self) -> int:
        return 22

    @staticmethod
    def _update_uploads_table(cursor: Cursor) -> None:
        """Update the Uploads table."""
        cursor.execute(
            "ALTER TABLE Uploads ADD transfer_status VARCHAR DEFAULT ('testing')"
        )


migration = MigrationInitial()
