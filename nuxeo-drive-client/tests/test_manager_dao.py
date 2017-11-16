# coding: utf-8
import os
import sqlite3
import tempfile
import unittest
from mock import Mock

import nxdrive
from nxdrive.engine.dao.sqlite import EngineDAO
from nxdrive.manager import Manager
from tests.common import RemoteDocumentClientForTests, clean_dir


class ManagerDAOTest(unittest.TestCase):

    def setUp(self):
        self.build_workspace = os.environ.get('WORKSPACE')
        self.tmpdir = None
        if self.build_workspace is not None:
            self.tmpdir = os.path.join(self.build_workspace, 'tmp')
            if not os.path.isdir(self.tmpdir):
                os.makedirs(self.tmpdir)
            self.addCleanup(clean_dir, self.tmpdir)
        self.test_folder = tempfile.mkdtemp(u'-nxdrive-tests', dir=self.tmpdir)
        self.nuxeo_url = os.environ.get('NXDRIVE_TEST_NUXEO_URL', 'http://localhost:8080/nuxeo')
        self.admin_user = os.environ.get('NXDRIVE_TEST_USER', 'Administrator')
        self.admin_password = os.environ.get('NXDRIVE_TEST_PASSWORD', 'Administrator')
        # Handle the # in url
        if '#' in self.nuxeo_url:
            # Remove the engine type for the rest of the test
            self.nuxeo_url = self.nuxeo_url.split('#')[0]
        if not self.nuxeo_url.endswith('/'):
            self.nuxeo_url += '/'

    def tearDown(self):
        Manager._singleton = None

    def _get_db(self, name):
        return os.path.join(os.path.dirname(__file__), 'resources', name)

    def _create_manager(self):
        options = Mock()
        options.debug = False
        options.force_locale = None
        options.log_level_file = None
        options.proxy_server = None
        options.update_site_url = None
        options.beta_update_site_url = None
        options.nxdrive_home = self.test_folder
        manager = Manager(options)
        return manager

    def test_autolock(self):
        # Create Manager
        manager = self._create_manager()
        dao = manager.get_dao()
        dao.lock_path('/test_1', 1, 'doc_id_1')
        dao.lock_path('/test_2', 2, 'doc_id_2')
        dao.lock_path('/test_3', 3, 'doc_id_3')
        # Verify that it does fail
        dao.lock_path('/test_3', 4, 'doc_id_4')
        locks = dao.get_locked_paths()
        self.assertEqual(len(locks), 3)
        dao.unlock_path('/test')
        locks = dao.get_locked_paths()
        self.assertEqual(len(locks), 3)
        dao.unlock_path('/test_1')
        locks = dao.get_locked_paths()
        self.assertEqual(len(locks), 2)
        self.assertEqual(locks[0].path, '/test_2')
        self.assertEqual(locks[0].process, 2)
        self.assertEqual(locks[0].remote_id, 'doc_id_2')
        self.assertEqual(locks[1].path, '/test_3')
        # Verify it has auto-update
        self.assertEqual(locks[1].process, 4)
        self.assertEqual(locks[1].remote_id, 'doc_id_4')

    def test_notifications(self):
        from nxdrive.notification import Notification
        notif = Notification('warning', flags=Notification.FLAG_DISCARDABLE)
        notif2 = Notification('plop')
        # Create Manager
        manager = self._create_manager()
        dao = manager.get_dao()
        dao.insert_notification(notif)
        dao.insert_notification(notif2)
        self.assertEqual(len(dao.get_notifications()), 2)
        dao.discard_notification(notif.uid)
        self.assertEqual(len(dao.get_notifications(discarded=False)), 1)
        self.assertEqual(len(dao.get_notifications()), 2)
        dao.remove_notification(notif.uid)
        self.assertEqual(len(dao.get_notifications()), 1)
        dao.discard_notification(notif2.uid)
        self.assertEqual(len(dao.get_notifications()), 1)
        self.assertEqual(len(dao.get_notifications(discarded=True)), 1)

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
        remote_client = RemoteDocumentClientForTests(
            self.nuxeo_url, self.admin_user, device_id, nxdrive.__version__,
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
        conn.close()

        # Create Manager with old DB migration
        manager = self._create_manager()
        dao = manager.get_dao()

        # Check Manager config
        self.assertEqual(dao.get_config('device_id'), device_id)
        self.assertEqual(dao.get_config('proxy_config'), 'Manual')
        self.assertEqual(dao.get_config('proxy_type'), 'http')
        self.assertEqual(dao.get_config('proxy_server'), 'proxy.server.com')
        self.assertEqual(dao.get_config('proxy_port'), '80')
        self.assertEqual(dao.get_config('proxy_authenticated'), '1')
        self.assertEqual(dao.get_config('proxy_username'), 'Administrator')
        self.assertEqual(dao.get_config('auto_update'), '1')
        self.assertEqual(dao.get_config('proxy_config'), 'Manual')

        # Check engine definition
        engines = dao.get_engines()
        self.assertEqual(len(engines), 1)
        engine = engines[0]
        self.assertEqual(engine.engine, 'NXDRIVE')
        self.assertEqual(engine.name, manager._get_engine_name(self.nuxeo_url))
        self.assertTrue(local_folder in engine.local_folder)

        # Check engine config
        engine_uid = engine.uid
        engine_db = os.path.join(self.test_folder, 'ndrive_%s.db' % engine_uid)
        engine_dao = EngineDAO(engine_db)
        self.assertEqual(engine_dao.get_config('server_url'), self.nuxeo_url)
        self.assertEqual(engine_dao.get_config('remote_user'), 'Administrator')
        self.assertEqual(engine_dao.get_config('remote_token'), token)

        engine_dao.dispose()
        manager.dispose_all()
