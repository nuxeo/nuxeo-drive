import importlib
from typing import Any, Dict

_PACKAGE = "nxdrive.drive.dao.migrations.manager"

__migrations_list = ["0004_initial_migration"]  # Keep sorted


def import_migrations() -> Dict[str, Any]:
    """Load all manager migrations."""
    migrations = {}
    for name in __migrations_list:
        mod = importlib.import_module(f"{_PACKAGE}.{name}")
        migrations[name] = mod.migration
    return migrations


manager_migrations = import_migrations()
