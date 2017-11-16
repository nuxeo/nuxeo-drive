# coding: utf-8
""" Common test utilities."""

import hashlib
import os
import shutil
import sys
import urllib2

from nxdrive.client import RemoteDocumentClient
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

    log.debug('Removing directory %r', _dir)

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
