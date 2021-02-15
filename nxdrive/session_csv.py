import csv
from pathlib import Path
from typing import Any, Dict, List

from nxdrive.objects import Session

from .engine.engine import Engine
from .manager import Manager


class SessionCsv:
    """
    Class to create a CSV from a Direct Transfer session.

    Usage:

        session_csv = SessionCsv(manager, engine, session)
        session_csv.generate(session_items)
        output_path = session_csv.output_file
    """

    def __init__(self, manager: "Manager", engine: Engine, session: Session, /) -> None:
        self._manager = manager
        self._engine = engine
        self._session = session

        name = f"session_{session.completed_on.replace(':', '-').replace(' ', '_')}"
        self.output_file = Path(self._manager.home / "csv" / name).with_suffix(".csv")
        self.output_tmp = Path(self._manager.home / "csv" / name).with_suffix(".tmp")
        self.output_file.parent.mkdir(exist_ok=True)

    def create_tmp(self) -> None:
        """Create a CSV file ready to be ingested by the Nuxeo CSV importer.
        It must be compatible with the add-on and so followes those specifications:
            https://doc.nuxeo.com/nxdoc/nuxeo-csv/#csv-file-definition.
        """
        if self.output_tmp.is_file():
            return

        with open(self.output_tmp, "w", newline="") as csv_file:
            writer = csv.writer(
                csv_file, delimiter=",", quotechar='"', quoting=csv.QUOTE_ALL
            )
            writer.writerow(["name", "dc:title", "type"])

    def store_data(self, data: List[Dict[str, Any]]) -> None:
        """Fill the csv file with the elements from *data*."""
        if not self.output_tmp.is_file():
            return

        with open(self.output_tmp, "a", newline="") as csv_file:
            writer = csv.writer(
                csv_file, delimiter=",", quotechar='"', quoting=csv.QUOTE_ALL
            )
            for elem in data:
                name = (
                    elem["path"]
                    .removeprefix(self._session.remote_path)
                    .removeprefix("/")
                )
                writer.writerow(
                    [
                        name,
                        elem["properties"]["dc:title"],
                        elem["type"],
                    ]
                )
        self.output_tmp.rename(self.output_file)
