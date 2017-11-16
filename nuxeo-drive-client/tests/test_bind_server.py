# coding: utf-8
import os
import tempfile
import unittest

from mock import Mock

from nxdrive.manager import FolderAlreadyUsed, Manager
from tests.common import TEST_DEFAULT_DELAY, clean_dir


class BindServerTest(unittest.TestCase):
    def setUp(self):
        self.tmpdir = os.path.join(os.environ.get('WORKSPACE', ''), 'tmp')
        self.addCleanup(clean_dir, self.tmpdir)
        if not os.path.isdir(self.tmpdir):
            os.makedirs(self.tmpdir)

        self.local_test_folder = tempfile.mkdtemp(u'-nxdrive-temp-config', dir=self.tmpdir)
        self.nxdrive_conf_folder = os.path.join(self.local_test_folder, u'nuxeo-drive-conf')

        self.nuxeo_url = os.environ.get('NXDRIVE_TEST_NUXEO_URL', "http://localhost:8080/nuxeo")
        self.user = os.environ.get('NXDRIVE_TEST_USER', "Administrator")
        self.password = os.environ.get('NXDRIVE_TEST_PASSWORD', "Administrator")

    def tearDown(self):
        self.manager.unbind_all()
        self.manager.dispose_all()
        Manager._singleton = None

    def test_bind_local_folder_on_config_folder(self):
        options = Mock()
        options.debug = False
        options.delay = TEST_DEFAULT_DELAY
        options.force_locale = None
        options.proxy_server = None
        options.log_level_file = None
        options.update_site_url = None
        options.beta_update_site_url = None
        options.nxdrive_home = self.nxdrive_conf_folder
        self.manager = Manager(options)

        with self.assertRaises(FolderAlreadyUsed):
            self.manager.bind_server(self.nxdrive_conf_folder, self.nuxeo_url, self.user,
                                     self.password, start_engine=False)
