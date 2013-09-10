"""Common test utilities"""
import os
import unittest
import tempfile
import hashlib
import shutil

from nxdrive.utils import safe_long_path
from nxdrive.model import LastKnownState
from nxdrive.client import RemoteDocumentClient
from nxdrive.client import RemoteFileSystemClient
from nxdrive.controller import Controller


class IntegrationTestCase(unittest.TestCase):

    TEST_WORKSPACE_PATH = (
        u'/default-domain/workspaces/nuxeo-drive-test-workspace')
    FS_ITEM_ID_PREFIX = u'defaultFileSystemItemFactory#default#'

    EMPTY_DIGEST = hashlib.md5().hexdigest()
    SOME_TEXT_CONTENT = b"Some text content."
    SOME_TEXT_DIGEST = hashlib.md5(SOME_TEXT_CONTENT).hexdigest()

    # 1s time resolution because of the datetime resolution of MYSQL
    AUDIT_CHANGE_FINDER_TIME_RESOLUTION = 1.0

    # 1s resolution on HFS+ on OSX
    # 2s resolution on FAT but can be ignored as no Jenkins is running the test
    # suite under windows on FAT partitions
    # ~0.01s resolution for NTFS
    # 0.001s for EXT4FS
    OS_STAT_MTIME_RESOLUTION = 1.0

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
        root_remote_client = RemoteDocumentClient(
            self.nuxeo_url, self.admin_user,
            u'nxdrive-test-administrator-device',
            self.password, base_folder=u'/', timeout=60)

        # Call the Nuxeo operation to setup the integration test environment
        credentials = root_remote_client.execute(
            "NuxeoDrive.SetupIntegrationTests",
            userNames="user_1, user_2")

        credentials = [c.strip().split(u":") for c in credentials.split(u",")]
        self.user_1, self.password_1 = credentials[0]
        self.user_2, self.password_2 = credentials[1]

        ws_info = root_remote_client.fetch(self.TEST_WORKSPACE_PATH)
        self.workspace = ws_info[u'uid']
        self.workspace_title = ws_info[u'title']

        # Document client to be used to create remote test documents
        # and folders
        self.upload_tmp_dir = tempfile.mkdtemp(u'-nxdrive-uploads')
        remote_document_client_1 = RemoteDocumentClient(
            self.nuxeo_url, self.user_1, u'nxdrive-test-device-1',
            self.password_1, base_folder=self.workspace,
            upload_tmp_dir=self.upload_tmp_dir)

        remote_document_client_2 = RemoteDocumentClient(
            self.nuxeo_url, self.user_2, u'nxdrive-test-device-2',
            self.password_2, base_folder=self.workspace,
            upload_tmp_dir=self.upload_tmp_dir)

        # File system client to be used to create remote test documents
        # and folders
        remote_file_system_client_1 = RemoteFileSystemClient(
            self.nuxeo_url, self.user_1, u'nxdrive-test-device-1',
            self.password_1, upload_tmp_dir=self.upload_tmp_dir)

        remote_file_system_client_2 = RemoteFileSystemClient(
            self.nuxeo_url, self.user_2, u'nxdrive-test-device-2',
            self.password_2, upload_tmp_dir=self.upload_tmp_dir)

        # Check the local filesystem test environment
        self.local_test_folder_1 = tempfile.mkdtemp(u'-nxdrive-tests-user-1')
        self.local_test_folder_2 = tempfile.mkdtemp(u'-nxdrive-tests-user-2')

        self.local_nxdrive_folder_1 = os.path.join(
            self.local_test_folder_1, u'Nuxeo Drive')
        os.mkdir(self.local_nxdrive_folder_1)
        self.local_nxdrive_folder_2 = os.path.join(
            self.local_test_folder_2, u'Nuxeo Drive')
        os.mkdir(self.local_nxdrive_folder_2)

        self.nxdrive_conf_folder_1 = os.path.join(
            self.local_test_folder_1, u'nuxeo-drive-conf')
        os.mkdir(self.nxdrive_conf_folder_1)

        self.nxdrive_conf_folder_2 = os.path.join(
            self.local_test_folder_2, u'nuxeo-drive-conf')
        os.mkdir(self.nxdrive_conf_folder_2)

        # set echo to true for enabling sql statements logging 
        self.controller_1 = Controller(self.nxdrive_conf_folder_1, echo=False) 
        self.controller_2 = Controller(self.nxdrive_conf_folder_2, echo=False)
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
        self.root_remote_client.execute(u"NuxeoDrive.TearDownIntegrationTests")

        self.root_remote_client.revoke_token()

        if os.path.exists(self.upload_tmp_dir):
            shutil.rmtree(safe_long_path(self.upload_tmp_dir))

        if os.path.exists(self.local_test_folder_1):
            self.controller_1.dispose()
            shutil.rmtree(safe_long_path(self.local_test_folder_1))

        if os.path.exists(self.local_test_folder_2):
            self.controller_2.dispose()
            shutil.rmtree(safe_long_path(self.local_test_folder_2))

    def get_all_states(self, session=None):
        """Utility to quickly introspect the current known states"""
        if session is None:
            session = self.controller_1.get_session()
        pairs = session.query(LastKnownState).order_by(
            LastKnownState.local_path,
            LastKnownState.remote_parent_path,
            LastKnownState.remote_name).all()
        return [(p.local_path, p.local_state, p.remote_state) for p in pairs]

    def make_server_tree(self):
        remote_client = self.remote_document_client_1
        # create some folders on the server
        folder_1 = remote_client.make_folder(self.workspace, u'Folder 1')
        folder_1_1 = remote_client.make_folder(folder_1, u'Folder 1.1')
        folder_1_2 = remote_client.make_folder(folder_1, u'Folder 1.2')
        folder_2 = remote_client.make_folder(self.workspace, u'Folder 2')

        # create some files on the server
        remote_client.make_file(folder_2, u'Duplicated File.txt',
                                content=b"Some content.")
        remote_client.make_file(folder_2, u'Duplicated File.txt',
                                content=b"Other content.")

        remote_client.make_file(folder_1, u'File 1.txt', content=b"aaa")
        remote_client.make_file(folder_1_1, u'File 2.txt', content=b"bbb")
        remote_client.make_file(folder_1_2, u'File 3.txt', content=b"ccc")
        remote_client.make_file(folder_2, u'File 4.txt', content=b"ddd")
        remote_client.make_file(self.workspace, u'File 5.txt', content=b"eee")

    def wait(self):
        self.root_remote_client.wait()
