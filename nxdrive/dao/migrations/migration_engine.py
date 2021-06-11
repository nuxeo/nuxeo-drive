import sqlite3
from logging import getLogger
from sqlite3.dbapi2 import Connection
from typing import Any, Callable, Dict

log = getLogger(__name__)


class MigrationEngine:
    def __init__(
        self,
        connection: Connection,
        migrations: Dict[str, Any],
    ) -> None:
        self.connection = connection
        self.migrations = migrations

    def execute_database_upgrade(
        self,
        starting_schema_version: int,
        old_migrations_schema_version: int,
        old_migrations_callback: Callable,
    ) -> None:
        """
        Execute all the database migrations upgrades up to the last version.
        Will run the old migrations if necessary before switching to the new system.
        """
        try:
            with self.connection as conn:
                cursor = conn.cursor()
                cursor.execute("BEGIN")
                # Let's execute old migrations if they haven't been run yet
                if (
                    0 < starting_schema_version < old_migrations_schema_version
                    or starting_schema_version == -1
                ):
                    old_migrations_callback(cursor, starting_schema_version)
                    # Old migrations have been applied successfully, we update the starting_schema_version
                    starting_schema_version = old_migrations_schema_version

                # Let's execute the new migrations
                for name, migration in self.migrations.items():
                    if migration.version <= starting_schema_version:
                        continue
                    log.debug(f"Running migration {name}.")
                    migration.upgrade(cursor)
                    log.debug(
                        f"Migration {name} upgrade applied successfully. Schema is now at version {migration.version}."
                    )
        except sqlite3.Error:
            log.exception("Database upgrade failed.")
            raise

    def execute_database_donwgrade(
        self,
        starting_schema_version: int,
        targeted_schema_version: int,
        old_migrations_schema_version: int,
    ) -> None:
        """
        Execute all the database migrations downgrades down to the *targeted_schema_version*.
        Will not downgrade under the *old_migrations_schema_version* as it is the old system.
        """
        try:
            with self.connection as conn:
                conn.execute("BEGIN")
                cursor = conn.cursor()

                # Let's reverse the migrations order
                reversed_keys = list(self.migrations.keys().__reversed__())
                reversed_migrations: Dict[str, Any] = {
                    key: self.migrations[key] for key in reversed_keys
                }

                # Let's execute all the migrations downgrade, starting from the last one.
                for name, migration in reversed_migrations.items():
                    if migration.version > starting_schema_version:
                        continue
                    if (
                        migration.version <= targeted_schema_version
                        or migration.version <= old_migrations_schema_version
                    ):
                        break
                    log.debug(f"Running migration {name}.")
                    migration.downgrade(cursor)
                    log.debug(
                        f"Migration {name} downgrade applied successfully."
                        f"Schema is now at version {migration.previous_version}."
                    )
                    if migration.previous_version == targeted_schema_version:
                        break
                    if migration.previous_version == old_migrations_schema_version:
                        break

        except sqlite3.Error:
            log.exception("Database downgrade failed.")
            raise
