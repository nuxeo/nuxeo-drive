# coding: utf-8
""" Common test utilities."""

import hashlib
import os
import shutil
import sys
import tempfile
import urllib2
from unittest import TestCase

import nxdrive
from nxdrive.client import LocalClient, RemoteDocumentClient, \
    RemoteFileSystemClient
from nxdrive.client.common import BaseClient
from nxdrive.logging_config import configure, get_logger
from nxdrive.utils import safe_long_path

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
    configure(console_level='TRACE',
              command_name='test',
              force_configure=True)

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
        exit(code)


def clean_dir(_dir):
    if not os.path.exists(_dir):
        return

    to_remove = safe_long_path(_dir)
    test_data = os.environ.get('TEST_SAVE_DATA')
    if test_data:
        shutil.move(to_remove, test_data)
        return
    try:
        for dirpath, folders, filenames in os.walk(to_remove):
            for folder in folders:
                BaseClient.unset_path_readonly(os.path.join(dirpath, folder))
            for filename in filenames:
                BaseClient.unset_path_readonly(os.path.join(dirpath, filename))
        shutil.rmtree(to_remove)
    except OSError:
        if sys.platform == 'win32':
            os.system('rmdir /S /Q %s' % to_remove)
    except:
        pass


class RemoteDocumentClientForTests(RemoteDocumentClient):

    def get_repository_names(self):
        return self.execute("GetRepositories")[u'value']

    def make_file_in_user_workspace(self, content, filename):
        """Stream the given content as a document in the user workspace"""
        file_path = self.make_tmp_file(content)
        try:
            return self.execute_with_blob_streaming(
                'UserWorkspace.CreateDocumentFromBlob',
                file_path,
                filename=filename)
        finally:
            os.remove(file_path)

    def activate_profile(self, profile):
        self.execute('NuxeoDrive.SetActiveFactories', profile=profile)

    def deactivate_profile(self, profile):
        self.execute('NuxeoDrive.SetActiveFactories', profile=profile,
                     enable=False)

    def add_to_locally_edited_collection(self, ref):
        doc = self.execute('NuxeoDrive.AddToLocallyEditedCollection',
                           op_input='doc:' + self._check_ref(ref))
        return doc['uid']

    def get_collection_members(self, ref):
        docs = self.execute('Collection.GetDocumentsFromCollection',
                           op_input='doc:' + self._check_ref(ref))
        return [doc['uid'] for doc in docs['entries']]

    def mass_import(self, target_path, nb_nodes, nb_threads=12):
        tx_timeout = 3600
        url = self.server_url + 'site/randomImporter/run?'
        params = {
            'targetPath': target_path,
            'batchSize': 50,
            'nbThreads': nb_threads,
            'interactive': 'true',
            'fileSizeKB': 1,
            'nbNodes': nb_nodes,
            'nonUniform': 'true',
            'transactionTimeout': tx_timeout
        }
        for param, value in params.iteritems():
            url += param + '=' + str(value) + '&'
        headers = self._get_common_headers()
        headers.update({'Nuxeo-Transaction-Timeout': tx_timeout})
        try:
            log.info(
                'Calling random mass importer on %s with %d threads and %d nodes',
                target_path, nb_threads, nb_nodes)
            self.opener.open(urllib2.Request(url, headers=headers), timeout=tx_timeout)
        except Exception as e:
            self._log_details(e)
            raise e

    def wait_for_async_and_es_indexing(self):
        """ Use for test_volume only. """

        tx_timeout = 3600
        extra_headers = {'Nuxeo-Transaction-Timeout': tx_timeout}
        self.execute(
            'Elasticsearch.WaitForIndexing',
            timeout=tx_timeout,
            extra_headers=extra_headers,
            timeoutSecond=tx_timeout,
            refresh=True)

    def result_set_query(self, query):
        return self.execute('Repository.ResultSetQuery', query=query)


class IntegrationTestCase(TestCase):

    def setUp(self):
        # Save the current path for test files
        self.location = dirname(__file__)

        # Check the Nuxeo server test environment
        self.nuxeo_url = os.environ.get('NXDRIVE_TEST_NUXEO_URL', 'http://localhost:8080/nuxeo')
        self.admin_user = os.environ.get('NXDRIVE_TEST_USER', 'Administrator')
        self.password = os.environ.get('NXDRIVE_TEST_PASSWORD', 'Administrator')
        self.build_workspace = os.environ.get('WORKSPACE')

        self.tmpdir = None
        if self.build_workspace is not None:
            self.tmpdir = os.path.join(self.build_workspace, "tmp")
            if not os.path.isdir(self.tmpdir):
                os.makedirs(self.tmpdir)

        self.full_nuxeo_url = self.nuxeo_url
        if '#' in self.nuxeo_url:
            self.nuxeo_url = self.nuxeo_url.split('#')[0]
        # Check the local filesystem test environment
        self.local_test_folder_1 = tempfile.mkdtemp(u'drive-1', dir=self.tmpdir)
        self.local_test_folder_2 = tempfile.mkdtemp(u'drive-2', dir=self.tmpdir)

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
        root_remote_client = RemoteDocumentClientForTests(
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
        remote_document_client_1 = RemoteDocumentClientForTests(
            self.nuxeo_url, self.user_1, u'nxdrive-test-device-1',
            self.version,
            password=self.password_1, base_folder=self.workspace,
            upload_tmp_dir=self.upload_tmp_dir)

        remote_document_client_2 = RemoteDocumentClientForTests(
            self.nuxeo_url, self.user_2, u'nxdrive-test-device-2',
            self.version,
            password=self.password_2, base_folder=self.workspace,
            upload_tmp_dir=self.upload_tmp_dir)

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

        self.ndrive_exec = os.path.join(self.location, '..', 'scripts', 'ndrive')
        cmdline_options = ' --log-level-file=TRACE'
        cmdline_options += ' --nxdrive-home="%s"'
        if os.environ.get('PYDEV_DEBUG') == 'True':
            cmdline_options += ' --debug-pydev'
        self.ndrive_1_options = cmdline_options % self.nxdrive_conf_folder_1
        self.ndrive_2_options = cmdline_options % self.nxdrive_conf_folder_2

    def tearDown(self):
        # Don't need to revoke tokens for the file system remote clients
        # since they use the same users as the remote document clients
        try:
            self.root_remote_client.execute("NuxeoDrive.TearDownIntegrationTests")
        except AttributeError:
            # If a test did not have enough time, failed early, `root_remote_client` could be inexistant. Just ignore.
            pass

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

    def setUpDrive_1(self, bind_root=True, root=None, first_sync=False):
        # Bind the server and root workspace
        self.bind_server(self.ndrive_1_options, self.user_1, self.nuxeo_url, self.local_nxdrive_folder_1,
                         self.password_1)
        if bind_root:
            root_to_bind = root if root is not None else self.workspace
            self.bind_root(self.ndrive_1_options, root_to_bind, self.local_nxdrive_folder_1)
        if first_sync:
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
        cmdline = '%s unbind-server --local-folder="%s" %s' % (self.ndrive_exec, local_folder, ndrive_options)
        execute(cmdline)

    def ndrive(self, ndrive_options=None, quit_if_done=True, quit_timeout=TEST_DEFAULT_QUIT_TIMEOUT,
               delay=TEST_DEFAULT_DELAY):
        if not ndrive_options:
            ndrive_options = self.ndrive_1_options
        cmdline = self.ndrive_exec + ' console'
        if quit_if_done:
            cmdline += ' --quit-if-done'
        cmdline += ' --quit-timeout=%d' % quit_timeout
        cmdline += ' --delay=%d' % delay
        cmdline += ' ' + ndrive_options
        execute(cmdline)
