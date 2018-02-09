# coding: utf-8
import os

from nxdrive.client import LocalClient
from nxdrive.client.common import LOCALLY_EDITED_FOLDER_NAME
from nxdrive.engine.engine import Engine, ServerBindingSettings
from tests.common_unit_test import UnitTestCase


class MockUrlTestEngine(Engine):
    def __init__(self, url):
        self._url = url

    def get_binder(self):
        return ServerBindingSettings(
            server_url=self._url,
            web_authentication=None,
            username='Administrator',
            local_folder='/',
            initialized=True,
        )


class TestDirectEdit(UnitTestCase):

    locally_edited_path = ('/default-domain/UserWorkspaces/'
                           + 'nuxeoDriveTestUser-user-1/Collections/'
                           + LOCALLY_EDITED_FOLDER_NAME)

    def setUpApp(self):
        super(TestDirectEdit, self).setUpApp()
        self.direct_edit = self.manager_1.direct_edit
        self.direct_edit.directEditUploadCompleted.connect(self.app.sync_completed)
        self.direct_edit.start()

        self.remote = self.remote_document_client_1
        self.local = LocalClient(os.path.join(self.nxdrive_conf_folder_1, 'edit'))

    def tearDownApp(self):
        self.direct_edit.stop()
        super(TestDirectEdit, self).tearDownApp()

    def test_binder(self):
        engine = self.manager_1._engines.items()[0][1]
        binder = engine.get_binder()
        assert repr(binder)
        assert not binder.server_version
        assert not binder.password
        assert not binder.pwd_update_required
        assert binder.server_url
        assert binder.username
        assert binder.initialized
        assert binder.local_folder

    def test_url_resolver(self):
        user = 'Administrator'
        get_engine = self.direct_edit._get_engine
        
        assert get_engine(self.nuxeo_url, self.user_1)

        self.manager_1._engine_types['NXDRIVETESTURL'] = MockUrlTestEngine

        # HTTP explicit
        self.manager_1._engines['0'] = MockUrlTestEngine('http://localhost:80/nuxeo')
        assert not get_engine('http://localhost:8080/nuxeo', user=user)
        assert get_engine('http://localhost:80/nuxeo', user=user)
        assert get_engine('http://localhost/nuxeo/', user=user)

        # HTTP implicit
        self.manager_1._engines['0'] = MockUrlTestEngine('http://localhost/nuxeo')
        assert not get_engine('http://localhost:8080/nuxeo', user=user)
        assert get_engine('http://localhost:80/nuxeo/', user=user)
        assert get_engine('http://localhost/nuxeo', user=user)

        # HTTPS explicit
        self.manager_1._engines['0'] = MockUrlTestEngine('https://localhost:443/nuxeo')
        assert not get_engine('http://localhost:8080/nuxeo', user=user)
        assert get_engine('https://localhost:443/nuxeo', user=user)
        assert get_engine('https://localhost/nuxeo/', user=user)

        # HTTPS implicit
        self.manager_1._engines['0'] = MockUrlTestEngine('https://localhost/nuxeo')
        assert not get_engine('http://localhost:8080/nuxeo', user=user)
        assert get_engine('https://localhost:443/nuxeo/', user=user)
        assert get_engine('https://localhost/nuxeo', user=user)

    def test_note_edit(self):
        remote_fs_client = self.remote_file_system_client_1
        toplevel_folder_info = remote_fs_client.get_filesystem_root_info()
        workspace_id = remote_fs_client.get_children_info(
            toplevel_folder_info.uid)[0].uid
        file_1_id = remote_fs_client.make_file(workspace_id, u'Mode op\xe9ratoire.txt',
                                               "Content of file 1 Avec des accents h\xe9h\xe9.").uid
        doc_id = file_1_id.split('#')[-1]
        self._direct_edit_update(doc_id, u'Mode op\xe9ratoire.txt', 'Atol de PomPom Gali')

    def test_filename_encoding(self):
        filename = u'Mode op\xe9ratoire.txt'
        doc_id = self.remote.make_file('/', filename, 'Some content.')
        self._direct_edit_update(doc_id, filename, 'Test')

    def _test_locked_file_signal(self):
        self._received = True

    def test_locked_file(self):
        self._received = False
        filename = u'Mode operatoire.txt'
        doc_id = self.remote.make_file('/', filename, 'Some content.')
        self.remote_document_client_2.lock(doc_id)
        self.direct_edit.directEditLocked.connect(self._test_locked_file_signal)
        self.direct_edit._prepare_edit(self.nuxeo_url, doc_id)
        self.assertTrue(self._received)

    def test_self_locked_file(self):
        filename = u'Mode operatoire.txt'
        doc_id = self.remote.make_file('/', filename, 'Some content.')
        self.remote.lock(doc_id)
        self._direct_edit_update(doc_id, filename, 'Test')

    def _direct_edit_update(self, doc_id, filename, content, url=None):
        # Download file
        local_path = u'/%s/%s' % (doc_id, filename)

        def open_local_file(_):
            pass

        self.manager_1.open_local_file = open_local_file
        if url is None:
            self.direct_edit._prepare_edit(self.nuxeo_url, doc_id)
        else:
            self.direct_edit.handle_url(url)
        self.assertTrue(self.local.exists(local_path))
        self.wait_sync(timeout=2, fail_if_timeout=False)
        self.local.delete_final(local_path)

        # Update file content
        self.local.update_content(local_path, content)
        self.wait_sync()
        self.assertEqual(self.remote.get_blob(self.remote.get_info(doc_id)), content)

        # Update file content twice
        update_content = content + ' updated'
        self.local.update_content(local_path, update_content)
        self.wait_sync()
        self.assertEqual(self.remote.get_blob(self.remote.get_info(doc_id)), update_content)

    def test_direct_edit_cleanup(self):
        filename = u'Mode op\xe9ratoire.txt'
        doc_id = self.remote.make_file('/', filename, 'Some content.')
        # Download file
        local_path = u'/%s/%s' % (doc_id, filename)

        def open_local_file(_):
            pass

        self.manager_1.open_local_file = open_local_file
        self.direct_edit._prepare_edit(self.nuxeo_url, doc_id)
        self.assertTrue(self.local.exists(local_path))
        self.wait_sync(timeout=2, fail_if_timeout=False)
        self.direct_edit.stop()

        # Update file content
        self.local.update_content(local_path, 'Test')
        # Create empty folder (NXDRIVE-598)
        self.local.make_folder('/', 'emptyfolder')

        # Verify the cleanup dont delete document
        self.direct_edit._cleanup()
        self.assertTrue(self.local.exists(local_path))
        self.assertNotEquals(self.remote.get_blob(self.remote.get_info(doc_id)), 'Test')

        # Verify it reupload it
        self.direct_edit.start()
        self.wait_sync(timeout=2, fail_if_timeout=False)
        self.assertTrue(self.local.exists(local_path))
        self.assertEqual(self.remote.get_blob(self.remote.get_info(doc_id)), 'Test')

        # Verify it is cleanup if sync
        self.direct_edit.stop()
        self.direct_edit._cleanup()
        self.assertFalse(self.local.exists(local_path))

    def test_user_name(self):
        # user_1 is drive_user_1, no more informations
        user = self.engine_1.get_user_full_name(self.user_1)
        self.assertEqual(user, self.user_1)

        # Create a complete user
        remote = self.root_remote_client
        remote.create_user('john', firstName='John', lastName='Doe')
        user = self.engine_1.get_user_full_name('john')
        self.assertEqual(user, 'John Doe')

        # Unknown user
        user = self.engine_1.get_user_full_name('unknown')
        self.assertEqual(user, 'unknown')
