# coding: utf-8
import os
import tempfile
from logging import getLogger

import pytest

from nxdrive.manager import Manager
from nxdrive.options import Options
from nxdrive.report import Report


@Options.mock()
def test_logs():
    log = getLogger(__name__)
    folder = tempfile.mkdtemp('-nxdrive-tests')
    Options.nxdrive_home = folder
    manager = Manager()

    try:
        log.debug('Strange encoding \xe8 \xe9')

        # Crafted problematic logRecord
        try:
            raise ValueError('[tests] folder/\xeatre ou ne pas \xeatre.odt')
        except ValueError as e:
            log.exception('Oups!')
            log.exception(repr(e))
            log.exception(str(e))
            log.exception(e)

        report = Report(manager, os.path.join(folder, 'report'))
        report.generate()
    finally:
        manager.dispose_db()
        Manager._singleton = None
