# coding: utf-8
import tempfile
from logging import getLogger
from pathlib import Path

from nxdrive.manager import Manager
from nxdrive.options import Options
from nxdrive.report import Report
from sentry_sdk import configure_scope


@Options.mock()
def test_logs():
    log = getLogger(__name__)
    folder = Path(tempfile.mkdtemp("-nxdrive-tests"))
    Options.nxdrive_home = folder
    manager = Manager()

    try:
        log.debug("Strange encoding \xe8 \xe9")

        # Crafted problematic logRecord
        with configure_scope() as scope:
            scope._should_capture = False
            try:
                raise ValueError("[tests] folder/\xeatre ou ne pas \xeatre.odt")
            except ValueError as e:
                log.exception("Oups!")
                log.exception(repr(e))
                log.exception(str(e))
                log.exception(e)

        report = Report(manager, folder / "report")
        report.generate()
    finally:
        manager.dispose_db()
        Manager._singleton = None
