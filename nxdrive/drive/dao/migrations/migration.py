from abc import ABC, abstractmethod
from sqlite3 import Cursor


class MigrationInterface(ABC):
    """Migration interface inherited by all migrations."""

    @abstractmethod
    def upgrade(self, cursor: Cursor) -> None:
        """Use the *cursor* to upgrade the database to a new state."""
        pass

    @abstractmethod
    def downgrade(self, cursor: Cursor) -> None:
        """Use the *cursor* to revert all changes done during the upgrade."""
        pass

    @property
    @abstractmethod
    def version(self) -> int:
        """Return the database version number linked to the migration."""
        pass

    @property
    @abstractmethod
    def previous_version(self) -> int:
        """Return the database version number prior to the migration."""
        pass
