"""Common test utilities"""
import os
import unittest
import tempfile
import hashlib
import shutil

from nxdrive.model import LastKnownState
from nxdrive.client import NuxeoClient
from nxdrive.controller import Controller


class IntegrationTestCase(unittest.TestCase):

    TEST_WORKSPACE_PATH = '/default-domain/workspaces/test-nxdrive'
    TEST_WORKSPACE_TITLE = 'Nuxeo Drive Tests'

    EMPTY_DIGEST = hashlib.md5().hexdigest()
    SOME_TEXT_CONTENT = "Some text content."
    SOME_TEXT_DIGEST = hashlib.md5(SOME_TEXT_CONTENT).hexdigest()

    def setUp(self):
        # Check the Nuxeo server test environment
        self.nuxeo_url = os.environ.get('NXDRIVE_TEST_NUXEO_URL')
        self.admin_user = os.environ.get('NXDRIVE_TEST_USER')
        self.password = os.environ.get('NXDRIVE_TEST_PASSWORD')

        # TODO: use different users for the actual clients
        self.user_1 = self.admin_user
        self.password_1 = self.password
        self.user_2 = self.admin_user
        self.password_2 = self.password

        if None in (self.nuxeo_url, self.admin_user, self.password):
            raise unittest.SkipTest(
                "No integration server configuration found in environment.")

        parent_path = os.path.dirname(self.TEST_WORKSPACE_PATH)
        workspace_name = os.path.basename(self.TEST_WORKSPACE_PATH)
        root_remote_client = NuxeoClient(
            self.nuxeo_url, self.admin_user, 'test-device',
            self.password, base_folder='/')

        self.workspace = root_remote_client.create(
            parent_path, 'Workspace', name=workspace_name,
            properties={'dc:title': self.TEST_WORKSPACE_TITLE})[u'uid']

        # Client to be use to create remote test documents and folders
        remote_client_1 = NuxeoClient(self.nuxeo_url, self.user_1, 'test-device-1',
                                    self.password_1, base_folder=self.workspace)

        remote_client_2 = NuxeoClient(self.nuxeo_url, self.user_2, 'test-device-2',
                                    self.password_2, base_folder=self.workspace)

        # Check the local filesystem test environment
        self.local_test_folder_1 = tempfile.mkdtemp('-nuxeo-drive-tests-user-1')
        self.local_test_folder_2 = tempfile.mkdtemp('-nuxeo-drive-tests-user-2')

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
        self.remote_client_1 = remote_client_1
        self.remote_client_2 = remote_client_2

    def tearDown(self):
        if self.controller_1 is not None:
            self.controller_1.unbind_all()
            self.controller_1.dispose()

        if (self.remote_client_1 is not None
            and self.remote_client_1.exists(self.workspace)):
            self.remote_client_1.delete(self.workspace, use_trash=False)

        if self.remote_client_1 is not None:
            self.remote_client_1.revoke_token()

        if os.path.exists(self.local_test_folder_1):
            shutil.rmtree(self.local_test_folder_1)

        if os.path.exists(self.local_test_folder_2):
            shutil.rmtree(self.local_test_folder_2)

    def get_all_states(self, session=None):
        """Utility to quickly introspect the current known states"""
        if session is None:
            session = self.controller_1.get_session()
        pairs = session.query(LastKnownState).order_by(LastKnownState.path).all()
        return [(p.path, p.local_state, p.remote_state) for p in pairs]

    def make_server_tree(self):
        remote_client = self.remote_client_1
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


