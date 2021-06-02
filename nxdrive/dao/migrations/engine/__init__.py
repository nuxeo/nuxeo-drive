import importlib
from typing import Any, Dict

__migrations_list = ["0021_initial_migration"]  # Keep sorted


def import_migrations() -> Dict[str, Any]:
    """Dynamically load all the migrations from the module."""
    migrations = {}

    for migration_name in __migrations_list:
        module = getattr(
            importlib.import_module(
                f".{migration_name}", package="nxdrive.dao.migrations.engine"
            ),
            "migration",
        )
        migrations[migration_name] = module
    return migrations


engine_migrations = import_migrations()
