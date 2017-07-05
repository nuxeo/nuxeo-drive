# coding: utf-8
import os
import tempfile
from unittest import TestCase

from mock import Mock

from nxdrive.logging_config import get_logger
from nxdrive.manager import Manager
from nxdrive.report import Report
from tests.common import clean_dir


log = get_logger(__name__)


class ReportTest(TestCase):

    def setUp(self):
        self.folder = tempfile.mkdtemp(u'-nxdrive-tests')
        options = Mock()
        options.debug = False
        options.force_locale = None
        options.proxy_server = None
        options.log_level_file = None
        options.update_site_url = None
        options.beta_update_site_url = None
        options.nxdrive_home = self.folder
        self.manager = Manager(options)

    def tearDown(self):
        # Remove singleton
        self.manager.dispose_db()
        Manager._singleton = None
        clean_dir(self.folder)

    def test_logs(self):
        log.debug("Strange encoding \xe9")
        log.debug(u"Unicode encoding \xe8")

        # Crafted problematic logRecord
        try:
            raise ValueError(u'[tests] folder/\xeatre ou ne pas \xeatre.odt')
        except ValueError as e:
            log.exception('Oups!')
            log.exception(repr(e))
            log.exception(unicode(e))  # Works but not recommended

            with self.assertRaises(UnicodeEncodeError):
                log.exception(str(e))

                # Using the syntax below will raise the same UnicodeEncodeError
                # but the logging module takes care of it and just prints out
                # the exception without raising it.  So I let it there FI.
                # log.exception(e)

        report = Report(self.manager, os.path.join(self.folder, 'report'))
        report.generate()
