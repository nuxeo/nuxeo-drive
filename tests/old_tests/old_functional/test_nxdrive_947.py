"""
Duplicates are created when the parent is renamed while syncing up.

Steps:
    - Create a new folder and named as temp8 in Nuxeo Drive to sync up
    - Copy 1,000 files in the folder in Nuxeo Drive to sync up
    - While syncing up, rename the folder temp8 to temp9
"""

import shutil
from contextlib import suppress
from time import sleep

from ..utils import random_png
from .common import TwoUsersTest


class Test(TwoUsersTest):
    def _setup(self, count: int = 10, wait_for_sync: bool = True):
        """
        1. Create folder a1 at the root
        2. Create folder a2 at the root
        3. Add *count* pictures in a1
        4. Add *count* pictures in a2
        """
        self.engine_1.start()
        self.wait_sync(wait_for_async=True)
        self.engine_1.stop()

        local = self.local_1
        remote = self.remote_1

        # Create a1 and a2
        self.folder_path_1 = local.make_folder("/", "a1")
        self.folder_path_2 = local.make_folder("/", "a2")

        names = {f"file{n + 1:03d}.png" for n in range(count)}

        for path in (self.folder_path_1, self.folder_path_2):
            for name in names:
                file_path = local.abspath(path) / name
                random_png(file_path)

        self.engine_1.start()

        if wait_for_sync:
            self.wait_sync(timeout=30, wait_win=True)

        # Check /a1 and /a2
        for folder in ("/a1", "/a2"):
            # Check local files
            assert local.exists(folder)
            children = [child.name for child in local.get_children_info(folder)]
            assert len(children) == count
            assert set(children) == names

            if wait_for_sync:
                # Check remote files
                uid = local.get_remote_id(folder)
                assert uid
                assert remote.fs_exists(uid)
                children = [child.name for child in remote.get_fs_children(uid)]
                assert len(children) == count
                assert set(children) == names

    def tearDown(self):
        with suppress(TypeError, AttributeError):
            self.engine_1._local_watcher.localScanFinished.disconnect(
                self.app.local_scan_finished
            )

    def test_nxdrive_947(self):
        sync_count = self.engine_1.dao.get_sync_count
        local = self.local_1
        remote = self.remote_1
        remote_doc = self.remote_document_client_1

        # NXDRIVE-987: count the number of local scan
        self.engine_1._local_watcher.localScanFinished.connect(
            self.app.local_scan_finished
        )

        count = 1000
        self._setup(count=count, wait_for_sync=False)  # 2,000 files

        # Wait for 1,000+ files to be synced before doing anything
        while sync_count() <= 1000:
            sleep(1)

        # Rename a1 to "a1 moved"
        src = local.abspath(self.folder_path_1)
        dst = src.with_name(f"{src.name} moved")
        shutil.move(src, dst)

        # Rename a2 to "a2 moved"
        src = local.abspath(self.folder_path_2)
        dst = src.with_name(f"{src.name} moved")
        shutil.move(src, dst)

        # Wait for the sync to finish
        self.wait_sync(timeout=100, wait_win=True)

        # Expected files
        names = {f"file{n + 1:03d}.png" for n in range(count)}

        # Check that a* doesn't exist anymore locally and remotely
        assert not local.exists("/a1")
        assert not local.exists("/a2")
        children = remote_doc.get_children_info(self.workspace)
        assert len(children) == 2
        for child in children:
            assert child.name in ("a1 moved", "a2 moved")

        # Check "a* moved" content
        for folder in ("/a1 moved", "/a2 moved"):
            # Local checks
            assert local.exists(folder)
            children = [
                child.name
                for child in local.get_children_info(folder)
                if not child.folderish
            ]
            assert len(children) == count
            assert set(children) == names

            # Remote checks
            uid = local.get_remote_id(folder)
            assert uid
            assert remote.fs_exists(uid)
            children = [
                child.name
                for child in remote.get_fs_children(uid)
                if not child.folderish
            ]
            assert len(children) == count
            assert set(children) == names

        # NXDRIVE-987: ensure there was only 1 local scan done
        assert self.app.local_scan_count == 1
