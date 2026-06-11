import importlib
from typing import Any, Dict

_PACKAGE = "nxdrive.drive.dao.migrations.engine"

__migrations_list = [
    "0021_initial_migration",
    "0022_initial_migration",
    "0023_direct_downloads",
]  # Keep sorted


def import_migrations() -> Dict[str, Any]:
    """Load all engine migrations."""
    migrations = {}
    for name in __migrations_list:
        mod = importlib.import_module(f"{_PACKAGE}.{name}")
        migrations[name] = mod.migration
    return migrations


engine_migrations = import_migrations()
