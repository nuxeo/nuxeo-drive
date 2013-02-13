"""Common test utilities"""
import os
import unittest
import tempfile
import hashlib
import shutil

from nxdrive.model import LastKnownState
from nxdrive.client import NuxeoClient
from nxdrive.controller import Controller
from nxdrive.client.remote_file_system_client import RemoteFileSystemClient


class IntegrationTestCase(unittest.TestCase):

    TEST_WORKSPACE_PATH = '/default-domain/workspaces/nuxeo-drive-test-workspace'

    EMPTY_DIGEST = hashlib.md5().hexdigest()
    SOME_TEXT_CONTENT = "Some text content."
    SOME_TEXT_DIGEST = hashlib.md5(SOME_TEXT_CONTENT).hexdigest()

    def setUp(self):
        # Check the Nuxeo server test environment
        self.nuxeo_url = os.environ.get('NXDRIVE_TEST_NUXEO_URL')
        self.admin_user = os.environ.get('NXDRIVE_TEST_USER')
        self.password = os.environ.get('NXDRIVE_TEST_PASSWORD')

        if None in (self.nuxeo_url, self.admin_user, self.password):
            raise unittest.SkipTest(
                "No integration server configuration found in environment.")

        # Long timeout for the root client that is responsible for the test
        # environment set: this client is doing the first query on the Nuxeo
        # server and might need to wait for a long time without failing for
        # Nuxeo to finish initialize the repo on the first request after
        # startup
        root_remote_client = NuxeoClient(
            self.nuxeo_url, self.admin_user, 'nxdrive-test-administrator-device',
            self.password, base_folder='/', timeout=60)

        # Call the Nuxeo operation to setup the integration test environment
        credentials = root_remote_client.execute(
            "NuxeoDrive.SetupIntegrationTests",
            userNames="user_1, user_2")

        credentials = [c.strip().split(":") for c in credentials.split(",")]
        self.user_1, self.password_1 = credentials[0]
        self.user_2, self.password_2 = credentials[1]

        ws_info = root_remote_client.fetch(self.TEST_WORKSPACE_PATH)
        self.workspace = ws_info['uid']
        self.workspace_title = ws_info['title']

        # Document client to be used to create remote test documents
        # and folders
        remote_document_client_1 = NuxeoClient(
            self.nuxeo_url, self.user_1, 'nxdrive-test-device-1',
            self.password_1, base_folder=self.workspace)

        remote_document_client_2 = NuxeoClient(
            self.nuxeo_url, self.user_2, 'nxdrive-test-device-2',
            self.password_2, base_folder=self.workspace)

        # File system client to be used to create remote test documents
        # and folders
        remote_file_system_client_1 = RemoteFileSystemClient(
            self.nuxeo_url, self.user_1, 'nxdrive-test-device-1',
            self.password_1)

        remote_file_system_client_2 = RemoteFileSystemClient(
            self.nuxeo_url, self.user_2, 'nxdrive-test-device-2',
            self.password_2)

        # Check the local filesystem test environment
        self.local_test_folder_1 = tempfile.mkdtemp('-nxdrive-tests-user-1')
        self.local_test_folder_2 = tempfile.mkdtemp('-nxdrive-tests-user-2')

        self.local_nxdrive_folder_1 = os.path.join(
            self.local_test_folder_1, 'Nuxeo Drive')
        os.mkdir(self.local_nxdrive_folder_1)
        self.local_nxdrive_folder_2 = os.path.join(
            self.local_test_folder_2, 'Nuxeo Drive')
        os.mkdir(self.local_nxdrive_folder_2)

        nxdrive_conf_folder_1 = os.path.join(
            self.local_test_folder_1, 'nuxeo-drive-conf')
        os.mkdir(nxdrive_conf_folder_1)

        nxdrive_conf_folder_2 = os.path.join(
            self.local_test_folder_2, 'nuxeo-drive-conf')
        os.mkdir(nxdrive_conf_folder_2)

        self.controller_1 = Controller(nxdrive_conf_folder_1)
        self.controller_2 = Controller(nxdrive_conf_folder_2)
        self.root_remote_client = root_remote_client
        self.remote_document_client_1 = remote_document_client_1
        self.remote_document_client_2 = remote_document_client_2
        self.remote_file_system_client_1 = remote_file_system_client_1
        self.remote_file_system_client_2 = remote_file_system_client_2

    def tearDown(self):
        self.controller_1.unbind_all()
        self.controller_2.unbind_all()
        self.remote_document_client_1.revoke_token()
        self.remote_document_client_2.revoke_token()
        # Don't need to revoke tokens for the file system remote clients
        # since they use the same users as the remote document clients
        self.root_remote_client.execute("NuxeoDrive.TearDownIntegrationTests")

        self.root_remote_client.revoke_token()

        if os.path.exists(self.local_test_folder_1):
            self.controller_1.dispose()
            shutil.rmtree(self.local_test_folder_1)

        if os.path.exists(self.local_test_folder_2):
            self.controller_2.dispose()
            shutil.rmtree(self.local_test_folder_2)

    def get_all_states(self, session=None):
        """Utility to quickly introspect the current known states"""
        if session is None:
            session = self.controller_1.get_session()
        pairs = session.query(LastKnownState).order_by(LastKnownState.path).all()
        return [(p.path, p.local_state, p.remote_state) for p in pairs]

    def make_server_tree(self):
        remote_client = self.remote_document_client_1
        # create some folders on the server
        folder_1 = remote_client.make_folder(self.workspace, 'Folder 1')
        folder_1_1 = remote_client.make_folder(folder_1, 'Folder 1.1')
        folder_1_2 = remote_client.make_folder(folder_1, 'Folder 1.2')
        folder_2 = remote_client.make_folder(self.workspace, 'Folder 2')

        # create some files on the server
        remote_client.make_file(folder_2, 'Duplicated File.txt',
                                content="Some content.")
        remote_client.make_file(folder_2, 'Duplicated File.txt',
                                content="Other content.")

        remote_client.make_file(folder_1, 'File 1.txt', content="aaa")
        remote_client.make_file(folder_1_1, 'File 2.txt', content="bbb")
        remote_client.make_file(folder_1_2, 'File 3.txt', content="ccc")
        remote_client.make_file(folder_2, 'File 4.txt', content="ddd")
        remote_client.make_file(self.workspace, 'File 5.txt', content="eee")

    def wait(self):
        self.root_remote_client.wait()
