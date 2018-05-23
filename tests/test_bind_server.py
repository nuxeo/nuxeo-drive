# coding: utf-8
import os
import tempfile
import unittest

import pytest

from nxdrive.manager import FolderAlreadyUsed, Manager
from nxdrive.options import Options
from nxdrive.osi.darwin.darwin import DarwinIntegration
from .common import TEST_DEFAULT_DELAY, clean_dir

DarwinIntegration._init = lambda *args: None
DarwinIntegration._cleanup = lambda *args: None
DarwinIntegration._send_notification = lambda *args: None


class BindServerTest(unittest.TestCase):
    def setUp(self):
        self.tmpdir = os.path.join(os.environ.get('WORKSPACE', ''), 'tmp')
        self.addCleanup(clean_dir, self.tmpdir)
        if not os.path.isdir(self.tmpdir):
            os.makedirs(self.tmpdir)

        self.local_test_folder = tempfile.mkdtemp(u'-nxdrive-temp-config',
                                                  dir=self.tmpdir)
        self.nxdrive_conf_folder = os.path.join(self.local_test_folder,
                                                u'nuxeo-drive-conf')

        self.nuxeo_url = os.environ.get('NXDRIVE_TEST_NUXEO_URL',
                                        'http://localhost:8080/nuxeo')
        self.user = os.environ.get('NXDRIVE_TEST_USER', 'Administrator')
        self.password = os.environ.get('NXDRIVE_TEST_PASSWORD',
                                       'Administrator')

    def tearDown(self):
        Manager._singleton = None

    @Options.mock()
    def test_bind_local_folder_on_config_folder(self):
        Options.delay = TEST_DEFAULT_DELAY
        Options.nxdrive_home = self.nxdrive_conf_folder
        self.manager = Manager()
        self.addCleanup(self.manager.unbind_all)
        self.addCleanup(self.manager.dispose_all)

        with pytest.raises(FolderAlreadyUsed):
            self.manager.bind_server(
                self.nxdrive_conf_folder, self.nuxeo_url, self.user,
                self.password, start_engine=False)
