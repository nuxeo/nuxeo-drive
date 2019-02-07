# coding: utf-8
import tempfile
from logging import getLogger
from pathlib import Path

from nxdrive.manager import Manager
from nxdrive.options import Options
from nxdrive.report import Report


@Options.mock()
def test_logs():
    log = getLogger(__name__)
    folder = Path(tempfile.mkdtemp("-nxdrive-tests"))
    Options.nxdrive_home = folder

    with Manager() as manager:
        log.debug("Strange encoding \xe8 \xe9")

        # Crafted problematic logRecord
        try:
            raise ValueError("[Mock] folder/\xeatre ou ne pas \xeatre.odt")
        except ValueError as e:
            log.exception("Oups!")
            log.exception(repr(e))
            log.exception(str(e))
            log.exception(e)

        report = Report(manager, folder / "report")
        report.generate()
