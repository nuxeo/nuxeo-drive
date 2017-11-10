# coding: utf-8
import os
import tempfile

import pytest

from nxdrive.logging_config import get_logger
from nxdrive.manager import Manager
from nxdrive.options import Options
from nxdrive.report import Report


@Options.mock()
def test_logs():
    log = get_logger(__name__)
    folder = tempfile.mkdtemp(u'-nxdrive-tests')
    Options.nxdrive_home = folder
    manager = Manager()

    try:
        log.debug("Strange encoding \xe9")
        log.debug(u"Unicode encoding \xe8")

        # Crafted problematic logRecord
        try:
            raise ValueError(u'[tests] folder/\xeatre ou ne pas \xeatre.odt')
        except ValueError as e:
            log.exception('Oups!')
            log.exception(repr(e))
            log.exception(unicode(e))  # Works but not recommended

            with pytest.raises(UnicodeEncodeError):
                log.exception(str(e))

                # Using the syntax below will raise the same UnicodeEncodeError
                # but the logging module takes care of it and just prints out
                # the exception without raising it.  So I let it there FI.
                # log.exception(e)

        report = Report(manager, os.path.join(folder, 'report'))
        report.generate()
    finally:
        manager.dispose_db()
        Manager._singleton = None
