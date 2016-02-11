"""Common test utilities"""
import sys
import os
import unittest
import tempfile
import hashlib
import shutil

import nxdrive
from nxdrive.utils import safe_long_path
from nxdrive.client import RemoteDocumentClient
from nxdrive.client import RemoteFileSystemClient
from nxdrive.client import RestAPIClient
from nxdrive.client import LocalClient
from nxdrive.client.common import BaseClient
from nxdrive.logging_config import configure
from nxdrive.logging_config import get_logger

WindowsError = None
try:
    from exceptions import WindowsError
except ImportError:
    pass  # This will never be raised under Unix

DEFAULT_CONSOLE_LOG_LEVEL = 'DEBUG'

# Default remote watcher delay used for tests
TEST_DEFAULT_DELAY = 3

TEST_WORKSPACE_PATH = (
    u'/default-domain/workspaces/nuxeo-drive-test-workspace')
FS_ITEM_ID_PREFIX = u'defaultFileSystemItemFactory#default#'

EMPTY_DIGEST = hashlib.md5().hexdigest()
SOME_TEXT_CONTENT = b"Some text content."
SOME_TEXT_DIGEST = hashlib.md5(SOME_TEXT_CONTENT).hexdigest()

# 1s time resolution as we truncate remote last modification time to the
# seconds in RemoteFileSystemClient.file_to_info() because of the datetime
# resolution of some databases (MySQL...)
REMOTE_MODIFICATION_TIME_RESOLUTION = 1.0

# 1s resolution on HFS+ on OSX
# 2s resolution on FAT but can be ignored as no Jenkins is running the test
# suite under windows on FAT partitions
# ~0.01s resolution for NTFS
# 0.001s for EXT4FS
OS_STAT_MTIME_RESOLUTION = 1.0

# Nuxeo max length for document name
DOC_NAME_MAX_LENGTH = 24

# Default quit timeout used for tests
# 6s for watcher / 9s for sync
TEST_DEFAULT_QUIT_TIMEOUT = 30


def configure_logger():
    configure(
        console_level=DEFAULT_CONSOLE_LOG_LEVEL,
        command_name='test',
    )

# Configure test logger
configure_logger()
log = get_logger(__name__)


def execute(cmd, exit_on_failure=True):
    log.debug("Launched command: %s", cmd)
    code = os.system(cmd)
    if hasattr(os, 'WEXITSTATUS'):
        # Find the exit code in from the POSIX status that also include
        # the kill signal if any (only under POSIX)
        code = os.WEXITSTATUS(code)
    if code != 0 and exit_on_failure:
        log.error("Command %s returned with code %d", cmd, code)
        sys.exit(code)


def clean_dir(_dir):
    if os.path.exists(_dir):
        to_remove = safe_long_path(_dir)
        if "TEST_SAVE_DATA" in os.environ:
            shutil.move(to_remove, os.environ["TEST_SAVE_DATA"])
            return
        try:
            for dirpath, dirnames, filenames in os.walk(to_remove):
                for dirname in dirnames:
                    BaseClient.unset_path_readonly(os.path.join(dirpath, dirname))
                for filename in filenames:
                    BaseClient.unset_path_readonly(os.path.join(dirpath, filename))
            shutil.rmtree(to_remove)
        except Exception as e:
            if type(e) == WindowsError:
                os.system('rmdir /S /Q %s' % to_remove)


class IntegrationTestCase(unittest.TestCase):

    def setUp(self):
        # Check the Nuxeo server test environment
        self.nuxeo_url = os.environ.get('NXDRIVE_TEST_NUXEO_URL')
        self.admin_user = os.environ.get('NXDRIVE_TEST_USER')
        self.password = os.environ.get('NXDRIVE_TEST_PASSWORD')
        self.build_workspace = os.environ.get('WORKSPACE')

        # Take default parameter if none has been set
        if self.nuxeo_url is None:
            self.nuxeo_url = "http://localhost:8080/nuxeo"
        if self.admin_user is None:
            self.admin_user = "Administrator"
        if self.password is None:
            self.password = "Administrator"
        self.tmpdir = None
        if self.build_workspace is not None:
            self.tmpdir = os.path.join(self.build_workspace, "tmp")
            if not os.path.isdir(self.tmpdir):
                os.makedirs(self.tmpdir)

        if None in (self.nuxeo_url, self.admin_user, self.password):
            raise unittest.SkipTest(
                "No integration server configuration found in environment.")

        self.full_nuxeo_url = self.nuxeo_url
        if '#' in self.nuxeo_url:
            self.nuxeo_url = self.nuxeo_url.split('#')[0]
        # Check the local filesystem test environment
        self.local_test_folder_1 = tempfile.mkdtemp(u'-nxdrive-tests-user-1', dir=self.tmpdir)
        self.local_test_folder_2 = tempfile.mkdtemp(u'-nxdrive-tests-user-2', dir=self.tmpdir)

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

        self.version = nxdrive.__version__

        # Long timeout for the root client that is responsible for the test
        # environment set: this client is doing the first query on the Nuxeo
        # server and might need to wait for a long time without failing for
        # Nuxeo to finish initialize the repo on the first request after
        # startup
        root_remote_client = RemoteDocumentClient(
            self.nuxeo_url, self.admin_user,
            u'nxdrive-test-administrator-device', self.version,
            password=self.password, base_folder=u'/', timeout=60)

        # Call the Nuxeo operation to setup the integration test environment
        credentials = root_remote_client.execute(
            "NuxeoDrive.SetupIntegrationTests",
            userNames="user_1, user_2", permission='ReadWrite')

        credentials = [c.strip().split(u":") for c in credentials.split(u",")]
        self.user_1, self.password_1 = credentials[0]
        self.user_2, self.password_2 = credentials[1]

        ws_info = root_remote_client.fetch(TEST_WORKSPACE_PATH)
        self.workspace = ws_info[u'uid']
        self.workspace_title = ws_info[u'title']

        # Document client to be used to create remote test documents
        # and folders
        self.upload_tmp_dir = tempfile.mkdtemp(u'-nxdrive-uploads', dir=self.tmpdir)
        remote_document_client_1 = RemoteDocumentClient(
            self.nuxeo_url, self.user_1, u'nxdrive-test-device-1',
            self.version,
            password=self.password_1, base_folder=self.workspace,
            upload_tmp_dir=self.upload_tmp_dir)

        remote_document_client_2 = RemoteDocumentClient(
            self.nuxeo_url, self.user_2, u'nxdrive-test-device-2',
            self.version,
            password=self.password_2, base_folder=self.workspace,
            upload_tmp_dir=self.upload_tmp_dir)

        self.remote_restapi_client_1 = RestAPIClient(
            self.nuxeo_url, self.user_1, u'nxdrive-test-device-1',
            self.version,
            password=self.password_1
        )
        self.remote_restapi_client_2 = RestAPIClient(
            self.nuxeo_url, self.user_2, u'nxdrive-test-device-2',
            self.version,
            password=self.password_2
        )

        # File system client to be used to create remote test documents
        # and folders
        remote_file_system_client_1 = RemoteFileSystemClient(
            self.nuxeo_url, self.user_1, u'nxdrive-test-device-1',
            self.version,
            password=self.password_1, upload_tmp_dir=self.upload_tmp_dir)

        remote_file_system_client_2 = RemoteFileSystemClient(
            self.nuxeo_url, self.user_2, u'nxdrive-test-device-2',
            self.version,
            password=self.password_2, upload_tmp_dir=self.upload_tmp_dir)

        self.root_remote_client = root_remote_client
        self.remote_document_client_1 = remote_document_client_1
        self.remote_document_client_2 = remote_document_client_2
        self.remote_file_system_client_1 = remote_file_system_client_1
        self.remote_file_system_client_2 = remote_file_system_client_2

        self.local_client_1 = LocalClient(os.path.join(self.local_nxdrive_folder_1, self.workspace_title))
        self.local_client_2 = LocalClient(os.path.join(self.local_nxdrive_folder_2, self.workspace_title))
        ndrive_path = os.path.dirname(nxdrive.__file__)
        self.ndrive_exec = os.path.join(ndrive_path, '..', 'scripts', 'ndrive.py')
        cmdline_options = '--log-level-console=%s' % DEFAULT_CONSOLE_LOG_LEVEL
        cmdline_options += ' --log-level-file=TRACE'
        cmdline_options += ' --nxdrive-home="%s"'
        if os.environ.get('PYDEV_DEBUG') == 'True':
            cmdline_options += ' --debug-pydev'
        self.ndrive_1_options = cmdline_options % self.nxdrive_conf_folder_1
        self.ndrive_2_options = cmdline_options % self.nxdrive_conf_folder_2

    def tearDown(self):
        # Don't need to revoke tokens for the file system remote clients
        # since they use the same users as the remote document clients
        self.root_remote_client.execute("NuxeoDrive.TearDownIntegrationTests")

        clean_dir(self.upload_tmp_dir)
        clean_dir(self.local_test_folder_1)
        clean_dir(self.local_test_folder_2)

    def wait(self, retry=3):
        try:
            self.root_remote_client.wait()
        except Exception as e:
            log.debug("Exception while waiting for server : %r", e)
            # Not the nicest
            if retry > 0:
                log.debug("Retry to wait")
                self.wait(retry - 1)

    def setUpDrive_1(self, bind_root=True, root=None, firstSync=False):
        # Bind the server and root workspace
        self.bind_server(self.ndrive_1_options, self.user_1, self.nuxeo_url, self.local_nxdrive_folder_1,
                         self.password_1)
        if bind_root:
            root_to_bind = root if root is not None else self.workspace
            self.bind_root(self.ndrive_1_options, root_to_bind, self.local_nxdrive_folder_1)
        if firstSync:
            self.ndrive(self.ndrive_1_options)

    def bind_root(self, ndrive_options, workspace, local_folder):
        cmdline = '%s bind-root "%s" --local-folder="%s" %s' % (self.ndrive_exec, workspace, local_folder,
                                                                ndrive_options)
        execute(cmdline)

    def unbind_root(self, ndrive_options, workspace, local_folder):
        cmdline = '%s unbind-root "%s" --local-folder="%s" %s' % (self.ndrive_exec, workspace, local_folder,
                                                                  ndrive_options)
        execute(cmdline)

    def bind_server(self, ndrive_options, user, server_url, local_folder, password):
        cmdline = '%s bind-server %s %s --local-folder="%s" --password=%s %s' % (
            self.ndrive_exec, user, server_url, local_folder, password, ndrive_options)
        execute(cmdline)

    def unbind_server(self, ndrive_options, local_folder):
        cmdline = '%s unbind-server --local-folder="%s"' % (self.ndrive_exec, local_folder, ndrive_options)
        execute(cmdline)

    def ndrive(self, ndrive_options=None, quit_if_done=True, quit_timeout=None, delay=None):
        if ndrive_options is None:
            ndrive_options = self.ndrive_1_options
        cmdline = self.ndrive_exec + ' console'
        if quit_if_done:
            cmdline += ' --quit-if-done'
        quit_timeout = quit_timeout if quit_timeout is not None else TEST_DEFAULT_QUIT_TIMEOUT
        cmdline += ' --quit-timeout=%d' % quit_timeout
        delay = delay if delay is not None else TEST_DEFAULT_DELAY
        cmdline += ' --delay=%d' % delay
        cmdline += ' ' + ndrive_options
        execute(cmdline)
