'''
Created on 2 juil. 2015

@author: Remi Cattiau
'''
import os
import tempfile
from mock import Mock
from unittest import TestCase, skipIf

from nxdrive.manager import Manager
from nxdrive.report import Report
from tests.common import clean_dir, log


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
        report = Report(self.manager, os.path.join(self.folder, "report.zip"))
        log.debug("Strange encoding \xe9")
        log.debug(u"Unicode encoding \xe8")
        report.generate()
