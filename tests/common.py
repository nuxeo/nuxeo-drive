# coding: utf-8
""" Common test utilities."""

import hashlib
import os
import shutil
import time

from nxdrive.utils import safe_long_path, unset_path_readonly

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
# ~0.01s resolution for NTFS
# 0.001s for EXT4FS
OS_STAT_MTIME_RESOLUTION = 1.0


def clean_dir(_dir, retry=1, max_retries=5):
    # type: (unicode, int, int) -> None

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
                unset_path_readonly(os.path.join(dirpath, folder))
            for filename in filenames:
                unset_path_readonly(os.path.join(dirpath, filename))
        shutil.rmtree(to_remove)
    except:
        if retry < max_retries:
            time.sleep(2)
            clean_dir(_dir, retry=retry + 1)
