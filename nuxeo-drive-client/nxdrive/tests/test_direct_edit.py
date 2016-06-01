import os

from nxdrive.client import LocalClient
from nxdrive.client.common import LOCALLY_EDITED_FOLDER_NAME
from nxdrive.tests.common_unit_test import UnitTestCase
from nxdrive.engine.engine import Engine

DRIVE_EDIT_XATTR_NAMES = ['ndrive', 'nxdriveedit', 'nxdriveeditdigest', 'nxdriveeditname']

class MockUrlTestEngine(Engine):
    def __init__(self, url):
        self._url = url

    def get_binder(self):
        from nxdrive.manager import ServerBindingSettings
        return ServerBindingSettings(server_url=self._url,
                        web_authentication=None,
                        server_version=None,
                        username='Administrator',
                        local_folder='/',
                        initialized=True,
                        pwd_update_required=False)


class TestDirectEdit(UnitTestCase):

    locally_edited_path = ('/default-domain/UserWorkspaces/'
                           + 'nuxeoDriveTestUser-user-1/Collections/'
                           + LOCALLY_EDITED_FOLDER_NAME)

    def setUpApp(self):
        super(TestDirectEdit, self).setUpApp()
        self.direct_edit = self.manager_1.get_direct_edit()
        self.direct_edit.directEditUploadCompleted.connect(self.app.sync_completed)
        self.direct_edit.start()

        self.remote = self.remote_document_client_1
        self.local = LocalClient(os.path.join(self.nxdrive_conf_folder_1, 'edit'))

    def tearDownApp(self):
        self.direct_edit.stop()
        super(TestDirectEdit, self).tearDownApp()

    def test_url_resolver(self):
        self.assertIsNotNone(self.direct_edit._get_engine("http://localhost:8080/nuxeo", self.user_1))
        self.assertIsNone(self.direct_edit._get_engine("http://localhost:8080/nuxeo", u'Administrator'))
        self.manager_1._engine_types['NXDRIVETESTURL'] = MockUrlTestEngine
        # HTTP EXPLICIT
        self.manager_1._engines['0'] = MockUrlTestEngine('http://localhost:80/nuxeo')
        self.assertIsNone(self.direct_edit._get_engine("http://localhost:8080/nuxeo", u'Administrator'))
        self.assertIsNotNone(self.direct_edit._get_engine("http://localhost:80/nuxeo", u'Administrator'))
        self.assertIsNotNone(self.direct_edit._get_engine("http://localhost/nuxeo/", u'Administrator'))
        # HTTP IMPLICIT
        self.manager_1._engines['0'] = MockUrlTestEngine('http://localhost/nuxeo')
        self.assertIsNone(self.direct_edit._get_engine("http://localhost:8080/nuxeo", u'Administrator'))
        self.assertIsNotNone(self.direct_edit._get_engine("http://localhost:80/nuxeo/", u'Administrator'))
        self.assertIsNotNone(self.direct_edit._get_engine("http://localhost/nuxeo", u'Administrator'))
        # HTTPS EXPLICIT
        self.manager_1._engines['0'] = MockUrlTestEngine('https://localhost:443/nuxeo')
        self.assertIsNone(self.direct_edit._get_engine("http://localhost:8080/nuxeo", u'Administrator'))
        self.assertIsNotNone(self.direct_edit._get_engine("https://localhost:443/nuxeo", u'Administrator'))
        self.assertIsNotNone(self.direct_edit._get_engine("https://localhost/nuxeo/", u'Administrator'))
        # HTTPS IMPLICIT
        self.manager_1._engines['0'] = MockUrlTestEngine('https://localhost/nuxeo')
        self.assertIsNone(self.direct_edit._get_engine("http://localhost:8080/nuxeo", u'Administrator'))
        self.assertIsNotNone(self.direct_edit._get_engine("https://localhost:443/nuxeo/", u'Administrator'))
        self.assertIsNotNone(self.direct_edit._get_engine("https://localhost/nuxeo", u'Administrator'))

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

    def _office_locker(self, path):
        return os.path.join(os.path.dirname(path), "~$" + os.path.basename(path)[2:])

    def _openoffice_locker(self, path):
        return os.path.join(os.path.dirname(path), ".~lock." + os.path.basename(path)[2:])

#     def test_autolock_office(self):
#         self._autolock(self._office_locker)

#     def test_autolock_openoffice(self):
#      LibreOffice as well
#         self._autolock(self._openoffice_locker)

    def _autolock(self, locker):
        global called_open, lock_file
        called_open = False
        filename = u'Document.docx'
        doc_id = self.remote.make_file('/', filename, 'Some content.')

        def open_local_file(path):
            global called_open, lock_file
            called_open = True
            # Lock file
            lock_file = locker(path)
            with open(lock_file, 'w') as f:
                f.write("plop")

        self.manager_1.open_local_file = open_local_file
        self.manager_1.set_direct_edit_auto_lock(1)
        self.direct_edit._manager.open_local_file = open_local_file
        self.direct_edit.edit(self.nuxeo_url, doc_id, filename=filename, user=self.user_1)
        self.wait_sync(timeout=2, fail_if_timeout=False)
        self.assertTrue(called_open, "Should have called open_local_file")
        # Should be able to test lock
        self.assertTrue(self.remote_restapi_client_1.is_locked(doc_id))
        os.remove(lock_file)
        self.wait_sync(timeout=2, fail_if_timeout=False)
        # Should be unlock
        self.assertFalse(self.remote_restapi_client_1.is_locked(doc_id))
        self.manager_1.set_direct_edit_auto_lock(0)
        with open(lock_file, 'w') as f:
            f.write("plop")
        self.wait_sync(timeout=2, fail_if_timeout=False)
        self.assertFalse(self.remote_restapi_client_1.is_locked(doc_id))

    def _direct_edit_update(self, doc_id, filename, content, url=None):
        # Download file
        local_path = u'/%s/%s' % (doc_id, filename)

        def open_local_file(path):
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
        self.assertEquals(self.remote.get_blob(self.remote.get_info(doc_id)), content)

        # Update file content twice
        update_content = content + ' updated'
        self.local.update_content(local_path, update_content)
        self.wait_sync()
        self.assertEquals(self.remote.get_blob(self.remote.get_info(doc_id)), update_content)


    def test_direct_edit_cleanup(self):
        filename = u'Mode op\xe9ratoire.txt'
        doc_id = self.remote.make_file('/', filename, 'Some content.')
        # Download file
        local_path = u'/%s/%s' % (doc_id, filename)

        def open_local_file(path):
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
        self.assertEquals(self.remote.get_blob(self.remote.get_info(doc_id)), 'Test')

        # Verify it is cleanup if sync
        self.direct_edit.stop()
        self.direct_edit._cleanup()
        self.assertFalse(self.local.exists(local_path))
