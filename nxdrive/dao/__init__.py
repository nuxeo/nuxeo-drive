from pathlib import PosixPath, WindowsPath
from sqlite3 import register_adapter

from ..constants import WINDOWS
from .adapters import adapt_path

SCHEMA_VERSION = "schema_version"


register_adapter(WindowsPath if WINDOWS else PosixPath, adapt_path)

# To check and update on each beta release !!!
versions_history = {
    "5.2.8": 21,
    "5.3.0": 22,
    "5.3.3": 23,
}
