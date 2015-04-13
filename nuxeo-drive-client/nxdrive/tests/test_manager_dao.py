import unittest
import os
import sys
import shutil
import tempfile
import nxdrive
from mock import Mock
from nxdrive.manager import Manager
from nxdrive.engine.dao.sqlite import EngineDAO


class ManagerDAOTest(unittest.TestCase):

    def setUp(self):
        self.test_folder = tempfile.mkdtemp(u'-nxdrive-tests')

    def tearDown(self):
        shutil.rmtree(self.test_folder)

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

        # Create Manager with old DB migration
        options = Mock()
        options.debug = False
        options.force_locale = None
        options.log_level_file = None
        options.update_site_url = None
        options.beta_update_site_url = None
        options.nxdrive_home = self.test_folder
        manager = Manager(options)
        dao = manager.get_dao()

        # Check Manager config
        self.assertEquals(dao.get_config('device_id'), '8025aa54e1e311e481b7c8f733c9742b')
        self.assertEquals(dao.get_config('proxy_config'), 'Manual')
        self.assertEquals(dao.get_config('proxy_type'), 'http')
        self.assertEquals(dao.get_config('proxy_server'), 'proxy.server.com')
        self.assertEquals(dao.get_config('proxy_port'), '80')
        self.assertEquals(dao.get_config('proxy_authenticated'), '1')
        self.assertEquals(dao.get_config('proxy_username'), 'proxy_user')
        self.assertEquals(dao.get_config('auto_update'), '1')
        self.assertEquals(dao.get_config('proxy_config'), 'Manual')

        # Check engine definition
        engines = dao.get_engines()
        self.assertEquals(len(engines), 1)
        engine = engines[0]
        self.assertEquals(engine.engine, 'NXDRIVE')
        self.assertEquals(engine.name, 'localhost')
        self.assertEquals(engine.local_folder, '/home/ataillefer/Nuxeo Drive')

        # Check engine config
        engine_uid = engine.uid
        engine_db = os.path.join(self.test_folder, 'ndrive_%s.db' % engine_uid)
        engine_dao = EngineDAO(engine_db)
        self.assertEquals(engine_dao.get_config('server_url'), 'http://localhost:8080/nuxeo/')
        self.assertEquals(engine_dao.get_config('remote_user'), 'joe')
        self.assertEquals(engine_dao.get_config('remote_token'), 'db4d93a3-bbb2-4c84-a26d-0b82a6f4bd87')
