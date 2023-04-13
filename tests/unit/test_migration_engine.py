import random
import sqlite3
import string
from sqlite3 import Cursor
from typing import Any, Dict

from pytest import raises

from nxdrive.dao.migrations.migration import MigrationInterface
from nxdrive.dao.migrations.migration_engine import MigrationEngine


def generate_migration(
    schema_version: int, previous_schema_version: int, /, *, should_raise: bool = False
):
    """Instantiate and return a migration object."""

    class TestMigration(MigrationInterface):
        table_name = "".join(random.choice(string.ascii_letters) for _ in range(5))

        def __init__(self, schema_version, previous_schema_version) -> None:
            self._schema_version = schema_version
            self._previous_schema_version = previous_schema_version

        def upgrade(self, cursor: Cursor) -> None:
            """Create a table with a random name or generate an exception."""
            if not should_raise:
                cursor.execute(
                    f"CREATE TABLE {self.table_name} ("
                    "   path STRING NOT NULL,"
                    "   PRIMARY KEY (path)"
                    ")"
                )
            else:
                raise sqlite3.Error("Mocked error")

        def downgrade(self, cursor: Cursor) -> None:
            """Drop the created table or generate an exception."""
            if not should_raise:
                cursor.execute(f"DROP TABLE {self.table_name}")
            else:
                raise sqlite3.Error("Mocked error")

        @property
        def version(self) -> int:
            return self._schema_version

        @property
        def previous_version(self) -> int:
            return self._previous_schema_version

    return TestMigration(schema_version, previous_schema_version)


def generate_migrations_dict(count: int) -> Dict[str, Any]:
    """Generate a dictionary of migration objects."""
    migrations_dict = {}
    previous_migration = 0

    for x in range(1, count):
        migration = generate_migration(x, previous_migration)
        migrations_dict.update({f"{x}_added_table_{migration.table_name}": migration})
        previous_migration = x

    return migrations_dict


def test_migration_engine_no_error():
    """A simple test to see if the downgrade remove all the upgrade modifications."""
    migrations_dict = generate_migrations_dict(10)

    def old_migrations_callback(*_, **__):
        pass

    with sqlite3.connect(":memory:") as conn:
        cursor = conn.cursor()
        migration_engine = MigrationEngine(conn, migrations_dict)

        # Let's do a database upgrade
        migration_engine.execute_database_upgrade(0, 0, old_migrations_callback)
        user_version = cursor.execute("PRAGMA user_version").fetchone()[0]
        assert user_version == 9

        # Let's do a database downgrade to version 5
        migration_engine.execute_database_donwgrade(user_version, 5, 0)
        user_version = cursor.execute("PRAGMA user_version").fetchone()[0]
        assert user_version == 5

        # Let's do a database downgrade to version 0
        migration_engine.execute_database_donwgrade(user_version, 0, 0)
        user_version = cursor.execute("PRAGMA user_version").fetchone()[0]
        assert user_version == 0


def test_migration_engine_upgrade_new_migration_error():
    """Check that no changes are done to the database when the new migrations fails."""
    migrations_dict = {}
    migration_1 = generate_migration(1, 0)
    migration_2 = generate_migration(2, 1, should_raise=True)
    migrations_dict.update(
        {
            f"1_added_table_{migration_1.table_name}": migration_1,
            f"2_added_table_{migration_2.table_name}": migration_2,
        }
    )

    def old_migrations_callback(*_, **__):
        pass

    with sqlite3.connect(":memory:") as conn:
        cursor = conn.cursor()
        migration_engine = MigrationEngine(conn, migrations_dict)

        # Let's do a database upgrade that should raises
        with raises(sqlite3.Error):
            migration_engine.execute_database_upgrade(0, 0, old_migrations_callback)

        # Assert that no change has been done
        user_version = cursor.execute("PRAGMA user_version").fetchone()[0]
        assert user_version == 0


def test_migration_engine_upgrade_old_migrations_error():
    """Check that no changes are done to the database when the old migrations fails."""
    migrations_dict = generate_migrations_dict(10)

    def old_migrations_callback(*_, **__):
        raise sqlite3.Error("Mocked error")

    with sqlite3.connect(":memory:") as conn:
        cursor = conn.cursor()
        migration_engine = MigrationEngine(conn, migrations_dict)

        # Let's do a database upgrade that should raises
        with raises(sqlite3.Error):
            # Migrations from 1 to 5 are covered by all migrations
            migration_engine.execute_database_upgrade(2, 5, old_migrations_callback)

        # Assert that no change has been done
        user_version = cursor.execute("PRAGMA user_version").fetchone()[0]
        assert user_version == 0


def test_migration_engine_downgrade_new_migrations_error():
    """Check that now changes are done to the datatabse when the downgrade fails."""
    migrations_dict = generate_migrations_dict(10)

    def old_migrations_callback(*_, **__):
        pass

    with sqlite3.connect(":memory:") as conn:
        cursor = conn.cursor()
        migration_engine = MigrationEngine(conn, migrations_dict)

        # Let's do a database upgrade
        migration_engine.execute_database_upgrade(0, 0, old_migrations_callback)
        user_version = cursor.execute("PRAGMA user_version").fetchone()[0]
        assert user_version == 9

        for name, migration in migrations_dict.items():
            if migration.version == 5:
                migrations_dict[name] = generate_migration(5, 4, should_raise=True)
        # Let's do a database upgrade that should raises
        with raises(sqlite3.Error):
            migration_engine.execute_database_donwgrade(9, 0, 0)
        # Assert that no change has been done
        user_version = cursor.execute("PRAGMA user_version").fetchone()[0]
        assert user_version == 9


def test_migration_downgrade_to_old_migrations():
    """Check that a downgrade can't go under the old migrations schema version."""
    migrations_dict = generate_migrations_dict(10)

    def old_migrations_callback(*_, **__):
        pass

    with sqlite3.connect(":memory:") as conn:
        cursor = conn.cursor()
        migration_engine = MigrationEngine(conn, migrations_dict)

        # Let's do a database upgrade
        migration_engine.execute_database_upgrade(0, 0, old_migrations_callback)
        user_version = cursor.execute("PRAGMA user_version").fetchone()[0]
        assert user_version == 9

        # Let's do a database upgrade to the same version (shouldn't do anything)
        migration_engine.execute_database_donwgrade(user_version, 9, 2)
        user_version = cursor.execute("PRAGMA user_version").fetchone()[0]
        assert user_version == 9

        # Let's do a database downgrade to version 0
        migration_engine.execute_database_donwgrade(user_version, 0, 2)
        user_version = cursor.execute("PRAGMA user_version").fetchone()[0]
        assert user_version == 2  # We can't go under the old migrations
