# coding: utf-8
""" Common test utilities."""

import hashlib
import logging
import os
import shutil
import time
from logging import getLogger

from nxdrive.client import RemoteDocumentClient
from nxdrive.logging_config import configure
from nxdrive.utils import make_tmp_file, safe_long_path, unset_path_readonly

# Default remote watcher delay used for tests
TEST_DEFAULT_DELAY = 3

TEST_WORKSPACE_PATH = (
    '/default-domain/workspaces/nuxeo-drive-test-workspace')
FS_ITEM_ID_PREFIX = 'defaultFileSystemItemFactory#default#'

EMPTY_DIGEST = hashlib.md5().hexdigest()
SOME_TEXT_CONTENT = b'Some text content.'
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


def configure_logger():
    formatter = logging.Formatter(
        '%(thread)-4d %(module)-22s %(levelname).1s %(message)s')
    configure(console_level='TRACE',
              command_name='test',
              force_configure=True,
              formatter=formatter)


# Configure test logger
configure_logger()
log = getLogger(__name__)


def clean_dir(_dir, retry=1, max_retries=5):
    # type: (unicode, int, int) -> None

    if not os.path.exists(_dir):
        return

    log.debug('%d/%d Removing directory %r', retry, max_retries, _dir)

    to_remove = safe_long_path(_dir)
    test_data = os.environ.get('TEST_SAVE_DATA')
    if test_data:
        shutil.move(to_remove, test_data)
        return

    try:
        for dirpath, folders, filenames in os.walk(to_remove):
            for folder in folders:
                unset_path_readonly(os.path.join(dirpath, folder))
            for filename in filenames:
                unset_path_readonly(os.path.join(dirpath, filename))
        shutil.rmtree(to_remove)
    except:
        if retry < max_retries:
            time.sleep(2)
            clean_dir(_dir, retry=retry + 1)


class RemoteDocumentClientForTests(RemoteDocumentClient):

    def get_repository_names(self):
        return self.operations.execute(command='GetRepositories')[u'value']

    def make_file_in_user_workspace(self, content, filename):
        """Stream the given content as a document in the user workspace"""
        file_path = make_tmp_file(self.upload_tmp_dir, content)
        try:
            return self.upload(file_path, filename=filename,
                               command='UserWorkspace.CreateDocumentFromBlob')
        finally:
            os.remove(file_path)

    def activate_profile(self, profile):
        self.operations.execute(
            command='NuxeoDrive.SetActiveFactories', profile=profile)

    def deactivate_profile(self, profile):
        self.operations.execute(
            command='NuxeoDrive.SetActiveFactories', profile=profile,
            enable=False)

    def mass_import(self, target_path, nb_nodes, nb_threads=12):
        tx_timeout = 3600
        url = 'site/randomImporter/run'
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
        headers = {'Nuxeo-Transaction-Timeout': str(tx_timeout)}

        log.info('Calling random mass importer on %s with %d threads '
                 'and %d nodes', target_path, nb_threads, nb_nodes)

        self.client.request('GET', url, params=params, headers=headers,
                            timeout=tx_timeout)

    def wait_for_async_and_es_indexing(self):
        """ Use for test_volume only. """

        tx_timeout = 3600
        headers = {'Nuxeo-Transaction-Timeout': str(tx_timeout)}
        self.operations.execute(
            command='Elasticsearch.WaitForIndexing', timeout=tx_timeout,
            headers=headers, timeoutSecond=tx_timeout, refresh=True)

    def result_set_query(self, query):
        return self.operations.execute(
            command='Repository.ResultSetQuery', query=query)
