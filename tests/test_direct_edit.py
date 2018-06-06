# coding: utf-8
import os

import pytest
from mock import patch

from nuxeo.exceptions import HTTPError
from nuxeo.models import User

from nxdrive.client import LocalClient
from nxdrive.engine.engine import Engine, ServerBindingSettings
from .common import UnitTestCase


class MockUrlTestEngine(Engine):
    def __init__(self, url):
        self._url = url
        self._invalid_credentials = False

    def get_binder(self):
        return ServerBindingSettings(
            server_url=self._url,
            web_authentication=None,
            username='Administrator',
            local_folder='/',
            initialized=True,
        )


class TestDirectEdit(UnitTestCase):

    def setUpApp(self, *args):
        super().setUpApp()
        self.direct_edit = self.manager_1.direct_edit
        self.direct_edit.directEditUploadCompleted.connect(
            self.app.sync_completed)
        self.direct_edit.start()

        self.remote = self.remote_document_client_1
        self.local = LocalClient(os.path.join(self.nxdrive_conf_folder_1, 'edit'))

    def tearDownApp(self):
        self.direct_edit.stop()
        super().tearDownApp()

    def test_binder(self):
        engine = list(self.manager_1._engines.items())[0][1]
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
        
        assert get_engine(pytest.nuxeo_url, self.user_1)

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
        remote = self.remote_1
        info = remote.get_filesystem_root_info()
        workspace_id = remote.get_fs_children(info.uid)[0].uid
        content = 'Content of file 1 Avec des accents h\xe9h\xe9.'.encode()
        file_id = remote.make_file(
            workspace_id, 'Mode op\xe9ratoire.txt', content=content).uid
        doc_id = file_id.split('#')[-1]
        self._direct_edit_update(
            doc_id, 'Mode op\xe9ratoire.txt', b'Atol de PomPom Gali')

    def test_filename_encoding(self):
        filename = 'Mode op\xe9ratoire.txt'
        doc_id = self.remote.make_file('/', filename, content=b'Some content.')
        self._direct_edit_update(doc_id, filename, b'Test')

    def _test_locked_file_signal(self):
        self._received = True

    def test_locked_file(self):
        self._received = False
        filename = 'Mode operatoire.txt'
        doc_id = self.remote.make_file('/', filename, 'Some content.')
        self.remote_document_client_2.lock(doc_id)
        self.direct_edit.directEditLocked.connect(
            self._test_locked_file_signal)
        self.direct_edit._prepare_edit(pytest.nuxeo_url, doc_id)
        assert self._received

    def test_self_locked_file(self):
        filename = 'Mode operatoire.txt'
        doc_id = self.remote.make_file('/', filename, content=b'Some content.')
        self.remote.lock(doc_id)
        self._direct_edit_update(doc_id, filename, b'Test')

    def _direct_edit_update(
        self,
        doc_id: str,
        filename: str,
        content: bytes,
        url: str=None,
    ):
        # Download file
        local_path = '/%s/%s' % (doc_id, filename)

        def open_local_file(*args, **kwargs):
            pass

        with patch.object(self.manager_1, 'open_local_file',
                          new=open_local_file):
            if url is None:
                self.direct_edit._prepare_edit(pytest.nuxeo_url, doc_id)
            else:
                self.direct_edit.handle_url(url)
            assert self.local.exists(local_path)
            self.wait_sync(fail_if_timeout=False)
            self.local.delete_final(local_path)

            # Update file content
            self.local.update_content(local_path, content)
            self.wait_sync()
            assert self.remote.get_blob(self.remote.get_info(doc_id)) == content

            # Update file content twice
            content += b' updated'
            self.local.update_content(local_path, content)
            self.wait_sync()
            assert self.remote.get_blob(self.remote.get_info(doc_id)) == content

    def test_direct_edit_cleanup(self):
        filename = 'Mode op\xe9ratoire.txt'
        doc_id = self.remote.make_file('/', filename, content=b'Some content.')
        # Download file
        local_path = '/%s/%s' % (doc_id, filename)

        def open_local_file(*args, **kwargs):
            pass

        with patch.object(self.manager_1, 'open_local_file',
                          new=open_local_file):
            self.direct_edit._prepare_edit(pytest.nuxeo_url, doc_id)
            assert self.local.exists(local_path)
            self.wait_sync(timeout=2, fail_if_timeout=False)
            self.direct_edit.stop()

            # Update file content
            self.local.update_content(local_path, b'Test')
            # Create empty folder (NXDRIVE-598)
            self.local.make_folder('/', 'emptyfolder')

            # Verify the cleanup dont delete document
            self.direct_edit._cleanup()
            assert self.local.exists(local_path)
            assert self.remote.get_blob(self.remote.get_info(doc_id)) != b'Test'

            # Verify it reupload it
            self.direct_edit.start()
            self.wait_sync(timeout=2, fail_if_timeout=False)
            assert self.local.exists(local_path)
            assert self.remote.get_blob(self.remote.get_info(doc_id)) == b'Test'

            # Verify it is cleanup if sync
            self.direct_edit.stop()
            self.direct_edit._cleanup()
            assert not self.local.exists(local_path)

    def test_user_name(self):
        # user_1 is drive_user_1, no more informations
        user = self.engine_1.get_user_full_name(self.user_1)
        assert user == self.user_1

        # Create a complete user
        remote = self.root_remote
        try:
            user = remote.users.create(User(properties={
                'username': 'john', 'firstName': 'John', 'lastName': 'Doe'}))
        except HTTPError as exc:
            if exc.status != 409:
                raise
            user = remote.users.get('john')

        try:
            username = self.engine_1.get_user_full_name('john')
            assert username == 'John Doe'
        finally:
            user.delete()

        # Unknown user
        username = self.engine_1.get_user_full_name('unknown')
        assert username == 'unknown'

    def test_download_url_with_spaces(self):
        scheme, host = pytest.nuxeo_url.split('://')
        filename = 'My file with spaces.txt'
        doc_id = self.remote.make_file('/', filename, content=b'Some content.')

        url = ('nxdrive://edit/{scheme}/{host}'
               '/user/{user}'
               '/repo/default'
               '/nxdocid/{doc_id}'
               '/filename/{filename}'
               '/downloadUrl/nxfile/default/{doc_id}'
               '/file:content/{filename}').format(
            scheme=scheme, host=host, user=self.user_1,
            doc_id=doc_id, filename=filename)

        self._direct_edit_update(doc_id, filename, b'Test', url)

    def test_download_url_with_accents(self):
        scheme, host = pytest.nuxeo_url.split('://')
        filename = 'éèáä.txt'
        doc_id = self.remote.make_file('/', filename, content=b'Some content.')

        url = ('nxdrive://edit/{scheme}/{host}'
               '/user/{user}'
               '/repo/default'
               '/nxdocid/{doc_id}'
               '/filename/{filename}'
               '/downloadUrl/nxfile/default/{doc_id}'
               '/file:content/{filename}').format(
            scheme=scheme, host=host, user=self.user_1,
            doc_id=doc_id, filename=filename)

        self._direct_edit_update(doc_id, filename, b'Test', url)

    def test_download_url_missing_username(self):
        """ The username must be in the URL. """
        url = ('nxdrive://edit/https/server.cloud.nuxeo.com/nuxeo'
               '/repo/default'
               '/nxdocid/xxxxxxxx-xxxx-xxxx-xxxx'
               '/filename/lebron-james-beats-by-dre-powerb.psd'
               '/downloadUrl/nxfile/default/xxxxxxxx-xxxx-xxxx-xxxx'
               '/file:content/lebron-james-beats-by-dre-powerb.psd')
        with pytest.raises(ValueError):
            self._direct_edit_update('', '', b'', url)
