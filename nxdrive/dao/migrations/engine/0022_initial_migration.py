from sqlite3 import Cursor

from ..migration import MigrationInterface


class MigrationInitial(MigrationInterface):
    def upgrade(self, cursor: Cursor) -> None:
        """
        Update the States table.
        """
        self._update_state_table(cursor)

    def downgrade(self, cursor: Cursor) -> None:
        """Update the States table."""
        # Drop Column doc_type to States table
        cursor.execute("ALTER TABLE States DROP COLUMN doc_type")

    @property
    def version(self) -> int:
        return 22

    @property
    def previous_version(self) -> int:
        return 21

    @staticmethod
    def _update_state_table(cursor: Cursor) -> None:
        """Update the States table."""
        cursor.execute("ALTER TABLE States ADD doc_type VARCHAR")


migration = MigrationInitial()
