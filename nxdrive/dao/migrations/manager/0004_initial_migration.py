from sqlite3 import Cursor

from ..migration import MigrationInterface


class MigrationInitial(MigrationInterface):
    def upgrade(self, cursor: Cursor) -> None:
        """
        Create all the basics table.
        Setup the *journal_mode* and *temp_store*.
        """
        cursor.execute("PRAGMA journal_mode = DELETE")
        cursor.execute("PRAGMA temp_store = MEMORY")

        self._create_configuration_table(cursor)
        cursor.execute(
            "CREATE TABLE Engines ("
            "    uid          VARCHAR,"
            "    engine       VARCHAR NOT NULL,"
            "    name         VARCHAR,"
            "    local_folder VARCHAR NOT NULL UNIQUE,"
            "    PRIMARY KEY (uid)"
            ")"
        )
        cursor.execute(
            "CREATE TABLE Notifications ("
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
            "CREATE TABLE AutoLock ("
            "    path      VARCHAR,"
            "    remote_id VARCHAR,"
            "    process   INT,"
            "    PRIMARY KEY(path)"
            ")"
        )

        cursor.execute(f"PRAGMA user_version = {self.version}")

    def downgrade(self, cursor: Cursor) -> None:
        """
        Drop all the created tables.
        Only revert the *user_version* PRAGMA.
        """
        for table in [
            "Configuration",
            "Engines",
            "Notifications",
            "Autolock",
        ]:
            cursor.execute(f"DROP TABLE {table}")

        cursor.execute(f"PRAGMA user_version = {self.previous_version}")

    @property
    def version(self) -> int:
        return 4

    @property
    def previous_version(self) -> int:
        return 0

    def _create_configuration_table(self, cursor: Cursor, /) -> None:
        cursor.execute(
            "CREATE TABLE Configuration ("
            "    name    VARCHAR NOT NULL,"
            "    value   VARCHAR,"
            "    PRIMARY KEY (name)"
            ")"
        )


migration = MigrationInitial()
