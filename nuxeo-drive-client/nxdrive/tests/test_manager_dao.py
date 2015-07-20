import unittest
import os
import shutil
import tempfile
import sqlite3
from mock import Mock
import nxdrive
from nxdrive.client import RemoteDocumentClient
from nxdrive.manager import Manager
from nxdrive.engine.dao.sqlite import EngineDAO
from nxdrive.logging_config import configure

WindowsError = None
try:
    from exceptions import WindowsError
except ImportError:
    pass  # This will never be raised under Unix


def configure_logger():
    configure(
        console_level='DEBUG',
        command_name='test',
    )
configure_logger()


class ManagerDAOTest(unittest.TestCase):

    def setUp(self):
        self.build_workspace = os.environ.get('WORKSPACE')
        self.tmpdir = None
        if self.build_workspace is not None:
            self.tmpdir = os.path.join(self.build_workspace, "tmp")
            if not os.path.isdir(self.tmpdir):
                os.makedirs(self.tmpdir)
        self.test_folder = tempfile.mkdtemp(u'-nxdrive-tests', dir=self.tmpdir)
        self.nuxeo_url = os.environ.get('NXDRIVE_TEST_NUXEO_URL')
        self.admin_user = os.environ.get('NXDRIVE_TEST_USER')
        self.admin_password = os.environ.get('NXDRIVE_TEST_PASSWORD')
        if self.nuxeo_url is None:
            self.nuxeo_url = "http://localhost:8080/nuxeo/"
        if not self.nuxeo_url.endswith('/'):
            self.nuxeo_url += '/'
        if self.admin_user is None:
            self.admin_user = "Administrator"
        if self.admin_password is None:
            self.admin_password = "Administrator"

    def tearDown(self):
        Manager._singleton = None
        self._clean_dir(self.test_folder)

    def _clean_dir(self, _dir):
        if os.path.exists(_dir):
            try:
                shutil.rmtree(_dir)
            except Exception as e:
                if type(e) == WindowsError:
                    os.system('rmdir /S /Q %s' % _dir)

    def _get_db(self, name):
        nxdrive_path = os.path.dirname(nxdrive.__file__)
        return os.path.join(nxdrive_path, 'tests', 'resources', name)

    def test_migration_db_v1(self):
        # Initialize old DB
        db = open(self._get_db('test_manager_migration.db'), 'rb')
        old_db = os.path.join(self.test_folder, 'nxdrive.db')
        with open(old_db, 'wb') as f:
            f.write(db.read())
        db.close()

        # Update token with one acquired against the test server
        conn = sqlite3.connect(old_db)
        c = conn.cursor()
        device_id = c.execute("SELECT device_id FROM device_config LIMIT 1").fetchone()[0]
        remote_client = RemoteDocumentClient(self.nuxeo_url, self.admin_user, device_id, nxdrive.__version__,
                                             password=self.admin_password)
        token = remote_client.request_token()
        c.execute("UPDATE server_bindings SET remote_token='%s' WHERE local_folder='%s'" % (
            token, '/home/ataillefer/Nuxeo Drive'))

        # Update server URL with test server URL
        c.execute("UPDATE server_bindings SET server_url='%s' WHERE local_folder='%s'" % (
            self.nuxeo_url, '/home/ataillefer/Nuxeo Drive'))

        # Update local folder with test temp dir
        local_folder = os.path.join(self.test_folder, 'Nuxeo Drive')
        c.execute("UPDATE server_bindings SET local_folder='%s' WHERE local_folder='%s'" % (
            local_folder, '/home/ataillefer/Nuxeo Drive'))
        conn.commit()

        # Create Manager with old DB migration
        options = Mock()
        options.debug = False
        options.force_locale = None
        options.log_level_file = None
        options.proxy_server = None
        options.update_site_url = None
        options.beta_update_site_url = None
        options.nxdrive_home = self.test_folder
        manager = Manager(options)
        dao = manager.get_dao()

        # Check Manager config
        self.assertEquals(dao.get_config('device_id'), device_id)
        self.assertEquals(dao.get_config('proxy_config'), 'Manual')
        self.assertEquals(dao.get_config('proxy_type'), 'http')
        self.assertEquals(dao.get_config('proxy_server'), 'proxy.server.com')
        self.assertEquals(dao.get_config('proxy_port'), '80')
        self.assertEquals(dao.get_config('proxy_authenticated'), '1')
        self.assertEquals(dao.get_config('proxy_username'), 'Administrator')
        self.assertEquals(dao.get_config('auto_update'), '1')
        self.assertEquals(dao.get_config('proxy_config'), 'Manual')

        # Check engine definition
        engines = dao.get_engines()
        self.assertEquals(len(engines), 1)
        engine = engines[0]
        self.assertEquals(engine.engine, 'NXDRIVE')
        self.assertEquals(engine.name, manager._get_engine_name(self.nuxeo_url))
        self.assertEquals(engine.local_folder, local_folder)

        # Check engine config
        engine_uid = engine.uid
        engine_db = os.path.join(self.test_folder, 'ndrive_%s.db' % engine_uid)
        engine_dao = EngineDAO(engine_db)
        self.assertEquals(engine_dao.get_config('server_url'), self.nuxeo_url)
        self.assertEquals(engine_dao.get_config('remote_user'), 'Administrator')
        self.assertEquals(engine_dao.get_config('remote_token'), token)
