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
        self.user = os.environ.get('NXDRIVE_TEST_USER')
        self.password = os.environ.get('NXDRIVE_TEST_PASSWORD')
        if None in (self.nuxeo_url, self.user, self.password):
            raise unittest.SkipTest(
                "No integration server configuration found in environment.")

        parent_path = os.path.dirname(self.TEST_WORKSPACE_PATH)
        workspace_name = os.path.basename(self.TEST_WORKSPACE_PATH)
        root_remote_client = NuxeoClient(
            self.nuxeo_url, self.user, 'test-device',
            self.password, base_folder='/')

        self.workspace = root_remote_client.create(
            parent_path, 'Workspace', name=workspace_name,
            properties={'dc:title': self.TEST_WORKSPACE_TITLE})[u'uid']

        # Client to be use to create remote test documents and folders
        remote_client = NuxeoClient(self.nuxeo_url, self.user, 'test-device',
                                    self.password, base_folder=self.workspace)

        # Check the local filesystem test environment
        self.local_test_folder = tempfile.mkdtemp('-nuxeo-drive-tests')

        self.local_nxdrive_folder = os.path.join(
            self.local_test_folder, 'Nuxeo Drive')
        os.mkdir(self.local_nxdrive_folder)

        LOCAL_NXDRIVE_CONF_FOLDER = os.path.join(
            self.local_test_folder, 'nuxeo-drive-conf')
        os.mkdir(LOCAL_NXDRIVE_CONF_FOLDER)

        self.ctl = Controller(LOCAL_NXDRIVE_CONF_FOLDER)
        self.remote_client = remote_client

    def tearDown(self):
        remote_client = self.remote_client
        ctl = self.ctl
        if ctl is not None:
            ctl.unbind_all()
            ctl.dispose()

        if remote_client is not None and remote_client.exists(self.workspace):
            remote_client.delete(self.workspace, use_trash=False)

        if remote_client is not None:
            remote_client.revoke_token()

        if os.path.exists(self.local_test_folder):
            shutil.rmtree(self.local_test_folder)

    def get_all_states(self, session=None):
        """Utility to quickly introspect the current known states"""
        session = session if session is not None else self.ctl.get_session()
        pairs = self.ctl.get_session().query(
            LastKnownState).order_by(LastKnownState.path).all()
        return [(p.path, p.local_state, p.remote_state) for p in pairs]

    def make_server_tree(self):
        remote_client = self.remote_client
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


