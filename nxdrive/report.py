from contextlib import suppress
from datetime import datetime
from logging import getLogger
from pathlib import Path
from typing import TYPE_CHECKING, Iterator
from zipfile import ZIP_DEFLATED, ZIP_STORED, ZipFile

from . import constants
from .logging_config import get_handler
from .utils import force_encode

if TYPE_CHECKING:
    from .dao.engine import EngineDAO  # noqa
    from .manager import Manager  # noqa

__all__ = ("Report",)

log = getLogger(__name__)


class Report:
    """
    Class to create a complete report useful for bug reports.

    Usage:

        report = Report(manager, report_path=output_dir)
        report.generate()
        final_path = report.get_path()

    TODO: More pythonic class

        with Report(manager, report_path=output_dir) as report:
            report.generate()
            final_path = report.path
    """

    def __init__(self, manager: "Manager", /, *, report_path: Path = None) -> None:
        self._manager = manager
        name = f"report_{datetime.now().strftime('%y%m%d_%H%M%S')}"
        report_path = report_path or self._manager.home / "reports" / name

        if not report_path.parent.exists():
            report_path.parent.mkdir()
        self._zipfile = report_path.with_suffix(".zip")

    def copy_logs(self, myzip: ZipFile, /) -> None:
        """
        Copy all log files to the ZIP report.
        If one log file fails, we just try the next one.
        """

        folder = self._manager.home / "logs"
        if not folder.is_dir():
            return

        for path in folder.iterdir():
            if not path.is_file():
                continue
            if (
                path.name not in ("nxdrive.log", "segfault.log")
                and path.suffix != ".zip"
            ):
                continue

            comp = ZIP_DEFLATED if path.suffix == ".log" else ZIP_STORED
            rel_path = path.relative_to(self._manager.home)
            try:
                myzip.write(str(path), str(rel_path), compress_type=comp)
            except Exception:
                log.exception(f"Impossible to copy the log {rel_path!r}")

    @staticmethod
    def copy_db(myzip: ZipFile, dao: "EngineDAO", /) -> None:
        """
        Copy a database file to the ZIP report.
        If it fails, we just try ignore the file.
        """

        # Lock to avoid inconsistence
        with dao.lock:
            try:
                dao.force_commit()
                myzip.write(dao.db, dao.db.name, compress_type=ZIP_DEFLATED)
            except Exception:
                log.exception(f"Impossible to copy the database {dao.db.name!r}")

    def get_path(self) -> Path:
        return self._zipfile

    @staticmethod
    def export_logs(lines: int = constants.MAX_LOG_DISPLAYED, /) -> Iterator[bytes]:
        """
        Export all lines from the memory logger.

        :return bytes: bytes needed by zipfile.writestr()
        """

        handler = get_handler("memory")
        if not handler:
            return

        log_buffer = handler.get_buffer(lines)  # type: ignore

        for record in log_buffer:
            try:
                line = handler.format(record)
            except Exception:
                with suppress(Exception):
                    yield force_encode(f"Logging record error: {record!r}")
            else:
                if isinstance(line, bytes):
                    yield line
                else:
                    yield line.encode(errors="replace")

    def generate(self) -> None:
        """Create the ZIP report with all interesting files."""

        log.info(f"Create report {self._zipfile!r}")

        with ZipFile(self._zipfile, mode="w", allowZip64=True) as zip_:
            # Databases
            self.copy_db(zip_, self._manager.dao)
            for engine in self._manager.engines.copy().values():
                self.copy_db(zip_, engine.dao)

            # Logs
            self.copy_logs(zip_)

            # Memory logger -> debug.log
            try:
                lines = b"\n".join(self.export_logs())
                zip_.writestr("debug.log", lines, compress_type=ZIP_DEFLATED)
            except Exception:
                log.exception("Impossible to get lines from the memory logger")
