import csv
from pathlib import Path
from typing import Any, Dict, List

from nxdrive.objects import Session

from .engine.engine import Engine
from .manager import Manager


class SessionCsv:
    """
    Class to create a csv from a DT session.

    Usage:

        session_csv = SessionCsv(manager, engine, session)
        session_csv.generate(session_items)
        output_path = csv.get_path()
    """

    def __init__(self, manager: "Manager", engine: Engine, session: Session, /) -> None:
        self._manager = manager
        self._engine = engine
        self._session = session

        name = f"session_{session.completed_on.replace(':', '-').replace(' ', '_')}.tmp"
        self._csv_path = self._manager.home / "csv" / name
        if not self._csv_path.parent.exists():
            self._csv_path.parent.mkdir()

    def create_tmp(self) -> None:
        """Create a temporary csv containing only the columns names."""
        if self._csv_path.is_file():
            return

        with open(self._csv_path, "w", newline="") as csv_file:
            writer = csv.writer(
                csv_file, delimiter=",", quotechar='"', quoting=csv.QUOTE_ALL
            )
            writer.writerow(["path", "dc:title", "type", "uid"])

    def store_data(self, data: List[Dict[str, Any]]) -> None:
        """Fill the csv file with the elements from *data*."""
        if not self._csv_path.is_file():
            return

        with open(self._csv_path, "a", newline="") as csv_file:
            writer = csv.writer(
                csv_file, delimiter=",", quotechar='"', quoting=csv.QUOTE_ALL
            )
            for elem in data:
                writer.writerow(
                    [
                        elem["path"],
                        elem["properties"]["dc:title"],
                        elem["type"],
                        elem["uid"],
                    ]
                )
        self._csv_path.rename(self._csv_path.with_suffix(".csv"))
        self._csv_path = self._csv_path.with_suffix(".csv")

    def get_path(self) -> Path:
        """Return the path to the csv file."""
        return self._csv_path
