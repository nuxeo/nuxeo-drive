import sqlite3
from logging import getLogger
from sqlite3.dbapi2 import Connection
from typing import Any, Callable, Dict

log = getLogger(__name__)


class MigrationEngine:
    def __init__(
        self,
        connection: Connection,
        schema_version: int,
        migrations: Dict[str, Any],
    ) -> None:
        self.connection = connection
        self.starting_schema_version = schema_version
        self.migrations = migrations

    def execute_database_upgrade(
        self,
        old_migrations_schema_version: int,
        old_migrations_callback: Callable = None,
    ):
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
                    old_migrations_callback
                    and (
                        0 < self.starting_schema_version < old_migrations_schema_version
                    )
                    or self.starting_schema_version == -1
                ):
                    old_migrations_callback(cursor, self.starting_schema_version)
                    # Old migrations have been applied succesfully, we update the starting_schema_version
                    self.starting_schema_version = old_migrations_schema_version

                # Let's execute the new migrations
                for name, migration in self.migrations.items():
                    if migration.version <= self.starting_schema_version:
                        continue
                    log.debug(f"Running migration {name}.")
                    migration.upgrade(cursor)
                    log.debug(
                        f"Migration {name} applied succesfully. Schema is now at version {migration.version}."
                    )
        except sqlite3.Error:
            log.exception("Database upgrade failed.")
            raise

    def execute_database_donwgrade(
        self,
        targeted_schema_version: int,
        old_migrations_schema_version: int,
    ) -> None:
        """
        Execute all the database migrations downgrades down to the *targeted_schema_version*.
        Will not downgrade under the *old_migrations_schema_version* as it is the old system.
        """
        if targeted_schema_version >= self.starting_schema_version:
            return

        try:
            with self.connection as conn:
                conn.execute("BEGIN")
                cursor = conn.cursor()

                # Let's execute all the migrations downgrade, starting from the last one.
                for name, migration in self.migrations.__reversed__.items():
                    if (
                        migration.version > old_migrations_schema_version
                        and migration.version >= targeted_schema_version
                    ):
                        log.debug(f"Running migration {name}.")
                        migration.downgrade(cursor)
                        log.debug(
                            f"Migration {name} applied succesfully. Schema is now at version {migration.version}."
                        )
                    else:
                        break

        except sqlite3.Error:
            log.exception("Database upgrade failed.")
            raise
